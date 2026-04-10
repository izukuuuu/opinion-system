from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.report.deep_report.document import build_chart_catalog, build_report_document, sanitize_report_document
from src.report.deep_report.schemas import ReportDataBundle, ReportDocument


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
            "propagation_features": [
                {
                    "feature_id": "pf-1",
                    "dimension": "平台扩散",
                    "finding": "微博扩散最快",
                    "explanation": "微博在首轮峰值中起到扩散作用。",
                    "citation_ids": ["C1"],
                }
            ],
            "risk_judgement": [
                {
                    "risk_id": "risk-1",
                    "label": "争议延续",
                    "level": "medium",
                    "summary": "若缺少回应，争议可能持续。",
                    "citation_ids": ["C1"],
                }
            ],
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


class DeepReportDocumentTests(unittest.TestCase):
    def test_build_chart_catalog_has_stable_chart_ids(self):
        catalog = build_chart_catalog(sample_functions_payload())
        chart_ids = {item["chart_id"] for item in catalog}
        self.assertIn("volume:总体", chart_ids)
        self.assertIn("trends:微博", chart_ids)
        self.assertIn("trends:视频", chart_ids)
        self.assertIn("trends:trend-flow", chart_ids)
        self.assertIn("trends:trend-share", chart_ids)

    def test_build_report_document_validates_against_schema(self):
        bundle = sample_bundle()
        catalog = build_chart_catalog(sample_functions_payload())
        document = build_report_document(bundle, catalog, {"total_volume": 19})
        parsed = ReportDocument.model_validate(document)
        self.assertEqual(parsed.chart_catalog_version, 1)
        self.assertEqual([section.section_id for section in parsed.sections], [
            "core-dimensions",
            "lifecycle",
            "subjects-and-stance",
            "propagation-and-response",
        ])

    def test_sanitize_report_document_downgrades_missing_chart_slot(self):
        sanitized = sanitize_report_document(
            {
                "hero": {},
                "sections": [
                    {
                        "section_id": "demo",
                        "title": "Demo",
                        "blocks": [
                            {
                                "type": "chart_slot",
                                "block_id": "missing-chart",
                                "title": "缺图区块",
                                "description": "",
                                "chart_ids": ["volume:not-found"],
                            }
                        ],
                    }
                ],
                "appendix": {"blocks": []},
                "chart_catalog_version": 1,
            },
            [],
        )
        block = sanitized["sections"][0]["blocks"][0]
        self.assertEqual(block["type"], "callout")
        self.assertEqual(block["title"], "缺图区块")
        self.assertIn("自动降级", block["content"])


if __name__ == "__main__":
    unittest.main()
