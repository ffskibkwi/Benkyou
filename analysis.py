"""基于 Gemini API 的分句批量分析。

功能：
- 读取系统提示词（`main.prompt`）
- 将句子按 ≥50 字拼接为一批
- 使用 Gemini 调用进行分析，期望输出 JSON 数组字符串
"""

from __future__ import annotations

import os
from typing import Iterable, List, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import time

from config import GeminiConfig, apply_proxy_environment


def load_system_prompt(prompt_path: Optional[str] = None) -> str:
    """读取系统提示词。

    默认从当前项目根目录下的 `main.prompt` 加载。
    """
    if prompt_path is None:
        prompt_path = os.path.join(os.path.dirname(__file__), "main.prompt")
    if not os.path.exists(prompt_path):
        raise FileNotFoundError(f"未找到系统提示文件：{prompt_path}")
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


def batch_sentences(sentences: Iterable[str], min_chars: int = 50) -> List[str]:
    """按 ≥min_chars 的最小字数合并分句为批次。

    规则：
    - 从前到后累积分句，直到累计长度 > min_chars，收束为一批
    - 若单句本身已 ≥ min_chars，则单句独立成批
    - 末尾不足一批（<= min_chars）的残留不返回（保持与需求一致）
    """
    batches: List[str] = []
    buf: List[str] = []
    count = 0
    for s in sentences:
        s = (s or "").strip()
        if not s:
            continue
        # 若当前无缓冲且单句已达阈值，直接独立成批
        if count == 0 and len(s) >= min_chars:
            batches.append(s)
            continue
        # 否则加入缓冲后判断是否超过阈值
        buf.append(s)
        count += len(s)
        if count > min_chars:
            batches.append("".join(buf))
            buf.clear()
            count = 0
    # 末尾残留丢弃（不满阈值）
    return batches


def _import_genai():
    try:
        import google.generativeai as genai  # type: ignore
        return genai
    except Exception as exc:
        raise ImportError(
            "缺少依赖：请先安装 google-generativeai：pip install google-generativeai"
        ) from exc


def create_gemini_model(cfg: GeminiConfig, system_prompt: str):
    """创建 Gemini 模型实例，已设置代理环境。"""
    apply_proxy_environment(cfg.http_proxy, cfg.https_proxy)
    genai = _import_genai()
    genai.configure(api_key=cfg.api_key)
    # 对应 v1 API：GenerativeModel 接收 model_name、system_instruction
    model = genai.GenerativeModel(model_name=cfg.model, system_instruction=system_prompt)
    return model


def generate_json_with_model(model, input_text: str) -> str:
    """调用 Gemini 生成内容，返回文本。

    期望返回为严格 JSON 数组（由 `main.prompt` 约束）。
    """
    # 传入纯用户内容，由系统提示约束输出
    resp = model.generate_content(input_text)
    # 兼容不同 SDK 版本的响应字段
    if hasattr(resp, "text") and callable(getattr(resp, "text")):
        return resp.text()  # 部分版本 text 为可调用方法
    if hasattr(resp, "text"):
        return resp.text  # 部分版本 text 为属性
    if hasattr(resp, "candidates") and resp.candidates:
        # 兜底从 candidates/parts 中提取
        try:
            return resp.candidates[0].content.parts[0].text  # type: ignore[attr-defined]
        except Exception:
            pass
    return str(resp)


def test_connectivity(
    cfg: GeminiConfig,
    debug: bool = False,
    timeout_secs: int = 10,
    max_retries: int = 2,
) -> None:
    """在正式分析前进行一次连通性测试。

    若在重试后仍失败，将抛出异常给调用方。
    """
    # 轻量系统提示与内容
    model = create_gemini_model(cfg, system_prompt="Connectivity check")
    prompt = "ping"
    last_err: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        try:
            if debug:
                print(f"[DEBUG] 连通性测试 第 {attempt}/{max_retries} 次，超时 {timeout_secs}s")
            with ThreadPoolExecutor(max_workers=1) as executor:
                fut = executor.submit(generate_json_with_model, model, prompt)
                _ = fut.result(timeout=timeout_secs)
            if debug:
                print("[DEBUG] 连通性测试成功")
            return
        except FuturesTimeoutError as exc:
            last_err = exc
            if debug:
                print("[DEBUG] 连通性测试超时，重试…")
            continue
        except Exception as exc:
            last_err = exc
            if debug:
                print(f"[DEBUG] 连通性测试异常：{exc}，重试…")
            continue
    raise RuntimeError(f"连通性测试失败：{last_err}")


def analyze_batches(
    cfg: GeminiConfig,
    sentences: List[str],
    max_batches: Optional[int] = None,
    min_chars: int = 50,
    debug: bool = False,
    timeout_secs: int = 30,
    max_retries: int = 5,
    on_batch: Optional[Callable[[int, str, str], None]] = None,
    tick_interval_secs: int = 3,
) -> List[str]:
    """对分句进行批量分析，返回每批的 JSON 字符串结果列表。

    - debug: 打印每批的完整输入与输出
    - timeout_secs: 单次请求最长等待时间
    - max_retries: 超时或异常时的最大重试次数
    """
    system_prompt = load_system_prompt()
    model = create_gemini_model(cfg, system_prompt)
    batches = batch_sentences(sentences, min_chars=min_chars)
    if max_batches is not None and max_batches >= 0:
        batches = batches[: max_batches]

    results: List[str] = []
    total = len(batches)
    for idx, batch in enumerate(batches, 1):
        if debug:
            print(f"[DEBUG] 第 {idx}/{total} 批 输入（len={len(batch)}）:\n{batch}")
        else:
            print(f"[INFO] 提交第 {idx}/{total} 批，长度 {len(batch)} 字")

        last_err: Optional[Exception] = None
        for attempt in range(1, max_retries + 1):
            try:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    fut = executor.submit(generate_json_with_model, model, batch)
                    start_ts = time.time()
                    elapsed = 0
                    out: Optional[str] = None
                    while True:
                        remaining = max(0.0, timeout_secs - elapsed)
                        if remaining <= 0:
                            raise FuturesTimeoutError()
                        wait = min(tick_interval_secs, remaining)
                        try:
                            out = fut.result(timeout=wait)
                            break
                        except FuturesTimeoutError:
                            elapsed = int(time.time() - start_ts)
                            print(f"[INFO] 第 {idx}/{total} 批 第 {attempt}/{max_retries} 次等待中… {elapsed}s/{timeout_secs}s")
                            continue
                    assert out is not None
                if debug:
                    print(f"[DEBUG] 第 {idx}/{total} 批 第 {attempt} 次返回（len={len(out)}）:\n{out}")
                else:
                    print(f"[INFO] 第 {idx}/{total} 批 完成")
                results.append(out)
                if on_batch is not None:
                    try:
                        on_batch(idx, out, batch)
                    except Exception as cb_exc:
                        print(f"[WARN] 第 {idx} 批写入回调失败：{cb_exc}")
                break
            except FuturesTimeoutError as exc:
                last_err = exc
                print(f"[INFO] 第 {idx}/{total} 批 第 {attempt}/{max_retries} 次超时（>{timeout_secs}s），重试…")
                continue
            except Exception as exc:
                last_err = exc
                print(f"[INFO] 第 {idx}/{total} 批 第 {attempt}/{max_retries} 次异常：{exc}，重试…")
                continue
        else:
            # 全部尝试失败
            raise RuntimeError(
                f"批次 {idx}/{total} 在重试 {max_retries} 次后仍失败：{last_err}"
            )
    return results


