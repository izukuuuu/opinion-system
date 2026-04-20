from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.report.deep_report.presenter import build_full_payload, compile_markdown_artifacts
from src.report.deep_report.report_ir import attach_report_ir, build_artifact_manifest

from test_deep_report_document import sample_structured_payload


class TestDeepReportPresenter(TestCase):
    def test_build_full_payload_uses_attitude_rows_when_sentiment_overview_is_empty(self) -> None:
        structured = sample_structured_payload()
        structured["basic_analysis_snapshot"]["overview"]["sentiment"] = {"positive": 0, "neutral": 0, "negative": 0}
        structured["basic_analysis_snapshot"]["functions"] = [
            {
                "name": "attitude",
                "top_items": [
                    {"label": "neutral", "value": 12},
                    {"label": "negative", "value": 5},
                    {"label": "positive", "value": 3},
                ],
            }
        ]
        manifest = build_artifact_manifest(
            topic_identifier="demo-topic-dynamic-figures",
            thread_id="report::demo-topic-dynamic-figures::2025-01-01::2025-01-31",
            task_id="task-dynamic-figures",
            structured_path="structured.json",
            draft_path="draft.json",
            full_path="full.json",
            ir_path="report_ir.json",
            figure_artifacts=structured["figure_artifacts"],
        )
        enriched = attach_report_ir(structured, artifact_manifest=manifest, task_id="task-dynamic-figures")

        payload = build_full_payload(
            enriched,
            "# 示例专题\n\n## 基础分析洞察\n\n结论。\n\n::figure{ref=\"fig:basic-analysis:sentiment-overview\"}",
            cache_version=7,
        )
        figures = payload.get("artifact_manifest", {}).get("figures") or []
        sentiment = next(item for item in figures if item.get("figure_id") == "fig:basic-analysis:sentiment-overview")
        rows = sentiment.get("dataset", {}).get("rows") or []
        self.assertEqual([row.get("name") for row in rows], ["positive", "neutral", "negative"])
        self.assertEqual([row.get("value") for row in rows], [3.0, 12.0, 5.0])

    def test_build_full_payload_wordcloud_expands_to_30_terms_from_snapshot_source_root(self) -> None:
        structured = sample_structured_payload()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            keywords_dir = root / "keywords" / "总体"
            keywords_dir.mkdir(parents=True, exist_ok=True)
            payload = {
                "data": [{"name": f"词{i}", "value": 100 - i} for i in range(40)]
            }
            (keywords_dir / "keywords.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            structured["basic_analysis_snapshot"]["source_root"] = str(root)
            structured["basic_analysis_snapshot"]["overview"]["top_keywords"] = [{"name": "旧词", "value": 1}]
            manifest = build_artifact_manifest(
                topic_identifier="demo-topic-dynamic-figures",
                thread_id="report::demo-topic-dynamic-figures::2025-01-01::2025-01-31",
                task_id="task-dynamic-figures",
                structured_path="structured.json",
                draft_path="draft.json",
                full_path="full.json",
                ir_path="report_ir.json",
                figure_artifacts=structured["figure_artifacts"],
            )
            enriched = attach_report_ir(structured, artifact_manifest=manifest, task_id="task-dynamic-figures")

            built = build_full_payload(
                enriched,
                "# 示例专题\n\n## 基础分析洞察\n\n结论。\n\n::figure{ref=\"fig:basic-analysis:keywords-wordcloud\"}",
                cache_version=7,
            )
        figures = built.get("artifact_manifest", {}).get("figures") or []
        wordcloud = next(item for item in figures if item.get("figure_id") == "fig:basic-analysis:keywords-wordcloud")
        rows = wordcloud.get("dataset", {}).get("rows") or []
        self.assertEqual(len(rows), 30)
        self.assertEqual(rows[0]["name"], "词0")
        self.assertEqual(rows[-1]["name"], "词29")

    def test_build_full_payload_bertopic_figure_uses_theme_level_series(self) -> None:
        structured = sample_structured_payload()
        structured["bertopic_snapshot"]["llm_clusters"] = [
            {"name": "主题A", "count": 20},
            {"name": "主题B", "count": 10},
            {"name": "主题C", "count": 5},
        ]
        structured["bertopic_snapshot"]["temporal_points"] = [
            {
                "label": "1月上旬",
                "themes": [
                    {"name": "主题A", "value": 3},
                    {"name": "主题B", "value": 1},
                ],
            },
            {
                "label": "1月中旬",
                "themes": [
                    {"name": "主题A", "value": 5},
                    {"name": "主题C", "value": 2},
                ],
            },
        ]
        manifest = build_artifact_manifest(
            topic_identifier="demo-topic-dynamic-figures",
            thread_id="report::demo-topic-dynamic-figures::2025-01-01::2025-01-31",
            task_id="task-dynamic-figures",
            structured_path="structured.json",
            draft_path="draft.json",
            full_path="full.json",
            ir_path="report_ir.json",
            figure_artifacts=structured["figure_artifacts"],
        )
        enriched = attach_report_ir(structured, artifact_manifest=manifest, task_id="task-dynamic-figures")

        payload = build_full_payload(
            enriched,
            "# 示例专题\n\n## BERTopic 主题演化\n\n结论。\n\n::figure{ref=\"fig:bertopic:temporal-evolution\"}",
            cache_version=7,
        )
        figures = payload.get("artifact_manifest", {}).get("figures") or []
        bertopic = next(item for item in figures if item.get("figure_id") == "fig:bertopic:temporal-evolution")
        series = bertopic.get("option", {}).get("option", {}).get("series") or []
        self.assertEqual([item.get("name") for item in series], ["主题A", "主题B", "主题C"])
        self.assertEqual(series[0].get("data"), [3.0, 5.0])
        self.assertEqual(series[1].get("data"), [1.0, 0.0])
        self.assertEqual(series[2].get("data"), [0.0, 2.0])

    def test_build_full_payload_synthesizes_lightweight_dynamic_figures(self) -> None:
        structured = sample_structured_payload()
        manifest = build_artifact_manifest(
            topic_identifier="demo-topic-dynamic-figures",
            thread_id="report::demo-topic-dynamic-figures::2025-01-01::2025-01-31",
            task_id="task-dynamic-figures",
            structured_path="structured.json",
            draft_path="draft.json",
            full_path="full.json",
            ir_path="report_ir.json",
            figure_artifacts=structured["figure_artifacts"],
        )
        enriched = attach_report_ir(structured, artifact_manifest=manifest, task_id="task-dynamic-figures")

        payload = build_full_payload(
            enriched,
            "# 示例专题\n\n## 基础分析洞察\n\n结论。\n\n::figure{ref=\"fig:basic-analysis:sentiment-overview\"}",
            cache_version=7,
        )

        figure_ids = [item.get("figure_id") for item in (payload.get("report_ir", {}).get("figures") or [])]
        self.assertEqual(
            figure_ids,
            [
                "fig:basic-analysis:sentiment-overview",
                "fig:basic-analysis:keywords-wordcloud",
                "fig:bertopic:temporal-evolution",
            ],
        )
        artifact_ids = [item.get("figure_id") for item in (payload.get("artifact_manifest", {}).get("figures") or [])]
        self.assertEqual(artifact_ids, figure_ids)
        self.assertEqual(payload["meta"]["figure_ids"], figure_ids)

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
