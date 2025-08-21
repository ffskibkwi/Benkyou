"""基于 Gemini API 的分句批量分析。

功能：
- 读取系统提示词（`main.prompt`）
- 将句子按 ≥50 字拼接为一批
- 使用 Gemini 调用进行分析，期望输出 JSON 数组字符串
"""

from __future__ import annotations

import os
from typing import Iterable, List, Optional

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


def analyze_batches(cfg: GeminiConfig, sentences: List[str], max_batches: Optional[int] = None, min_chars: int = 50) -> List[str]:
    """对分句进行批量分析，返回每批的 JSON 字符串结果列表。"""
    system_prompt = load_system_prompt()
    model = create_gemini_model(cfg, system_prompt)
    batches = batch_sentences(sentences, min_chars=min_chars)
    if max_batches is not None and max_batches >= 0:
        batches = batches[: max_batches]

    results: List[str] = []
    for idx, batch in enumerate(batches, 1):
        print(f"[DEBUG] 投递第 {idx} 批，字符数={len(batch)}")
        out = generate_json_with_model(model, batch)
        print(f"[DEBUG] 第 {idx} 批返回长度={len(out)}")
        results.append(out)
    return results


