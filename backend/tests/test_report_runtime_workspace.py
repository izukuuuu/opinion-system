from __future__ import annotations

import json
import shutil
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from deepagents.backends.utils import create_file_data

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.report.configs import get_subagent_output_globs
from src.report.deep_report.deterministic import build_runtime_workspace_layout, build_workspace_files
from src.report.deep_report.service import _build_reuse_planning, _persist_workspace_state, _runtime_file_exists


class ReportRuntimeWorkspaceTests(unittest.TestCase):
    def _make_case_dir(self, name: str) -> Path:
        root = Path(__file__).resolve().parents[1] / "data" / "_tmp_runtime_workspace_tests" / name
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        return root

    def test_build_workspace_files_uses_project_scoped_runtime_layout(self) -> None:
        layout = build_runtime_workspace_layout(
            project_identifier="demo-project",
            topic_identifier="demo-topic",
            start="2026-04-01",
            end="2026-04-18",
        )
        files = build_workspace_files(
            {
                "topic_identifier": "demo-topic",
                "topic_label": "示例项目",
                "project_identifier": "demo-project",
                "time_range": {"start": "2026-04-01", "end": "2026-04-18"},
                "mode": "fast",
                "task_contract": {"topic_identifier": "demo-topic", "project_identifier": "demo-project"},
                "overview": {},
                "raw_digest": {},
            },
            layout=layout,
        )
        self.assertIn(layout.base_context_path, files)
        self.assertIn(layout.state_file("task_contract.json"), files)
        self.assertNotIn("/workspace/state/task_contract.json", files)
        rendered = get_subagent_output_globs("writer", path_tokens={"project_identifier": layout.project_component, "report_range": layout.range_component})
        self.assertEqual(
            rendered,
            [f"/workspace/projects/{layout.project_component}/reports/{layout.range_component}/state/section_drafts/*.json"],
        )

    def test_persist_workspace_state_writes_manifest_v2_and_state_tree(self) -> None:
        layout = build_runtime_workspace_layout(
            project_identifier="proj-a",
            topic_identifier="topic-a",
            start="2026-04-01",
            end="2026-04-18",
        )
        runtime_files = {
            layout.state_file("evidence_cards.json"): create_file_data(json.dumps({"status": "ready", "result": [{"id": "e1"}]}, ensure_ascii=False)),
            layout.state_file("section_packets/overview.json"): create_file_data(json.dumps({"status": "ready", "result": {"summary": "ok"}}, ensure_ascii=False)),
        }
        cache_dir = self._make_case_dir("persist")
        manifest = _persist_workspace_state(
            cache_dir=cache_dir,
            runtime_files=runtime_files,
            identity={
                "project_identifier": "proj-a",
                "topic_identifier": "topic-a",
                "start": "2026-04-01",
                "end": "2026-04-18",
                "mode": "fast",
            },
        )
        self.assertEqual(manifest.get("schema_version"), "reuse-manifest.v2")
        self.assertTrue((cache_dir / "state" / "evidence_cards.json").exists())
        self.assertTrue((cache_dir / "state" / "section_packets" / "overview.json").exists())
        artifacts = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), list) else []
        evidence = next(item for item in artifacts if item.get("artifact_key") == "evidence_cards")
        self.assertEqual(evidence.get("relative_path"), "state/evidence_cards.json")
        self.assertEqual(evidence.get("status"), "ready")

    def test_runtime_file_exists_accepts_relative_artifact_key_for_workspace_paths(self) -> None:
        layout = build_runtime_workspace_layout(
            project_identifier="proj-a",
            topic_identifier="topic-a",
            start="2026-04-01",
            end="2026-04-18",
        )
        runtime_files = {
            layout.state_file("evidence_cards.json"): create_file_data(json.dumps({"result": [{"id": "e1"}]}, ensure_ascii=False)),
        }
        self.assertTrue(_runtime_file_exists(runtime_files, layout.state_file("evidence_cards.json")))
        self.assertTrue(_runtime_file_exists(runtime_files, "evidence_cards.json"))
        self.assertFalse(_runtime_file_exists(runtime_files, "timeline_nodes.json"))

    def test_reuse_planning_applies_exact_match_and_fixed_tier_invalidation(self) -> None:
        root = self._make_case_dir("reuse")
        current = root / "2026-04-01_2026-04-18"
        exact = root / "2026-04-01_2026-04-18_exact"
        cross = root / "2026-03-01_2026-03-31"
        for path in (current, exact, cross):
            path.mkdir(parents=True, exist_ok=True)

        (exact / "reuse_manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": "reuse-manifest.v2",
                    "identity": {
                        "project_identifier": "proj-a",
                        "start": "2026-04-01",
                        "end": "2026-04-18",
                        "mode": "fast",
                    },
                    "artifacts": [
                        {"artifact_key": "utility_assessment", "status": "ready", "relative_path": "utility_assessment.json"},
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (cross / "reuse_manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": "reuse-manifest.v2",
                    "identity": {
                        "project_identifier": "proj-a",
                        "start": "2026-03-01",
                        "end": "2026-03-31",
                        "mode": "fast",
                    },
                    "artifacts": [
                        {"artifact_key": "timeline_nodes", "status": "ready", "relative_path": "state/timeline_nodes.json"},
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        with patch("src.report.deep_report.service._collect_project_report_dirs", return_value=[current, exact, cross]):
            planning = _build_reuse_planning(
                cache_dir=current,
                identity={
                    "project_identifier": "proj-a",
                    "topic_identifier": "topic-a",
                    "start": "2026-04-01",
                    "end": "2026-04-18",
                    "mode": "fast",
                },
            )

            artifacts = {item["artifact_key"]: item for item in planning.get("artifacts") or [] if isinstance(item, dict)}
            self.assertEqual(artifacts["utility_assessment"]["decision"], "reuse")
            self.assertEqual(artifacts["evidence_cards"]["decision"], "rerun")
            self.assertEqual(artifacts["timeline_nodes"]["decision"], "rerun")
            self.assertEqual(artifacts["timeline_nodes"]["blocked_by"], ["evidence_cards"])

    def test_builder_and_skills_no_longer_reference_legacy_workspace_state_paths(self) -> None:
        builder_path = Path(__file__).resolve().parents[1] / "src" / "report" / "deep_report" / "builder.py"
        builder_text = builder_path.read_text(encoding="utf-8")
        self.assertNotIn("/workspace/state/", builder_text)
        self.assertNotIn("/workspace/base_context.json", builder_text)

        skill_root = Path(__file__).resolve().parents[1] / "src" / "report" / "skills"
        for skill_path in skill_root.rglob("SKILL.md"):
            skill_text = skill_path.read_text(encoding="utf-8")
            self.assertNotIn("/workspace/state/", skill_text, msg=str(skill_path))
            self.assertNotIn("/workspace/base_context.json", skill_text, msg=str(skill_path))


if __name__ == "__main__":
    unittest.main()
