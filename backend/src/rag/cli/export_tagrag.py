"""Enhanced CLI script to convert TagRAG format JSON into RouterRAG text chunks.

Usage Examples:
    # Basic conversion
    python -m rag.cli.export_tagrag \
        --input ../src/utils/rag/tagrag/format_db/控烟.json \
        --output ../src/utils/rag/ragrouter/控烟数据库/normal_db/text_db \
        --topic 控烟 \
        --chunk-size 3

    # Advanced options
    python -m rag.cli.export_tagrag \
        --input data.json \
        --output output_dir \
        --topic custom_topic \
        --chunk-strategy size \
        --max-chunk-chars 2000 \
        --preserve-metadata \
        --text-field content \
        --id-field doc_id

    # Batch processing
    python -m rag.cli.export_tagrag \
        --input-dir ./input_files \
        --output-dir ./output_files \
        --chunk-size 5
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import List, Optional

from ..converters.tagrag_converter import TagRAGConverter, TagRAGConfig

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def setup_parser() -> argparse.ArgumentParser:
    """Setup command line argument parser."""
    parser = argparse.ArgumentParser(
        description="Export TagRAG JSON texts into RouterRAG text chunks.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    # Input options
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--input",
        type=str,
        help="Path to single TagRAG JSON file."
    )
    input_group.add_argument(
        "--input-dir",
        type=str,
        help="Directory containing multiple TagRAG JSON files."
    )

    # Output options
    parser.add_argument(
        "--output",
        type=str,
        help="Output directory for RouterRAG text files (used with --input)."
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        help="Base output directory (used with --input-dir)."
    )

    # Conversion options
    parser.add_argument(
        "--topic",
        default="topic",
        help="Topic name for file naming (default: topic)."
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=3,
        help="Number of JSON entries combined into one txt file (default: 3)."
    )
    parser.add_argument(
        "--chunk-strategy",
        choices=["count", "size"],
        default="count",
        help="Chunking strategy: 'count' or 'size' (default: count)."
    )
    parser.add_argument(
        "--max-chunk-chars",
        type=int,
        default=2000,
        help="Maximum characters per chunk when using size strategy (default: 2000)."
    )
    parser.add_argument(
        "--text-field",
        default="text",
        help="Field name containing text data (default: text)."
    )
    parser.add_argument(
        "--id-field",
        help="Field name containing document ID (optional)."
    )

    # Metadata options
    parser.add_argument(
        "--preserve-metadata",
        action="store_true",
        help="Preserve metadata from source JSON files."
    )

    # File naming options
    parser.add_argument(
        "--file-prefix",
        default="doc",
        help="Prefix for output files (default: doc)."
    )
    parser.add_argument(
        "--file-suffix",
        default="_text1.txt",
        help="Suffix for output files (default: _text1.txt)."
    )

    # Separator options
    parser.add_argument(
        "--separator",
        default="\n\n---\n\n",
        help="Separator between texts in chunks (default: '\\n\\n---\\n\\n')."
    )

    # Other options
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without actually converting."
    )

    return parser


def find_json_files(directory: Path) -> List[Path]:
    """Find all JSON files in directory."""
    if not directory.exists():
        raise FileNotFoundError(f"Directory not found: {directory}")

    json_files = list(directory.glob("**/*.json"))
    if not json_files:
        logger.warning(f"No JSON files found in {directory}")

    return json_files


def convert_single_file(input_path: Path,
                       output_path: Path,
                       config: TagRAGConfig,
                       dry_run: bool = False) -> None:
    """Convert a single JSON file."""
    if dry_run:
        logger.info(f"[DRY RUN] Would convert: {input_path} -> {output_path}")
        return

    converter = TagRAGConverter(config)
    converter.convert(input_path, output_path)
    logger.info(f"✓ Converted: {input_path.name}")


def convert_directory(input_dir: Path,
                     output_base_dir: Path,
                     config: TagRAGConfig,
                     dry_run: bool = False) -> None:
    """Convert all JSON files in a directory."""
    json_files = find_json_files(input_dir)

    if not json_files:
        logger.warning(f"No files to convert in {input_dir}")
        return

    logger.info(f"Found {len(json_files)} JSON files to convert")

    for input_file in json_files:
        # Determine output path based on relative path
        rel_path = input_file.relative_to(input_dir)
        output_path = output_base_dir / rel_path.stem / "text_db"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Update config topic based on filename
        file_config = TagRAGConfig(
            topic=config.topic or input_file.stem,
            chunk_size=config.chunk_size,
            chunk_strategy=config.chunk_strategy,
            max_chunk_chars=config.max_chunk_chars,
            preserve_metadata=config.preserve_metadata,
            text_field=config.text_field,
            id_field=config.id_field
        )

        convert_single_file(input_file, output_path, file_config, dry_run)


def main():
    """Main CLI entry point."""
    parser = setup_parser()
    args = parser.parse_args()

    # Setup logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Create config
    config = TagRAGConfig(
        chunk_size=args.chunk_size,
        chunk_strategy=args.chunk_strategy,
        max_chunk_chars=args.max_chunk_chars,
        topic=args.topic,
        preserve_metadata=args.preserve_metadata,
        text_field=args.text_field,
        id_field=args.id_field
    )

    try:
        if args.input:
            # Single file conversion
            input_path = Path(args.input).resolve()
            if not input_path.exists():
                raise FileNotFoundError(f"Input file not found: {input_path}")

            if not args.output:
                # Default output based on input filename
                output_path = input_path.parent / input_path.stem / "text_db"
            else:
                output_path = Path(args.output).resolve()

            convert_single_file(input_path, output_path, config, args.dry_run)

        else:
            # Directory conversion
            input_dir = Path(args.input_dir).resolve()
            if not args.output_dir:
                output_base_dir = input_dir.parent / "converted"
            else:
                output_base_dir = Path(args.output_dir).resolve()

            convert_directory(input_dir, output_base_dir, config, args.dry_run)

        logger.info("Conversion completed successfully")

    except Exception as e:
        logger.error(f"Conversion failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()