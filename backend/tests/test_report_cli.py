from __future__ import annotations

import io
import json
import shutil
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server_support.topic_context import TopicContext
from src.report import cli as report_cli


class ReportCliTests(unittest.TestCase):
    def _make_tmp_dir(self, name: str) -> Path:
        root = Path(__file__).resolve().parents[1] / "data" / "_tmp_report_cli_tests" / name
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        return root

    def test_run_uses_api_aligned_default_range_when_start_end_omitted(self) -> None:
        tmp_dir = self._make_tmp_dir("run-default-range")
        ctx = TopicContext(identifier="demo-topic", project_identifier="demo-project", display_name="示例专题")
        captured = {}
        event_path = tmp_dir / "events.jsonl"

        def _fake_run(topic_identifier, start, end, **kwargs):
            captured["topic_identifier"] = topic_identifier
            captured["start"] = start
            captured["end"] = end
            callback = kwargs.get("event_callback")
            if callable(callback):
                callback({"type": "phase.progress", "phase": "prepare", "message": "started"})
            return {
                "status": "completed",
                "message": "ok",
                "thread_id": "thread-1",
                "structured_payload": {
                    "metadata": {
                        "workspace_root": "/workspace/projects/demo-project/reports/2025-01-01_2025-01-31",
                        "state_root": "/workspace/projects/demo-project/reports/2025-01-01_2025-01-31/state",
                        "todos": [],
                    }
                },
                "full_payload": {},
                "exploration_bundle": {"gap_summary": [], "todos": []},
            }

        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch(
            "src.report.cli._resolve_report_range",
            return_value=(
                ctx,
                [{"start": "2025-01-01", "end": "2025-01-31"}],
                [],
                {"start": "2024-12-01", "end": "2025-01-31"},
            ),
        ), patch(
            "src.report.cli.ensure_cache_dir_v2",
            return_value=tmp_dir,
        ), patch(
            "src.report.cli.run_or_resume_deep_report_task",
            side_effect=_fake_run,
        ):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = report_cli.main(
                    ["run", "--topic", "示例专题", "--event-log", str(event_path), "--json"]
                )

        self.assertEqual(exit_code, 0)
        self.assertEqual(captured["topic_identifier"], "demo-topic")
        self.assertEqual(captured["start"], "2025-01-01")
        self.assertEqual(captured["end"], "2025-01-31")
        self.assertTrue(event_path.exists())
        self.assertTrue((tmp_dir / report_cli.DEFAULT_DEBUG_SUMMARY_FILENAME).exists())

    def test_run_writes_event_log_and_debug_summary(self) -> None:
        tmp_dir = self._make_tmp_dir("run-artifacts")
        ctx = TopicContext(identifier="demo-topic", project_identifier="demo-project", display_name="示例专题")
        event_path = tmp_dir / "custom-events.jsonl"

        def _fake_run(_topic_identifier, _start, _end, **kwargs):
            callback = kwargs.get("event_callback")
            if callable(callback):
                callback({"type": "graph.node.started", "phase": "exploration", "agent": "retrieval_router", "message": "running"})
            return {
                "status": "completed",
                "message": "ok",
                "thread_id": "thread-1",
                "structured_payload": {
                    "metadata": {
                        "workspace_root": "/workspace/projects/demo-project/reports/2025-01-01_2025-01-31",
                        "state_root": "/workspace/projects/demo-project/reports/2025-01-01_2025-01-31/state",
                        "todos": [{"id": "tier-1", "status": "completed"}],
                        "execution_plan": {"nodes": {}},
                        "reused_artifacts": {"evidence_cards": {"source_report_range": "2024-12-01_2024-12-31"}},
                        "skipped_agents": {"archive_evidence_organizer": {"reason": "reused_from_history"}},
                    }
                },
                "full_payload": {},
                "exploration_bundle": {
                    "gap_summary": [],
                    "todos": [{"id": "tier-1", "status": "completed"}],
                    "artifact_semantic_status": {"evidence_cards.json": {"status": "ready"}},
                    "readiness_gate_passed": True,
                    "repair_attempts": 1,
                    "repair_trace": [{"target_agent": "archive_evidence_organizer", "status": "ready"}],
                    "blocked_stage": "",
                },
            }

        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch(
            "src.report.cli._resolve_report_range",
            return_value=(ctx, [], [], {"start": "2025-01-01", "end": "2025-01-31"}),
        ), patch(
            "src.report.cli.ensure_cache_dir_v2",
            return_value=tmp_dir,
        ), patch(
            "src.report.cli.run_or_resume_deep_report_task",
            side_effect=_fake_run,
        ):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = report_cli.main(
                    ["run", "--topic", "示例专题", "--event-log", str(event_path)]
                )

        self.assertEqual(exit_code, 0)
        event_lines = event_path.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(event_lines), 1)
        summary = json.loads((tmp_dir / report_cli.DEFAULT_DEBUG_SUMMARY_FILENAME).read_text(encoding="utf-8"))
        self.assertEqual(summary["status"], "completed")
        self.assertEqual(summary["workspace_root"], "/workspace/projects/demo-project/reports/2025-01-01_2025-01-31")
        self.assertIn("execution_plan", summary)
        self.assertIn("reused_artifacts", summary)
        self.assertIn("skipped_agents", summary)
        self.assertTrue(summary["readiness_gate_passed"])
        self.assertEqual(summary["repair_attempts"], 1)
        self.assertIn("artifact_semantic_status", summary)

    def test_availability_outputs_current_default_range_only(self) -> None:
        ctx = TopicContext(identifier="demo-topic", project_identifier="demo-project", display_name="示例专题")
        stdout = io.StringIO()
        with patch(
            "src.report.cli._resolve_report_range",
            return_value=(
                ctx,
                [{"start": "2025-02-01", "end": "2025-02-28"}],
                [{"start": "2025-01-01", "end": "2025-01-31"}],
                {"start": "2024-01-01", "end": "2025-02-28"},
            ),
        ):
            with redirect_stdout(stdout):
                exit_code = report_cli.main(["availability", "--topic", "示例专题"])
        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["range"]["start"], "2025-02-01")
        self.assertEqual(payload["topic_identifier"], "demo-topic")

    def test_replay_task_can_build_failure_resume_context(self) -> None:
        tmp_dir = self._make_tmp_dir("replay-task")
        event_path = tmp_dir / "events.jsonl"
        task = {
            "id": "rp-task-1",
            "topic": "示例专题",
            "topic_identifier": "demo-topic",
            "thread_id": "report::demo-topic::2025-01-01::2025-01-31",
            "start": "2025-01-01",
            "end": "2025-01-31",
            "mode": "fast",
            "request": {"project": "Demo Project", "dataset_id": "", "skip_validation": False},
        }
        ctx = TopicContext(identifier="demo-topic", project_identifier="demo-project", display_name="示例专题")
        captured = {}

        def _fake_run(_topic_identifier, _start, _end, **kwargs):
            captured["failure_resume_context"] = kwargs.get("failure_resume_context")
            callback = kwargs.get("event_callback")
            if callable(callback):
                callback({"type": "phase.progress", "phase": "compile", "message": "resume"})
            return {
                "status": "completed",
                "message": "ok",
                "thread_id": "thread-1",
                "structured_payload": {"metadata": {}},
                "full_payload": {},
                "exploration_bundle": {"gap_summary": [], "todos": []},
            }

        with patch("src.report.cli.get_task", return_value=task), patch(
            "src.report.cli.evaluate_resume_before_failure",
            return_value={
                "enabled": True,
                "source_phase": "compile",
                "source_actor": "markdown_compiler",
                "structured_cache_path": str(tmp_dir / "report_payload.json"),
            },
        ), patch(
            "src.report.cli._resolve_report_range",
            return_value=(ctx, [], [], {"start": "2025-01-01", "end": "2025-01-31"}),
        ), patch(
            "src.report.cli.ensure_cache_dir_v2",
            return_value=tmp_dir,
        ), patch(
            "src.report.cli.run_or_resume_deep_report_task",
            side_effect=_fake_run,
        ):
            exit_code = report_cli.main(
                ["replay-task", "--task-id", "rp-task-1", "--resume-before-failure", "--event-log", str(event_path), "--quiet-events"]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(captured["failure_resume_context"]["source_task_id"], "rp-task-1")
        self.assertEqual(captured["failure_resume_context"]["source_failed_phase"], "compile")


if __name__ == "__main__":
    unittest.main()
