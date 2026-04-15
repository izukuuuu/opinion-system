from __future__ import annotations

import json
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from flask import Flask

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.report import task_queue as task_queue_module
from src.report.api import report_bp
from src.report.deep_report import REPORT_CACHE_FILENAME
from src.report.deep_report.service import run_or_resume_deep_report_task
from src.report.task_queue import cancel_task, create_task, get_task, resume_before_failure_task


class ReportResumeBeforeFailureTests(unittest.TestCase):
    def _task_queue_context(self) -> tuple[ExitStack, Path]:
        temp_dir = tempfile.TemporaryDirectory()
        root = Path(temp_dir.name)
        stack = ExitStack()
        stack.enter_context(patch.object(task_queue_module, "STATE_ROOT", root / "_report"))
        stack.enter_context(patch.object(task_queue_module, "TASK_STATE_DIR", root / "_report" / "tasks"))
        stack.enter_context(patch.object(task_queue_module, "WORKER_STATUS_PATH", root / "_report" / "worker.json"))
        stack.callback(temp_dir.cleanup)
        return stack, root

    def _create_failed_task(self, cache_path: Path) -> dict:
        task = create_task(
            {
                "topic": "示例专题",
                "topic_identifier": "demo-topic",
                "start": "2025-01-01",
                "end": "2025-01-31",
                "mode": "fast",
            }
        )
        source_task_id = str(task["id"] or "").strip()
        with patch.object(task_queue_module, "_structured_cache_path_for_task", return_value=cache_path):
            task_queue_module._update_task(
                source_task_id,
                mutate=lambda current: current.update(
                    {
                        "status": "failed",
                        "phase": "compile",
                        "message": "compile failed",
                        "last_diagnostic": {
                            "failed_phase": "compile",
                            "failed_actor": "compile_subgraph",
                        },
                    }
                ),
            )
            cache_path.write_text(
                json.dumps(
                    {
                        "report_ir": {},
                        "metadata": {
                            "runtime_task_id": source_task_id,
                            "thread_id": task["thread_id"],
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            return get_task(source_task_id)

    def test_get_task_surfaces_resume_before_failure_capability(self) -> None:
        stack, root = self._task_queue_context()
        cache_path = root / REPORT_CACHE_FILENAME
        with stack:
            task = self._create_failed_task(cache_path)
            capability = task["resume_capabilities"]["resume_before_failure"]
            self.assertTrue(capability["enabled"])
            self.assertEqual(capability["restart_phase"], "compile")
            self.assertEqual(capability["source_phase"], "compile")

    def test_resume_before_failure_task_requeues_same_task_with_resume_context(self) -> None:
        stack, root = self._task_queue_context()
        cache_path = root / REPORT_CACHE_FILENAME
        with stack:
            source_task = self._create_failed_task(cache_path)
            with patch.object(task_queue_module, "_structured_cache_path_for_task", return_value=cache_path):
                resumed = resume_before_failure_task(source_task["id"])

            self.assertEqual(resumed["id"], source_task["id"])
            self.assertEqual(resumed["thread_id"], source_task["thread_id"])
            self.assertEqual(resumed["status"], "queued")
            self.assertEqual(resumed["phase"], "prepare")
            self.assertEqual(resumed["resume_kind"], "resume_before_failure")
            self.assertEqual(resumed["resume_source_task_id"], source_task["id"])
            self.assertEqual(resumed["resume_source_phase"], "compile")
            self.assertEqual(resumed["resume_source_actor"], "compile_subgraph")
            self.assertEqual(resumed["request"]["resume_context"]["kind"], "resume_before_failure")
            self.assertEqual(resumed["request"]["resume_context"]["source_task_id"], source_task["id"])

    def test_resume_before_failure_endpoint_returns_resumed_task(self) -> None:
        app = Flask(__name__)
        app.register_blueprint(report_bp, url_prefix="/api/report")
        client = app.test_client()
        stack, root = self._task_queue_context()
        cache_path = root / REPORT_CACHE_FILENAME
        with stack:
            source_task = self._create_failed_task(cache_path)
            with patch.object(task_queue_module, "_structured_cache_path_for_task", return_value=cache_path), patch(
                "src.report.api.ensure_worker_running",
                return_value={"running": True},
            ):
                response = client.post(f"/api/report/tasks/{source_task['id']}/resume-before-failure")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["task"]["resume_kind"], "resume_before_failure")
        self.assertEqual(payload["task"]["id"], source_task["id"])
        self.assertEqual(payload["task"]["status"], "queued")

    def test_cancel_waiting_approval_task_marks_cancelled_and_clears_approvals(self) -> None:
        stack, _ = self._task_queue_context()
        with stack:
            task = create_task(
                {
                    "topic": "示例专题",
                    "topic_identifier": "demo-topic",
                    "start": "2025-01-01",
                    "end": "2025-01-31",
                    "mode": "fast",
                }
            )
            task_id = str(task["id"] or "").strip()
            task_queue_module._update_task(
                task_id,
                mutate=lambda current: current.update(
                    {
                        "status": "waiting_approval",
                        "phase": "review",
                        "message": "等待人工审批",
                        "approvals": [
                            {
                                "approval_id": "approval-1",
                                "status": "pending",
                                "tool_name": "graph_interrupt",
                            }
                        ],
                    }
                ),
            )

            cancelled = cancel_task(task_id)

        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(cancelled["phase"], "cancelled")
        self.assertEqual(cancelled["approvals"], [])
        self.assertIn("人工复核阶段取消", cancelled["message"])

    def test_run_or_resume_deep_report_task_uses_source_structured_cache_for_failure_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir)
            cache_path = cache_dir / REPORT_CACHE_FILENAME
            thread_id = "report::demo-topic::2025-01-01::2025-01-31"
            cache_path.write_text(
                json.dumps(
                    {
                        "report_ir": {},
                        "metadata": {
                            "runtime_task_id": "task-source",
                            "thread_id": thread_id,
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            captured: dict = {}

            def _fake_orchestrator(*, request, root_thread_id, invoke_deep_agent, run_compile, event_callback=None):
                exploration = invoke_deep_agent(request)
                captured["request"] = request
                captured["exploration"] = exploration
                return {
                    "status": "completed",
                    "message": "ok",
                    "approvals": [],
                    "structured_payload": exploration["structured_payload"],
                    "full_payload": {},
                    "exploration_bundle": exploration["exploration_bundle"],
                    "thread_id": request["thread_id"],
                }

            with patch("src.report.deep_report.service.ensure_cache_dir", return_value=cache_dir), patch(
                "src.report.deep_report.service._run_deep_report_exploration_task"
            ) as explore_mock, patch(
                "src.report.deep_report.service.run_report_orchestrator_graph",
                side_effect=_fake_orchestrator,
            ):
                result = run_or_resume_deep_report_task(
                    "demo-topic",
                    "2025-01-01",
                    "2025-01-31",
                    topic_label="示例专题",
                    mode="fast",
                    thread_id=thread_id,
                    task_id="task-child",
                    failure_resume_context={
                        "kind": "resume_before_failure",
                        "source_task_id": "task-source",
                        "source_failed_phase": "compile",
                        "source_failed_actor": "compile_subgraph",
                        "source_thread_id": thread_id,
                        "structured_cache_path": str(cache_path),
                    },
                )

        self.assertEqual(result["status"], "completed")
        self.assertFalse(explore_mock.called)
        self.assertEqual(captured["request"]["compile_thread_id"], "task-child:compile")
        self.assertEqual(
            captured["exploration"]["message"],
            "已从源任务结构化缓存恢复探索结果。",
        )
        self.assertEqual(
            captured["exploration"]["structured_payload"]["metadata"]["runtime_task_id"],
            "task-source",
        )


if __name__ == "__main__":
    unittest.main()
