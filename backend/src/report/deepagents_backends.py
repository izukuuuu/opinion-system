from __future__ import annotations

from pathlib import Path
from typing import Any, Callable


def build_state_backend() -> Any:
    from deepagents.backends import StateBackend

    return StateBackend()


def _build_artifacts_backend(artifacts_root: Path) -> Any:
    from deepagents.backends import FilesystemBackend

    # Keep artifact writes constrained to the runtime artifact root.
    return FilesystemBackend(root_dir=artifacts_root, virtual_mode=True)


def build_report_backend(
    *,
    artifacts_root: Path,
    memory_namespace: Callable[[Any], tuple[str, ...]],
) -> Any:
    from deepagents.backends import CompositeBackend, StoreBackend

    return CompositeBackend(
        default=build_state_backend(),
        routes={
            "/memories/": StoreBackend(namespace=memory_namespace),
            "/artifacts/": _build_artifacts_backend(artifacts_root),
        },
    )


__all__ = [
    "build_report_backend",
    "build_state_backend",
]
