from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.report.deep_report.service import run_or_resume_deep_report_task


class ReportPipelineMockE2ETests(unittest.TestCase):
    def _common_runtime_patches(self, tmp: str):
        cache_dir = Path(tmp)
        return [
            patch("src.report.deep_report.service.ensure_cache_dir_v2", return_value=cache_dir),
            patch("src.report.deep_report.service.build_artifacts_root", return_value=cache_dir / "artifacts"),
            patch(
                "src.report.deep_report.service._prepare_runtime",
                return_value=(
                    {
                        "topic_identifier": "demo-topic",
                        "topic_label": "示例专题",
                        "project_identifier": "demo-project",
                        "workspace_root": "/workspace/projects/demo-project/reports/2025-01-01_2025-01-31",
                        "state_root": "/workspace/projects/demo-project/reports/2025-01-01_2025-01-31/state",
                        "execution_plan": {"nodes": {}},
                        "reused_artifacts": {},
                        "supplement_candidates": {},
                    },
                    {},
                    object(),
                    {},
                    [],
                ),
            ),
            patch("src.report.deep_report.service.build_langchain_chat_model", return_value=(object(), {})),
            patch(
                "src.report.deep_report.exploration_deterministic_graph.run_exploration_deterministic_graph",
                return_value={
                    "status": "completed",
                    "message": "探索已完成",
                    "structured_payload": {},
                    "files": {},
                    "gaps": [],
                    "execution_plan": {"nodes": {}},
                    "reused_artifacts": {},
                    "skipped_agents": {},
                    "todos": [],
                },
            ),
        ]

    def test_mock_e2e_happy_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            patches = self._common_runtime_patches(tmp)
            patches.extend(
                [
                    patch(
                        "src.report.deep_report.service._run_readiness_repair_loop",
                        return_value={
                            "runtime_files": {},
                            "artifact_semantic_status": {"evidence_cards.json": {"status": "ready"}},
                            "readiness_gate_passed": True,
                            "repair_attempts": 1,
                            "repair_trace": [{"target_agent": "archive_evidence_organizer", "status": "ready"}],
                            "blocked_stage": "",
                        },
                    ),
                    patch(
                        "src.report.deep_report.service._synthesize_structured_report_from_files",
                        return_value={
                            "task": {
                                "topic_identifier": "demo-topic",
                                "topic_label": "示例专题",
                                "start": "2025-01-01",
                                "end": "2025-01-31",
                                "mode": "fast",
                                "thread_id": "thread-1",
                            },
                            "structured_valid": True,
                            "report_ir": {"summary": "ok"},
                            "metadata": {
                                "workspace_root": "/workspace/projects/demo-project/reports/2025-01-01_2025-01-31",
                                "state_root": "/workspace/projects/demo-project/reports/2025-01-01_2025-01-31/state",
                            },
                        },
                    ),
                    patch(
                        "src.report.deep_report.service.generate_full_report_payload",
                        return_value={
                            "status": "completed",
                            "message": "compile ok",
                            "markdown": "# Report",
                            "metadata": {},
                            "meta": {},
                        },
                    ),
                ]
            )
            for item in patches:
                item.start()
            try:
                result = run_or_resume_deep_report_task(
                    "demo-topic",
                    "2025-01-01",
                    "2025-01-31",
                    topic_label="示例专题",
                    project_identifier="demo-project",
                    mode="fast",
                    thread_id="thread-1",
                    task_id="task-1",
                )
            finally:
                for item in reversed(patches):
                    item.stop()

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["full_payload"]["status"], "completed")
        self.assertTrue(result["full_payload"]["readiness_gate_passed"])
        self.assertEqual(result["full_payload"]["repair_attempts"], 1)
        self.assertIn("artifact_semantic_status", result["full_payload"])

    def test_mock_e2e_blocks_compile_when_readiness_gate_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            patches = self._common_runtime_patches(tmp)
            patches.extend(
                [
                    patch(
                        "src.report.deep_report.service._run_readiness_repair_loop",
                        return_value={
                            "runtime_files": {},
                            "artifact_semantic_status": {"evidence_cards.json": {"status": "empty"}},
                            "readiness_gate_passed": False,
                            "repair_attempts": 2,
                            "repair_trace": [{"target_agent": "archive_evidence_organizer", "status": "partial"}],
                            "blocked_stage": "exploration_readiness",
                        },
                    ),
                    patch("src.report.deep_report.service._synthesize_structured_report_from_files"),
                    patch("src.report.deep_report.service.generate_full_report_payload"),
                ]
            )
            for item in patches:
                item.start()
            try:
                result = run_or_resume_deep_report_task(
                    "demo-topic",
                    "2025-01-01",
                    "2025-01-31",
                    topic_label="示例专题",
                    project_identifier="demo-project",
                    mode="fast",
                    thread_id="thread-1",
                    task_id="task-1",
                )
            finally:
                for item in reversed(patches):
                    item.stop()

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["message"], "探索阶段未通过 readiness gate，已阻断 compile。")
        self.assertEqual(result["exploration_bundle"]["blocked_stage"], "exploration_readiness")
        self.assertFalse(bool(result["structured_payload"]))

    def test_mock_e2e_surfaces_compile_provider_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            patches = self._common_runtime_patches(tmp)
            patches.extend(
                [
                    patch(
                        "src.report.deep_report.service._run_readiness_repair_loop",
                        return_value={
                            "runtime_files": {},
                            "artifact_semantic_status": {"evidence_cards.json": {"status": "ready"}},
                            "readiness_gate_passed": True,
                            "repair_attempts": 0,
                            "repair_trace": [],
                            "blocked_stage": "",
                        },
                    ),
                    patch(
                        "src.report.deep_report.service._synthesize_structured_report_from_files",
                        return_value={
                            "task": {
                                "topic_identifier": "demo-topic",
                                "topic_label": "示例专题",
                                "start": "2025-01-01",
                                "end": "2025-01-31",
                                "mode": "fast",
                                "thread_id": "thread-1",
                            },
                            "structured_valid": True,
                            "report_ir": {"summary": "ok"},
                            "metadata": {},
                        },
                    ),
                    patch(
                        "src.report.deep_report.service.generate_full_report_payload",
                        return_value={
                            "status": "failed",
                            "message": "Error code: 429 - week allocated quota exceeded.",
                            "metadata": {},
                            "meta": {},
                        },
                    ),
                ]
            )
            for item in patches:
                item.start()
            try:
                result = run_or_resume_deep_report_task(
                    "demo-topic",
                    "2025-01-01",
                    "2025-01-31",
                    topic_label="示例专题",
                    project_identifier="demo-project",
                    mode="fast",
                    thread_id="thread-1",
                    task_id="task-1",
                )
            finally:
                for item in reversed(patches):
                    item.stop()

        self.assertEqual(result["status"], "failed")
        self.assertIn("429", result["message"])
        self.assertEqual(result["full_payload"]["status"], "failed")
        self.assertTrue(result["full_payload"]["readiness_gate_passed"])


if __name__ == "__main__":
    unittest.main()
