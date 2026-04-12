from __future__ import annotations

from contextlib import ExitStack
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.report.api import report_bp
from src.report.agent_runtime import _json_safe_runtime_value, snapshot_tool_policy
from src.report.deep_report.compiler import sanitize_public_markdown
from src.report.deep_report.service import (
    _build_tool_intelligence_receipt,
    _ensure_validation_notes_from_claim_checks,
    _normalized_task_contract_violation,
    _ready_for_deterministic_finalize,
)
from src.report.worker import _run_task


class DummyThread:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def start(self) -> None:
        return None

    def join(self, timeout: float | None = None) -> None:
        return None


class FullReportPipelineTests(unittest.TestCase):
    def test_normalized_task_contract_violation_is_corrected_before_downstream_tools(self):
        tracker = {
            "task_contract": {
                "topic_identifier": "20260304-091855-2025控烟舆情",
                "topic_label": "2025控烟舆情分析报告",
                "start": "2025-01-15",
                "end": "2025-12-31",
                "mode": "fast",
                "thread_id": "thread-1",
            }
        }
        payload = {
            "normalized_task": {
                "task_id": "tobacco_control_2025:2025-01-01:2025-06-30",
                "topic": "2025控烟舆情分析报告",
                "topic_identifier": "tobacco_control_2025",
                "time_range": {"start": "2025-01-01", "end": "2025-06-30"},
                "mode": "research",
            },
            "result": {
                "task_id": "tobacco_control_2025:2025-01-01:2025-06-30",
                "topic": "2025控烟舆情分析报告",
                "topic_identifier": "tobacco_control_2025",
                "time_range": {"start": "2025-01-01", "end": "2025-06-30"},
                "mode": "research",
            },
        }

        corrected, violations = _normalized_task_contract_violation(payload, tracker)

        self.assertIn("topic_identifier", violations)
        self.assertEqual(corrected["normalized_task"]["topic_identifier"], "20260304-091855-2025控烟舆情")
        self.assertEqual(corrected["normalized_task"]["time_range"]["start"], "2025-01-15")
        self.assertEqual(corrected["normalized_task"]["time_range"]["end"], "2025-12-31")
        self.assertEqual(corrected["normalized_task"]["mode"], "fast")

    def test_coverage_receipt_surfaces_partial_range_coverage(self):
        receipt = _build_tool_intelligence_receipt(
            "get_corpus_coverage",
            {
                "coverage": {
                    "matched_count": 3,
                    "sampled_count": 3,
                    "platform_counts": {"新闻": 3},
                    "source_resolution": "overlap_fetch_range",
                    "resolved_fetch_range": {"start": "2025-01-15", "end": "2025-12-31"},
                    "requested_time_range": {"start": "2025-01-01", "end": "2025-06-30"},
                    "effective_time_range": {"start": "2025-01-01", "end": "2025-06-30"},
                    "effective_topic_identifier": "20260304-091855-2025控烟舆情",
                    "source_quality_flags": ["partial_range_coverage"],
                    "readiness_flags": ["records_available"],
                }
            },
            {},
        )

        self.assertEqual(receipt["diagnostic_kind"], "partial_range_coverage")
        self.assertIn("部分重叠", receipt["decision_summary"])
        self.assertEqual(receipt["resolved_fetch_range"]["start"], "2025-01-15")

    def test_coverage_receipt_surfaces_contract_binding_failure(self):
        receipt = _build_tool_intelligence_receipt(
            "get_corpus_coverage",
            {
                "coverage": {
                    "matched_count": 0,
                    "sampled_count": 0,
                    "platform_counts": {},
                    "source_resolution": "contract_binding_failed",
                    "requested_time_range": {"start": "2025-01-01", "end": "2025-06-30"},
                    "effective_time_range": {"start": "2025-01-01", "end": "2025-06-30"},
                    "readiness_flags": ["contract_binding_failed"],
                },
                "contract_value": {"topic_identifier": "demo-topic", "start": "2025-01-01", "end": "2025-06-30", "mode": "fast"},
                "agent_proposed_value": {"topic_identifier": "demo-topic", "start": "2025-01-01", "end": "2025-06-30", "mode": "fast"},
                "effective_value": {"topic_identifier": "", "start": "", "end": "", "mode": ""},
                "violation_origin": "payload_adapter",
                "repair_action": "reject_missing_contract",
            },
            {},
        )

        self.assertEqual(receipt["diagnostic_kind"], "contract_binding_failed")
        self.assertEqual(receipt["outcome_kind"], "failed")
        self.assertEqual(receipt["violation_origin"], "payload_adapter")

    def test_coverage_receipt_surfaces_legacy_adapter_hit(self):
        receipt = _build_tool_intelligence_receipt(
            "get_corpus_coverage",
            {
                "legacy_adapter_hit": True,
                "legacy_input_kind": ["normalized_task_json"],
                "coverage": {
                    "matched_count": 2,
                    "sampled_count": 2,
                    "platform_counts": {"新闻": 2},
                    "source_resolution": "covering_fetch_range",
                    "requested_time_range": {"start": "2025-01-15", "end": "2025-12-31"},
                    "effective_time_range": {"start": "2025-01-15", "end": "2025-12-31"},
                    "readiness_flags": ["records_available"],
                },
                "contract_value": {"topic_identifier": "demo-topic", "start": "2025-01-15", "end": "2025-12-31", "mode": "fast"},
                "agent_proposed_value": {"topic_identifier": "demo-topic", "start": "2025-01-15", "end": "2025-12-31", "mode": "fast"},
                "effective_value": {"topic_identifier": "demo-topic", "start": "2025-01-15", "end": "2025-12-31", "mode": "fast"},
                "violation_origin": "payload_adapter",
                "repair_action": "mapped_legacy_fields",
            },
            {},
        )

        self.assertEqual(receipt["diagnostic_kind"], "legacy_adapter_hit")
        self.assertEqual(receipt["outcome_kind"], "degraded")

    def test_empty_evidence_receipt_prefers_empty_path_even_without_no_cards_flag(self):
        receipt = _build_tool_intelligence_receipt(
            "retrieve_evidence_cards",
            {
                "result": [],
                "coverage": {
                    "matched_count": 0,
                    "sampled_count": 0,
                    "platform_counts": {},
                    "readiness_flags": [],
                },
            },
            {"coverage_state": "ready"},
        )

        self.assertEqual(receipt["outcome_kind"], "empty")
        self.assertEqual(receipt["skip_reason"], "empty_evidence")
        self.assertIn("没有召回到可用证据卡", receipt["decision_summary"])
        self.assertIn("空证据对象", receipt["next_action"])

    def test_ready_for_deterministic_finalize_only_requires_structured_report_for_graph_handoff(self):
        runtime_files = {
            "/workspace/state/structured_report.json": {"content": ["{}"]},
        }

        self.assertTrue(_ready_for_deterministic_finalize(runtime_files))

        runtime_files["/workspace/state/structured_report.json"] = {"content": ["   "]}
        self.assertFalse(_ready_for_deterministic_finalize(runtime_files))

    def test_validation_notes_are_derived_from_claim_checks(self):
        runtime_files = {
            "/workspace/state/claim_checks.json": {
                "content": [
                    '{"result":['
                    '{"claim_id":"c1","claim_text":"A","status":"supported"},'
                    '{"claim_id":"c2","claim_text":"B","status":"unsupported","gap_note":"缺直接证据"},'
                    '{"claim_id":"c3","claim_text":"C","status":"contradicted","gap_note":"存在反证"}'
                    ']}'
                ]
            }
        }

        counts = _ensure_validation_notes_from_claim_checks(runtime_files, topic_label="示例专题")

        self.assertEqual(counts["checked_count"], 3)
        self.assertEqual(counts["unsupported_count"], 1)
        self.assertEqual(counts["contradicted_count"], 1)
        notes = "\n".join(runtime_files["/workspace/state/validation_notes.md"]["content"])
        self.assertIn("unsupported：1 条", notes)
        self.assertIn("contradicted：1 条", notes)

    def test_tool_policy_snapshot_keeps_only_serializable_fields(self):
        class FakeStructuredTool:
            name = "claim_verifier_tool"

        snapshot = snapshot_tool_policy(
            {
                "allowed_tools": [FakeStructuredTool()],
                "required_tools": ["claim_verifier_tool"],
                "max_exploration_turns": 2,
                "parallel_tool_calls": False,
                "exploration_mode": "deep",
                "scope_id": "policy_dynamics::summary",
            }
        )

        self.assertEqual(snapshot["allowed_tools"], ["claim_verifier_tool"])
        self.assertEqual(snapshot["required_tools"], ["claim_verifier_tool"])
        self.assertEqual(snapshot["max_exploration_turns"], 2)
        self.assertEqual(snapshot["exploration_mode"], "deep")

    def test_runtime_payload_sanitizer_converts_tool_objects_to_json_safe_values(self):
        class FakeStructuredTool:
            name = "claim_verifier_tool"

        payload = {
            "policy": {
                "allowed_tools": [FakeStructuredTool()],
                "required_tools": ["claim_verifier_tool"],
            },
            "trace": {
                "tool_calls": [{"name": "claim_verifier_tool", "args": {"claim": "示例"}}],
            },
        }

        sanitized = _json_safe_runtime_value(payload)

        self.assertEqual(sanitized["policy"]["allowed_tools"], ["claim_verifier_tool"])
        self.assertEqual(
            sanitized["trace"]["tool_calls"][0]["name"],
            "claim_verifier_tool",
        )
        self.assertIsInstance(sanitized, dict)

    def test_public_markdown_sanitizer_hides_internal_unverified_sections(self):
        raw = (
            "# 标题\n\n"
            "## 待核验提醒\n"
            "- 8月峰值原因待核验\n\n"
            "## 深层动因\n"
            "相关传播动因仍待核验\n"
        )
        cleaned = sanitize_public_markdown(raw)
        self.assertNotIn("待核验提醒", cleaned)
        self.assertNotIn("待核验", cleaned)
        self.assertIn("深层动因", cleaned)
        self.assertIn("暂不作确定判断", cleaned)

    def test_full_report_route_uses_markdown_service(self):
        app = Flask(__name__)
        app.register_blueprint(report_bp, url_prefix="/api/report")
        client = app.test_client()

        with patch("src.report.api._resolve_topic", return_value=("demo-topic", "示例专题")), patch(
            "src.report.api.generate_full_report_payload",
            return_value={"title": "示例专题", "markdown": "# 示例专题", "meta": {"report_mode": "markdown_full_report"}},
        ) as full_mock:
            response = client.get("/api/report/full?topic=demo&start=2025-01-01")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["data"]["markdown"], "# 示例专题")
        self.assertEqual(payload["data"]["meta"]["report_mode"], "markdown_full_report")
        full_mock.assert_called_once()

    def test_worker_generates_markdown_full_report_after_structured_payload(self):
        sample_task = {
            "id": "rp-demo",
            "topic_identifier": "demo-topic",
            "topic": "示例专题",
            "start": "2025-01-01",
            "end": "2025-01-31",
            "thread_id": "report::demo-topic::2025-01-01::2025-01-31",
            "request": {
                "topic_identifier": "demo-topic",
                "topic": "示例专题",
                "start": "2025-01-01",
                "end": "2025-01-31",
                "mode": "fast",
                "aliases": [],
            },
        }
        structured_payload = {
            "task": {"topic_label": "示例专题"},
            "title": "示例专题正式报告",
            "subtitle": "副标题",
            "rangeText": "2025-01-01 → 2025-01-31",
        }
        full_payload = {
            "title": "示例专题正式报告",
            "markdown": "# 示例专题正式报告",
            "meta": {"report_mode": "markdown_full_report"},
        }

        with ExitStack() as stack:
            stack.enter_context(patch("src.report.worker.get_task", return_value=sample_task))
            stack.enter_context(
                patch(
                    "src.report.worker.ensure_analyze_results",
                    return_value={"prepared": True, "analyze_root": "ok", "message": "分析就绪"},
                )
            )
            stack.enter_context(
                patch(
                    "src.report.worker.ensure_explain_results",
                    return_value={"ready": True, "message": "解读就绪"},
                )
            )
            stack.enter_context(
                patch(
                    "src.report.worker.run_or_resume_deep_report_task",
                    return_value={"status": "completed", "structured_payload": structured_payload, "full_payload": full_payload},
                )
            )
            stack.enter_context(
                patch(
                    "src.report.worker._structured_digest_from_payload",
                    return_value={},
                )
            )
            stack.enter_context(
                patch(
                    "src.report.worker._trust_from_payload",
                    return_value={},
                )
            )
            stack.enter_context(
                patch(
                    "src.report.worker._raise_if_cancelled",
                    return_value=None,
                )
            )
            stack.enter_context(
                patch(
                    "src.report.worker._maybe_update_fallback_todos",
                    return_value=None,
                )
            )
            stack.enter_context(
                patch(
                    "src.report.worker._has_rejected_approval",
                    return_value=False,
                )
            )
            stack.enter_context(
                patch(
                    "src.report.worker._build_resume_payload_from_task",
                    return_value=None,
                )
            )
            stack.enter_context(
                patch(
                    "src.report.worker.threading.Thread",
                    return_value=DummyThread(),
                )
            )
            stack.enter_context(patch("src.report.worker.set_worker_pid"))
            stack.enter_context(patch("src.report.worker.mark_agent_started"))
            stack.enter_context(patch("src.report.worker.mark_task_progress"))
            stack.enter_context(patch("src.report.worker.append_agent_memo"))
            stack.enter_context(patch("src.report.worker.set_structured_result_digest"))
            stack.enter_context(patch("src.report.worker.update_task_trust"))
            stack.enter_context(patch("src.report.worker.mark_artifact_ready"))
            completed_mock = stack.enter_context(patch("src.report.worker.mark_task_completed"))
            stack.enter_context(
                patch(
                    "src.report.worker.build_artifacts_root",
                    return_value=Path("f:/opinion-system/backend/data/_report/runtime"),
                )
            )
            _run_task("rp-demo")

        completed_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
