from __future__ import annotations

import json
import os
import re
from typing import List, Optional, Tuple

from config import GeminiConfig


def _ensure_dirs(base_dir: str) -> Tuple[str, str]:
    sentence_dir = os.path.join(base_dir, "sentence")
    piece_dir = os.path.join(base_dir, "piece")
    os.makedirs(sentence_dir, exist_ok=True)
    os.makedirs(piece_dir, exist_ok=True)
    return sentence_dir, piece_dir


_ILLEGAL_CHARS = re.compile(r"[\\/:*?\"<>|]")


def _sanitize_filename(name: str) -> str:
    name = name.strip().rstrip(".")
    name = _ILLEGAL_CHARS.sub(" ", name)
    return name[:180] if len(name) > 180 else name


def _strip_code_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```") and t.endswith("```"):
        # 移除首尾围栏
        t = "\n".join(t.splitlines()[1:-1])
    return t


def _try_parse_json_array(text: str) -> Optional[List[dict]]:
    t = _strip_code_fences(text)
    try:
        obj = json.loads(t)
        if isinstance(obj, list):
            return obj  # type: ignore[return-value]
    except Exception:
        pass
    # 兜底：尝试提取首个成对的方括号片段
    start = t.find("[")
    end = t.rfind("]")
    if start != -1 and end != -1 and end > start:
        frag = t[start : end + 1]
        try:
            obj = json.loads(frag)
            if isinstance(obj, list):
                return obj  # type: ignore[return-value]
        except Exception:
            return None
    return None


def _first_n_chars(s: str, n: int) -> str:
    s = s.replace("\n", " ").strip()
    return s[:n]


def _write_sentence_file(sentence_dir: str, idx: int, sentence_obj: dict) -> Tuple[str, str]:
    sentence_text = str(sentence_obj.get("sentence", "")).strip()
    translation = str(sentence_obj.get("translation", "")).strip()
    pieces = sentence_obj.get("pieces") or []

    title_snippet = _first_n_chars(sentence_text, 10)
    file_stem = f"S{idx} - {title_snippet}"
    file_name = _sanitize_filename(file_stem) + ".md"
    file_path = os.path.join(sentence_dir, file_name)

    lines: List[str] = []
    lines.append(sentence_text)
    lines.append("---")
    lines.append(translation)
    lines.append("---")

    for piece in pieces:
        piece_name = str(piece.get("piece", "")).strip()
        reading = str(piece.get("reading", "")).strip()
        meaning = str(piece.get("meaning", "")).strip()
        function = str(piece.get("function", "")).strip()
        # 句内对 piece 的引用
        lines.append(f"- [[{piece_name}]] - {reading}")
        lines.append(f"\t- {meaning}")
        lines.append(f"    - {function}")

    with open(file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip() + "\n")

    return file_name, sentence_text


def _append_piece_file(piece_dir: str, piece_obj: dict, sentence_file_stem: str, sentence_text: str) -> None:
    piece_name = str(piece_obj.get("piece", "")).strip()
    piece_type = str(piece_obj.get("type", "")).strip()
    meaning = str(piece_obj.get("meaning", "")).strip()
    function = str(piece_obj.get("function", "")).strip()

    if not piece_name:
        return

    file_stem = _sanitize_filename(piece_name)
    file_path = os.path.join(piece_dir, file_stem + ".md")
    exists = os.path.exists(file_path)

    if not exists:
        # 新建文件头与首个 meaning 段
        lines: List[str] = []
        # 若需要标题，可在此处插入 piece_name 行；保持与现有格式一致仅写前言块
        lines.append("---")
        lines.append(f"type: {piece_type}")
        lines.append("---")
        lines.append(f"- {meaning}")
        lines.append(f"    - [[{sentence_file_stem}|{sentence_text}]]")
        lines.append(f"        - {function}")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines).rstrip() + "\n")
        return

    # 已存在：若有相同 meaning，则在该段内追加；否则新增一个 meaning 段
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    target_heading = f"- {meaning}"
    insert_at: Optional[int] = None
    for idx, line in enumerate(lines):
        if line.strip() == target_heading:
            # 找到 meaning 段起始，向下寻找下一顶级 "- " 的位置
            j = idx + 1
            while j < len(lines):
                if lines[j].startswith("- "):
                    break
                j += 1
            insert_at = j
            break

    if insert_at is not None:
        addition = [
            f"    - [[{sentence_file_stem}|{sentence_text}]]",
            f"        - {function}",
        ]
        lines[insert_at:insert_at] = addition
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines).rstrip() + "\n")
        return

    # 未找到相同 meaning：在末尾新增一个 meaning 段
    tail = [
        "",
        f"- {meaning}",
        f"    - [[{sentence_file_stem}|{sentence_text}]]",
        f"        - {function}",
    ]
    with open(file_path, "a", encoding="utf-8") as f:
        f.write("\n".join(tail).rstrip() + "\n")


def save_notes(cfg: GeminiConfig, results: List[str]) -> None:
    """根据 LLM 输出的 JSON 批次，生成双向链接 Markdown。

    - sentence 文件：`S{ID} - {前10字}.md`
    - piece 文件：以 piece 名称为文件名，若已存在则续写
    """
    if not cfg.output_lib:
        raise ValueError("config.ini 缺少 [file].output_lib，无法生成 Markdown 笔记")

    base_dir = cfg.output_lib
    sentence_dir, piece_dir = _ensure_dirs(base_dir)

    sentence_index = 0
    for batch_idx, text in enumerate(results, 1):
        arr = _try_parse_json_array(text)
        if arr is None:
            print(f"[WARN] 第 {batch_idx} 批输出非 JSON，已跳过")
            continue
        for obj in arr:
            # 写入 sentence 文件
            sentence_file_name, sentence_text = _write_sentence_file(
                sentence_dir, sentence_index, obj
            )
            sentence_file_stem = os.path.splitext(sentence_file_name)[0]
            # 更新 piece 文件
            for piece in obj.get("pieces") or []:
                _append_piece_file(piece_dir, piece, sentence_file_stem, sentence_text)
            sentence_index += 1


def save_batch(cfg: GeminiConfig, batch_index: int, out_text: str, current_sentence_index: int) -> int:
    """将单个批次 out_text 写入 Markdown。返回更新后的 sentence_index。

    - batch_index：用于日志
    - current_sentence_index：用于给本批次的 sentence 连续编号
    """
    if not cfg.output_lib:
        raise ValueError("config.ini 缺少 [file].output_lib，无法生成 Markdown 笔记")

    base_dir = cfg.output_lib
    sentence_dir, piece_dir = _ensure_dirs(base_dir)

    arr = _try_parse_json_array(out_text)
    if arr is None:
        print(f"[WARN] 第 {batch_index} 批输出非 JSON，已跳过写入")
        return current_sentence_index

    for obj in arr:
        sentence_file_name, sentence_text = _write_sentence_file(
            sentence_dir, current_sentence_index, obj
        )
        sentence_file_stem = os.path.splitext(sentence_file_name)[0]
        for piece in obj.get("pieces") or []:
            _append_piece_file(piece_dir, piece, sentence_file_stem, sentence_text)
        current_sentence_index += 1
    return current_sentence_index


