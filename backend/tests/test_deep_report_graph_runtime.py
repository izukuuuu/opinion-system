from __future__ import annotations

import sys
import tempfile
import uuid
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

    def test_graph_interrupt_resume_with_sqlite_checkpoint_and_edit(self) -> None:
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
                        "decision": "edit",
                        "edited_action": {"markdown": "# 人工修订后的正式文稿"},
                    },
                )
        finally:
            try:
                Path(checkpoint_path).unlink()
            except OSError:
                pass

        self.assertEqual(resumed["markdown"], "# 人工修订后的正式文稿")
        self.assertFalse(resumed["review_required"])
        self.assertEqual(resumed["graph_state_v2"]["metadata"]["graph_thread_id"], "graph-thread-1")
        self.assertEqual(resumed["graph_state_v2"]["metadata"]["checkpoint_path"], checkpoint_path)
        self.assertEqual(resumed["checkpoint_backend"], "sqlite")
        self.assertEqual(resumed["checkpoint_locator"], checkpoint_path)

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
