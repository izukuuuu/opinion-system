"""Tests for section-markdown deep_writer helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.report.deep_report.deep_writer import build_template_brief, light_edit_draft_bundle
from src.report.deep_report.schemas import (
    CompilerSceneProfile,
    DraftBundleV2,
    DraftUnitV2,
    SectionPlan,
    TraceRef,
)


class TestDeepWriter(unittest.TestCase):
    def test_build_template_brief_preserves_section_order(self):
        scene = CompilerSceneProfile(
            scene_id="policy_dynamics",
            scene_label="政策行业场景",
            template_id="policy_dynamics",
            template_name="policy_dynamics",
            template_path="policy_dynamics.md",
        )
        plan = SectionPlan.model_validate(
            {
                "sections": [
                    {
                        "section_id": "summary",
                        "title": "摘要",
                        "goal": "概括核心判断。说明边界。",
                        "target_words": 220,
                    },
                    {
                        "section_id": "impact",
                        "title": "影响与动作",
                        "goal": "说明影响传导。提出动作建议。",
                        "target_words": 320,
                        "writing_instruction": "建议必须对应风险。",
                    },
                ]
            }
        )

        brief = build_template_brief(plan, scene, {"topic": "示例专题"})

        self.assertEqual(brief["writing_mode"], "section_markdown_first")
        self.assertEqual(brief["section_order"], ["summary", "impact"])
        self.assertIn("概括核心判断", "".join(brief["sections"][0]["must_cover"]))

    def test_light_edit_draft_bundle_inserts_transition(self):
        plan = SectionPlan.model_validate(
            {
                "sections": [
                    {"section_id": "summary", "title": "摘要", "goal": "概括判断。", "target_words": 200},
                    {"section_id": "impact", "title": "影响与动作", "goal": "说明影响。", "target_words": 300},
                ]
            }
        )
        bundle = DraftBundleV2(
            source_artifact_id="draft_bundle.llm.v2",
            policy_version="policy.v2",
            schema_version="draft-bundle.llm.v2",
            section_order=["summary", "impact"],
            units=[
                DraftUnitV2(
                    unit_id="unit:summary:heading",
                    section_id="summary",
                    unit_type="heading",
                    text="## 摘要",
                    trace_refs=[TraceRef(trace_id="summary", trace_kind="section_context", support_level="structural")],
                    derived_from=[],
                    support_level="structural",
                    render_template_id="summary:heading",
                    metadata={},
                ),
                DraftUnitV2(
                    unit_id="unit:summary:finding",
                    section_id="summary",
                    unit_type="finding",
                    text="摘要正文。",
                    trace_refs=[TraceRef(trace_id="claim-1", trace_kind="claim", support_level="direct")],
                    derived_from=["claim-1"],
                    support_level="aggregated",
                    render_template_id="summary:finding",
                    metadata={},
                ),
                DraftUnitV2(
                    unit_id="unit:impact:heading",
                    section_id="impact",
                    unit_type="heading",
                    text="## 影响与动作",
                    trace_refs=[TraceRef(trace_id="impact", trace_kind="section_context", support_level="structural")],
                    derived_from=[],
                    support_level="structural",
                    render_template_id="impact:heading",
                    metadata={},
                ),
                DraftUnitV2(
                    unit_id="unit:impact:finding",
                    section_id="impact",
                    unit_type="finding",
                    text="影响正文。",
                    trace_refs=[TraceRef(trace_id="claim-2", trace_kind="claim", support_level="direct")],
                    derived_from=["claim-2"],
                    support_level="aggregated",
                    render_template_id="impact:finding",
                    metadata={},
                ),
            ],
            metadata={},
        )

        edited = light_edit_draft_bundle(bundle, plan)

        transition_units = [unit for unit in edited.units if unit.unit_type == "transition"]
        self.assertEqual(len(transition_units), 1)
        self.assertIn("摘要", transition_units[0].text)
        self.assertEqual(edited.metadata["editor_receipt"]["editor_mode"], "light_transition_editor")


if __name__ == "__main__":
    unittest.main()
