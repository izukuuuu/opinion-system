from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from deepagents.backends.utils import create_file_data

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.report.deep_report.exploration_deterministic_graph import _ExplorationRuntimeDeps, _invoke_subagent_once


class _FakeCheckpointerProfile:
    checkpoint_locator = "memory://test"


class _FakeAgent:
    def __init__(self, tracker: dict, target_path: str) -> None:
        self._tracker = tracker
        self._target_path = target_path

    def invoke(self, *_args, **_kwargs):
        runtime_files = self._tracker.setdefault("runtime_files", {})
        runtime_files[self._target_path] = create_file_data(json.dumps({"result": [{"evidence_id": "ev-1"}]}, ensure_ascii=False))
        return {"messages": [{"content": "done"}], "files": {}}


class ExplorationRuntimeSyncTests(unittest.TestCase):
    def test_invoke_subagent_once_merges_lifecycle_tracker_runtime_files(self) -> None:
        target_path = "/workspace/projects/demo/reports/2025-01-01_2025-01-31/state/evidence_cards.json"
        tracker = {"runtime_files": {}}
        deps = _ExplorationRuntimeDeps(
            skill_assets={},
            middleware_factory=lambda _name: [],
            event_callback=None,
            llm="fake-model",
            runtime_backend=None,
            common_context={
                "topic_identifier": "demo-topic",
                "topic_label": "示例专题",
                "start": "2025-01-01",
                "end": "2025-01-31",
                "task_id": "task-1",
                "thread_id": "thread-1",
                "project_identifier": "demo",
                "workspace_root": "/workspace/projects/demo/reports/2025-01-01_2025-01-31",
                "state_root": "/workspace/projects/demo/reports/2025-01-01_2025-01-31/state",
            },
            subagent_specs={
                "archive_evidence_organizer": {
                    "tools": [],
                    "system_prompt": "test",
                    "skills": [],
                }
            },
            lifecycle_tracker=tracker,
        )
        state = {
            "task_id": "task-1",
            "thread_id": "thread-1",
            "topic_identifier": "demo-topic",
            "topic_label": "示例专题",
            "start": "2025-01-01",
            "end": "2025-01-31",
            "files": {},
        }

        with patch("src.report.deep_report.exploration_deterministic_graph.get_shared_report_checkpointer", return_value=(None, _FakeCheckpointerProfile())), patch(
            "src.report.deep_report.exploration_deterministic_graph.create_deep_agent",
            side_effect=lambda **_kwargs: _FakeAgent(tracker, target_path),
        ):
            result = _invoke_subagent_once(
                "archive_evidence_organizer",
                state,
                deps,
                tier=1,
            )

        files = result.get("files") if isinstance(result.get("files"), dict) else {}
        self.assertIn(target_path, files)
        self.assertIn(target_path, tracker.get("runtime_files", {}))


if __name__ == "__main__":
    unittest.main()
