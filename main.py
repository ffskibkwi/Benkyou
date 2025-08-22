from __future__ import annotations

import argparse
import os
import sys
from typing import Optional

from config import load_config
from pdf_read import read_pdf_sentences
from analysis import analyze_batches
from note import save_notes


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="日语文本分句与 Gemini 批量分析")
    parser.add_argument(
        "-b",
        "--batches",
        type=int,
        default=None,
        help="要向 LLM 投递的批次数；默认不限（使用全部批次）",
    )
    parser.add_argument(
        "--min-chars",
        type=int,
        default=50,
        help="每批最小字数阈值（默认 50）",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)

    try:
        cfg = load_config()
        print(f"[DEBUG] 使用模型: {cfg.model}")
        print(f"[DEBUG] 代理: http={cfg.http_proxy} https={cfg.https_proxy}")
        print(f"[DEBUG] 输入文件: {cfg.input_file}")

        sentences = read_pdf_sentences(cfg.input_file)
        print(f"[DEBUG] 分句完成，共 {len(sentences)} 句")
        if sentences[:5]:
            print(f"[DEBUG] 示例句子: {sentences[:5]}")

        results = analyze_batches(
            cfg,
            sentences,
            max_batches=args.batches,
            min_chars=args.min_chars,
        )

        print(f"[DEBUG] LLM 返回批次数: {len(results)}")
        for i, r in enumerate(results, 1):
            print(f"\n===== 批 {i} 输出（开始） =====")
            print(r)
            print(f"===== 批 {i} 输出（结束） =====\n")

        # 将结果保存为带双向链接的 Markdown
        try:
            save_notes(cfg, results)
            print("[DEBUG] 已将输出写入 Markdown 笔记库")
        except Exception as note_exc:
            print(f"[WARN] 笔记生成失败: {note_exc}")

    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())


