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
from src.report.deep_report.payloads import build_retrieval_plan_payload, normalize_task_payload
from src.report.deep_report.document import build_figure_pipeline, build_report_document, load_report_blueprint, sanitize_report_document
from src.report.deep_report.presenter import build_full_payload, compile_markdown_artifacts, render_markdown
from src.report.deep_report.report_ir import attach_report_ir, build_artifact_manifest, build_report_ir
from src.report.deep_report.service import _build_semantic_review_payload, generate_full_report_payload
from src.report.deep_report.schemas import ReportDataBundle, ReportDocument, SemanticLatticeState


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

        self.assertEqual(scene.render_mode, "claim_anchored")
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

    def test_compile_markdown_artifacts_requires_utility_gate_pass(self):
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
        with self.assertRaisesRegex(ValueError, "UtilityAssessment requires fallback_recompile"):
            compile_markdown_artifacts(enriched)

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
        self.assertEqual(payload["artifact_manifest"]["approval_records"]["status"], "ready")
        self.assertTrue(payload["semantic_interrupt"]["semantic_deltas"])
        self.assertTrue(payload["approval_records"])


if __name__ == "__main__":
    unittest.main()
