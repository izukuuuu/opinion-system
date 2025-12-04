"""General helper functions for RAG operations."""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Union, Tuple
import numpy as np
from datetime import datetime

logger = logging.getLogger(__name__)


def load_json(path: Union[str, Path]) -> Any:
    """Load JSON file with error handling."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {path}: {e}")


def save_json(data: Any, path: Union[str, Path], indent: int = 2) -> None:
    """Save data to JSON file with error handling."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=indent, ensure_ascii=False, default=str)
    except Exception as e:
        raise RuntimeError(f"Failed to save JSON to {path}: {e}")


def validate_rag_data(data: List[Dict[str, Any]],
                     text_field: str = "text",
                     min_length: int = 10) -> Tuple[bool, List[str]]:
    """Validate RAG dataset format and quality."""
    issues = []

    if not isinstance(data, list):
        issues.append("Data must be a list")
        return False, issues

    if len(data) == 0:
        issues.append("Data list is empty")
        return False, issues

    # Check each item
    for i, item in enumerate(data[:100]):  # Sample first 100 items
        if not isinstance(item, dict):
            issues.append(f"Item {i} is not a dictionary")
            continue

        if text_field not in item:
            issues.append(f"Item {i} missing '{text_field}' field")
        else:
            text = str(item[text_field]).strip()
            if len(text) < min_length:
                issues.append(f"Item {i} text too short ({len(text)} chars)")

    # Check for duplicates
    texts = [str(item.get(text_field, "")) for item in data if text_field in item]
    unique_texts = set(texts)
    if len(texts) != len(unique_texts):
        issues.append(f"Found {len(texts) - len(unique_texts)} duplicate texts")

    return len(issues) == 0, issues


def compute_metrics(predictions: List[Any],
                   targets: List[Any],
                   metrics: List[str] = None) -> Dict[str, float]:
    """Compute various evaluation metrics."""
    if metrics is None:
        metrics = ["accuracy", "precision", "recall", "f1"]

    results = {}
    n = len(predictions)
    if n != len(targets):
        raise ValueError(f"Predictions and targets must have same length (got {n} vs {len(targets)})")

    # Simple metrics for classification
    if "accuracy" in metrics:
        correct = sum(p == t for p, t in zip(predictions, targets))
        results["accuracy"] = correct / n

    # For more complex metrics, you might want to use sklearn
    try:
        from sklearn import metrics as sklearn_metrics

        if "precision" in metrics or "recall" in metrics or "f1" in metrics:
            precision = sklearn_metrics.precision_score(targets, predictions, average='weighted', zero_division=0)
            recall = sklearn_metrics.recall_score(targets, predictions, average='weighted', zero_division=0)
            f1 = sklearn_metrics.f1_score(targets, predictions, average='weighted', zero_division=0)

            if "precision" in metrics:
                results["precision"] = precision
            if "recall" in metrics:
                results["recall"] = recall
            if "f1" in metrics:
                results["f1"] = f1

    except ImportError:
        logger.warning("sklearn not available, skipping complex metrics")

    return results


def merge_results(results_list: List[Dict[str, Any]],
                 strategy: str = "union") -> Dict[str, Any]:
    """Merge multiple result dictionaries."""
    if not results_list:
        return {}

    if strategy == "union":
        # Union of all keys with last value taking precedence
        merged = {}
        for result in results_list:
            merged.update(result)
        return merged

    elif strategy == "intersection":
        # Only keep keys present in all results
        common_keys = set(results_list[0].keys())
        for result in results_list[1:]:
            common_keys.intersection_update(result.keys())

        return {key: results_list[0][key] for key in common_keys}

    else:
        raise ValueError(f"Unknown merge strategy: {strategy}")


def get_timestamp() -> str:
    """Get current timestamp as string."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def create_file_identifier(prefix: str = "", extension: str = "") -> str:
    """Create a unique file identifier with timestamp."""
    timestamp = get_timestamp()
    parts = [p for p in [prefix, timestamp, extension] if p]
    return "_".join(parts)


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """Truncate text to maximum length."""
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def flatten_dict(d: Dict[str, Any], parent_key: str = "", sep: str = "_") -> Dict[str, Any]:
    """Flatten nested dictionary."""
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


def batch_iterate(items: List[Any], batch_size: int):
    """Iterate over items in batches."""
    for i in range(0, len(items), batch_size):
        yield items[i:i + batch_size]