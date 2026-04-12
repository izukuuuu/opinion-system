from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.report.worker import _build_resume_payload_from_task, _resolved_graph_review, _run_task
from src.report.deep_report.runtime_contract import RUNTIME_CONTRACT_VERSION


class DummyThread:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def start(self) -> None:
        return None

    def join(self, timeout: float | None = None) -> None:
        return None


def _sample_task(*, status: str = "running", approvals: list[dict] | None = None) -> dict:
    return {
        "id": "rp-smoke",
        "topic_identifier": "demo-topic",
        "topic": "示例专题",
        "start": "2025-01-01",
        "end": "2025-01-31",
        "thread_id": "report::demo-topic::2025-01-01::2025-01-31",
        "status": status,
        "phase": "interpret",
        "request": {
            "topic_identifier": "demo-topic",
            "topic": "示例专题",
            "start": "2025-01-01",
            "end": "2025-01-31",
            "mode": "fast",
            "runtime_contract_version": RUNTIME_CONTRACT_VERSION,
            "aliases": [],
        },
        "approvals": approvals or [],
        "runtime_contract_version": RUNTIME_CONTRACT_VERSION,
    }


def _structured_payload() -> dict:
    return {
        "task": {"topic_label": "示例专题"},
        "title": "示例专题结构化报告",
        "rangeText": "2025-01-01 → 2025-01-31",
        "artifact_manifest": {
            "structured_projection": {"status": "ready"},
            "draft_bundle": {"status": "ready"},
        },
        "report_ir_summary": {"summary": "结构化摘要"},
    }


def _full_payload(*, waiting_approval: bool = False) -> dict:
    base = {
        "title": "示例专题正式报告",
        "markdown": "# 示例专题正式报告",
        "artifact_manifest": {
            "structured_projection": {"status": "ready"},
            "draft_bundle": {"status": "ready"},
            "full_markdown": {"status": "ready"},
            "approval_records": {"status": "ready"},
        },
    }
    if waiting_approval:
        base.update(
            {
                "status": "waiting_approval",
                "message": "正式文稿需要人工审批。",
                "approvals": [
                    {
                        "approval_id": "approval-1",
                        "interrupt_id": "interrupt-1",
                        "decision_index": 0,
                        "tool_name": "graph_interrupt",
                        "status": "pending",
                    }
                ],
            }
        )
    return base


class ReportRuntimeSmokeTests(unittest.TestCase):
    def _common_patches(self):
        return [
            patch("src.report.worker.ensure_analyze_results", return_value={"prepared": True, "analyze_root": "ok", "message": "分析就绪"}),
            patch("src.report.worker.ensure_explain_results", return_value={"ready": True, "message": "解读就绪"}),
            patch("src.report.worker._raise_if_cancelled", return_value=None),
            patch("src.report.worker._maybe_update_fallback_todos", return_value=None),
            patch("src.report.worker._has_rejected_approval", return_value=False),
            patch("src.report.worker.threading.Thread", return_value=DummyThread()),
            patch("src.report.worker.set_worker_pid"),
            patch("src.report.worker.mark_agent_started"),
            patch("src.report.worker.mark_task_progress"),
            patch("src.report.worker.append_agent_memo"),
            patch("src.report.worker.set_structured_result_digest"),
            patch("src.report.worker.update_task_trust"),
            patch("src.report.worker.build_artifacts_root", return_value=Path("f:/opinion-system/backend/data/_report/runtime")),
            patch("src.report.worker._structured_digest_from_payload", return_value={"report_ir_summary": {"summary": "结构化摘要"}}),
            patch("src.report.worker._trust_from_payload", return_value={}),
        ]

    def test_happy_path_smoke_keeps_thread_and_manifest(self) -> None:
        task = _sample_task()
        with patch("src.report.worker.get_task", return_value=task), patch(
            "src.report.worker.run_or_resume_deep_report_task",
            return_value={"status": "completed", "structured_payload": _structured_payload(), "full_payload": _full_payload()},
        ) as runtime_mock, patch(
            "src.report.worker.mark_artifact_ready"
        ) as artifact_ready_mock, patch(
            "src.report.worker.mark_task_completed"
        ) as completed_mock:
            stack = self._common_patches()
            for item in stack:
                item.start()
            try:
                _run_task("rp-smoke")
            finally:
                for item in reversed(stack):
                    item.stop()

        self.assertEqual(runtime_mock.call_args.kwargs["thread_id"], task["thread_id"])
        artifact_payload = artifact_ready_mock.call_args.kwargs["payload"]
        self.assertIn("artifact_manifest", artifact_payload)
        self.assertTrue(artifact_payload["artifact_manifest"]["full_markdown"]["status"] == "ready")
        completed_payload = completed_mock.call_args.kwargs["payload"]
        self.assertIn("artifact_manifest", completed_payload)
        self.assertEqual(completed_payload["artifact_manifest"]["full_markdown"]["status"], "ready")

    def test_semantic_review_smoke_writes_approval_and_preserves_thread(self) -> None:
        task = _sample_task()
        with patch("src.report.worker.get_task", return_value=task), patch(
            "src.report.worker.run_or_resume_deep_report_task",
            return_value={"status": "waiting_approval", "structured_payload": _structured_payload(), **_full_payload(waiting_approval=True)},
        ), patch("src.report.worker.mark_artifact_ready") as artifact_ready_mock, patch(
            "src.report.worker.mark_approval_required"
        ) as approval_required_mock, patch("src.report.worker.mark_task_completed") as completed_mock:
            stack = self._common_patches()
            for item in stack:
                item.start()
            try:
                _run_task("rp-smoke")
            finally:
                for item in reversed(stack):
                    item.stop()

        artifact_payload = artifact_ready_mock.call_args.kwargs["payload"]
        self.assertIn("artifact_manifest", artifact_payload)
        self.assertEqual(approval_required_mock.call_args.kwargs["phase"], "review")
        self.assertEqual(approval_required_mock.call_args.kwargs["approvals"][0]["tool_name"], "graph_interrupt")
        self.assertFalse(completed_mock.called)

    def test_fallback_recompile_smoke_appends_same_lineage_surface(self) -> None:
        task = _sample_task()
        full_payload = _full_payload()
        full_payload["artifact_manifest"]["draft_bundle"]["source_artifact_ids"] = ["draft-v1"]
        full_payload["artifact_manifest"]["full_markdown"]["source_artifact_ids"] = ["draft-v2"]
        with patch("src.report.worker.get_task", return_value=task), patch(
            "src.report.worker.run_or_resume_deep_report_task",
            return_value={"status": "completed", "structured_payload": _structured_payload(), "full_payload": full_payload},
        ), patch("src.report.worker.mark_artifact_ready") as artifact_ready_mock, patch(
            "src.report.worker.mark_task_completed"
        ) as completed_mock:
            stack = self._common_patches()
            for item in stack:
                item.start()
            try:
                _run_task("rp-smoke")
            finally:
                for item in reversed(stack):
                    item.stop()

        artifact_manifest = artifact_ready_mock.call_args.kwargs["payload"]["artifact_manifest"]
        self.assertEqual(artifact_manifest["draft_bundle"]["source_artifact_ids"], ["draft-v1"])
        self.assertEqual(artifact_manifest["full_markdown"]["source_artifact_ids"], ["draft-v2"])
        completed_manifest = completed_mock.call_args.kwargs["payload"]["artifact_manifest"]
        self.assertEqual(completed_manifest["full_markdown"]["source_artifact_ids"], ["draft-v2"])

    def test_resume_after_failure_smoke_keeps_thread_and_lineage(self) -> None:
        approvals = [
            {
                "approval_id": "approval-1",
                "interrupt_id": "interrupt-1",
                "decision_index": 0,
                "tool_name": "graph_interrupt",
                "status": "resolved",
                "decision": "approve",
                "action": {"tool_args": {"markdown": "# old"}},
            }
        ]
        task = _sample_task(status="queued", approvals=approvals)
        with patch("src.report.worker.get_task", return_value=task), patch(
            "src.report.worker.run_or_resume_deep_report_task",
            return_value={"status": "completed", "structured_payload": _structured_payload(), "full_payload": _full_payload()},
        ) as runtime_mock, patch(
            "src.report.worker.mark_artifact_ready"
        ), patch(
            "src.report.worker.mark_task_completed"
        ):
            stack = self._common_patches()
            for item in stack:
                item.start()
            try:
                _run_task("rp-smoke")
            finally:
                for item in reversed(stack):
                    item.stop()

        self.assertEqual(runtime_mock.call_args.kwargs["thread_id"], task["thread_id"])
        self.assertIsNotNone(runtime_mock.call_args.kwargs["resume_payload"])

    def test_legacy_runtime_version_blocks_resume(self) -> None:
        approvals = [
            {
                "approval_id": "approval-1",
                "interrupt_id": "interrupt-1",
                "decision_index": 0,
                "tool_name": "graph_interrupt",
                "status": "resolved",
                "decision": "approve",
                "action": {"tool_args": {"markdown": "# old"}},
            }
        ]
        task = _sample_task(status="queued", approvals=approvals)
        task["request"]["runtime_contract_version"] = "deep-report-contract.v2"
        task["runtime_contract_version"] = "deep-report-contract.v2"
        with patch("src.report.worker.get_task", return_value=task), patch(
            "src.report.worker.run_or_resume_deep_report_task"
        ) as runtime_mock, patch("src.report.worker.append_event") as append_event_mock:
            stack = self._common_patches()
            for item in stack:
                item.start()
            try:
                with self.assertRaises(Exception) as ctx:
                    _run_task("rp-smoke")
            finally:
                for item in reversed(stack):
                    item.stop()

        self.assertIn("旧 ABI 任务不能直接 resume", str(ctx.exception))
        self.assertFalse(runtime_mock.called)
        self.assertTrue(append_event_mock.called)
        payload = append_event_mock.call_args.kwargs["payload"]
        self.assertEqual(payload["diagnostic_kind"], "legacy_runtime_version")

    def test_resolved_graph_review_ignores_legacy_semantic_tool_name(self) -> None:
        task = _sample_task(
            approvals=[
                {
                    "approval_id": "approval-1",
                    "interrupt_id": "interrupt-1",
                    "decision_index": 0,
                    "tool_name": "semantic_review_markdown",
                    "status": "resolved",
                    "decision": "approve",
                }
            ]
        )
        self.assertIsNone(_resolved_graph_review(task))

    def test_build_resume_payload_uses_interrupt_id_only(self) -> None:
        task = _sample_task(
            approvals=[
                {
                    "approval_id": "approval-1",
                    "interrupt_id": "interrupt-1",
                    "decision_index": 0,
                    "tool_name": "graph_interrupt",
                    "status": "resolved",
                    "decision": "approve",
                    "action": {"tool_args": {"markdown": "# old"}},
                },
                {
                    "approval_id": "approval-2",
                    "decision_index": 0,
                    "tool_name": "graph_interrupt",
                    "status": "resolved",
                    "decision": "approve",
                    "action": {"tool_args": {"markdown": "# ignored"}},
                },
            ]
        )
        payload = _build_resume_payload_from_task(task)
        self.assertEqual(payload, {"decisions": [{"type": "approve"}]})


if __name__ == "__main__":
    unittest.main()
