"""简单的 PDF 文本读取示例。

功能：
- 读取同目录下 `config.ini` 的 `[file]` 节的 `input_file` 路径
- 打开本地 PDF 文件，提取文本，并打印前 n 行（默认 10）

依赖：
- 优先使用 `pypdf`，若不可用则尝试 `PyPDF2`
- 若二者均未安装，请先安装：
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
    except Exception:
        try:
            from PyPDF2 import PdfReader  # type: ignore
            return PdfReader
        except Exception as exc:
            raise ImportError(
                "缺少依赖：请先安装 pypdf（或 PyPDF2）：pip install pypdf"
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
    parser = argparse.ArgumentParser(description="从 PDF 打印前 n 行文本")
    parser.add_argument(
        "-n",
        "--num-lines",
        type=int,
        default=10,
        help="要打印的行数（默认 10）",
    )
    args = parser.parse_args()

    if args.num_lines <= 0:
        print("参数 -n 必须为正整数", file=sys.stderr)
        sys.exit(2)
    try:
        pdf_path = read_pdf_path_from_config(config_path)
        lines = extract_first_lines_from_pdf(pdf_path, max_lines=args.num_lines)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    for line in lines[: args.num_lines]:
        print(line)


if __name__ == "__main__":
    main()


