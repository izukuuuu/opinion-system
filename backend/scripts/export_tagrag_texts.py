"""Utility script to convert TagRAG format JSON into RouterRAG text chunks.

Usage:
    python scripts/export_tagrag_texts.py \
        --input ../src/utils/rag/tagrag/format_db/控烟.json \
        --output ../src/utils/rag/ragrouter/控烟数据库/normal_db/text_db \
        --topic 控烟 \
        --chunk-size 3
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def chunk_list(items, size):
    for i in range(0, len(items), size):
        yield items[i : i + size], (i // size) + 1


def main():
    parser = argparse.ArgumentParser(
        description="Export TagRAG JSON texts into RouterRAG text chunks."
    )
    parser.add_argument("--input", required=True, help="Path to TagRAG JSON file.")
    parser.add_argument(
        "--output",
        required=True,
        help="Output directory for RouterRAG text files (text_db).",
    )
    parser.add_argument("--topic", default="topic", help="Topic name for file naming.")
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=3,
        help="Number of JSON entries combined into one txt file.",
    )
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    with input_path.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    if isinstance(raw, dict) and "data" in raw:
        data = raw["data"]
    elif isinstance(raw, list):
        data = raw
    else:
        raise ValueError("JSON format unsupported: expected list or object with 'data'.")

    texts = [item.get("text", "").strip() for item in data if item.get("text")]
    if not texts:
        raise ValueError("Input JSON does not contain any text fields.")

    for chunk, idx in chunk_list(texts, args.chunk_size):
        doc_id = f"doc{idx}"
        file_name = f"{doc_id}_{args.topic}_text1.txt"
        file_path = output_dir / file_name

        content = "\n\n---\n\n".join(chunk)
        file_path.write_text(content, encoding="utf-8")
        print(f"Written {file_path.name} with {len(chunk)} texts.")


if __name__ == "__main__":
    main()

