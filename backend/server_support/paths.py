"""Filesystem path helpers shared across the backend server modules."""

from __future__ import annotations

from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = PACKAGE_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent
SRC_DIR = BACKEND_DIR / "src"
CONFIGS_DIR = BACKEND_DIR / "configs"
DATA_PROJECTS_ROOT = BACKEND_DIR / "data" / "projects"
CONFIG_PATH = PROJECT_ROOT / "config.yaml"
FILTER_PROMPT_DIR = CONFIGS_DIR / "prompt" / "filter"
CONTENT_PROMPT_DIR = CONFIGS_DIR / "prompt" / "contentanalysis"
FILTER_PROGRESS_DIR = SRC_DIR / "filter"
FILTER_SUMMARY_FILENAME = "_summary.json"

__all__ = [
    "BACKEND_DIR",
    "CONFIG_PATH",
    "CONFIGS_DIR",
    "DATA_PROJECTS_ROOT",
    "FILTER_PROMPT_DIR",
    "CONTENT_PROMPT_DIR",
    "FILTER_PROGRESS_DIR",
    "FILTER_SUMMARY_FILENAME",
    "PROJECT_ROOT",
    "SRC_DIR",
]
