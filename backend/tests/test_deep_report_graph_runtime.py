from __future__ import annotations

import sys
import tempfile
import uuid
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.report.deep_report.graph_runtime import (
    _payload_from_state,
    _stream_graph_events,
    build_repair_plan_v2,
    run_report_compilation_graph,
    validate_draft_bundle_v2,
)
from src.report.deep_report.schemas import DraftBundle, DraftBundleV2, DraftUnit, DraftUnitV2, TraceRef, ValidationResultV2


class _Dumpable(dict):
    def model_dump(self) -> dict:
        return dict(self)


class _DummyInterrupt:
    def __init__(self, value: object, interrupt_id: str = "interrupt-1") -> None:
        self.value = value
        self.id = interrupt_id


class _DummyGraphOutput:
    def __init__(self, value: object, interrupts=()) -> None:
        self.value = value
        self.interrupts = interrupts


class _DummyGraph:
    def stream(self, *_args, **_kwargs):
        yield {"type": "updates", "ns": (), "data": {"planner": {"status": "running"}}}
        yield {"type": "updates", "ns": (), "data": {"__interrupt__": (_DummyInterrupt({"question": "approve?"}),)}}


class _DummyInvokeGraph:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def invoke(self, *_args, **kwargs):
        self.calls.append(kwargs)
        return _DummyGraphOutput(
            {"status": "waiting"},
            interrupts=(_DummyInterrupt({"question": "approve?"}),),
        )


def _minimal_payload() -> dict:
    return {
        "task": {
            "topic_label": "示例专题",
            "thread_id": "report::demo-topic::2025-01-01::2025-01-31",
        },
        "report_ir": {
            "meta": {
                "topic_label": "示例专题",
                "topic_identifier": "demo-topic",
                "time_scope": {"start": "2025-01-01", "end": "2025-01-31"},
                "mode": "fast",
            },
            "placement_plan": {"entries": []},
            "claim_set": {"claims": []},
            "evidence_ledger": {"entries": []},
            "risk_register": {"risks": []},
            "recommendation_candidates": {"items": []},
        },
    }


def _invalid_draft_bundle(*_args, **_kwargs) -> DraftBundle:
    return DraftBundle(
        source_artifact_id="draft_bundle",
        policy_version="policy.v2",
        section_order=["claims"],
        units=[
            DraftUnit(
                unit_id="unit:claims:1",
                section_role="claims",
                text="- 当前判断仍需要人工边界确认。",
                trace_ids=["claims"],
                claim_ids=[],
                evidence_ids=[],
                risk_ids=[],
                unresolved_point_ids=[],
                stance_row_ids=[],
                confidence="medium",
                is_unresolved=False,
            )
        ],
        metadata={},
    )


class DeepReportGraphRuntimeTests(unittest.TestCase):
    def test_payload_from_state_recovers_minimal_payload_when_missing(self) -> None:
        state = {
            "report_ir": _minimal_payload()["report_ir"],
            "task": _minimal_payload()["task"],
        }

        payload = _payload_from_state(state)

        self.assertIn("report_ir", payload)
        self.assertIn("task", payload)
        self.assertEqual(payload["task"]["topic_label"], "示例专题")

    def test_build_repair_plan_v2_recovers_missing_derived_from_from_candidate_trace_refs(self) -> None:
        bundle = DraftBundleV2(
            units=[
                DraftUnitV2(
                    unit_id="unit:recommendations:action-001",
                    section_id="recommendations",
                    unit_type="recommendation",
                    text="[action-001] 建议动作 1",
                    trace_refs=[TraceRef(trace_id="action-001", trace_kind="recommendation", support_level="derived")],
                    derived_from=[],
                    support_level="derived",
                    render_template_id="recommendations:recommendation",
                    metadata={},
                )
            ],
            section_order=["recommendations"],
            metadata={},
        )
        validation = ValidationResultV2(
            passed=False,
            failures=[
                {
                    "failure_id": "dangling_derived_from:1",
                    "target_unit_id": "unit:recommendations:action-001",
                    "failure_type": "dangling_derived_from",
                    "message": "分析型单元必须携带 derived_from 追溯链。",
                    "candidate_trace_refs": [{"trace_id": "action-001", "trace_kind": "recommendation", "support_level": "derived"}],
                    "candidate_derived_from": [],
                    "patchable": True,
                    "patch_status": "pending",
                    "metadata": {"section_id": "recommendations", "unit_type": "recommendation", "support_level": "derived"},
                }
            ],
            patchable_failures=[],
            gate="repair",
            repair_count=0,
            next_node="repair_patch_planner",
            metadata={},
        )

        plan = build_repair_plan_v2(_minimal_payload()["report_ir"], bundle, validation)

        self.assertEqual(len(plan.patches), 1)
        self.assertEqual(plan.patches[0].replacement_unit.derived_from, ["action-001"])

    def test_build_repair_plan_v2_demotes_unrepairable_observation_placeholder(self) -> None:
        bundle = DraftBundleV2(
            units=[
                DraftUnitV2(
                    unit_id="unit:timeline:event-1",
                    section_id="timeline",
                    unit_type="observation",
                    text="[event-1] 事件 1（support=none）",
                    trace_refs=[TraceRef(trace_id="event-1", trace_kind="section_context", support_level="direct")],
                    derived_from=[],
                    support_level="direct",
                    render_template_id="timeline:observation",
                    metadata={},
                )
            ],
            section_order=["timeline"],
            metadata={},
        )
        validation = ValidationResultV2(
            passed=False,
            failures=[
                {
                    "failure_id": "unsupported_inference:1",
                    "target_unit_id": "unit:timeline:event-1",
                    "failure_type": "unsupported_inference",
                    "message": "观察句必须直连 evidence 且使用 direct support。",
                    "candidate_trace_refs": [{"trace_id": "event-1", "trace_kind": "section_context", "support_level": "direct"}],
                    "candidate_derived_from": [],
                    "patchable": True,
                    "patch_status": "pending",
                    "metadata": {"section_id": "timeline", "unit_type": "observation", "support_level": "direct"},
                }
            ],
            patchable_failures=[],
            gate="repair",
            repair_count=0,
            next_node="repair_patch_planner",
            metadata={},
        )

        plan = build_repair_plan_v2(_minimal_payload()["report_ir"], bundle, validation)

        self.assertEqual(plan.patches[0].replacement_unit.unit_type, "transition")
        self.assertEqual(plan.patches[0].replacement_unit.support_level, "structural")

    def test_validate_draft_bundle_v2_stops_repair_after_zero_effective_patches(self) -> None:
        bundle = DraftBundleV2(
            units=[
                DraftUnitV2(
                    unit_id="unit:risks:risk-1",
                    section_id="risks",
                    unit_type="risk",
                    text="[risk-1] 风险 1",
                    trace_refs=[TraceRef(trace_id="risk-1", trace_kind="risk", support_level="derived")],
                    derived_from=[],
                    support_level="derived",
                    render_template_id="risks:risk",
                    metadata={},
                )
            ],
            section_order=["risks"],
            metadata={"repair_patch_count": 0},
        )

        result = validate_draft_bundle_v2(_minimal_payload()["report_ir"], bundle, repair_count=1, max_repairs=2)

        self.assertEqual(result.gate, "human_review")
        self.assertEqual(result.next_node, "compile_blocked")

    def test_stream_graph_events_supports_v2_updates_shape(self) -> None:
        events: list[dict] = []

        state = _stream_graph_events(
            _DummyGraph(),
            {"input": "demo"},
            {"configurable": {"thread_id": "graph-v2"}},
            events.append,
        )

        self.assertEqual(state["status"], "running")
        self.assertEqual(len(state["__interrupt__"]), 1)
        self.assertEqual(events[0]["type"], "graph.node.update")
        self.assertEqual(events[0]["agent"], "planner")

    def test_stream_graph_events_without_callback_prefers_v2_invoke_shape(self) -> None:
        graph = _DummyInvokeGraph()

        state = _stream_graph_events(
            graph,
            {"input": "demo"},
            {"configurable": {"thread_id": "graph-v2"}},
            None,
        )

        self.assertEqual(state["status"], "waiting")
        self.assertEqual(len(state["__interrupt__"]), 1)
        self.assertEqual(graph.calls[0]["version"], "v2")

    def _patched_runtime(self) -> ExitStack:
        stack = ExitStack()
        dumpable = _Dumpable()
        stack.enter_context(patch("src.report.deep_report.graph_runtime.build_conformance_policy_registry", return_value=_Dumpable({"policy_version": "policy.v2"})))
        stack.enter_context(patch("src.report.deep_report.graph_runtime.select_scene_profile", return_value=dumpable))
        stack.enter_context(patch("src.report.deep_report.graph_runtime.resolve_style_profile", return_value=dumpable))
        stack.enter_context(patch("src.report.deep_report.graph_runtime.build_layout_plan", return_value=dumpable))
        stack.enter_context(patch("src.report.deep_report.graph_runtime.build_section_budget", return_value=dumpable))
        stack.enter_context(patch("src.report.deep_report.graph_runtime.assemble_writer_context", return_value=dumpable))
        stack.enter_context(
            patch(
                "src.report.deep_report.graph_runtime.build_section_plan",
                return_value=_Dumpable(
                    {
                        "sections": [
                            {
                                "section_id": "claims",
                                "goal": "形成主体判断",
                                "source_groups": ["claims"],
                            }
                        ]
                    }
                ),
            )
        )
        stack.enter_context(patch("src.report.deep_report.graph_runtime.compile_draft_units", side_effect=_invalid_draft_bundle))
        return stack

    def test_graph_interrupt_resume_with_sqlite_checkpoint_and_annotation(self) -> None:
        events: list[dict] = []
        base_dir = Path(__file__).resolve().parents[1] / "data" / "_tmp"
        base_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_path = str(base_dir / f"compile_graph_{uuid.uuid4().hex}.sqlite")
        try:
            with self._patched_runtime():
                first = run_report_compilation_graph(
                    _minimal_payload(),
                    event_callback=events.append,
                    max_repairs=1,
                    checkpointer_path=checkpoint_path,
                    graph_thread_id="graph-thread-1",
                )

                self.assertEqual(first["status"], "interrupted")
                self.assertTrue(Path(checkpoint_path).exists())
                self.assertTrue(first["interrupts"])
                preview_markdown = str(first["markdown"] or "").strip()
                self.assertEqual(first["graph_thread_id"], "graph-thread-1")
                self.assertEqual(first["checkpoint_backend"], "sqlite")
                self.assertEqual(first["checkpoint_locator"], checkpoint_path)
                self.assertEqual(
                    first["graph_state_v2"]["metadata"]["checkpoint_path"],
                    checkpoint_path,
                )

                resumed = run_report_compilation_graph(
                    _minimal_payload(),
                    event_callback=events.append,
                    max_repairs=1,
                    checkpointer_path=checkpoint_path,
                    graph_thread_id="graph-thread-1",
                    review_decision={
                        "decision": "approve",
                        "review_payload": {
                            "review_mode": "annotation",
                            "comment": "保留原文稿，只记录人工边界批注。",
                        },
                    },
                )
        finally:
            try:
                Path(checkpoint_path).unlink()
            except OSError:
                pass

        self.assertEqual(resumed["markdown"], preview_markdown)
        self.assertFalse(resumed["review_required"])
        self.assertEqual(resumed["graph_state_v2"]["metadata"]["graph_thread_id"], "graph-thread-1")
        self.assertEqual(resumed["graph_state_v2"]["metadata"]["checkpoint_path"], checkpoint_path)
        self.assertEqual(resumed["checkpoint_backend"], "sqlite")
        self.assertEqual(resumed["checkpoint_locator"], checkpoint_path)
        self.assertEqual(first["interrupts"][0]["value"]["review_mode"], "annotation")
        self.assertIn("人工审核批注", first["interrupts"][0]["value"]["review_prompt"])

    def test_graph_interrupt_resume_with_approve_uses_preview(self) -> None:
        events: list[dict] = []
        base_dir = Path(__file__).resolve().parents[1] / "data" / "_tmp"
        base_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_path = str(base_dir / f"compile_graph_{uuid.uuid4().hex}.sqlite")
        try:
            with self._patched_runtime():
                first = run_report_compilation_graph(
                    _minimal_payload(),
                    event_callback=events.append,
                    max_repairs=1,
                    checkpointer_path=checkpoint_path,
                    graph_thread_id="graph-thread-approve",
                )

                resumed = run_report_compilation_graph(
                    _minimal_payload(),
                    event_callback=events.append,
                    max_repairs=1,
                    checkpointer_path=checkpoint_path,
                    graph_thread_id="graph-thread-approve",
                    review_decision={"decision": "approve"},
                )
        finally:
            try:
                Path(checkpoint_path).unlink()
            except OSError:
                pass

        self.assertEqual(first["status"], "interrupted")
        self.assertTrue(resumed["markdown"])
        self.assertFalse(resumed["review_required"])
        self.assertEqual(resumed["graph_state_v2"]["metadata"]["graph_thread_id"], "graph-thread-approve")
        self.assertEqual(resumed["checkpoint_backend"], "sqlite")
        self.assertEqual(resumed["checkpoint_locator"], checkpoint_path)
        blocked_events = [event for event in events if str(event.get("type") or "") == "compile.blocked"]
        interrupt_events = [event for event in events if str(event.get("type") or "") == "interrupt.human_review"]
        self.assertEqual(len(blocked_events), 1)
        self.assertEqual(len(interrupt_events), 1)

    def test_graph_interrupt_resume_reject_keeps_review_required(self) -> None:
        base_dir = Path(__file__).resolve().parents[1] / "data" / "_tmp"
        base_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_path = str(base_dir / f"compile_graph_{uuid.uuid4().hex}.sqlite")
        try:
            with self._patched_runtime():
                first = run_report_compilation_graph(
                    _minimal_payload(),
                    max_repairs=1,
                    checkpointer_path=checkpoint_path,
                    graph_thread_id="graph-thread-reject",
                )

                resumed = run_report_compilation_graph(
                    _minimal_payload(),
                    max_repairs=1,
                    checkpointer_path=checkpoint_path,
                    graph_thread_id="graph-thread-reject",
                    review_decision={"decision": "reject"},
                )
        finally:
            try:
                Path(checkpoint_path).unlink()
            except OSError:
                pass

        self.assertEqual(first["status"], "interrupted")
        self.assertTrue(resumed["review_required"])
        self.assertEqual(resumed["blocked_reason"], "rejected_by_human_review")
        self.assertEqual(resumed["graph_state_v2"]["metadata"]["graph_thread_id"], "graph-thread-reject")
        self.assertEqual(resumed["checkpoint_backend"], "sqlite")
        self.assertEqual(resumed["checkpoint_locator"], checkpoint_path)

    def test_graph_send_fanout_emits_section_and_repair_worker_nodes(self) -> None:
        events: list[dict] = []
        base_dir = Path(__file__).resolve().parents[1] / "data" / "_tmp"
        base_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_path = str(base_dir / f"compile_graph_{uuid.uuid4().hex}.sqlite")
        try:
            with self._patched_runtime():
                run_report_compilation_graph(
                    _minimal_payload(),
                    event_callback=events.append,
                    max_repairs=1,
                    checkpointer_path=checkpoint_path,
                    graph_thread_id="graph-thread-send",
                )
        finally:
            try:
                Path(checkpoint_path).unlink()
            except OSError:
                pass

        started_nodes = [
            str(event.get("agent") or "").strip()
            for event in events
            if str(event.get("type") or "").strip() == "graph.node.started"
        ]
        self.assertIn("section_realizer_worker", started_nodes)
        self.assertIn("section_realizer_finalize", started_nodes)
        self.assertIn("repair_worker", started_nodes)
        self.assertIn("repair_finalize", started_nodes)


if __name__ == "__main__":
    unittest.main()
