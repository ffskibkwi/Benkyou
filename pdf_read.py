"""PDF 文本读取与分句工具。

参考 `pdf_demo.py` 的抽取逻辑，输出清洗后的句子列表。
"""

from __future__ import annotations

import os
from typing import List

from pdf_demo import _import_pdf_reader  # 复用已实现的安全导入


def extract_sentences_from_text(raw_text: str) -> List[str]:
    """将整段文本按句子切分，尽量贴合 `main.prompt` Stage 1/2 的边界定义。

    规则：
    - 先清理掉多余换行，将疑似段内换行合并为空格。
    - 句末标点：`。`、`！`、`？`；
    - 引号 `「...」` 或 `『...』` 视为整体，句子在其后的标点结束。
    简化实现：基于字符扫描，遇到终止符收束为一句。
    """
    if not raw_text:
        return []

    # 归一化换行：将多余换行压缩为单个换行，再将行内换行替换为空格
    text = raw_text.replace("\r", "\n")
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    text = " ".join(lines)

    sentences: List[str] = []
    buf: List[str] = []
    quote_stack: List[str] = []  # 跟踪「」「」或『』『』是否闭合

    terminators = {"。", "！", "？"}
    quote_pairs = {"「": "」", "『": "』"}
    closing_quotes = set(quote_pairs.values())

    for ch in text:
        buf.append(ch)
        if ch in quote_pairs:
            quote_stack.append(quote_pairs[ch])
        elif ch in closing_quotes:
            if quote_stack and quote_stack[-1] == ch:
                quote_stack.pop()
        if ch in terminators and not quote_stack:
            sent = "".join(buf).strip()
            buf.clear()
            if sent:
                sentences.append(sent)

    # 末尾若残留但没有句末标点，不作为完整句子返回
    return sentences


def read_pdf_sentences(pdf_path: str) -> List[str]:
    """从 PDF 读取文本并进行分句。"""
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"未找到 PDF 文件：{pdf_path}")

    PdfReader = _import_pdf_reader()
    reader = PdfReader(pdf_path)

    all_text_parts: List[str] = []
    for page in getattr(reader, "pages", []):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if text:
            all_text_parts.append(text)

    raw_text = "\n".join(all_text_parts)
    return extract_sentences_from_text(raw_text)


