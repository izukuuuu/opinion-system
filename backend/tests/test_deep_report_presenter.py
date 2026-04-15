from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.report.deep_report.presenter import compile_markdown_artifacts
from src.report.deep_report.report_ir import attach_report_ir, build_artifact_manifest

from test_deep_report_document import sample_structured_payload


class TestDeepReportPresenter(TestCase):
    def test_compile_markdown_artifacts_allows_approved_human_override_after_fallback_recompile(self) -> None:
        bundle = sample_structured_payload()
        bundle["utility_assessment"] = {
            "decision": "fallback_recompile",
            "next_action": "先补 recommendation 结构，再进入正式文稿编译。",
            "missing_dimensions": ["actionable_recommendations"],
            "fallback_trace": [{"dimension": "actionable_recommendations"}],
            "improvement_trace": [],
            "confidence": 0.62,
        }
        manifest = build_artifact_manifest(
            topic_identifier="demo-topic-override",
            thread_id="report::demo-topic-override::2025-01-01::2025-01-31",
            task_id="task-override",
            structured_path="structured.json",
            draft_path="draft.json",
            full_path="full.json",
            ir_path="report_ir.json",
            figure_artifacts=bundle["figure_artifacts"],
        )
        enriched = attach_report_ir(bundle, artifact_manifest=manifest, task_id="task-override")
        enriched["report_ir"]["utility_assessment"] = dict(bundle["utility_assessment"])
        with patch(
            "src.report.deep_report.presenter.run_report_compilation_graph",
            return_value={
                "policy_registry": {"policy_version": "policy.v2"},
                "scene_profile": {},
                "style_profile": {},
                "layout_plan": {},
                "section_budget": {},
                "writer_context": {},
                "section_plan": {},
                "draft_bundle": {"source_artifact_id": "draft_bundle", "units": [], "section_order": []},
                "draft_bundle_v2": {"source_artifact_id": "draft_bundle.v2", "units": [], "section_order": []},
                "styled_draft_bundle": {"source_artifact_id": "draft_bundle", "units": [], "section_order": []},
                "validation_result_v2": {"passed": True, "failures": [], "patchable_failures": [], "gate": "pass", "repair_count": 0, "next_node": "artifact_renderer"},
                "repair_plan_v2": {"patches": [], "blocked_failures": [], "metadata": {}},
                "graph_state_v2": {"current_node": "artifact_renderer", "repair_count": 0},
                "factual_conformance": {
                    "passed": False,
                    "policy_version": "policy.v2",
                    "stage": "final_markdown",
                    "can_auto_recover": False,
                    "requires_human_review": False,
                    "issues": [],
                    "semantic_deltas": [],
                    "metadata": {},
                },
                "review_required": False,
                "markdown": "# 示例专题\n\n人工确认后继续写入。",
                "utility_assessment": bundle["utility_assessment"],
            },
        ):
            compiled = compile_markdown_artifacts(
                enriched,
                allow_review_pending=True,
                review_decision={"decision": "approve"},
            )
        self.assertEqual(compiled["markdown"], "# 示例专题\n\n人工确认后继续写入。")
        self.assertFalse(compiled["review_required"])
        self.assertFalse(compiled["factual_conformance"]["requires_human_review"])
        self.assertTrue(compiled["factual_conformance"]["metadata"]["human_override_accepted"])

    def test_compile_markdown_artifacts_allows_graph_recorded_human_override_without_explicit_review_decision(self) -> None:
        bundle = sample_structured_payload()
        bundle["utility_assessment"] = {
            "decision": "fallback_recompile",
            "next_action": "先补 recommendation 结构，再进入正式文稿编译。",
            "missing_dimensions": ["actionable_recommendations"],
            "fallback_trace": [{"dimension": "actionable_recommendations"}],
            "improvement_trace": [],
            "confidence": 0.62,
        }
        manifest = build_artifact_manifest(
            topic_identifier="demo-topic-graph-override",
            thread_id="report::demo-topic-graph-override::2025-01-01::2025-01-31",
            task_id="task-graph-override",
            structured_path="structured.json",
            draft_path="draft.json",
            full_path="full.json",
            ir_path="report_ir.json",
            figure_artifacts=bundle["figure_artifacts"],
        )
        enriched = attach_report_ir(bundle, artifact_manifest=manifest, task_id="task-graph-override")
        enriched["report_ir"]["utility_assessment"] = dict(bundle["utility_assessment"])
        with patch(
            "src.report.deep_report.presenter.run_report_compilation_graph",
            return_value={
                "policy_registry": {"policy_version": "policy.v2"},
                "scene_profile": {},
                "style_profile": {},
                "layout_plan": {},
                "section_budget": {},
                "writer_context": {},
                "section_plan": {},
                "draft_bundle": {"source_artifact_id": "draft_bundle", "units": [], "section_order": []},
                "draft_bundle_v2": {"source_artifact_id": "draft_bundle.v2", "units": [], "section_order": []},
                "styled_draft_bundle": {"source_artifact_id": "draft_bundle", "units": [], "section_order": []},
                "validation_result_v2": {"passed": False, "failures": [], "patchable_failures": [], "gate": "human_review", "repair_count": 2, "next_node": "artifact_renderer"},
                "repair_plan_v2": {"patches": [], "blocked_failures": [], "metadata": {}},
                "graph_state_v2": {"current_node": "artifact_renderer", "repair_count": 2},
                "factual_conformance": {
                    "passed": False,
                    "policy_version": "policy.v2",
                    "stage": "final_markdown",
                    "can_auto_recover": False,
                    "requires_human_review": False,
                    "issues": [],
                    "semantic_deltas": [],
                    "metadata": {"decision": "approve", "repair_count": 2},
                },
                "review_required": False,
                "markdown": "# 示例专题\n\n审批结果已被编译图记录。",
                "utility_assessment": bundle["utility_assessment"],
            },
        ):
            compiled = compile_markdown_artifacts(enriched, allow_review_pending=True)
        self.assertEqual(compiled["markdown"], "# 示例专题\n\n审批结果已被编译图记录。")
        self.assertFalse(compiled["review_required"])
        self.assertFalse(compiled["factual_conformance"]["requires_human_review"])
        self.assertEqual(compiled["factual_conformance"]["metadata"]["review_decision"], "approve")
        self.assertTrue(compiled["factual_conformance"]["metadata"]["human_override_accepted"])
