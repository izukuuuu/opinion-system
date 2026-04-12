from __future__ import annotations

import sys
import uuid
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.report.deep_report.graph_runtime import run_report_compilation_graph
from src.report.deep_report.schemas import DraftBundle, DraftUnit


class _Dumpable(dict):
    def model_dump(self) -> dict:
        return dict(self)


def _minimal_payload() -> dict:
    return {
        "task": {
            "topic_label": "合规专题",
            "thread_id": "report::conformance-topic::2025-01-01::2025-01-31",
        },
        "report_ir": {
            "meta": {
                "topic_label": "合规专题",
                "topic_identifier": "conformance-topic",
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
        section_order=["overview"],
        units=[
            DraftUnit(
                unit_id="unit:overview:1",
                section_role="overview",
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


class ProviderConformanceTests(unittest.TestCase):
    """
    隔离的 provider 协议一致性测试。
    只依赖 graph_runtime + schemas，不依赖 service 层。
    覆盖：单轮调用、结构化输出绑定、interrupt/resume 模式。
    """

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
                                "section_id": "overview",
                                "goal": "概述",
                                "source_groups": ["claims"],
                            }
                        ]
                    }
                ),
            )
        )
        stack.enter_context(patch("src.report.deep_report.graph_runtime.compile_draft_units", side_effect=_invalid_draft_bundle))
        return stack

    def test_single_tool_call_round_trip(self) -> None:
        """单轮调用能完成（或产生可识别的中断/失败），并发出至少一个 graph.node.started 事件。"""
        events: list[dict] = []
        base_dir = Path(__file__).resolve().parents[1] / "data" / "_tmp"
        base_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_path = str(base_dir / f"conformance_{uuid.uuid4().hex}.sqlite")
        try:
            with self._patched_runtime():
                result = run_report_compilation_graph(
                    _minimal_payload(),
                    event_callback=events.append,
                    max_repairs=0,
                    checkpointer_path=checkpoint_path,
                    graph_thread_id="conformance-round-trip",
                )
        finally:
            try:
                Path(checkpoint_path).unlink()
            except OSError:
                pass

        started_events = [e for e in events if e.get("type") == "graph.node.started"]
        self.assertGreater(len(started_events), 0, "期望至少一个 graph.node.started 事件")
        self.assertIn("status", result)
        self.assertIn(result["status"], ("interrupted", "completed", "failed"))

    def test_structured_output_binding_produces_graph_state(self) -> None:
        """中断时 graph_state_v2 必须包含 schema_version 字段（DeepReportGraphState 结构化输出约定）。"""
        base_dir = Path(__file__).resolve().parents[1] / "data" / "_tmp"
        base_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_path = str(base_dir / f"conformance_{uuid.uuid4().hex}.sqlite")
        try:
            with self._patched_runtime():
                result = run_report_compilation_graph(
                    _minimal_payload(),
                    max_repairs=1,
                    checkpointer_path=checkpoint_path,
                    graph_thread_id="conformance-schema-binding",
                )
        finally:
            try:
                Path(checkpoint_path).unlink()
            except OSError:
                pass

        self.assertEqual(result["status"], "interrupted")
        graph_state = result.get("graph_state_v2") or {}
        self.assertIn("schema_version", graph_state, "graph_state_v2 必须包含 schema_version")
        self.assertEqual(graph_state["schema_version"], "deep-report-graph.v2")
        self.assertIn("run_state_version", graph_state, "graph_state_v2 必须包含 run_state_version")
        self.assertEqual(graph_state["run_state_version"], "run-state.v1")

    def test_interrupt_resume_pattern(self) -> None:
        """SQLite checkpoint → 第一次中断 → resume approve → 得到 markdown。"""
        base_dir = Path(__file__).resolve().parents[1] / "data" / "_tmp"
        base_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_path = str(base_dir / f"conformance_{uuid.uuid4().hex}.sqlite")
        try:
            with self._patched_runtime():
                first = run_report_compilation_graph(
                    _minimal_payload(),
                    max_repairs=1,
                    checkpointer_path=checkpoint_path,
                    graph_thread_id="conformance-interrupt-resume",
                )
                self.assertEqual(first["status"], "interrupted")
                self.assertTrue(Path(checkpoint_path).exists())

                resumed = run_report_compilation_graph(
                    _minimal_payload(),
                    max_repairs=1,
                    checkpointer_path=checkpoint_path,
                    graph_thread_id="conformance-interrupt-resume",
                    review_decision={"decision": "approve"},
                )
        finally:
            try:
                Path(checkpoint_path).unlink()
            except OSError:
                pass

        self.assertFalse(resumed.get("review_required"))
        self.assertTrue(resumed.get("markdown"))


if __name__ == "__main__":
    unittest.main()
