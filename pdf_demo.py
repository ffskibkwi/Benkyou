"""简单的 PDF 文本读取示例。

功能：
- 读取同目录下 `config.ini` 的 `[file]` 节的 `input_file` 路径
- 打开本地 PDF 文件，提取文本：
  - 行模式：打印前 n 行（默认 10），通过 -n 控制
  - 句子模式：从头遍历文本，忽略换行；遇到 "。" 或 "」" 后紧跟换行即分句，打印前 s 个句子，通过 -s 控制

依赖：
- 使用 `pypdf`；未安装请先安装：
  pip install pypdf
"""

from __future__ import annotations

import argparse
import configparser
import os
import sys
from typing import List


def _import_pdf_reader():
    """尝试导入 PDF 读取器类，返回 PdfReader 或抛出 ImportError。"""
    try:
        from pypdf import PdfReader  # type: ignore
        return PdfReader
    except Exception as exc:
        raise ImportError(
            "缺少依赖：请先安装 pypdf：pip install pypdf"
        ) from exc


def _normalize_path(raw_path: str) -> str:
    """规范化路径：去除引号、展开 ~ 和环境变量，并转为绝对路径。"""
    path = raw_path.strip().strip("\"").strip("'")
    path = os.path.expanduser(os.path.expandvars(path))
    return os.path.abspath(path)


def extract_first_lines_from_pdf(pdf_path: str, max_lines: int = 10) -> List[str]:
    """从 PDF 提取前 max_lines 行文本。

    若文本不足 max_lines 行，则返回全部提取到的行。
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"未找到 PDF 文件：{pdf_path}")

    PdfReader = _import_pdf_reader()
    reader = PdfReader(pdf_path)

    lines: List[str] = []
    for page in getattr(reader, "pages", []):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""

        if not text:
            continue

        for line in text.splitlines():
            # 去除末尾换行符，保留内容
            lines.append(line.rstrip("\r\n"))
            if len(lines) >= max_lines:
                return lines

    return lines


def extract_sentences_from_pdf(pdf_path: str, max_sentences: int) -> List[str]:
    """按规则提取前 max_sentences 个句子：

    - 忽略所有换行
    - 遇到 "。" 视为分句边界
    - 遇到 "」" 且其后紧接着换行视为分句边界
    """
    if max_sentences <= 0:
        return []

    PdfReader = _import_pdf_reader()
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"未找到 PDF 文件：{pdf_path}")

    reader = PdfReader(pdf_path)

    sentences: List[str] = []
    current_chars: List[str] = []

    def flush_sentence_if_any() -> None:
        if not current_chars:
            return
        sentence = "".join(current_chars).strip()
        current_chars.clear()
        if sentence:
            sentences.append(sentence)

    for page_index, page in enumerate(getattr(reader, "pages", [])):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""

        # 在页与页之间人为插入一个换行，保证跨页的 "」" + 换行 也能触发分句
        if page_index > 0:
            ch = "\n"
            # 处理跨页的换行：如果上一句以「」」结尾，这里的换行可触发分句
            if current_chars and current_chars[-1] == "」":
                flush_sentence_if_any()

        for ch in text:
            # 若是换行：仅当上一字符为 "」" 时作为分句边界；否则忽略
            if ch == "\n" or ch == "\r":
                if current_chars and current_chars[-1] == "」":
                    flush_sentence_if_any()
                    if len(sentences) >= max_sentences:
                        return sentences
                continue

            current_chars.append(ch)

            if ch == "。":
                flush_sentence_if_any()
                if len(sentences) >= max_sentences:
                    return sentences

    # 文末不补齐不完整句子（仅在命中边界时加入）
    return sentences


def read_pdf_path_from_config(config_path: str) -> str:
    """从 config.ini 读取 `[file]` 节的 `input_file` 路径。"""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"未找到配置文件：{config_path}")

    parser = configparser.ConfigParser(interpolation=None)
    parser.read(config_path, encoding="utf-8")

    if not parser.has_section("file"):
        raise KeyError("配置缺少 [file] 段")
    if not parser.has_option("file", "input_file"):
        raise KeyError("[file] 段缺少 input_file 键")

    raw = parser.get("file", "input_file")
    return _normalize_path(raw)


def main() -> None:
    # 默认读取脚本所在目录下的 config.ini
    config_path = os.path.join(os.path.dirname(__file__), "config.ini")
    parser = argparse.ArgumentParser(description="从 PDF 打印行或句子")
    parser.add_argument(
        "-n",
        "--num-lines",
        type=int,
        default=10,
        help="要打印的行数（默认 10）",
    )
    parser.add_argument(
        "-s",
        "--num-sentences",
        type=int,
        default=None,
        help="要打印的句子数（启用句子模式时必填）",
    )
    args = parser.parse_args()

    # 若指定了句子模式，优先生效
    if args.num_sentences is not None:
        if args.num_sentences <= 0:
            print("参数 -s 必须为正整数", file=sys.stderr)
            sys.exit(2)
    else:
        if args.num_lines <= 0:
            print("参数 -n 必须为正整数", file=sys.stderr)
            sys.exit(2)
    try:
        pdf_path = read_pdf_path_from_config(config_path)
        if args.num_sentences is not None:
            lines_or_sentences = extract_sentences_from_pdf(
                pdf_path, max_sentences=args.num_sentences
            )
        else:
            lines_or_sentences = extract_first_lines_from_pdf(
                pdf_path, max_lines=args.num_lines
            )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    # 统一打印
    limit = args.num_sentences if args.num_sentences is not None else args.num_lines
    for item in lines_or_sentences[: limit]:
        print(item)


if __name__ == "__main__":
    main()


