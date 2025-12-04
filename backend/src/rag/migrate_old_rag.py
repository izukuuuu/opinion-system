"""Migration script to move from old RAG structure to new modular RAG system."""

import shutil
from pathlib import Path
import logging
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate_tagrag_data(old_dir: Path, new_dir: Path) -> None:
    """Migrate TagRAG data to new structure."""
    old_tagrag = old_dir / "tagrag"
    new_tagrag = new_dir / "storage" / "tagrag_data"

    if old_tagrag.exists():
        logger.info(f"Migrating TagRAG data from {old_tagrag} to {new_tagrag}")
        new_tagrag.parent.mkdir(parents=True, exist_ok=True)

        # Copy all contents
        for item in old_tagrag.iterdir():
            if item.is_file():
                shutil.copy2(item, new_tagrag)
                logger.info(f"Copied {item.name}")
            elif item.is_dir():
                shutil.copytree(item, new_tagrag / item.name, dirs_exist_ok=True)
                logger.info(f"Copied directory {item.name}")


def migrate_ragrouter_data(old_dir: Path, new_dir: Path) -> None:
    """Migrate RouterRAG data to new structure."""
    old_router = old_dir / "ragrouter"
    new_router = new_dir / "storage" / "ragrouter_data"

    if old_router.exists():
        logger.info(f"Migrating RouterRAG data from {old_router} to {new_router}")
        new_router.parent.mkdir(parents=True, exist_ok=True)

        # Copy all contents
        for item in old_router.iterdir():
            if item.is_file():
                shutil.copy2(item, new_router)
                logger.info(f"Copied {item.name}")
            elif item.is_dir():
                shutil.copytree(item, new_router / item.name, dirs_exist_ok=True)
                logger.info(f"Copied directory {item.name}")


def create_migration_config() -> dict:
    """Create migration configuration."""
    return {
        "migration_timestamp": "2024-12-03",
        "old_structure": {
            "utils_path": "backend/src/utils/rag",
            "scripts_path": "backend/scripts"
        },
        "new_structure": {
            "rag_module": "backend/src/rag",
            "components": [
                "core",
                "converters",
                "embeddings",
                "retrievers",
                "storage",
                "config",
                "utils",
                "cli"
            ]
        },
        "migrated_files": [
            "tagrag/*.py -> storage/",
            "ragrouter/*.py -> storage/",
            "scripts/export_tagrag_texts.py -> cli/export_tagrag.py"
        ]
    }


def update_imports(file_path: Path, old_import: str, new_import: str) -> None:
    """Update imports in a Python file."""
    if file_path.suffix != ".py":
        return

    try:
        content = file_path.read_text(encoding="utf-8")
        if old_import in content:
            content = content.replace(old_import, new_import)
            file_path.write_text(content, encoding="utf-8")
            logger.info(f"Updated imports in {file_path}")
    except Exception as e:
        logger.warning(f"Failed to update imports in {file_path}: {e}")


def main():
    """Run migration."""
    # Paths
    backend_dir = Path(__file__).parent.parent.parent
    old_rag_dir = backend_dir / "src" / "utils" / "rag"
    new_rag_dir = backend_dir / "src" / "rag"
    scripts_dir = backend_dir / "scripts"

    logger.info("Starting RAG migration...")

    # Create migration config
    config = create_migration_config()
    config_path = new_rag_dir / "migration_config.json"
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    logger.info(f"Created migration config at {config_path}")

    # Migrate data
    migrate_tagrag_data(old_rag_dir, new_rag_dir)
    migrate_ragrouter_data(old_rag_dir, new_rag_dir)

    # Create a backup note
    backup_note = """
# Migration Notes

## Old Structure (Preserved for Reference)
- backend/src/utils/rag/ - Original RAG utilities
- backend/scripts/export_tagrag_texts.py - Original export script

## New Structure
- backend/src/rag/ - New modular RAG system

## Usage Updates

### Old Usage:
```bash
python scripts/export_tagrag_texts.py \
    --input ../src/utils/rag/tagrag/format_db/控烟.json \
    --output ../src/utils/rag/ragrouter/控烟数据库/normal_db/text_db \
    --topic 控烟 \
    --chunk-size 3
```

### New Usage:
```bash
python -m rag.cli.export_tagrag \
    --input ../src/utils/rag/tagrag/format_db/控烟.json \
    --output ../src/utils/rag/ragrouter/控烟数据库/normal_db/text_db \
    --topic 控烟 \
    --chunk-size 3
```

## New Features
- Enhanced text processing and cleaning
- Configurable chunking strategies
- Support for multiple embedding models
- Batch processing capabilities
- Comprehensive validation and error handling
- Metadata preservation
- Flexible file naming options

## Integration with Server
To integrate with server.py, add:
```python
from rag import RAGPipeline

# Initialize pipeline
pipeline = RAGPipeline()

# Load existing data
pipeline.load("path/to/saved/rag_index")

# Use in endpoints
@app.post("/retrieve")
def retrieve_documents(query: str):
    results = pipeline.retrieve(query)
    return {"results": results}
```
"""

    note_path = new_rag_dir / "MIGRATION_NOTES.md"
    note_path.write_text(backup_note, encoding="utf-8")
    logger.info(f"Created migration notes at {note_path}")

    logger.info("\nMigration completed successfully!")
    logger.info(f"\nNext steps:")
    logger.info("1. Review the new RAG module structure")
    logger.info("2. Update your server.py to use the new RAG pipeline")
    logger.info("3. Update any import statements in your code")
    logger.info("4. Test the new CLI tools with your data")


if __name__ == "__main__":
    main()