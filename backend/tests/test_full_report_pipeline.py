from __future__ import annotations

from contextlib import ExitStack
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask
from langchain.agents.middleware import ToolCallLimitMiddleware, ToolRetryMiddleware
from langchain.agents.middleware.types import ModelRequest
from langchain_core.messages import AIMessage, ToolMessage as LCToolMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.report.api import report_bp
from src.report.agent_runtime import _build_runtime_middleware, _json_safe_runtime_value, run_report_agent_step, snapshot_tool_policy
from src.report.deepagents_backends import _build_artifacts_backend, build_report_backend
from src.report.deep_report.compiler import sanitize_public_markdown
from src.report.deep_report import exploration_deterministic_graph as exploration_graph
from src.report.deep_report import service
from src.report.deep_report.service import (
    _collect_section_drafts_from_files,
    _extract_structured_response,
    _build_tool_intelligence_receipt,
    _ensure_validation_notes_from_claim_checks,
    _normalize_structured_report_payload,
    _repair_payload_from_validation_error,
    _normalized_task_contract_violation,
    _ready_for_deterministic_finalize,
    _result_diagnostic_summary,
    _run_deep_report_exploration_task,
    _synthesize_structured_report_from_files,
)
from src.report.deep_report.builder import ReportCoordinatorContext, build_report_deep_agent
from src.report.deep_report.deterministic import build_runtime_workspace_layout
from src.report.deep_report.exploration_deterministic_graph import run_exploration_deterministic_graph
from src.report.deep_report.orchestrator_graph import run_report_orchestrator_graph
from src.report.deep_report.schemas import StructuredReport
from src.report.worker import _run_task


class DummyThread:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def start(self) -> None:
        return None

    def join(self, timeout: float | None = None) -> None:
        return None


class DummyInterrupt:
    def __init__(self, value, interrupt_id: str = "interrupt-1"):
        self.value = value
        self.id = interrupt_id


class DummyGraphOutput:
    def __init__(self, value, interrupts=()):
        self.value = value
        self.interrupts = interrupts


class DummyAgent:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def invoke(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.result


class FullReportPipelineTests(unittest.TestCase):
    @staticmethod
    def _policy_model_middleware(policy):
        middleware = _build_runtime_middleware(policy=policy)
        return next(item for item in middleware if item.__class__.__name__ == "ReportRuntimePolicyMiddleware")

    @staticmethod
    def _policy_tool_middleware(policy):
        middleware = _build_runtime_middleware(policy=policy)
        return next(
            item
            for item in middleware
            if "wrap_tool_call" in item.__class__.__dict__ and item.__class__.__name__ != "ToolRetryMiddleware"
        )

    def test_result_helpers_support_graph_output_v2_shape(self):
        result = DummyGraphOutput(
            value={
                "structured_response": {"task": {"topic_label": "示例专题"}},
                "messages": [],
            },
            interrupts=(DummyInterrupt({"action_requests": []}),),
        )

        structured = _extract_structured_response(result)
        diagnostic = _result_diagnostic_summary(result)

        self.assertEqual(structured["task"]["topic_label"], "示例专题")
        self.assertEqual(diagnostic["interrupt_count"], 1)
        self.assertTrue(diagnostic["has_structured_response"])

    def test_build_report_deep_agent_passes_flat_middleware_list(self):
        middleware_sentinel = object()

        with patch("src.report.deep_report.builder.select_report_tools", return_value=[]), patch(
            "src.report.deep_report.builder.build_coordinator_skills",
            return_value=[],
        ), patch(
            "src.report.deep_report.builder._build_subagent_specs",
            return_value=[],
        ), patch(
            "src.report.deep_report.builder.get_shared_report_checkpointer",
            return_value=("checkpointer", {"profile": "ok"}),
        ), patch(
            "src.report.deep_report.builder.create_deep_agent",
            return_value="agent",
        ) as create_mock:
            bundle = build_report_deep_agent(
                llm=object(),
                topic_identifier="demo-topic",
                topic_label="示例专题",
                start_text="2025-01-01",
                end_text="2025-01-31",
                mode="fast",
                thread_id="thread-1",
                task_id="task-1",
                skill_assets={},
                memory_paths=[],
                runtime_backend=object(),
                extra_coordinator_tools=[],
                middleware_factory=lambda _name: [middleware_sentinel],
            )

        self.assertEqual(bundle["agent"], "agent")
        self.assertEqual(create_mock.call_args.kwargs["middleware"], [middleware_sentinel])
        self.assertIs(create_mock.call_args.kwargs["context_schema"], ReportCoordinatorContext)

    def test_build_report_deep_agent_prompt_uses_registry_tier_lines(self):
        with patch("src.report.deep_report.builder.select_report_tools", return_value=[]), patch(
            "src.report.deep_report.builder.build_coordinator_skills",
            return_value=[],
        ), patch(
            "src.report.deep_report.builder._build_subagent_specs",
            return_value=[],
        ), patch(
            "src.report.deep_report.builder.get_shared_report_checkpointer",
            return_value=("checkpointer", SimpleNamespace(checkpoint_locator="ok")),
        ), patch(
            "src.report.deep_report.builder.create_deep_agent",
            return_value="agent",
        ), patch(
            "src.report.deep_report.builder.build_tier_prompt_lines",
            return_value=["   Tier 0: retrieval_router", "   Tier 1: alpha、beta（并行）"],
        ):
            bundle = build_report_deep_agent(
                llm=object(),
                topic_identifier="demo-topic",
                topic_label="示例专题",
                start_text="2025-01-01",
                end_text="2025-01-31",
                mode="fast",
                thread_id="thread-1",
                task_id="task-1",
                skill_assets={},
                memory_paths=[],
                runtime_backend=object(),
                extra_coordinator_tools=[],
                middleware_factory=lambda _name: [],
            )

        self.assertIn("Tier 1: alpha、beta（并行）", bundle["prompt"])

    def test_run_report_agent_step_supports_graph_output_v2_shape(self):
        agent = DummyAgent(
            DummyGraphOutput(
                {
                    "messages": [
                        AIMessage(content="工具调用前置说明", tool_calls=[{"name": "demo_tool", "args": {}, "id": "call-1"}]),
                        AIMessage(content="最终回答"),
                    ]
                }
            )
        )

        result = run_report_agent_step(
            {
                "agent": agent,
                "thread_id": "thread-1",
                "runtime": "deepagents",
                "context": {},
                "policy": {"required_tools": [], "max_exploration_turns": 2},
                "runtime_diagnostics": {},
            },
            {"prompt": "请执行"},
        )

        self.assertEqual(result["content"], "最终回答")
        self.assertEqual(result["trace"]["runtime"], "deepagents")
        self.assertEqual(agent.calls[0][1]["version"], "v2")

    def test_build_report_backend_uses_direct_instances(self):
        from deepagents.backends import CompositeBackend, StateBackend, StoreBackend

        runtime_backend = build_report_backend(
            artifacts_root=Path("F:/opinion-system/backend/data/_report/runtime/test-artifacts"),
            memory_namespace=lambda _ctx: ("report", "demo"),
        )

        self.assertIsInstance(runtime_backend, CompositeBackend)
        self.assertIsInstance(runtime_backend.default, StateBackend)
        self.assertIsInstance(runtime_backend.routes["/memories/"], StoreBackend)
        self.assertEqual(runtime_backend.routes["/artifacts/"].__class__.__name__, "FilesystemBackend")

    def test_artifacts_backend_uses_virtual_mode_guardrails(self):
        backend = _build_artifacts_backend(Path("F:/opinion-system/backend/data/_report/runtime/test-artifacts"))

        self.assertTrue(backend.virtual_mode)

    def test_parallel_tool_calls_avoid_end_exit_behavior_in_tool_limit_middleware(self):
        middleware = _build_runtime_middleware(
            policy={
                "required_tools": ["claim_verifier_tool"],
                "max_exploration_turns": 3,
                "parallel_tool_calls": True,
            }
        )

        tool_limit = next(item for item in middleware if isinstance(item, ToolCallLimitMiddleware))
        self.assertEqual(tool_limit.exit_behavior, "continue")

    def test_serial_tool_calls_keep_end_exit_behavior_in_tool_limit_middleware(self):
        middleware = _build_runtime_middleware(
            policy={
                "required_tools": [],
                "max_exploration_turns": 2,
                "parallel_tool_calls": False,
            }
        )

        tool_limit = next(item for item in middleware if isinstance(item, ToolCallLimitMiddleware))
        self.assertEqual(tool_limit.exit_behavior, "end")

    def test_tool_retry_middleware_uses_non_deprecated_continue_mode(self):
        middleware = _build_runtime_middleware(
            policy={
                "required_tools": [],
                "max_exploration_turns": 2,
                "parallel_tool_calls": False,
            }
        )

        retry_middleware = next(item for item in middleware if isinstance(item, ToolRetryMiddleware))
        self.assertEqual(retry_middleware.on_failure, "continue")

    def test_required_any_policy_enforces_required_tool_subset_before_first_hit(self):
        class FakeTool:
            def __init__(self, name: str):
                self.name = name

        middleware = self._policy_model_middleware(
            {
                "required_tools": ["claim_verifier_tool"],
                "tool_choice_policy": "required_any",
                "max_exploration_turns": 2,
                "parallel_tool_calls": False,
            }
        )
        request = ModelRequest(
            model=SimpleNamespace(),
            messages=[AIMessage(content="请开始")],
            tools=[FakeTool("claim_verifier_tool"), FakeTool("retrieve_evidence_cards")],
            state={"messages": [AIMessage(content="请开始")]},
            runtime=SimpleNamespace(),
        )
        captured = {}

        def handler(req):
            captured["request"] = req
            return AIMessage(content="继续")

        middleware.wrap_model_call(request, handler)

        enforced_request = captured["request"]
        self.assertEqual([tool.name for tool in enforced_request.tools], ["claim_verifier_tool"])
        self.assertEqual(enforced_request.tool_choice, "any")

    def test_required_any_policy_releases_tool_subset_after_required_tool_hit(self):
        class FakeTool:
            def __init__(self, name: str):
                self.name = name

        middleware = self._policy_model_middleware(
            {
                "required_tools": ["claim_verifier_tool"],
                "tool_choice_policy": "required_any",
                "max_exploration_turns": 2,
                "parallel_tool_calls": False,
            }
        )
        request = ModelRequest(
            model=SimpleNamespace(),
            messages=[AIMessage(content="继续")],
            tools=[FakeTool("claim_verifier_tool"), FakeTool("retrieve_evidence_cards")],
            state={
                "messages": [
                    AIMessage(content="", tool_calls=[{"name": "claim_verifier_tool", "id": "call-1", "args": {}}]),
                    LCToolMessage(content="ok", tool_call_id="call-1", name="claim_verifier_tool"),
                ]
            },
            runtime=SimpleNamespace(),
        )
        captured = {}

        def handler(req):
            captured["request"] = req
            return AIMessage(content="继续")

        middleware.wrap_model_call(request, handler)

        released_request = captured["request"]
        self.assertEqual([tool.name for tool in released_request.tools], ["claim_verifier_tool", "retrieve_evidence_cards"])
        self.assertIsNone(released_request.tool_choice)

    def test_auto_tool_choice_policy_keeps_required_tools_as_diagnostic_only(self):
        class FakeTool:
            def __init__(self, name: str):
                self.name = name

        middleware = self._policy_model_middleware(
            {
                "required_tools": ["claim_verifier_tool"],
                "tool_choice_policy": "auto",
                "max_exploration_turns": 2,
                "parallel_tool_calls": False,
            }
        )
        request = ModelRequest(
            model=SimpleNamespace(),
            messages=[AIMessage(content="请开始")],
            tools=[FakeTool("claim_verifier_tool"), FakeTool("retrieve_evidence_cards")],
            state={"messages": [AIMessage(content="请开始")]},
            runtime=SimpleNamespace(),
        )
        captured = {}

        def handler(req):
            captured["request"] = req
            return AIMessage(content="继续")

        middleware.wrap_model_call(request, handler)

        passthrough_request = captured["request"]
        self.assertEqual([tool.name for tool in passthrough_request.tools], ["claim_verifier_tool", "retrieve_evidence_cards"])
        self.assertIsNone(passthrough_request.tool_choice)

    def test_unlisted_deepagents_builtin_tool_is_blocked_in_report_runtime(self):
        middleware = self._policy_tool_middleware(
            {
                "allowed_tools": [],
                "required_tools": [],
                "tool_choice_policy": "auto",
                "max_exploration_turns": 2,
                "parallel_tool_calls": False,
            }
        )

        result = middleware.wrap_tool_call(
            SimpleNamespace(tool_call={"name": "task", "id": "call-1", "args": {}}, tool=None),
            lambda _req: LCToolMessage(content="should-not-run", tool_call_id="call-1", name="task"),
        )

        self.assertIsInstance(result, LCToolMessage)
        self.assertEqual(result.status, "error")
        self.assertIn("not allowed", str(result.content))

    def test_read_only_deepagents_builtin_tool_remains_allowed_in_report_runtime(self):
        middleware = self._policy_tool_middleware(
            {
                "allowed_tools": [],
                "required_tools": [],
                "tool_choice_policy": "auto",
                "max_exploration_turns": 2,
                "parallel_tool_calls": False,
            }
        )
        marker = object()

        result = middleware.wrap_tool_call(
            SimpleNamespace(tool_call={"name": "read_file", "id": "call-2", "args": {"file_path": "/tmp/a.txt"}}, tool=None),
            lambda _req: marker,
        )

        self.assertIs(result, marker)

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
        layout = build_runtime_workspace_layout(
            project_identifier="demo-project",
            topic_identifier="demo-topic",
            start="2025-01-01",
            end="2025-01-31",
        )
        runtime_files = {
            layout.state_file("structured_report.json"): {"content": ["{}"]},
        }

        self.assertTrue(_ready_for_deterministic_finalize(runtime_files))

        runtime_files[layout.state_file("structured_report.json")] = {"content": ["   "]}
        self.assertFalse(_ready_for_deterministic_finalize(runtime_files))

    def test_validation_notes_are_derived_from_claim_checks(self):
        layout = build_runtime_workspace_layout(
            project_identifier="demo-project",
            topic_identifier="demo-topic",
            start="2025-01-01",
            end="2025-01-31",
        )
        runtime_files = {
            layout.state_file("claim_checks.json"): {
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
        raw_notes = runtime_files[layout.state_file("validation_notes.md")]["content"]
        notes = raw_notes if isinstance(raw_notes, str) else "\n".join(raw_notes)
        self.assertIn("unsupported：1 条", notes)
        self.assertIn("contradicted：1 条", notes)

    def test_normalize_structured_report_payload_preserves_optional_maps_and_timeline_wrappers(self):
        normalized = _normalize_structured_report_payload(
            {
                "task": {
                    "topic_identifier": "demo-topic",
                    "topic_label": "示例专题",
                    "start": "2025-01-01",
                    "end": "2025-01-31",
                    "mode": "fast",
                    "thread_id": "report::demo-topic::2025-01-01::2025-01-31",
                },
                "summary": "自动补写摘要",
                "timeline": {
                    "nodes": [
                        {
                            "event_id": "event-1",
                            "date": "2025-01-15",
                            "title": "关键节点",
                            "description": "讨论升温。",
                        }
                    ]
                },
                "agenda_frame_map": {"summary": "议题框架已生成"},
                "conflict_map": {"summary": "冲突图已生成"},
                "mechanism_summary": {"summary": "传播机制已生成"},
                "utility_assessment": {"decision": "usable"},
                "metric_bundle": {"volume": {"series": []}},
            }
        )

        self.assertEqual(normalized["conclusion"]["executive_summary"], "自动补写摘要")
        self.assertEqual(len(normalized["timeline"]), 1)
        self.assertEqual(normalized["timeline"][0]["event_id"], "event-1")
        self.assertEqual(normalized["agenda_frame_map"]["summary"], "议题框架已生成")
        self.assertEqual(normalized["conflict_map"]["summary"], "冲突图已生成")
        self.assertEqual(normalized["mechanism_summary"]["summary"], "传播机制已生成")
        self.assertEqual(normalized["utility_assessment"]["decision"], "usable")
        self.assertEqual(normalized["metric_bundle"]["volume"]["series"], [])

    def test_structured_report_validation_backfills_missing_utility_improvement_step_ids(self):
        normalized = _normalize_structured_report_payload(
            {
                "task": {
                    "topic_identifier": "demo-topic",
                    "topic_label": "示例专题",
                    "start": "2025-01-01",
                    "end": "2025-01-31",
                    "mode": "fast",
                    "thread_id": "report::demo-topic::2025-01-01::2025-01-31",
                },
                "summary": "自动补写摘要",
                "utility_assessment": {
                    "decision": "pass",
                    "improvement_trace": [
                        {
                            "triggered_by": "insufficient_structure",
                            "recompiled_pass": "risk_micro_pass",
                            "before_score": 0.3,
                            "after_score": 0.6,
                        }
                    ],
                },
            }
        )

        structured = StructuredReport.model_validate(normalized)

        self.assertEqual(len(structured.utility_assessment.improvement_trace), 1)
        self.assertEqual(
            structured.utility_assessment.improvement_trace[0].step_id,
            "improve-1-insufficient_structure-risk_micro_pass",
        )

    def test_validation_repair_replaces_invalid_optional_block_with_synthesized_version(self):
        fallback_payload = _normalize_structured_report_payload(
            {
                "task": {
                    "topic_identifier": "demo-topic",
                    "topic_label": "示例专题",
                    "start": "2025-01-01",
                    "end": "2025-01-31",
                    "mode": "fast",
                    "thread_id": "report::demo-topic::2025-01-01::2025-01-31",
                },
                "summary": "自动补写摘要",
                "utility_assessment": {"decision": "pass", "improvement_trace": []},
            }
        )
        invalid_payload = _normalize_structured_report_payload(
            {
                **fallback_payload,
                "utility_assessment": {"decision": "usable", "improvement_trace": []},
            }
        )

        try:
            StructuredReport.model_validate(invalid_payload)
        except Exception as exc:
            repaired, repaired_keys = _repair_payload_from_validation_error(invalid_payload, fallback_payload, exc)
        else:
            self.fail("expected validation to fail for invalid utility_assessment.decision")

        structured = StructuredReport.model_validate(repaired)

        self.assertEqual(repaired_keys, ["utility_assessment"])
        self.assertEqual(structured.utility_assessment.decision, "pass")

    def test_orchestrator_continues_to_compile_when_exploration_returns_structured_payload(self):
        with patch(
            "src.report.deep_report.orchestrator_graph.get_shared_report_checkpointer",
            return_value=(None, SimpleNamespace(checkpoint_locator="root.sqlite")),
        ):
            result = run_report_orchestrator_graph(
                request={"task_id": "task-123", "thread_id": "report::demo-topic::2025-01-01::2025-01-31"},
                root_thread_id="task-123:root",
                invoke_deep_agent=lambda _request: {
                    "status": "failed",
                    "message": "结构化结果已降级补齐，后续将继续进入编译阶段。",
                    "structured_payload": {"task": {"topic_identifier": "demo-topic"}, "report_ir": {}},
                    "exploration_bundle": {},
                    "full_payload": {},
                    "approvals": [],
                },
                run_compile=lambda structured_payload, exploration_bundle: {
                    "status": "completed",
                    "message": "compiled",
                    "markdown": "# report",
                    "structured_payload": structured_payload,
                    "exploration_bundle": exploration_bundle,
                },
            )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["message"], "compiled")
        self.assertEqual(result["full_payload"]["markdown"], "# report")

    def test_exploration_deterministic_graph_initial_state_excludes_runtime_callables(self):
        captured_initial_state = {}

        class FakeCompiledGraph:
            def stream(self, initial_state, **kwargs):
                captured_initial_state.update(initial_state)
                yield {
                    "type": "updates",
                    "data": {
                        "finalize_node": {
                            "status": "completed",
                            "message": "ok",
                            "files": {},
                            "gaps": [],
                            "structured_payload": {},
                        }
                    },
                }

        class FakeBuilder:
            def compile(self, checkpointer=None):
                return FakeCompiledGraph()

        with patch(
            "src.report.deep_report.exploration_deterministic_graph.build_exploration_deterministic_graph",
            return_value=FakeBuilder(),
        ), patch(
            "src.report.deep_report.exploration_deterministic_graph.get_shared_report_checkpointer",
            return_value=(None, SimpleNamespace(checkpoint_locator="explore.sqlite")),
        ):
            result = run_exploration_deterministic_graph(
                request={
                    "task_id": "task-123",
                    "thread_id": "task-123:explore",
                    "topic_identifier": "demo-topic",
                    "topic_label": "示例专题",
                    "start": "2025-01-01",
                    "end": "2025-01-31",
                    "mode": "fast",
                },
                skill_assets={"skill": "asset"},
                middleware_factory=lambda _agent: [],
                event_callback=lambda _event: None,
                llm=object(),
                initial_files={
                    build_runtime_workspace_layout(
                        project_identifier="demo-project",
                        topic_identifier="demo-topic",
                        start="2025-01-01",
                        end="2025-01-31",
                    ).base_context_path: {"content": ["{}"]}
                },
            )

        self.assertEqual(result["status"], "completed")
        self.assertIn("files", captured_initial_state)
        self.assertNotIn("skill_assets", captured_initial_state)
        self.assertNotIn("middleware_factory", captured_initial_state)
        self.assertNotIn("event_callback", captured_initial_state)
        self.assertNotIn("llm", captured_initial_state)

    def test_exploration_route_after_utility_accepts_nested_result_decision(self):
        layout = build_runtime_workspace_layout(
            project_identifier="demo-project",
            topic_identifier="demo-topic",
            start="2025-01-01",
            end="2025-01-31",
        )
        route = exploration_graph.route_after_utility(
            {
                "project_identifier": "demo-project",
                "topic_identifier": "demo-topic",
                "start": "2025-01-01",
                "end": "2025-01-31",
                "files": {
                    layout.state_file("utility_assessment.json"): {
                        "content": [json.dumps({"result": {"decision": "pass"}}, ensure_ascii=False)]
                    }
                }
            }
        )

        self.assertEqual(route, "writer_node")

    def test_exploration_parallel_dispatch_does_not_write_nonreduced_state(self):
        sends = exploration_graph.dispatch_tier1({})

        self.assertEqual(len(sends), 2)
        self.assertTrue(all(getattr(item, "arg", None) == {} for item in sends))

    def test_exploration_gather_tier_omits_status_and_emits_tier_todo(self):
        captured_events = []
        runtime_deps = exploration_graph._ExplorationRuntimeDeps(
            skill_assets={},
            middleware_factory=lambda _agent: [],
            event_callback=lambda event: captured_events.append(event),
            llm=None,
            runtime_backend=None,
            common_context={},
            subagent_specs={},
        )
        gather = exploration_graph._make_gather_node(
            runtime_deps,
            tier=1,
            phase="interpret",
            agent_names=["archive_evidence_organizer", "bertopic_evolution_analyst"],
        )

        with patch(
            "src.report.deep_report.exploration_deterministic_graph._collect_tier_gaps",
            return_value=([], []),
        ):
            result = gather(
                {
                    "agent_statuses": {
                        "archive_evidence_organizer": "completed",
                        "bertopic_evolution_analyst": "completed",
                    },
                    "tier_results": {},
                }
            )

        self.assertNotIn("status", result)
        self.assertEqual(result["tier_results"]["tier_1"]["status"], "completed")
        todo_event = next(event for event in captured_events if event.get("type") == "todo.updated")
        todos = todo_event.get("payload", {}).get("todos") or []
        self.assertEqual(todos[1]["id"], "tier-1")
        self.assertEqual(todos[1]["status"], "completed")

    def test_exploration_node_skip_by_reuse_emits_event_and_status(self):
        layout = build_runtime_workspace_layout(
            project_identifier="demo-project",
            topic_identifier="demo-topic",
            start="2025-01-01",
            end="2025-01-31",
        )
        captured_events = []
        runtime_deps = exploration_graph._ExplorationRuntimeDeps(
            skill_assets={},
            middleware_factory=lambda _agent: [],
            event_callback=lambda event: captured_events.append(event),
            llm=None,
            runtime_backend=None,
            common_context={
                "project_identifier": "demo-project",
                "topic_identifier": "demo-topic",
                "start": "2025-01-01",
                "end": "2025-01-31",
            },
            subagent_specs={},
        )

        result = exploration_graph._run_subagent_node(
            {
                "files": {
                    layout.state_file("evidence_cards.json"): {
                        "content": [json.dumps({"status": "ready", "result": [{"id": "e1"}]}, ensure_ascii=False)]
                    }
                },
                "project_identifier": "demo-project",
                "topic_identifier": "demo-topic",
                "start": "2025-01-01",
                "end": "2025-01-31",
                "execution_plan": {
                    "nodes": {
                        "archive_evidence_organizer": {
                            "skip": True,
                            "artifact_keys": ["evidence_cards"],
                            "source_report_ranges": ["2024-12-01_2024-12-31"],
                        }
                    }
                },
            },
            runtime_deps,
            agent_name="archive_evidence_organizer",
            tier=1,
            phase="interpret",
        )

        self.assertEqual(result["agent_statuses"]["archive_evidence_organizer"], "skipped")
        self.assertEqual(result["agent_results"]["archive_evidence_organizer"]["reason"], "reused_from_history")
        skip_event = next(event for event in captured_events if event.get("type") == "graph.node.skipped")
        self.assertEqual(skip_event["payload"]["artifact_keys"], ["evidence_cards"])

    def test_exploration_finalize_generates_non_empty_structured_payload_from_fallback(self):
        layout = build_runtime_workspace_layout(
            project_identifier="demo-project",
            topic_identifier="demo-topic",
            start="2025-01-01",
            end="2025-01-31",
        )
        runtime_deps = exploration_graph._ExplorationRuntimeDeps(
            skill_assets={},
            middleware_factory=lambda _agent: [],
            event_callback=None,
            llm=None,
            runtime_backend=None,
            common_context={"project_identifier": "demo-project", "topic_identifier": "demo-topic", "start": "2025-01-01", "end": "2025-01-31"},
            subagent_specs={},
        )

        with patch(
            "src.report.deep_report.service._synthesize_structured_report_from_files",
            return_value={
                "task": {
                    "topic_identifier": "demo-topic",
                    "topic_label": "示例专题",
                    "start": "2025-01-01",
                    "end": "2025-01-31",
                    "mode": "fast",
                    "thread_id": "task-123:explore",
                },
                "summary": "fallback summary",
            },
        ):
            result = exploration_graph.finalize_node(
                {
                    "files": {},
                    "topic_identifier": "demo-topic",
                    "project_identifier": "demo-project",
                    "topic_label": "示例专题",
                    "start": "2025-01-01",
                    "end": "2025-01-31",
                    "mode": "fast",
                    "thread_id": "task-123:explore",
                    "gaps": [{"agent": "writer", "file": "missing", "reason": "missing", "tier": 6}],
                    "agent_statuses": {"writer": "failed"},
                },
                runtime_deps,
            )

        self.assertEqual(result["status"], "partial")
        self.assertTrue(result["structured_payload"])
        self.assertEqual(result["structured_payload"]["conclusion"]["executive_summary"], "fallback summary")
        self.assertIn(layout.state_file("structured_report.json"), result["files"])

    def test_synthesize_structured_report_from_files_ignores_section_drafts_as_top_level_source(self):
        layout = build_runtime_workspace_layout(
            project_identifier="demo-project",
            topic_identifier="demo-topic",
            start="2025-01-01",
            end="2025-01-31",
        )

        files = {
            layout.state_file("section_drafts/overview.json"): {
                "content": [json.dumps({"section_id": "overview", "title": "概览", "content": "章节内容"}, ensure_ascii=False)]
            },
            layout.base_context_path: {
                "content": [json.dumps({"project_identifier": "demo-project"}, ensure_ascii=False)]
            },
        }

        with patch("src.report.deep_report.service.call_langchain_chat") as mocked_chat:
            result = _synthesize_structured_report_from_files(
                files=files,
                topic_identifier="demo-topic",
                topic_label="示例专题",
                start_text="2025-01-01",
                end_text="2025-01-31",
                mode="fast",
                thread_id="task-123",
            )

        mocked_chat.assert_not_called()
        self.assertEqual(result["task"]["topic_identifier"], "demo-topic")
        self.assertFalse((result.get("metadata") or {}).get("section_drafts"))

    def test_exploration_runtime_uses_task_scoped_coordinator_thread_and_fallback_normalizes_payload(self):
        layout = build_runtime_workspace_layout(
            project_identifier="demo-project",
            topic_identifier="demo-topic",
            start="2025-01-01",
            end="2025-01-31",
        )
        agent = DummyAgent({"messages": [], "files": {layout.state_file("timeline_nodes.json"): {"content": ["{}"]}}})

        cache_dir = Path("F:/opinion-system/.tmp_pytest/exploration-runtime")
        artifacts_dir = cache_dir / "artifacts"
        with patch("src.report.deep_report.service.ensure_cache_dir_v2", return_value=cache_dir), patch(
            "src.report.deep_report.service.build_artifacts_root",
            return_value=artifacts_dir,
        ), patch(
            "src.report.deep_report.service._prepare_runtime",
                return_value=(
                {"thread_id": "report::demo-topic::2025-01-01::2025-01-31", "task_id": "task-123"},
                {layout.state_file(".keep"): {"content": [""]}},
                object(),
                {},
                [],
            ),
        ), patch(
            "src.report.deep_report.service.build_langchain_chat_model",
            return_value=(object(), {}),
        ), patch(
            "src.report.deep_report.service.build_report_deep_agent",
            return_value={
                "agent": agent,
                "coordinator_runtime_profile": SimpleNamespace(checkpoint_locator="coordinator.sqlite"),
                "prompt": "prompt",
            },
        ), patch(
            "src.report.deep_report.service._hydrate_render_layers",
            side_effect=lambda payload, **_: payload,
        ), patch(
            "src.report.deep_report.service._attach_ir_layers",
            side_effect=lambda payload, **_: payload,
        ), patch(
            "src.report.deep_report.service._synthesize_structured_report_from_files",
            return_value={
                "task": {"topic_identifier": "demo-topic"},
                "summary": "fallback summary",
                "timeline": {
                    "nodes": [
                        {
                            "event_id": "event-1",
                            "date": "2025-01-15",
                            "title": "关键节点",
                            "description": "讨论升温。",
                        }
                    ]
                },
                "agenda_frame_map": {"summary": "议题框架已生成"},
            },
        ):
            result = _run_deep_report_exploration_task(
                "demo-topic",
                "2025-01-01",
                "2025-01-31",
                topic_label="示例专题",
                mode="fast",
                thread_id="report::demo-topic::2025-01-01::2025-01-31",
                task_id="task-123",
            )

        self.assertEqual(result.status, "completed")
        self.assertEqual(
            agent.calls[0][1]["config"]["configurable"]["thread_id"],
            "task-123:coordinator",
        )

    def test_run_or_resume_deep_report_task_attaches_ir_before_compile_when_missing(self):
        captured_structured = {}

        def _fake_orchestrator_graph(**kwargs):
            run_compile = kwargs["run_compile"]
            output = run_compile({"task": {"topic_identifier": "demo-topic"}}, {"gap_summary": [], "todos": []})
            return {
                "status": "completed",
                "message": "compiled",
                "structured_payload": {},
                "full_payload": output,
                "exploration_bundle": {},
                "thread_id": "report::demo-topic::2025-01-01::2025-01-31",
            }

        def _fake_generate_full_report_payload(topic_identifier, start_text, end_text, **kwargs):
            captured_structured["payload"] = kwargs.get("structured_payload")
            return {"status": "completed", "message": "ok", "markdown": "# report", "metadata": {}}

        with patch(
            "src.report.deep_report.service.run_report_orchestrator_graph",
            side_effect=_fake_orchestrator_graph,
        ), patch(
            "src.report.deep_report.service._attach_ir_layers",
            side_effect=lambda payload, **_kwargs: {**payload, "report_ir": {"meta": {"topic_identifier": "demo-topic"}}, "metadata": {}},
        ) as attach_ir_mock, patch(
            "src.report.deep_report.service.generate_full_report_payload",
            side_effect=_fake_generate_full_report_payload,
        ):
            result = service.run_or_resume_deep_report_task(
                "demo-topic",
                "2025-01-01",
                "2025-01-31",
                topic_label="示例专题",
                task_id="task-123",
                thread_id="report::demo-topic::2025-01-01::2025-01-31",
            )

        self.assertEqual(result["status"], "completed")
        self.assertTrue(attach_ir_mock.called)
        self.assertIn("report_ir", captured_structured["payload"])

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
            "src.report.api.ensure_cache_dir_v2",
            return_value=Path("F:/opinion-system/.tmp_pytest/full-route"),
        ), patch(
            "src.report.api.Path.exists",
            return_value=True,
        ), patch(
            "src.report.api._load_report_cache_payload",
            return_value={"markdown": "# cached"},
        ), patch(
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
