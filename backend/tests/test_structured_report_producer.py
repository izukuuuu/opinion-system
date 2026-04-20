from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.report.deep_report.deterministic import build_runtime_workspace_layout
from src.report.deep_report.service import (
    _attach_ir_layers,
    _build_structured_seed_payload,
    _synthesize_structured_report_from_files,
    generate_full_report_payload,
)


def _file_payload(obj: object) -> dict:
    return {"content": json.dumps(obj, ensure_ascii=False)}


class StructuredReportProducerTests(unittest.TestCase):
    def _build_runtime_files(self) -> dict:
        layout = build_runtime_workspace_layout(
            project_identifier="demo-project",
            topic_identifier="demo-topic",
            start="2025-01-01",
            end="2025-01-31",
        )
        files = {
            layout.base_context_path: _file_payload({"project_identifier": "demo-project"}),
            layout.state_file("normalized_task.json"): _file_payload(
                {
                    "normalized_task": {
                        "task_id": "task-1",
                        "topic_identifier": "demo-topic",
                        "topic_label": "示例专题",
                        "time_range": {"start": "2025-01-01", "end": "2025-01-31"},
                        "mode": "fast",
                    },
                    "result": {
                        "task_id": "task-1",
                        "topic_identifier": "demo-topic",
                        "topic_label": "示例专题",
                        "time_range": {"start": "2025-01-01", "end": "2025-01-31"},
                        "mode": "fast",
                    },
                    "task_contract": {"contract_id": "contract-1"},
                    "task_derivation": {"derivation_id": "derive-1"},
                    "proposal_snapshot": {},
                }
            ),
            layout.state_file("evidence_cards.json"): _file_payload(
                {
                    "result": [
                        {
                            "evidence_id": "ev-1",
                            "source_id": "src-1",
                            "title": "政策征求意见发布",
                            "snippet": "卫健部门发布控烟征求意见稿，引发集中讨论。",
                            "content": "完整正文1",
                            "published_at": "2025-01-05",
                            "platform": "news",
                            "author": "媒体A",
                            "entity_tags": ["卫健部门"],
                            "stance_hint": "推动监管",
                            "confidence": 0.9,
                            "url": "https://example.com/1",
                        },
                        {
                            "evidence_id": "ev-2",
                            "source_id": "src-2",
                            "title": "行业协会回应",
                            "snippet": "行业协会认为执行口径仍待明确。",
                            "content": "完整正文2",
                            "published_at": "2025-01-08",
                            "platform": "weibo",
                            "author": "协会B",
                            "entity_tags": ["行业协会"],
                            "stance_hint": "审慎观望",
                            "confidence": 0.72,
                            "url": "https://example.com/2",
                        },
                        {
                            "evidence_id": "ev-3",
                            "source_id": "src-3",
                            "title": "公众讨论升温",
                            "snippet": "公众讨论聚焦校园周边禁售与执法尺度。",
                            "content": "完整正文3",
                            "published_at": "2025-01-10",
                            "platform": "forum",
                            "author": "用户C",
                            "entity_tags": ["公众"],
                            "stance_hint": "支持严格执行",
                            "confidence": 0.65,
                            "url": "https://example.com/3",
                        },
                    ]
                }
            ),
            layout.state_file("timeline_nodes.json"): _file_payload(
                {
                    "result": [
                        {
                            "node_id": "t-1",
                            "time_label": "2025-01-05",
                            "summary": "征求意见稿发布后讨论显著升温",
                            "support_evidence_ids": ["ev-1"],
                            "event_type": "policy_release",
                        }
                    ]
                }
            ),
            layout.state_file("actor_positions.json"): _file_payload(
                {
                    "result": [
                        {
                            "actor_id": "a-1",
                            "name": "卫健部门",
                            "role_type": "government",
                            "speaker_role": "发布方",
                            "stance": "支持加强控烟",
                            "stance_shift": "维持强监管口径",
                            "representative_evidence_ids": ["ev-1"],
                            "conflict_actor_ids": ["a-2"],
                        },
                        {
                            "actor_id": "a-2",
                            "name": "行业协会",
                            "role_type": "association",
                            "speaker_role": "回应方",
                            "stance": "要求明确配套口径",
                            "stance_shift": "强调执行成本",
                            "representative_evidence_ids": ["ev-2"],
                            "conflict_actor_ids": ["a-1"],
                        },
                    ]
                }
            ),
            layout.state_file("conflict_map.json"): _file_payload(
                {
                    "result": {
                        "claims": [
                            {"claim_id": "c-1", "proposition": "应立即扩大禁售范围"},
                            {"claim_id": "c-2", "proposition": "应先明确配套执行细则"},
                        ],
                        "edges": [
                            {
                                "edge_id": "edge-1",
                                "claim_a_id": "c-1",
                                "claim_b_id": "c-2",
                                "conflict_type": "direct_contradiction",
                                "actor_scope": ["卫健部门", "行业协会"],
                                "evidence_refs": ["ev-1", "ev-2"],
                            }
                        ],
                    }
                }
            ),
            layout.state_file("mechanism_summary.json"): _file_payload(
                {
                    "result": {
                        "amplification_paths": [
                            {
                                "path_id": "m-1",
                                "platform_sequence": ["news", "weibo", "forum"],
                                "evidence_refs": ["ev-1", "ev-3"],
                                "amplifier_type": "cross_platform",
                            }
                        ],
                        "confidence_summary": "主流媒体首发后进入社交平台扩散",
                    }
                }
            ),
            layout.state_file("agenda_frame_map.json"): _file_payload(
                {
                    "result": {
                        "issues": [{"issue_id": "i-1", "label": "校园周边控烟"}],
                        "frames": [{"frame_id": "f-1", "label": "公共健康优先"}],
                        "summary": "讨论围绕公共健康与执行边界展开",
                    }
                }
            ),
            layout.state_file("risk_signals.json"): _file_payload(
                {
                    "result": [
                        {
                            "risk_id": "r-1",
                            "risk_type": "执行口径误读",
                            "trigger_evidence_ids": ["ev-2", "ev-3"],
                            "spread_condition": "若地方执法标准不一致，争议将继续放大",
                            "severity": "medium",
                        }
                    ]
                }
            ),
            layout.state_file("utility_assessment.json"): _file_payload(
                {
                    "result": {
                        "decision": "pass",
                        "next_action": "围绕执行口径与风险边界形成正式研判结论。",
                        "confidence": 0.81,
                        "missing_dimensions": [],
                    }
                }
            ),
        }
        return files

    def test_deterministic_assembler_populates_core_structured_fields(self) -> None:
        files = self._build_runtime_files()
        structured = _synthesize_structured_report_from_files(
            files=files,
            topic_identifier="demo-topic",
            topic_label="示例专题",
            start_text="2025-01-01",
            end_text="2025-01-31",
            mode="fast",
            thread_id="thread-1",
        )
        self.assertGreaterEqual(len(structured.get("key_evidence") or []), 3)
        self.assertGreaterEqual(len(structured.get("citations") or []), 3)
        self.assertGreaterEqual(len(structured.get("timeline") or []), 1)
        self.assertGreaterEqual(len(structured.get("subjects") or []), 1)
        self.assertEqual(structured.get("task", {}).get("topic_identifier"), "demo-topic")

    def test_attach_ir_layers_blocks_compile_when_core_fields_missing(self) -> None:
        seed = _build_structured_seed_payload(
            topic_identifier="demo-topic",
            topic_label="示例专题",
            start_text="2025-01-01",
            end_text="2025-01-31",
            mode="fast",
            thread_id="thread-1",
        )
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            attached = _attach_ir_layers(
                seed,
                topic_identifier="demo-topic",
                cache_dir=cache_dir,
                thread_id="thread-1",
                task_id="task-1",
            )
        self.assertFalse(attached.get("structured_valid"))
        self.assertTrue(attached.get("exploration_blocked_before_compile"))
        self.assertIn("key_evidence>=3", attached.get("structured_invalid_reason", ""))
        self.assertFalse(bool(attached.get("report_ir")))

    def test_attach_ir_layers_accepts_non_empty_core_payload(self) -> None:
        structured = _synthesize_structured_report_from_files(
            files=self._build_runtime_files(),
            topic_identifier="demo-topic",
            topic_label="示例专题",
            start_text="2025-01-01",
            end_text="2025-01-31",
            mode="fast",
            thread_id="thread-1",
        )
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            attached = _attach_ir_layers(
                structured,
                topic_identifier="demo-topic",
                cache_dir=cache_dir,
                thread_id="thread-1",
                task_id="task-1",
            )
        self.assertTrue(attached.get("structured_valid"))
        self.assertFalse(attached.get("exploration_blocked_before_compile"))
        counts = ((attached.get("metadata") or {}).get("report_ir_summary") or {}).get("counts") or {}
        self.assertGreater(int(counts.get("timeline") or 0), 0)
        self.assertGreater(int(counts.get("evidence") or 0), 0)
        self.assertGreater(int(counts.get("actors") or 0), 0)

    def test_generate_full_report_payload_rejects_invalid_structured_input(self) -> None:
        seed = _build_structured_seed_payload(
            topic_identifier="demo-topic",
            topic_label="示例专题",
            start_text="2025-01-01",
            end_text="2025-01-31",
            mode="fast",
            thread_id="thread-1",
        )
        seed["structured_valid"] = False
        seed["structured_invalid_reason"] = "core producer fields insufficient"
        with self.assertRaises(ValueError):
            generate_full_report_payload(
                "demo-topic",
                "2025-01-01",
                "2025-01-31",
                topic_label="示例专题",
                project_identifier="demo-project",
                regenerate=True,
                structured_payload=seed,
                mode="fast",
                thread_id="thread-1",
                task_id="task-1",
            )


if __name__ == "__main__":
    unittest.main()
