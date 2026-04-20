from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.report.deep_report.compiler import (
    assemble_writer_context,
    build_conformance_policy_registry,
    compile_section_draft_units,
    build_section_plan,
    build_layout_plan,
    build_section_budget,
    compile_draft_units,
    resolve_style_profile,
    render_final_markdown,
    run_factual_conformance,
    run_stylistic_rewrite,
    select_scene_profile,
)
from src.report.deep_report.deep_writer import DeepWriterError, build_template_brief, compile_draft_units_with_llm
from src.report.deep_report.payloads import build_retrieval_plan_payload, normalize_task_payload
from src.report.deep_report.document import build_figure_pipeline, build_report_document, load_report_blueprint, sanitize_report_document
from src.report.deep_report.presenter import build_full_payload, compile_markdown_artifacts, render_markdown
from src.report.deep_report.report_ir import attach_report_ir, build_artifact_manifest, build_report_ir
from src.report.deep_report.service import _build_semantic_review_payload, generate_full_report_payload
from src.report.deep_report.schemas import CompilerSceneProfile, ReportDataBundle, ReportDocument, SectionPlan, SemanticLatticeState
from src.report.full_report_templates import choose_best_template


def sample_bundle() -> ReportDataBundle:
    return ReportDataBundle.model_validate(
        {
            "task": {
                "topic_identifier": "demo-topic",
                "topic_label": "示例专题",
                "start": "2025-01-01",
                "end": "2025-01-31",
                "mode": "fast",
                "thread_id": "report::demo-topic::2025-01-01::2025-01-31",
            },
            "conclusion": {
                "executive_summary": "声量集中在节点期，主体表达明显分化。",
                "key_findings": ["声量在中旬抬升", "媒体与公众关注点不完全一致"],
                "key_risks": ["争议议题仍在发酵"],
                "confidence_label": "高",
            },
            "timeline": [
                {
                    "event_id": "evt-1",
                    "date": "2025-01-10",
                    "title": "关键节点",
                    "description": "事件触发讨论升温。",
                    "trigger": "政策发布",
                    "impact": "讨论量上升",
                    "citation_ids": ["C1"],
                }
            ],
            "subjects": [
                {
                    "subject_id": "sub-1",
                    "name": "平台用户",
                    "category": "公众",
                    "role": "讨论主体",
                    "summary": "关注执行影响。",
                    "citation_ids": ["C1"],
                }
            ],
            "stance_matrix": [
                {
                    "subject": "平台用户",
                    "stance": "质疑",
                    "summary": "更关注执行层面的现实问题。",
                    "citation_ids": ["C1"],
                }
            ],
            "key_evidence": [
                {
                    "evidence_id": "ev-1",
                    "finding": "中旬声量达到阶段高点。",
                    "subject": "平台用户",
                    "stance": "质疑",
                    "time_label": "中旬",
                    "source_summary": "来自多平台的集中讨论。",
                    "citation_ids": ["C1"],
                    "confidence": "high",
                }
            ],
            "conflict_points": [],
            "agenda_frame_map": {
                "issues": [
                    {
                        "issue_id": "issue-1",
                        "label": "控烟政策",
                        "salience": 0.82,
                        "time_scope": ["2025-01-10"],
                        "source_refs": ["ev-1"],
                    }
                ],
                "attributes": [
                    {
                        "attribute_id": "attribute-1",
                        "label": "执行争议",
                        "attribute_type": "execution",
                        "salience": 0.76,
                        "source_refs": ["ev-1"],
                    }
                ],
                "issue_attribute_edges": [
                    {
                        "edge_id": "issue-attr-1",
                        "issue_id": "issue-1",
                        "attribute_id": "attribute-1",
                        "weight": 0.74,
                        "time_scope": ["2025-01-10"],
                        "source_refs": ["ev-1"],
                    }
                ],
                "frames": [
                    {
                        "frame_id": "frame-1",
                        "problem": "执行安排引发争议",
                        "cause": "信息解释存在差异",
                        "judgment": "当前讨论已转向执行影响",
                        "remedy": "补充回应并澄清执行口径",
                        "confidence": 0.77,
                        "source_refs": ["ev-1"],
                    }
                ],
                "frame_carriers": [{"actor_id": "sub-1", "frame_ids": ["frame-1"], "role": "observer"}],
                "frame_shifts": [],
                "counter_frames": [],
                "summary": "已形成基础议题-框架对象。",
            },
            "conflict_map": {
                "claims": [
                    {
                        "claim_id": "claimrec-1",
                        "proposition": "平台用户质疑执行安排",
                        "proposition_slots": {"subject": "平台用户", "predicate": "质疑", "object": "执行安排", "qualifier": "negative", "polarity": "assert"},
                        "raw_spans": ["平台用户质疑执行安排"],
                        "time_anchor": "2025-01-10",
                        "source_ids": ["source-1"],
                        "verification_status": "pending_verification",
                        "evidence_coverage": "partial",
                        "source_diversity": 1,
                        "temporal_confidence": 1.0,
                        "evidence_density": 0.72,
                    }
                ],
                "actor_positions": [
                    {
                        "actor_id": "sub-1",
                        "name": "平台用户",
                        "aliases": ["平台用户"],
                        "role_type": "public",
                        "organization_type": "community",
                        "speaker_role": "observer",
                        "relay_role": "origin",
                        "account_tier": "primary",
                        "is_official": False,
                        "stance": "质疑",
                        "stance_shift": "更关注执行层面的现实问题。",
                        "claim_ids": ["claimrec-1"],
                        "representative_evidence_ids": ["ev-1"],
                        "conflict_actor_ids": [],
                        "confidence": 0.82,
                    }
                ],
                "edges": [
                    {
                        "edge_id": "edge-1",
                        "claim_a_id": "claimrec-1",
                        "claim_b_id": "claimrec-1",
                        "conflict_type": "evidence_conflict",
                        "actor_scope": ["sub-1"],
                        "time_scope": ["2025-01-10"],
                        "evidence_refs": ["ev-1"],
                        "evidence_density": 0.72,
                        "confidence": 0.68,
                    }
                ],
                "resolution_summary": [
                    {
                        "claim_id": "claimrec-1",
                        "status": "pending_verification",
                        "reason": "当前只掌握单侧证据。",
                        "supporting_claim_ids": ["claimrec-1"],
                        "unresolved_reason": "仍需更多交叉来源。",
                        "resolution_confidence": 0.48,
                    }
                ],
                "summary": "已形成一条待核验的冲突边。",
                "evidence_density": 0.72,
                "source_diversity": 1,
            },
            "propagation_features": [
                {
                    "feature_id": "pf-1",
                    "dimension": "平台扩散",
                    "finding": "微博扩散最快",
                    "explanation": "微博在首轮峰值中起到扩散作用。",
                    "citation_ids": ["C1"],
                }
            ],
            "mechanism_summary": {
                "amplification_paths": [
                    {
                        "path_id": "path-main",
                        "source_actor_ids": ["sub-1"],
                        "bridge_actor_ids": ["sub-1"],
                        "platform_sequence": ["微博", "视频"],
                        "linked_claim_ids": ["claimrec-1"],
                        "evidence_refs": ["ev-1"],
                        "confidence": 0.72,
                    }
                ],
                "trigger_events": [
                    {
                        "event_id": "evt-1",
                        "time_anchor": "2025-01-10",
                        "description": "政策节点触发讨论升温。",
                        "linked_claim_ids": ["claim:ev-1"],
                        "linked_actor_ids": ["sub-1"],
                        "evidence_refs": ["ev-1"],
                        "confidence": 0.7,
                    }
                ],
                "phase_shifts": [
                    {
                        "phase_id": "phase-1",
                        "from_phase": "attention",
                        "to_phase": "discussion",
                        "reason": "政策发布后讨论快速进入执行争议。",
                        "linked_claim_ids": ["claimrec-1"],
                        "evidence_refs": ["ev-1"],
                        "confidence": 0.69,
                    }
                ],
                "cross_platform_bridges": [
                    {
                        "bridge_id": "bridge-1",
                        "from_platform": "微博",
                        "to_platform": "视频",
                        "bridge_actor_ids": ["sub-1"],
                        "linked_claim_ids": ["claimrec-1"],
                        "evidence_refs": ["ev-1"],
                        "confidence": 0.67,
                    }
                ],
                "bridge_nodes": [
                    {
                        "node_id": "bridge-node-1",
                        "actor_id": "sub-1",
                        "platform": "微博",
                        "bridge_role": "cross_platform_bridge",
                        "linked_claim_ids": ["claimrec-1"],
                        "evidence_refs": ["ev-1"],
                        "confidence": 0.66,
                    }
                ],
                "cause_candidates": [
                    {
                        "cause_event_id": "evt-1",
                        "effect_event_id": "evt-1",
                        "causality_type": "single_event_attention_spike",
                        "confidence": 0.63,
                        "evidence_refs": ["ev-1"],
                    }
                ],
                "cross_platform_transfers": [
                    {
                        "transfer_id": "transfer-1",
                        "from_platform": "微博",
                        "to_platform": "视频",
                        "bridge_node_ids": ["bridge-node-1"],
                        "evidence_refs": ["ev-1"],
                    }
                ],
                "narrative_carriers": [
                    {
                        "carrier_id": "carrier-1",
                        "actor_id": "sub-1",
                        "platform_id": "微博",
                        "frame_ids": ["frame-1"],
                        "transport_role": "bridge",
                    }
                ],
                "refutation_lags": [],
                "confidence_summary": "传播机制已形成基础判断。",
            },
            "risk_judgement": [
                {
                    "risk_id": "risk-1",
                    "label": "争议延续",
                    "level": "medium",
                    "summary": "若缺少回应，争议可能持续。",
                    "citation_ids": ["C1"],
                }
            ],
            "utility_assessment": {
                "assessment_id": "utility-1",
                "has_object_scope": True,
                "has_time_window": True,
                "has_key_actors": True,
                "has_primary_contradiction": True,
                "has_mechanism_explanation": True,
                "has_issue_frame_context": True,
                "has_conditional_risk": True,
                "has_actionable_recommendations": True,
                "has_uncertainty_boundary": True,
                "recommendation_has_object": True,
                "recommendation_has_time": True,
                "recommendation_has_action": True,
                "recommendation_has_preconditions": True,
                "recommendation_has_side_effects": True,
                "missing_dimensions": [],
                "fallback_trace": [],
                "improvement_trace": [],
                "decision": "pass",
                "next_action": "允许进入编译层。",
                "utility_confidence": 0.88,
                "confidence": 0.88,
            },
            "unverified_points": [
                {
                    "item_id": "uv-1",
                    "statement": "部分截图来源待核验",
                    "reason": "原始链路不完整",
                    "citation_ids": [],
                }
            ],
            "suggested_actions": [
                {
                    "action_id": "act-1",
                    "action": "补充回应口径",
                    "rationale": "降低争议外溢风险。",
                    "priority": "high",
                    "citation_ids": ["C1"],
                }
            ],
            "citations": [
                {
                    "citation_id": "C1",
                    "title": "示例来源",
                    "url": "https://example.com/source",
                    "published_at": "2025-01-10",
                    "platform": "微博",
                    "snippet": "示例摘录",
                    "source_type": "post",
                }
            ],
            "validation_notes": [
                {
                    "note_id": "vn-1",
                    "category": "fact",
                    "severity": "low",
                    "message": "样本验证通过",
                    "related_ids": ["ev-1"],
                }
            ],
        }
    )


def sample_functions_payload():
    return [
        {
            "name": "volume",
            "targets": [
                {
                    "target": "总体",
                    "data": [
                        {"name": "微博", "value": 12},
                        {"name": "视频", "value": 7},
                    ],
                }
            ],
        },
        {
            "name": "trends",
            "targets": [
                {
                    "target": "微博",
                    "data": [
                        {"name": "2025-01-10", "value": 10},
                        {"name": "2025-01-11", "value": 18},
                    ],
                },
                {
                    "target": "视频",
                    "data": [
                        {"name": "2025-01-10", "value": 4},
                        {"name": "2025-01-11", "value": 6},
                    ],
                },
            ],
        },
    ]


def sample_overview():
    return {"total_volume": 19}


def sample_figure_pipeline(bundle: ReportDataBundle | None = None):
    current_bundle = bundle or sample_bundle()
    return build_figure_pipeline(sample_functions_payload(), bundle=current_bundle, bertopic_snapshot={})


def sample_structured_payload(bundle: ReportDataBundle | None = None):
    current_bundle = bundle or sample_bundle()
    metric_bundle, figures, figure_artifacts, placement_plan = sample_figure_pipeline(current_bundle)
    return {
        **current_bundle.model_dump(),
        "report_data": current_bundle.model_dump(),
        "basic_analysis_snapshot": {
            "snapshot_id": "basic-snapshot-1",
            "topic_identifier": "demo-topic",
            "topic_label": "示例专题",
            "available": True,
            "overview": {
                "sentiment": {"正向": 8, "中性": 6, "负向": 5},
                "top_keywords": [{"name": "控烟", "value": 18}, {"name": "执行", "value": 12}],
            },
        },
        "basic_analysis_insight": {
            "section_id": "basic-analysis-insight",
            "section_title": "基础分析洞察",
            "summary": "样本讨论以执行感知和公共场所体验为主。",
            "key_findings": ["中性与负向表达占比较高", "高频词集中在控烟、执行、场景体验"],
            "uncertainty_notes": ["县域与线下执行样本覆盖有限"],
        },
        "bertopic_snapshot": {
            "snapshot_id": "bertopic-snapshot-1",
            "topic_identifier": "demo-topic",
            "topic_label": "示例专题",
            "available": True,
            "temporal_points": [
                {"label": "1月上旬", "value": 0.22},
                {"label": "1月中旬", "value": 0.71},
                {"label": "1月下旬", "value": 0.46},
            ],
        },
        "bertopic_insight": {
            "section_id": "bertopic-evolution",
            "section_title": "BERTopic 主题演化",
            "summary": "主题从政策解读逐步转向执行体验与争议扩散。",
            "key_findings": ["中旬主题热度抬升", "后段从政策讨论转向执行体验"],
            "uncertainty_notes": ["当前仅覆盖公开平台主题分布"],
        },
        "report_document": build_report_document(current_bundle, figures, placement_plan, sample_overview()),
        "metric_bundle": metric_bundle.model_dump(),
        "figures": [item.model_dump() for item in figures],
        "figure_artifacts": [item.model_dump() for item in figure_artifacts],
        "placement_plan": placement_plan.model_dump(),
        "metadata": {"cache_version": 3},
    }


def fake_semantic_state_for_text(payload, *, text, section_role, trace_ids, baseline, registry):
    state = baseline.model_copy(deep=True)
    line = str(text or "").strip()
    if "舆论普遍反对" in line or "社会普遍认为" in line:
        state.scope_quantifier = "universal"
        state.actor_scope = "public"
    if "风险已形成" in line:
        state.risk_maturity = "formed"
    if "必须立即处理" in line or "必须立即启动强制处置" in line:
        state.action_force = "mandatory"
    if "已证明" in line or "已经证实" in line:
        state.assertion_certainty = "confirmed"
    return SemanticLatticeState.model_validate(state.model_dump())


class DeepReportDocumentTests(unittest.TestCase):
    def test_build_figure_pipeline_emits_typed_figures_and_artifacts(self):
        metric_bundle, figures, figure_artifacts, placement_plan = sample_figure_pipeline()
        figure_ids = {item.figure_id for item in figures}
        self.assertIn("fig:volume:总体", figure_ids)
        self.assertIn("fig:trends:微博", figure_ids)
        self.assertIn("fig:trends:trend-flow", figure_ids)
        self.assertTrue(metric_bundle.metrics)
        self.assertTrue(figure_artifacts)
        self.assertTrue(placement_plan.entries)
        self.assertTrue(all(item.dataset_ref and item.option_ref for item in figures))
        self.assertTrue(all(item.dataset.digest for item in figure_artifacts))

    def test_build_report_document_validates_against_schema(self):
        bundle = sample_bundle()
        _, figures, _, placement_plan = sample_figure_pipeline(bundle)
        document = build_report_document(bundle, figures, placement_plan, sample_overview())
        parsed = ReportDocument.model_validate(document)
        self.assertEqual([section.section_id for section in parsed.sections], [
            "basic-analysis-insight",
            "bertopic-evolution",
            "core-dimensions",
            "lifecycle",
            "subjects-and-stance",
            "propagation-and-response",
        ])
        self.assertTrue(any(block.type == "figure_ref" for section in parsed.sections for block in section.blocks))

    def test_analysis_report_blueprint_is_loaded_from_yaml(self):
        blueprint = load_report_blueprint("analysis_report")
        self.assertEqual(blueprint["document_type"], "analysis_report")
        self.assertEqual(blueprint["sections"][1]["section_id"], "basic-analysis-insight")
        self.assertEqual(blueprint["sections"][2]["section_id"], "bertopic-evolution")

    def test_sanitize_report_document_downgrades_missing_figure_ref(self):
        sanitized = sanitize_report_document(
            {
                "hero": {},
                "sections": [
                    {
                        "section_id": "demo",
                        "title": "Demo",
                        "blocks": [
                            {
                                "type": "figure_ref",
                                "block_id": "missing-figure",
                                "figure_id": "fig:not-found",
                                "placement_anchor": "after:summary_claim:claim_2",
                                "render_hint": "chart",
                            }
                        ],
                    }
                ],
                "appendix": {"blocks": []},
            },
            [],
        )
        block = sanitized["sections"][0]["blocks"][0]
        self.assertEqual(block["type"], "callout")
        self.assertEqual(block["title"], "图表暂缺")
        self.assertIn("自动降级", block["content"])
        with self.assertRaises(Exception):
            ReportDocument.model_validate(
                {
                    "hero": {},
                    "sections": [{"section_id": "demo", "title": "Demo", "blocks": [{"type": "chart_slot", "block_id": "legacy-slot"}]}],
                    "appendix": {"blocks": []},
                }
            )

    def test_attach_report_ir_builds_manifest_and_ir_summary(self):
        structured = sample_structured_payload()
        manifest = build_artifact_manifest(
            topic_identifier="demo-topic",
            thread_id="report::demo-topic::2025-01-01::2025-01-31",
            task_id="task-1",
            structured_path="F:/opinion-system/data/reports/demo-topic/2025-01-01/report_payload.json",
            ir_path="F:/opinion-system/data/reports/demo-topic/2025-01-01/report_ir.json",
            figure_artifacts=structured["figure_artifacts"],
        )
        enriched = attach_report_ir(structured, artifact_manifest=manifest, task_id="task-1")
        self.assertIn("report_ir", enriched)
        self.assertEqual(enriched["report_ir"]["meta"]["task_id"], "task-1")
        self.assertEqual(enriched["artifact_manifest"]["structured_projection"]["status"], "ready")
        self.assertEqual(enriched["report_ir"]["risk_register"]["risks"][0]["risk_id"], "risk-1")
        self.assertEqual(enriched["report_ir"]["agenda_frame_map"]["issues"][0]["issue_id"], "issue-1")
        self.assertEqual(enriched["report_ir"]["conflict_map"]["edges"][0]["edge_id"], "edge-1")
        self.assertEqual(enriched["report_ir"]["mechanism_summary"]["amplification_paths"][0]["path_id"], "path-main")
        self.assertEqual(enriched["report_ir"]["mechanism_summary"]["bridge_nodes"][0]["node_id"], "bridge-node-1")
        self.assertEqual(enriched["report_ir"]["utility_assessment"]["decision"], "pass")
        self.assertTrue(enriched["report_ir"]["figures"])
        self.assertTrue(enriched["artifact_manifest"]["figures"])

    def test_full_payload_is_rendered_from_report_ir(self):
        structured = sample_structured_payload()
        manifest = build_artifact_manifest(
            topic_identifier="demo-topic",
            thread_id="report::demo-topic::2025-01-01::2025-01-31",
            task_id="task-2",
            structured_path="structured.json",
            full_path="full.json",
            ir_path="report_ir.json",
            figure_artifacts=structured["figure_artifacts"],
        )
        enriched = attach_report_ir(structured, artifact_manifest=manifest, task_id="task-2")
        with patch(
            "src.report.deep_report.presenter.compile_markdown_artifacts",
            return_value={
                "markdown": "# 示例专题\n\n## 议题与框架\n示例框架。\n\n## 事实断言\n示例断言。\n\n## 冲突与收敛\n示例冲突。\n\n## 传播机制\n示例机制。",
            },
        ):
            markdown = render_markdown(enriched)
        full_payload = build_full_payload(enriched, markdown, cache_version=10)
        self.assertIn("## 议题与框架", markdown)
        self.assertIn("## 事实断言", markdown)
        self.assertIn("## 冲突与收敛", markdown)
        self.assertIn("## 传播机制", markdown)
        self.assertIn("report_ir_summary", full_payload)
        self.assertEqual(full_payload["meta"]["artifact_manifest"]["full_markdown"]["status"], "ready")
        self.assertEqual(full_payload["report_ir_summary"]["counts"]["claims"], 3)
        self.assertEqual(full_payload["report_ir_summary"]["counts"]["agenda_frames"], 1)
        self.assertEqual(full_payload["report_ir_summary"]["counts"]["conflict_edges"], 1)
        self.assertEqual(full_payload["report_ir_summary"]["counts"]["bridge_nodes"], 1)
        self.assertTrue(full_payload["meta"]["figure_ids"])

    def test_compiler_passes_are_typed_and_agent_free(self):
        bundle = sample_structured_payload()
        manifest = build_artifact_manifest(
            topic_identifier="demo-topic",
            thread_id="report::demo-topic::2025-01-01::2025-01-31",
            task_id="task-3",
            structured_path="structured.json",
            ir_path="report_ir.json",
        )
        ir = build_report_ir(bundle, artifact_manifest=manifest, task_id="task-3")
        scene = select_scene_profile(ir)
        style = resolve_style_profile(ir, scene)
        layout = build_layout_plan(ir, scene, style)
        budget = build_section_budget(ir, scene, layout)

        self.assertEqual(scene.render_mode, "template_driven")
        self.assertTrue(scene.template_id)
        self.assertTrue(scene.template_path)
        self.assertEqual(style.style_id, "evidence_first")
        self.assertTrue(layout.sections)
        self.assertTrue(budget.sections)
        self.assertTrue(all(entry.max_words >= entry.target_words for entry in budget.sections))

    def test_draft_bundle_keeps_traceability_before_markdown_render(self):
        bundle = sample_structured_payload()
        manifest = build_artifact_manifest(
            topic_identifier="demo-topic",
            thread_id="report::demo-topic::2025-01-01::2025-01-31",
            task_id="task-4",
            structured_path="structured.json",
            ir_path="report_ir.json",
        )
        ir = build_report_ir(bundle, artifact_manifest=manifest, task_id="task-4")
        scene = select_scene_profile(ir)
        style = resolve_style_profile(ir, scene)
        layout = build_layout_plan(ir, scene, style)
        budget = build_section_budget(ir, scene, layout)
        section_plan = build_section_plan(ir, layout, budget)
        draft_bundle = compile_draft_units(ir, section_plan)
        self.assertTrue(draft_bundle.units)
        self.assertTrue(all(unit.text.startswith("## ") or (unit.trace_ids or unit.claim_ids or unit.evidence_ids or unit.risk_ids or unit.unresolved_point_ids or unit.stance_row_ids) for unit in draft_bundle.units))
        conformance = run_factual_conformance(ir, draft_bundle)
        self.assertTrue(conformance.passed)
        section_units = compile_section_draft_units(ir, section_plan.sections[0])
        self.assertTrue(section_units)
        self.assertTrue(all(unit.text.startswith("## ") or (unit.trace_ids or unit.claim_ids or unit.evidence_ids or unit.risk_ids or unit.unresolved_point_ids or unit.stance_row_ids) for unit in section_units))

    def test_choose_best_template_prefers_policy_template_for_tobacco_governance_topic(self):
        bundle = sample_structured_payload()
        bundle["task"]["topic_label"] = "2025控烟舆情"
        bundle["report_data"]["task"]["topic_label"] = "2025控烟舆情"
        manifest = build_artifact_manifest(
            topic_identifier="demo-topic-policy",
            thread_id="report::demo-topic-policy::2025-01-01::2025-01-31",
            task_id="task-policy",
            structured_path="structured.json",
            ir_path="report_ir.json",
        )
        ir = build_report_ir(bundle, artifact_manifest=manifest, task_id="task-policy")

        selected = choose_best_template(
            topic_label="2025控烟舆情",
            title="2025控烟舆情",
            report_ir=ir.model_dump(),
        )

        self.assertEqual(selected["template_id"], "policy_dynamics")
        self.assertTrue(selected["matched_reasons"])

    def test_section_plan_uses_selected_template_sections_and_guides(self):
        bundle = sample_structured_payload()
        bundle["task"]["topic_label"] = "2025控烟舆情"
        bundle["report_data"]["task"]["topic_label"] = "2025控烟舆情"
        manifest = build_artifact_manifest(
            topic_identifier="demo-topic-policy-plan",
            thread_id="report::demo-topic-policy-plan::2025-01-01::2025-01-31",
            task_id="task-policy-plan",
            structured_path="structured.json",
            ir_path="report_ir.json",
        )
        ir = build_report_ir(bundle, artifact_manifest=manifest, task_id="task-policy-plan")
        scene = select_scene_profile(ir)
        style = resolve_style_profile(ir, scene)
        layout = build_layout_plan(ir, scene, style)
        budget = build_section_budget(ir, scene, layout)
        section_plan = build_section_plan(ir, layout, budget, scene)

        self.assertEqual(scene.template_id, "policy_dynamics")
        self.assertTrue(scene.template_sections)
        self.assertEqual(section_plan.sections[0].title, scene.template_sections[0]["title"])
        self.assertEqual(section_plan.sections[0].template_id, "policy_dynamics")
        self.assertTrue(section_plan.sections[0].writing_instruction)
        self.assertEqual(section_plan.sections[0].selection_context["template_id"], "policy_dynamics")

    def test_section_plan_inserts_dynamic_insight_sections_at_fixed_third_slot(self):
        bundle = sample_structured_payload()
        bundle["task"]["topic_label"] = "2025控烟舆情"
        bundle["report_data"]["task"]["topic_label"] = "2025控烟舆情"
        manifest = build_artifact_manifest(
            topic_identifier="demo-topic-dynamic-plan",
            thread_id="report::demo-topic-dynamic-plan::2025-01-01::2025-01-31",
            task_id="task-dynamic-plan",
            structured_path="structured.json",
            ir_path="report_ir.json",
        )
        ir = build_report_ir(bundle, artifact_manifest=manifest, task_id="task-dynamic-plan")
        scene = select_scene_profile(ir)
        style = resolve_style_profile(ir, scene)
        layout = build_layout_plan(ir, scene, style)
        budget = build_section_budget(ir, scene, layout)
        section_plan = build_section_plan(ir, layout, budget, scene, bundle)

        section_ids = [item.section_id for item in section_plan.sections[:5]]
        self.assertEqual(section_ids[2:4], ["basic_analysis_insight", "bertopic_insight"])

    def test_writer_context_carries_dynamic_insight_payloads_and_figure_refs(self):
        structured = sample_structured_payload()
        manifest = build_artifact_manifest(
            topic_identifier="demo-topic-writer-context",
            thread_id="report::demo-topic-writer-context::2025-01-01::2025-01-31",
            task_id="task-writer-context",
            structured_path="structured.json",
            ir_path="report_ir.json",
        )
        ir = build_report_ir(structured, artifact_manifest=manifest, task_id="task-writer-context")
        scene = select_scene_profile(ir)
        style = resolve_style_profile(ir, scene)
        layout = build_layout_plan(ir, scene, style)
        budget = build_section_budget(ir, scene, layout)
        context = assemble_writer_context(ir, scene, style, layout, budget, structured)

        self.assertTrue(context.basic_analysis_insight.get("summary"))
        self.assertTrue(context.bertopic_insight.get("summary"))
        self.assertEqual(
            [item["figure_id"] for item in context.section_figure_refs.get("basic_analysis_insight", [])],
            ["fig:basic-analysis:sentiment-overview", "fig:basic-analysis:keywords-wordcloud"],
        )

    def test_llm_deep_writer_records_tool_receipts(self):
        class _DummyAgent:
            def __init__(self, tools, name):
                self.tools = {tool.name: tool for tool in tools}
                self.name = name

            def invoke(self, *_args, **_kwargs):
                self.tools["artifact_search"].invoke(
                    {"query": "影响 争议", "scope": "report_ir template_brief", "section_goal": "影响传导"}
                )
                self.tools["evidence_search"].invoke(
                    {"query": "质疑 执行", "section_goal": "动作建议", "platforms": "微博", "limit": 4}
                )
                self.tools["build_section_packet"].invoke(
                    {
                        "section_id": "impact",
                        "section_goal": "说明影响传导和动作建议。",
                        "evidence_ids_json": json.dumps(["ev-1", "ev-2"], ensure_ascii=False),
                    }
                )
                return {"messages": [{"content": "争议主要集中在执行安排和解释节奏，建议优先补足解释口径并明确后续动作节奏。"}]}

        class _DummyLLM:
            def with_structured_output(self, schema):
                class _Structured:
                    def invoke(self, _messages):
                        return schema(
                            section_id="impact",
                            claim_refs=["claimrec-1"],
                            evidence_refs=["ev-1", "ev-2"],
                            notes="动作建议与影响传导绑定。",
                            confidence=0.92,
                        )

                return _Structured()

        bundle = sample_structured_payload()
        manifest = build_artifact_manifest(
            topic_identifier="demo-topic-writer",
            thread_id="report::demo-topic-writer::2025-01-01::2025-01-31",
            task_id="task-writer",
            structured_path="structured.json",
            ir_path="report_ir.json",
        )
        ir = build_report_ir(bundle, artifact_manifest=manifest, task_id="task-writer")
        scene = CompilerSceneProfile(
            scene_id="policy_dynamics",
            scene_label="政策行业场景",
            template_id="policy_dynamics",
            template_name="policy_dynamics",
            template_path="policy_dynamics.md",
        )
        section_plan = SectionPlan.model_validate(
            {
                "sections": [
                    {
                        "section_id": "impact",
                        "title": "影响与动作",
                        "goal": "结合工具结果写出影响传导和动作建议。",
                        "target_words": 360,
                        "template_id": "policy_dynamics",
                        "template_title": "影响与动作",
                        "writing_instruction": "先写影响传导，再写动作建议。",
                    }
                ]
            }
        )
        with patch("src.report.deep_report.deep_writer._get_llm_client", return_value=_DummyLLM()), patch(
            "src.report.deep_report.deep_writer.create_deep_agent",
            side_effect=lambda **kwargs: _DummyAgent(kwargs["tools"], kwargs["name"]),
        ):
            draft_bundle_v2 = compile_draft_units_with_llm(ir, section_plan, scene)

        metadata = draft_bundle_v2.metadata
        self.assertEqual(metadata["selected_template"]["template_id"], "policy_dynamics")
        self.assertFalse(metadata["degraded_sections"])
        self.assertEqual(len(metadata["section_generation_receipts"]), 1)
        self.assertEqual(
            metadata["section_generation_receipts"][0]["tool_names"],
            ["get_report_template", "artifact_search", "evidence_search", "build_section_packet"],
        )

    def test_llm_deep_writer_marks_empty_section_output_as_degraded(self):
        class _DummyAgent:
            def invoke(self, *_args, **_kwargs):
                return {"messages": [{"content": ""}]}

        class _DummyLLM:
            def with_structured_output(self, schema):
                class _Structured:
                    def invoke(self, _messages):
                        return schema(
                            section_id="focus",
                            claim_refs=[],
                            evidence_refs=[],
                            notes="trace_extraction_failed",
                            confidence=0.0,
                        )

                return _Structured()

        bundle = sample_structured_payload()
        manifest = build_artifact_manifest(
            topic_identifier="demo-topic-writer-degraded",
            thread_id="report::demo-topic-writer-degraded::2025-01-01::2025-01-31",
            task_id="task-writer-degraded",
            structured_path="structured.json",
            ir_path="report_ir.json",
        )
        ir = build_report_ir(bundle, artifact_manifest=manifest, task_id="task-writer-degraded")
        scene = CompilerSceneProfile(
            scene_id="public_hotspot",
            scene_label="公共热点场景",
            template_id="public_hotspot",
            template_name="public_hotspot",
            template_path="public_hotspot.md",
        )
        section_plan = SectionPlan.model_validate(
            {
                "sections": [
                    {
                        "section_id": "focus",
                        "title": "核心焦点与情绪",
                        "goal": "拆解议题重心和情绪结构。",
                        "target_words": 320,
                        "template_id": "public_hotspot",
                        "template_title": "核心焦点与情绪",
                        "writing_instruction": "情绪必须附着在具体议题上。",
                    }
                ]
            }
        )
        with patch("src.report.deep_report.deep_writer._get_llm_client", return_value=_DummyLLM()), patch(
            "src.report.deep_report.deep_writer.create_deep_agent",
            return_value=_DummyAgent(),
        ):
            bundle = compile_draft_units_with_llm(ir, section_plan, scene)

        self.assertTrue(bundle.metadata["degraded_sections"])
        self.assertEqual(bundle.metadata["degraded_sections"][0]["reason"], "empty_markdown_body")

    def test_free_writer_template_brief_preserves_template_order_and_guides(self):
        scene = CompilerSceneProfile(
            scene_id="policy_dynamics",
            scene_label="政策行业场景",
            template_id="policy_dynamics",
            template_name="policy_dynamics",
            template_path="policy_dynamics.md",
            matched_reasons=["行业政策波动"],
        )
        section_plan = SectionPlan.model_validate(
            {
                "sections": [
                    {
                        "section_id": "summary",
                        "title": "摘要",
                        "goal": "概括核心判断。说明边界。",
                        "target_words": 260,
                        "template_id": "policy_dynamics",
                        "template_title": "摘要",
                        "writing_instruction": "先写态势，再写分歧。",
                    },
                    {
                        "section_id": "impact",
                        "title": "影响与动作",
                        "goal": "说明影响传导。提出动作建议。",
                        "target_words": 360,
                        "template_id": "policy_dynamics",
                        "template_title": "影响与动作",
                        "writing_instruction": "建议必须对应风险。",
                    },
                ]
            }
        )

        brief = build_template_brief(section_plan, scene, {"topic": "控烟舆情", "counts": {"claims": 3}})

        self.assertEqual(brief["writing_mode"], "section_markdown_first")
        self.assertEqual(brief["section_order"], ["summary", "impact"])
        self.assertIn("概括核心判断", "".join(brief["sections"][0]["must_cover"]))
        self.assertEqual(brief["template"]["template_id"], "policy_dynamics")

    def test_section_markdown_flow_preserves_section_order_and_search_receipts(self):
        class _DummyAgent:
            def __init__(self, tools, name):
                self.tools = {tool.name: tool for tool in tools}
                self.name = name

            def invoke(self, *_args, **_kwargs):
                self.tools["artifact_search"].invoke(
                    {"query": "影响 争议", "scope": "report_ir template_brief", "section_goal": "影响传导"}
                )
                self.tools["evidence_search"].invoke(
                    {"query": "质疑 执行", "section_goal": "动作建议", "platforms": "微博", "limit": 4}
                )
                self.tools["build_section_packet"].invoke(
                    {"section_id": "impact", "section_goal": "说明影响传导和动作建议。", "evidence_ids_json": json.dumps(["ev-1", "ev-2"], ensure_ascii=False)}
                )
                if self.name.endswith(":summary"):
                    return {"messages": [{"content": "整体舆论围绕执行影响和回应节奏展开，讨论焦点较为集中。"}]}
                return {"messages": [{"content": "争议主要集中在执行安排和回应时点，建议优先补足解释口径并设置后续跟进节奏。"}]}

        class _DummyLLM:
            def with_structured_output(self, schema):
                class _Structured:
                    def invoke(self, messages):
                        content = str(messages[-1].content)
                        if "section_id=summary" in content:
                            return schema(section_id="summary", claim_refs=["claimrec-1"], evidence_refs=["ev-1"], notes="摘要保留审慎语气。", confidence=0.81)
                        return schema(section_id="impact", claim_refs=["claimrec-1"], evidence_refs=["ev-1", "ev-2"], notes="动作建议与影响传导绑定。", confidence=0.91)

                return _Structured()

        bundle = sample_structured_payload()
        manifest = build_artifact_manifest(
            topic_identifier="demo-topic-whole-doc",
            thread_id="report::demo-topic-whole-doc::2025-01-01::2025-01-31",
            task_id="task-whole-doc",
            structured_path="structured.json",
            ir_path="report_ir.json",
        )
        ir = build_report_ir(bundle, artifact_manifest=manifest, task_id="task-whole-doc")
        scene = CompilerSceneProfile(
            scene_id="policy_dynamics",
            scene_label="政策行业场景",
            template_id="policy_dynamics",
            template_name="policy_dynamics",
            template_path="policy_dynamics.md",
        )
        section_plan = SectionPlan.model_validate(
            {
                "sections": [
                    {
                        "section_id": "summary",
                        "title": "摘要",
                        "goal": "概括核心判断。",
                        "target_words": 220,
                        "template_id": "policy_dynamics",
                        "template_title": "摘要",
                        "writing_instruction": "先写态势，再写边界。",
                    },
                    {
                        "section_id": "impact",
                        "title": "影响与动作",
                        "goal": "说明影响传导并提出动作建议。",
                        "target_words": 320,
                        "template_id": "policy_dynamics",
                        "template_title": "影响与动作",
                        "writing_instruction": "建议必须对应风险。",
                    },
                ]
            }
        )

        with patch("src.report.deep_report.deep_writer._get_llm_client", return_value=_DummyLLM()), patch(
            "src.report.deep_report.deep_writer.create_deep_agent",
            side_effect=lambda **kwargs: _DummyAgent(kwargs["tools"], kwargs["name"]),
        ):
            draft_bundle_v2 = compile_draft_units_with_llm(ir, section_plan, scene)

        self.assertEqual(draft_bundle_v2.section_order, ["summary", "impact"])
        self.assertEqual(draft_bundle_v2.metadata["writing_mode"], "section_markdown_first")
        self.assertTrue(draft_bundle_v2.metadata["artifact_search_receipts"])
        self.assertTrue(draft_bundle_v2.metadata["evidence_search_receipts"])
        self.assertEqual(draft_bundle_v2.metadata["section_generation_receipts"][1]["tool_names"], ["get_report_template", "artifact_search", "evidence_search", "build_section_packet"])
        self.assertGreaterEqual(draft_bundle_v2.metadata["editor_receipt"]["transition_inserted"], 1)

    def test_section_markdown_writer_accepts_plain_markdown_output(self):
        class _DummyAgent:
            def invoke(self, *_args, **_kwargs):
                return {"messages": [{"content": "## 摘要\n整体判断以政策执行和公众接受度的拉扯为主线。"}]}

        class _DummyLLM:
            def with_structured_output(self, schema):
                class _Structured:
                    def invoke(self, _messages):
                        return schema(section_id="summary", claim_refs=["claimrec-1"], evidence_refs=["ev-1"], notes="", confidence=0.7)

                return _Structured()

        bundle = sample_structured_payload()
        manifest = build_artifact_manifest(
            topic_identifier="demo-topic-invalid-json",
            thread_id="report::demo-topic-invalid-json::2025-01-01::2025-01-31",
            task_id="task-invalid-json",
            structured_path="structured.json",
            ir_path="report_ir.json",
        )
        ir = build_report_ir(bundle, artifact_manifest=manifest, task_id="task-invalid-json")
        scene = CompilerSceneProfile(
            scene_id="policy_dynamics",
            scene_label="政策行业场景",
            template_id="policy_dynamics",
            template_name="policy_dynamics",
            template_path="policy_dynamics.md",
        )
        section_plan = SectionPlan.model_validate(
            {
                "sections": [
                    {
                        "section_id": "summary",
                        "title": "摘要",
                        "goal": "概括核心判断。",
                        "target_words": 220,
                        "template_id": "policy_dynamics",
                        "template_title": "摘要",
                    }
                ]
            }
        )

        with patch("src.report.deep_report.deep_writer._get_llm_client", return_value=_DummyLLM()), patch(
            "src.report.deep_report.deep_writer.create_deep_agent",
            return_value=_DummyAgent(),
        ):
            bundle = compile_draft_units_with_llm(ir, section_plan, scene)

        self.assertEqual(bundle.section_order, ["summary"])
        finding_units = [unit for unit in bundle.units if unit.section_id == "summary" and unit.unit_type == "finding"]
        self.assertTrue(finding_units)
        self.assertIn("整体判断以政策执行和公众接受度的拉扯为主线", finding_units[0].text)
        self.assertEqual(bundle.metadata["section_generation_receipts"][0]["section_id"], "summary")

    def test_recommendation_units_remain_traceable_without_support_claims(self):
        structured = sample_structured_payload()
        structured["suggested_actions"] = [
            {
                "action_id": "act-1",
                "action": "补充回应口径",
                "rationale": "降低争议外溢风险。",
                "priority": "high",
                "citation_ids": [],
            }
        ]
        manifest = build_artifact_manifest(
            topic_identifier="demo-topic",
            thread_id="report::demo-topic::2025-01-01::2025-01-31",
            task_id="task-4b",
            structured_path="structured.json",
            ir_path="report_ir.json",
        )
        ir = build_report_ir(structured, artifact_manifest=manifest, task_id="task-4b")
        scene = select_scene_profile(ir)
        style = resolve_style_profile(ir, scene)
        layout = build_layout_plan(ir, scene, style)
        budget = build_section_budget(ir, scene, layout)
        draft_bundle = compile_draft_units(ir, build_section_plan(ir, layout, budget))

        recommendation_units = [unit for unit in draft_bundle.units if unit.section_role == "recommendations" and not unit.text.startswith("## ")]
        self.assertTrue(recommendation_units)
        self.assertTrue(all(unit.trace_ids for unit in recommendation_units))
        conformance = run_factual_conformance(ir, draft_bundle)
        self.assertTrue(conformance.passed)

    def test_report_ir_registers_supplemental_evidence_refs_for_traceability(self):
        bundle = sample_bundle().model_dump()
        bundle["mechanism_summary"]["phase_shifts"][0]["evidence_refs"] = ["ev-extra"]
        manifest = build_artifact_manifest(
            topic_identifier="demo-topic",
            thread_id="report::demo-topic::2025-01-01::2025-01-31",
            task_id="task-4c",
            structured_path="structured.json",
            ir_path="report_ir.json",
        )
        ir = build_report_ir(bundle, artifact_manifest=manifest, task_id="task-4c")
        self.assertTrue(any(entry.evidence_id == "ev-extra" for entry in ir.evidence_ledger.entries))
        scene = select_scene_profile(ir)
        style = resolve_style_profile(ir, scene)
        layout = build_layout_plan(ir, scene, style)
        budget = build_section_budget(ir, scene, layout)
        draft_bundle = compile_draft_units(ir, build_section_plan(ir, layout, budget))
        conformance = run_factual_conformance(ir, draft_bundle)
        self.assertTrue(conformance.passed)

    def test_evidence_source_id_survives_into_report_ir(self):
        bundle = sample_bundle().model_dump()
        bundle["key_evidence"][0]["source_id"] = r"F:\opinion-system\backend\data\projects\demo-topic\fetch\2025-01-01_2025-01-31\总体.jsonl:42"
        manifest = build_artifact_manifest(
            topic_identifier="demo-topic",
            thread_id="report::demo-topic::2025-01-01::2025-01-31",
            task_id="task-4d",
            structured_path="structured.json",
            ir_path="report_ir.json",
        )
        ir = build_report_ir(bundle, artifact_manifest=manifest, task_id="task-4d")
        entry = next(item for item in ir.evidence_ledger.entries if item.evidence_id == "ev-1")
        self.assertEqual(entry.source_id, bundle["key_evidence"][0]["source_id"])

    def test_final_markdown_is_traceable_to_report_ir(self):
        bundle = sample_structured_payload()
        manifest = build_artifact_manifest(
            topic_identifier="demo-topic",
            thread_id="report::demo-topic::2025-01-01::2025-01-31",
            task_id="task-5",
            structured_path="structured.json",
            ir_path="report_ir.json",
        )
        ir = build_report_ir(bundle, artifact_manifest=manifest, task_id="task-5")
        scene = select_scene_profile(ir)
        style = resolve_style_profile(ir, scene)
        layout = build_layout_plan(ir, scene, style)
        budget = build_section_budget(ir, scene, layout)
        writer_context = assemble_writer_context(ir, scene, style, layout, budget)
        draft_bundle = compile_draft_units(ir, build_section_plan(ir, layout, budget))
        styled = run_stylistic_rewrite(ir, draft_bundle, writer_context)
        self.assertEqual(styled.rewrite_policy, "presentation_only")
        self.assertTrue(styled.semantic_fields_locked)
        self.assertTrue(isinstance(styled.rewrite_ops, list))
        finalized = render_final_markdown(ir, styled, layout, title="示例专题")
        conformance = run_factual_conformance(ir, finalized)
        self.assertTrue(conformance.passed)
        self.assertIn("## 事实断言", finalized)
        self.assertIn("## 冲突与收敛", finalized)
        self.assertIn("## 传播机制", finalized)
        self.assertIn("::figure{ref=", finalized)
        self.assertTrue(finalized.startswith("# 示例专题"))
        self.assertEqual(styled.policy_version, "policy.v2")
        self.assertTrue(all(diff.ops for diff in styled.rewrite_diffs))

    def test_build_full_payload_exposes_template_and_generation_receipts(self):
        structured = sample_structured_payload()
        payload = build_full_payload(
            structured,
            "# 示例专题\n\n## 摘要\n\n这是一段完整正文。",
            cache_version=5,
            draft_bundle={"units": [], "section_order": []},
            draft_bundle_v2={
                "units": [],
                "section_order": [],
                "metadata": {
                    "selected_template": {
                        "template_id": "policy_dynamics",
                        "template_name": "policy_dynamics",
                        "template_path": "policy_dynamics.md",
                        "scene_id": "policy_dynamics",
                        "scene_label": "政策行业场景",
                        "score": 9.2,
                        "matched_reasons": ["存在政策/治理信号: 控烟"],
                    },
                    "section_generation_receipts": [{"section_id": "summary", "tool_names": ["retrieve_evidence_cards"]}],
                    "degraded_sections": [{"section_id": "action", "reason": "质量不足"}],
                },
            },
            styled_draft_bundle={"units": [], "rewrite_ops": []},
            factual_conformance={"passed": True},
            scene_profile={"template_id": "policy_dynamics"},
        )

        self.assertEqual(payload["selected_template"]["template_id"], "policy_dynamics")
        self.assertEqual(payload["template_match_reasons"], ["存在政策/治理信号: 控烟"])
        self.assertTrue(payload["has_markdown_output"])
        self.assertEqual(payload["compile_quality"], "degraded")
        self.assertEqual(payload["publish_status"], "ready")
        self.assertEqual(payload["section_write_receipts"][0]["section_id"], "summary")
        self.assertEqual(payload["section_generation_receipts"][0]["tool_names"], ["retrieve_evidence_cards"])
        self.assertEqual(payload["degraded_sections"][0]["section_id"], "action")
        self.assertEqual(payload["meta"]["section_write_receipts"][0]["section_id"], "summary")
        self.assertEqual(payload["meta"]["publish_status"], "ready")

    def test_markdown_conformance_ignores_non_prefix_brackets(self):
        bundle = sample_structured_payload()
        manifest = build_artifact_manifest(
            topic_identifier="demo-topic",
            thread_id="report::demo-topic::2025-01-01::2025-01-31",
            task_id="task-5b",
            structured_path="structured.json",
            ir_path="report_ir.json",
        )
        ir = build_report_ir(bundle, artifact_manifest=manifest, task_id="task-5b")
        markdown = "\n".join(
            [
                "# 示例专题",
                "",
                "## 传播机制",
                "- [ev-1] 2025-01-10[约战] 第一把，平台用户继续扩散相关讨论。",
            ]
        )
        conformance = run_factual_conformance(ir, markdown)
        self.assertTrue(conformance.passed)
        self.assertFalse(any("约战" in list(getattr(issue, "trace_ids", []) or []) for issue in conformance.issues))

    def test_compile_markdown_artifacts_keeps_fallback_recompile_as_non_blocking_metadata(self):
        bundle = sample_bundle().model_dump()
        bundle["utility_assessment"] = {
            "assessment_id": "utility-1",
            "has_object_scope": True,
            "has_time_window": True,
            "has_key_actors": False,
            "has_conditional_risk": True,
            "has_actionable_recommendations": False,
            "has_uncertainty_boundary": False,
            "recommendation_has_object": False,
            "recommendation_has_time": False,
            "recommendation_has_action": False,
            "recommendation_has_preconditions": False,
            "recommendation_has_side_effects": False,
            "missing_dimensions": ["key_actors", "actionable_recommendations", "uncertainty_boundary"],
            "fallback_trace": [{"dimension": "actionable_recommendations", "suggested_pass": "compile_recommendation_units"}],
            "decision": "fallback_recompile",
            "next_action": "先补 recommendation 结构，再进入正式文稿编译。",
            "confidence": 0.62,
        }
        structured = sample_structured_payload(ReportDataBundle.model_validate(bundle))
        manifest = build_artifact_manifest(
            topic_identifier="demo-topic-gate",
            thread_id="report::demo-topic-gate::2025-01-01::2025-01-31",
            task_id="task-gate",
            structured_path="structured.json",
            ir_path="report_ir.json",
            figure_artifacts=structured["figure_artifacts"],
        )
        enriched = attach_report_ir(structured, artifact_manifest=manifest, task_id="task-gate")
        with patch(
            "src.report.deep_report.presenter.run_report_compilation_graph",
            return_value={
                "markdown": "# 示例专题\n\n## 摘要\n保留 markdown 主输出。",
                "factual_conformance": {
                    "passed": True,
                    "policy_version": "policy.v2",
                    "stage": "final_markdown",
                    "can_auto_recover": False,
                    "requires_human_review": False,
                    "issues": [],
                    "semantic_deltas": [],
                    "metadata": {},
                },
                "review_required": False,
                "compile_quality": "degraded",
                "publish_status": "ready",
            },
        ):
            compiled = compile_markdown_artifacts(enriched)

        self.assertEqual(compiled["utility_assessment"]["decision"], "fallback_recompile")
        self.assertEqual(compiled["compile_quality"], "degraded")
        self.assertEqual(compiled["publish_status"], "ready")
        self.assertFalse(compiled["review_required"])

    def test_compile_markdown_artifacts_exposes_draft_bundle_and_conformance(self):
        structured = sample_structured_payload()
        manifest = build_artifact_manifest(
            topic_identifier="demo-topic",
            thread_id="report::demo-topic::2025-01-01::2025-01-31",
            task_id="task-6",
            structured_path="structured.json",
            draft_path="draft.json",
            full_path="full.json",
            ir_path="report_ir.json",
            figure_artifacts=structured["figure_artifacts"],
        )
        enriched = attach_report_ir(structured, artifact_manifest=manifest, task_id="task-6")
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
                "validation_result_v2": {"passed": True, "failures": [], "patchable_failures": [], "gate": "pass", "repair_count": 0, "next_node": "markdown_compiler"},
                "repair_plan_v2": {"patches": [], "blocked_failures": [], "metadata": {}},
                "graph_state_v2": {"current_node": "artifact_renderer", "repair_count": 0},
                "factual_conformance": {
                    "passed": True,
                    "policy_version": "policy.v2",
                    "stage": "final_markdown",
                    "can_auto_recover": False,
                    "requires_human_review": False,
                    "issues": [],
                    "semantic_deltas": [],
                    "metadata": {},
                },
                "review_required": False,
                "markdown": "# 示例专题",
                "utility_assessment": {"decision": "pass"},
            },
        ):
            compiled = compile_markdown_artifacts(enriched)
        self.assertIn("draft_bundle", compiled)
        self.assertIn("draft_bundle_v2", compiled)
        self.assertIn("validation_result_v2", compiled)
        self.assertIn("graph_state_v2", compiled)
        self.assertIn("factual_conformance", compiled)
        self.assertTrue(compiled["factual_conformance"]["passed"])
        self.assertEqual(compiled["draft_bundle"]["source_artifact_id"], "draft_bundle")
        self.assertEqual(compiled["policy_registry"]["policy_version"], "policy.v2")
        self.assertEqual(compiled["draft_bundle_v2"]["source_artifact_id"], "draft_bundle.v2")

    def test_compile_markdown_artifacts_allows_review_pending_from_graph_gate(self):
        structured = sample_structured_payload()
        manifest = build_artifact_manifest(
            topic_identifier="demo-topic",
            thread_id="report::demo-topic::2025-01-01::2025-01-31",
            task_id="task-review",
            structured_path="structured.json",
            draft_path="draft.json",
            ir_path="report_ir.json",
            figure_artifacts=structured["figure_artifacts"],
        )
        enriched = attach_report_ir(structured, artifact_manifest=manifest, task_id="task-review")
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
                "validation_result_v2": {"passed": True, "failures": [], "patchable_failures": [], "gate": "pass", "repair_count": 0, "next_node": "markdown_compiler"},
                "repair_plan_v2": {"patches": [], "blocked_failures": [], "metadata": {}},
                "graph_state_v2": {"current_node": "artifact_renderer", "repair_count": 0},
                "factual_conformance": {
                    "passed": False,
                    "policy_version": "policy.v2",
                    "stage": "final_markdown",
                    "can_auto_recover": False,
                    "requires_human_review": True,
                    "issues": [
                        {
                            "issue_id": "semantic-review",
                            "issue_type": "semantic_drift",
                            "message": "需要人工复核",
                            "section_role": "claims",
                            "sentence": "示例句",
                            "trace_ids": [],
                            "suggested_action": "review",
                        }
                    ],
                    "semantic_deltas": [],
                    "metadata": {},
                },
                "review_required": True,
                "markdown": "# 示例专题\n\n## 主体与立场\n- [sub-1] 舆论普遍反对当前安排。",
                "utility_assessment": {"decision": "pass"},
            },
        ):
            compiled = compile_markdown_artifacts(enriched, allow_review_pending=True)
        self.assertTrue(compiled["review_required"])
        self.assertFalse(compiled["factual_conformance"]["passed"])
        self.assertTrue(compiled["factual_conformance"]["requires_human_review"])

    def test_artifact_manifest_lineage_expands_with_draft_bundle(self):
        _, _, figure_artifacts, _ = sample_figure_pipeline()
        base_manifest = build_artifact_manifest(
            topic_identifier="demo-topic",
            thread_id="report::demo-topic::2025-01-01::2025-01-31",
            task_id="task-7",
            structured_path="structured-v1.json",
            ir_path="report_ir-v1.json",
            figure_artifacts=[item.model_dump() for item in figure_artifacts],
        )
        next_manifest = build_artifact_manifest(
            topic_identifier="demo-topic",
            thread_id="report::demo-topic::2025-01-01::2025-01-31",
            task_id="task-7",
            structured_path="structured-v1.json",
            draft_path="draft-v1.json",
            full_path="full-v1.json",
            ir_path="report_ir-v1.json",
            figure_artifacts=[item.model_dump() for item in figure_artifacts],
            previous_manifest=base_manifest,
        )
        self.assertEqual(next_manifest.full_markdown.derived_from, ["draft_bundle", "ir"])
        self.assertEqual(next_manifest.draft_bundle.status, "ready")
        self.assertGreaterEqual(len(next_manifest.versions), len(base_manifest.versions))
        self.assertEqual(next_manifest.full_markdown.policy_version, "policy.v1")
        self.assertTrue(next_manifest.figures)
        self.assertEqual(next_manifest.figures[0].version, 1)

    def test_novel_claim_regression_flags_untraceable_markdown(self):
        bundle = sample_bundle().model_dump()
        manifest = build_artifact_manifest(
            topic_identifier="demo-topic",
            thread_id="report::demo-topic::2025-01-01::2025-01-31",
            task_id="task-8",
            structured_path="structured.json",
            ir_path="report_ir.json",
        )
        ir = build_report_ir(bundle, artifact_manifest=manifest, task_id="task-8")
        conformance = run_factual_conformance(ir, "# 示例专题\n\n## 执行摘要\n这是一个没有 trace 的新句子。")
        self.assertFalse(conformance.passed)
        self.assertEqual(conformance.issues[0].issue_type, "untraceable_sentence")

    def test_strength_escalation_is_rejected(self):
        bundle = sample_bundle().model_dump()
        manifest = build_artifact_manifest(
            topic_identifier="demo-topic",
            thread_id="report::demo-topic::2025-01-01::2025-01-31",
            task_id="task-9",
            structured_path="structured.json",
            ir_path="report_ir.json",
        )
        ir = build_report_ir(bundle, artifact_manifest=manifest, task_id="task-9")
        markdown = "# 示例专题\n\n## 主体与立场\n- [sub-1] 舆论普遍反对当前安排。"
        with patch("src.report.deep_report.compiler.extract_semantic_state", side_effect=fake_semantic_state_for_text):
            conformance = run_factual_conformance(ir, markdown)
        self.assertFalse(conformance.passed)
        self.assertIn("strength_escalation", [item.issue_type for item in conformance.issues])
        self.assertTrue(any(delta.direction == "up" for delta in conformance.semantic_deltas))

    def test_recommendation_boundary_violation_is_rejected(self):
        bundle = sample_bundle().model_dump()
        manifest = build_artifact_manifest(
            topic_identifier="demo-topic",
            thread_id="report::demo-topic::2025-01-01::2025-01-31",
            task_id="task-10",
            structured_path="structured.json",
            ir_path="report_ir.json",
        )
        ir = build_report_ir(bundle, artifact_manifest=manifest, task_id="task-10")
        markdown = "# 示例专题\n\n## 建议动作\n- [claim:ev-1] 必须立即启动强制处置。"
        with patch("src.report.deep_report.compiler.extract_semantic_state", side_effect=fake_semantic_state_for_text):
            conformance = run_factual_conformance(ir, markdown)
        self.assertFalse(conformance.passed)
        self.assertIn("recommendation_boundary_violation", [item.issue_type for item in conformance.issues])

    def test_claim_gate_violation_is_rejected(self):
        bundle = sample_bundle().model_dump()
        manifest = build_artifact_manifest(
            topic_identifier="demo-topic",
            thread_id="report::demo-topic::2025-01-01::2025-01-31",
            task_id="task-11",
            structured_path="structured.json",
            ir_path="report_ir.json",
        )
        ir = build_report_ir(bundle, artifact_manifest=manifest, task_id="task-11")
        markdown = "# 示例专题\n\n## 事实断言\n- [claim:uv-1] 该截图已证明存在主动策划。"
        with patch("src.report.deep_report.compiler.extract_semantic_state", side_effect=fake_semantic_state_for_text):
            conformance = run_factual_conformance(ir, markdown)
        self.assertFalse(conformance.passed)
        self.assertIn("claim_gate_violation", [item.issue_type for item in conformance.issues])

    def test_policy_registry_exposes_semantic_lattice_and_allowed_rewrite_ops(self):
        registry = build_conformance_policy_registry()
        self.assertEqual(registry.policy_version, "policy.v2")
        self.assertIn("assertion_certainty", registry.strength_escalation)
        self.assertIn("paragraph_to_list", registry.allowed_rewrite_ops)
        self.assertIn("generalize_public_opinion", registry.disallowed_rewrite_ops)
        self.assertIn("evidence_coverage", registry.strength_escalation)

    def test_retrieval_plan_payload_exposes_router_facets_and_dispatch_plan(self):
        normalized = normalize_task_payload(
            task_text="示例专题 舆情分析",
            topic_identifier="demo-topic",
            start="2025-01-01",
            end="2025-01-31",
            mode="research",
            hints_json='{"entities":["平台用户"],"platform_scope":["微博","视频"]}',
        )
        payload = build_retrieval_plan_payload(
            normalized_task_json='{"normalized_task": %s}' % json.dumps(normalized["normalized_task"], ensure_ascii=False),
            intent="timeline",
        )
        result = payload["result"]
        self.assertTrue(result["router_facets"])
        self.assertEqual(result["dispatch_plan"]["dispatches"][0]["specialist_target"], "timeline_analyst")
        self.assertEqual(result["dispatch_plan"]["policy_version"], "policy.v2")

    def test_semantic_review_payload_exposes_typed_deltas_and_rewrite_ops(self):
        compiled = {
            "styled_draft_bundle": {
                "rewrite_ops": ["compress", "lexical_soften"],
            },
            "factual_conformance": {
                "policy_version": "policy.v2",
                "issues": [
                    {
                        "issue_id": "unit:actors:1",
                        "issue_type": "strength_escalation",
                        "message": "语义上调",
                        "section_role": "actors",
                        "semantic_dimension": "scope_quantifier",
                        "before_level": "partial",
                        "after_level": "universal",
                    }
                ],
                "semantic_deltas": [
                    {
                        "dimension": "scope_quantifier",
                        "before_level": "partial",
                        "after_level": "universal",
                        "direction": "up",
                        "locked": True,
                    }
                ],
            },
        }
        payload = _build_semantic_review_payload(
            thread_id="thread-1",
            task_id="task-1",
            compiled=compiled,
            artifact_manifest={"structured_projection": {}, "ir": {}, "draft_bundle": {}, "approval_records": {}},
        )
        self.assertEqual(payload.policy_version, "policy.v2")
        self.assertTrue(payload.offending_unit_ids)
        self.assertTrue(payload.semantic_deltas)
        self.assertEqual(payload.allowed_rewrite_ops, ["compress", "lexical_soften"])
        self.assertIn("人工批注", payload.suggested_actions[-1])

    def test_generate_full_report_payload_returns_waiting_approval_when_semantic_review_is_required(self):
        structured = sample_structured_payload()
        manifest = build_artifact_manifest(
            topic_identifier="demo-topic-review",
            thread_id="report::demo-topic-review::2025-01-01::2025-01-31",
            task_id="task-review-service",
            structured_path="structured.json",
            ir_path="report_ir.json",
            figure_artifacts=structured["figure_artifacts"],
        )
        enriched = attach_report_ir(structured, artifact_manifest=manifest, task_id="task-review-service")
        compiled = {
            "draft_bundle": {"source_artifact_id": "draft_bundle", "policy_version": "policy.v2", "units": [], "section_order": [], "metadata": {}},
            "styled_draft_bundle": {"policy_version": "policy.v2", "units": [], "section_order": [], "style_id": "evidence_first", "rewrite_policy": "presentation_only", "rewrite_ops": [], "semantic_fields_locked": True, "rewrite_diffs": [], "metadata": {}},
            "factual_conformance": {"passed": False, "policy_version": "policy.v2", "stage": "final_markdown", "can_auto_recover": False, "requires_human_review": True, "issues": [{"issue_id": "issue-1", "issue_type": "strength_escalation", "message": "语义上调", "section_role": "actors", "sentence": "舆论普遍反对", "trace_ids": ["sub-1"], "semantic_dimension": "scope_quantifier", "before_level": "partial", "after_level": "universal", "severity": "high", "suggested_action": "降级"}], "semantic_deltas": [{"dimension": "scope_quantifier", "before_level": "partial", "after_level": "universal", "direction": "up", "locked": True}], "metadata": {}},
            "review_required": True,
            "markdown": "# 示例专题\n\n## 主体与立场\n- [sub-1] 舆论普遍反对当前安排。",
        }
        with patch("src.report.deep_report.service.compile_markdown_artifacts", return_value=compiled):
            payload = generate_full_report_payload(
                "demo-topic-review",
                "2025-01-01",
                "2025-01-31",
                topic_label="示例专题",
                regenerate=True,
                structured_payload=enriched,
                task_id="task-review-service",
                thread_id="report::demo-topic-review::2025-01-01::2025-01-31",
            )
        self.assertEqual(payload["status"], "waiting_approval")
        self.assertEqual(payload["approvals"][0]["tool_name"], "graph_interrupt")
        self.assertEqual(payload["approvals"][0]["action"]["review_mode"], "annotation")
        self.assertIn("只读", payload["approvals"][0]["action"]["review_prompt"])
        self.assertEqual(payload["artifact_manifest"]["approval_records"]["status"], "ready")
        self.assertTrue(payload["semantic_interrupt"]["semantic_deltas"])
        self.assertTrue(payload["approval_records"])


if __name__ == "__main__":
    unittest.main()
