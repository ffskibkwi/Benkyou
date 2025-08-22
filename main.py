from __future__ import annotations

import argparse
import os
import sys
from typing import Optional

from config import load_config
from pdf_read import read_pdf_sentences
from analysis import analyze_batches
from analysis import test_connectivity
from note import save_batch


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
    parser.add_argument(
        "--debug",
        action="store_true",
        help="启用调试模式：打印完整输入输出",
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

        print("[INFO] 执行连通性测试…")
        test_connectivity(cfg, debug=args.debug, timeout_secs=10, max_retries=2)
        print("[INFO] 连通性测试通过，开始调用 LLM 进行分析…")
        sentence_index_holder = {"idx": 0}
        def _on_batch(batch_idx: int, out_text: str, in_text: str) -> None:
            sentence_index_holder["idx"] = save_batch(
                cfg, batch_idx, out_text, sentence_index_holder["idx"]
            )

        results = analyze_batches(
            cfg,
            sentences,
            max_batches=args.batches,
            min_chars=args.min_chars,
            debug=args.debug,
            timeout_secs=30,
            max_retries=5,
            on_batch=_on_batch,
            tick_interval_secs=3,
        )

        if args.debug:
            print(f"[DEBUG] LLM 返回批次数: {len(results)}")
            for i, r in enumerate(results, 1):
                print(f"\n===== 批 {i} 输出（开始） =====")
                print(r)
                print(f"===== 批 {i} 输出（结束） =====\n")
        else:
            print(f"[INFO] 完成 LLM 调用，获得 {len(results)} 个批次结果")

        print(f"[INFO] Markdown 写入完成，共写入 {sentence_index_holder['idx']} 条句子")

    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())


