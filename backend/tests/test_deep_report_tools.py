from __future__ import annotations

import json
import shutil
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.report.deep_report.schemas import (
    AgendaFrameMapResult,
    ClaimActorConflictResult,
    ClaimVerificationPage,
    CorpusCoverageResult,
    EvidenceCardPage,
    MechanismSummaryResult,
    NormalizedTaskResult,
    SectionPacketResult,
    TimelineBuildResult,
    UtilityAssessmentResult,
)
from src.report.deep_report.payloads import (
    build_agenda_frame_map_payload,
    build_claim_actor_conflict_payload,
    build_event_timeline_payload,
    build_discourse_conflict_map_payload,
    build_mechanism_summary_payload,
    build_retrieval_plan_payload,
    build_section_packet_payload,
    extract_actor_positions_payload,
    get_corpus_coverage_payload,
    judge_decision_utility_payload,
    normalize_task_payload,
    persist_task_contract_bundle,
    retrieve_evidence_cards_payload,
    verify_claim_payload,
)
from src.report.deep_report.agent_tools import get_corpus_coverage, retrieve_evidence_cards
from src.report.evidence_retriever import search_raw_records
from src.report.tools import get_report_tool_catalog, select_report_tools
from src.utils.setting.paths import get_data_root


class DeepReportToolsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.topic_identifier = f"deep-tools-{uuid.uuid4().hex[:8]}"
        self.project_root = get_data_root() / "projects" / self.topic_identifier
        self.fetch_root = self.project_root / "fetch" / "2025-01-15_2025-12-31"
        self.fetch_root.mkdir(parents=True, exist_ok=True)
        rows = [
            {
                "title": "市卫健委发布公共场所控烟新规",
                "contents": "市卫健委发布控烟政策通知，要求加强公共场所禁烟执法。",
                "platform": "新闻",
                "author": "城市日报",
                "published_at": "2025-08-20T08:00:00",
                "url": "https://example.com/policy-1",
                "region": "本地",
                "hit_words": "控烟,卫健委",
                "polarity": "中性",
                "classification": "未筛选",
            },
            {
                "title": "网传市卫健委发布控烟通知系谣言",
                "contents": "该消息为网传不实信息，通知截图系误读，官方未发布。",
                "platform": "微博",
                "author": "辟谣号",
                "published_at": "2025-08-22T11:00:00",
                "url": "https://example.com/rumor-1",
                "region": "本地",
                "hit_words": "控烟,谣言",
                "polarity": "负面",
                "classification": "未筛选",
            },
            {
                "title": "执法部门开展控烟专项行动",
                "contents": "公共场所控烟执法专项行动启动，重点整治室内吸烟行为。",
                "platform": "新闻",
                "author": "晚报",
                "published_at": "2025-08-25T09:30:00",
                "url": "https://example.com/policy-2",
                "region": "本地",
                "hit_words": "控烟,执法",
                "polarity": "中性",
                "classification": "未筛选",
            },
            {
                "title": "世界无烟日前宣传活动升温",
                "contents": "无烟日宣传活动提前预热，社区和学校同步开展健康倡议。",
                "platform": "新闻",
                "author": "健康频道",
                "published_at": "2025-05-28T09:00:00",
                "url": "https://example.com/day-1",
                "region": "本地",
                "hit_words": "控烟,无烟日",
                "polarity": "正面",
                "classification": "未筛选",
            },
            {
                "title": "乘客投诉站台吸烟引发争议，铁路部门回应将核查",
                "contents": "多名乘客投诉站台吸烟问题，现场争议升温，铁路部门回应正在核查并评估是否处罚。",
                "platform": "自媒体号",
                "author": "深圳市大鹏新区控烟志愿者监督大队",
                "published_at": "2025-08-26T10:30:00",
                "url": "https://example.com/risk-1",
                "region": "深圳",
                "hit_words": "控烟,投诉,争议",
                "polarity": "负面",
                "classification": "未筛选",
            },
            {
                "title": "吸烟危害科普：戒烟建议与健康提示",
                "contents": "title: 吸烟危害科普：戒烟建议与健康提示",
                "platform": "自媒体号",
                "author": "健康科普站",
                "published_at": "2025-08-27T10:00:00",
                "url": "https://example.com/generic-1",
                "region": "本地",
                "hit_words": "控烟,戒烟",
                "polarity": "中性",
                "classification": "未筛选",
            },
        ]
        with (self.fetch_root / "总体.jsonl").open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    def tearDown(self) -> None:
        shutil.rmtree(self.project_root, ignore_errors=True)

    def test_normalize_and_coverage_contracts(self) -> None:
        normalized = NormalizedTaskResult.model_validate(
            normalize_task_payload(
                task_text="请生成控烟政策舆情分析报告",
                topic_identifier=self.topic_identifier,
                start="2025-08-01",
                end="2025-08-31",
                mode="fast",
            )
        )
        coverage = CorpusCoverageResult.model_validate(
            get_corpus_coverage_payload(
                normalized_task_json=json.dumps(normalized.normalized_task.model_dump(), ensure_ascii=False),
                include_samples=True,
                limit=5,
            )
        )
        self.assertEqual(normalized.normalized_task.topic_identifier, self.topic_identifier)
        self.assertEqual(normalized.task_contract.topic_identifier, self.topic_identifier)
        self.assertTrue(normalized.task_derivation.derivation_id)
        self.assertEqual(normalized.task_derivation.topic, normalized.normalized_task.topic)
        self.assertEqual(normalized.proposal_snapshot["effective_contract"]["topic_identifier"], self.topic_identifier)
        self.assertGreaterEqual(coverage.coverage.matched_count, 1)
        self.assertIn("records_available", coverage.coverage.readiness_flags)
        self.assertEqual(normalized.schema_version, "2.2")
        self.assertEqual(normalized.tool_name, "normalize_task")
        self.assertTrue(normalized.normalized_task.analysis_question_set)
        self.assertTrue(normalized.normalized_task.coverage_expectation)
        self.assertTrue(normalized.normalized_task.inference_policy)

    def test_normalize_task_applies_runtime_contract_overrides(self) -> None:
        normalized = NormalizedTaskResult.model_validate(
            normalize_task_payload(
                task_text="请生成控烟政策舆情分析报告",
                topic_identifier="tobacco_control_2025",
                start="2025-01-01",
                end="2025-06-30",
                mode="research",
                hints_json=json.dumps(
                    {
                        "topic": "2025控烟舆情分析报告",
                        "task_contract": {
                            "topic_identifier": self.topic_identifier,
                            "topic_label": "2025控烟舆情分析报告",
                            "start": "2025-01-15",
                            "end": "2025-12-31",
                            "mode": "fast",
                            "thread_id": "thread-1",
                        },
                    },
                    ensure_ascii=False,
                ),
            )
        )

        self.assertEqual(normalized.normalized_task.topic_identifier, self.topic_identifier)
        self.assertEqual(normalized.normalized_task.time_range.start, "2025-01-15")
        self.assertEqual(normalized.normalized_task.time_range.end, "2025-12-31")
        self.assertEqual(normalized.normalized_task.mode, "fast")
        self.assertIn("topic_identifier", normalized.normalized_task.contract_overrides_applied)
        self.assertIn("start", normalized.normalized_task.contract_overrides_applied)
        self.assertIn("end", normalized.normalized_task.contract_overrides_applied)
        self.assertEqual(normalized.normalized_task.task_contract["thread_id"], "thread-1")
        self.assertEqual(normalized.task_contract.topic_identifier, self.topic_identifier)
        self.assertEqual(normalized.task_derivation.attempted_overrides["topic_identifier"], "tobacco_control_2025")
        self.assertEqual(normalized.proposal_snapshot["repair_action"], "override")

    def test_coverage_reports_overlap_fetch_range_without_false_empty_corpus(self) -> None:
        normalized = NormalizedTaskResult.model_validate(
            normalize_task_payload(
                task_text="2025控烟舆情分析报告",
                topic_identifier=self.topic_identifier,
                start="2025-01-01",
                end="2025-06-30",
                mode="fast",
                hints_json=json.dumps(
                    {
                        "task_contract": {
                            "topic_identifier": self.topic_identifier,
                            "topic_label": "2025控烟舆情分析报告",
                            "start": "2025-01-01",
                            "end": "2025-06-30",
                            "mode": "fast",
                            "thread_id": "thread-2",
                        },
                    },
                    ensure_ascii=False,
                ),
            )
        )
        coverage = CorpusCoverageResult.model_validate(
            get_corpus_coverage_payload(
                normalized_task_json=json.dumps(normalized.normalized_task.model_dump(), ensure_ascii=False),
                include_samples=True,
                limit=5,
            )
        )

        self.assertEqual(coverage.coverage.source_resolution, "overlap_fetch_range")
        self.assertEqual(coverage.coverage.resolved_fetch_range["start"], "2025-01-15")
        self.assertEqual(coverage.coverage.resolved_fetch_range["end"], "2025-12-31")
        self.assertIn("partial_range_coverage", coverage.coverage.source_quality_flags)
        self.assertIn("records_available", coverage.coverage.readiness_flags)
        self.assertNotIn("no_records_in_scope", coverage.coverage.readiness_flags)
        self.assertGreaterEqual(coverage.coverage.matched_count, 1)

    def test_retrieval_scope_is_clipped_within_contract_without_changing_topic_identity(self) -> None:
        normalized = NormalizedTaskResult.model_validate(
            normalize_task_payload(
                task_text="2025控烟舆情分析报告",
                topic_identifier=self.topic_identifier,
                start="2025-01-15",
                end="2025-12-31",
                mode="fast",
                hints_json=json.dumps(
                    {
                        "task_contract": {
                            "topic_identifier": self.topic_identifier,
                            "topic_label": "2025控烟舆情分析报告",
                            "start": "2025-01-15",
                            "end": "2025-12-31",
                            "mode": "fast",
                            "thread_id": "thread-3",
                        },
                    },
                    ensure_ascii=False,
                ),
            )
        )
        coverage = CorpusCoverageResult.model_validate(
            get_corpus_coverage_payload(
                task_contract_json=json.dumps(normalized.task_contract.model_dump(), ensure_ascii=False),
                task_derivation_json=json.dumps(normalized.task_derivation.model_dump(), ensure_ascii=False),
                retrieval_scope_json=json.dumps(
                    {
                        "policy": "within_contract",
                        "start": "2025-01-01",
                        "end": "2025-05-31",
                    },
                    ensure_ascii=False,
                ),
                include_samples=False,
                limit=5,
            )
        )
        evidence = EvidenceCardPage.model_validate(
            retrieve_evidence_cards_payload(
                task_contract_json=json.dumps(normalized.task_contract.model_dump(), ensure_ascii=False),
                task_derivation_json=json.dumps(normalized.task_derivation.model_dump(), ensure_ascii=False),
                retrieval_scope_json=json.dumps(
                    {
                        "policy": "within_contract",
                        "start": "2025-01-01",
                        "end": "2025-05-31",
                    },
                    ensure_ascii=False,
                ),
                intent="overview",
                filters_json=json.dumps({"entities": ["无烟日", "控烟"]}, ensure_ascii=False),
                limit=6,
            )
        )

        self.assertEqual(coverage.coverage.contract_topic_identifier, self.topic_identifier)
        self.assertEqual(coverage.coverage.effective_topic_identifier, self.topic_identifier)
        self.assertEqual(coverage.coverage.requested_time_range["start"], "2025-01-01")
        self.assertEqual(coverage.coverage.effective_time_range["start"], "2025-01-15")
        self.assertIn("scope_clipped_to_contract", coverage.coverage.source_quality_flags)
        self.assertTrue(evidence.result)
        self.assertEqual(evidence.coverage.effective_time_range["start"], "2025-01-15")

    def test_contract_id_registry_drives_retrieval_without_normalized_task_input(self) -> None:
        normalized = NormalizedTaskResult.model_validate(
            normalize_task_payload(
                task_text="2025控烟舆情分析报告",
                topic_identifier=self.topic_identifier,
                start="2025-01-15",
                end="2025-12-31",
                mode="fast",
                hints_json=json.dumps(
                    {
                        "task_contract": {
                            "topic_identifier": self.topic_identifier,
                            "topic_label": "2025控烟舆情分析报告",
                            "start": "2025-01-15",
                            "end": "2025-12-31",
                            "mode": "fast",
                            "thread_id": "thread-4",
                        },
                        "entities": ["控烟", "无烟日"],
                        "platform_scope": ["新闻"],
                    },
                    ensure_ascii=False,
                ),
            )
        )
        persist_task_contract_bundle(
            task_contract=normalized.task_contract.model_dump(),
            task_derivation=normalized.task_derivation.model_dump(),
            proposal_snapshot=normalized.proposal_snapshot,
        )

        coverage = CorpusCoverageResult.model_validate(
            get_corpus_coverage_payload(
                contract_id=normalized.task_contract.contract_id,
                retrieval_scope_json=json.dumps(
                    {"policy": "within_contract", "start": "2025-05-01", "end": "2025-06-30"},
                    ensure_ascii=False,
                ),
                filters_json=json.dumps({"platforms": ["新闻"]}, ensure_ascii=False),
                include_samples=True,
                limit=5,
            )
        )
        evidence = EvidenceCardPage.model_validate(
            retrieve_evidence_cards_payload(
                contract_id=normalized.task_contract.contract_id,
                retrieval_scope_json=json.dumps(
                    {"policy": "within_contract", "start": "2025-05-01", "end": "2025-06-30"},
                    ensure_ascii=False,
                ),
                filters_json=json.dumps({"platforms": ["新闻"], "entities": ["无烟日"]}, ensure_ascii=False),
                intent="overview",
                limit=6,
            )
        )

        self.assertEqual(coverage.coverage.contract_topic_identifier, self.topic_identifier)
        self.assertEqual(coverage.coverage.effective_topic_identifier, self.topic_identifier)
        self.assertGreaterEqual(coverage.coverage.matched_count, 1)
        self.assertTrue(evidence.result)
        self.assertEqual(evidence.coverage.contract_topic_identifier, self.topic_identifier)

    def test_agent_facing_retrieval_tools_hide_normalized_task_inputs(self) -> None:
        coverage_args = getattr(get_corpus_coverage, "args", {})
        evidence_args = getattr(retrieve_evidence_cards, "args", {})

        self.assertIn("contract_id", coverage_args)
        self.assertIn("retrieval_scope_json", coverage_args)
        self.assertIn("filters_json", coverage_args)
        self.assertNotIn("normalized_task_json", coverage_args)
        self.assertNotIn("task_contract_json", coverage_args)
        self.assertNotIn("task_derivation_json", coverage_args)

        self.assertIn("contract_id", evidence_args)
        self.assertIn("retrieval_scope_json", evidence_args)
        self.assertIn("filters_json", evidence_args)
        self.assertIn("intent", evidence_args)
        self.assertNotIn("normalized_task_json", evidence_args)
        self.assertNotIn("task_contract_json", evidence_args)
        self.assertNotIn("task_derivation_json", evidence_args)

    def test_search_raw_records_exposes_available_raw_fields(self) -> None:
        retrieval = search_raw_records(
            topic_identifier=self.topic_identifier,
            start="2025-08-01",
            end="2025-08-31",
            query="控烟 卫健委 投诉 争议",
            top_k=6,
            mode="fast",
        )

        self.assertTrue(retrieval["items"])
        sample = retrieval["items"][0]
        self.assertIn("contents", sample)
        self.assertIn("polarity", sample)
        self.assertIn("classification", sample)
        self.assertIn("region", sample)
        self.assertIn("hit_words", sample)
        self.assertIn("matched_terms", sample)
        self.assertIn("content_quality_hint", sample)

    def test_retrieve_evidence_cards_exposes_inferred_fields_and_counts(self) -> None:
        normalized = normalize_task_payload(
            task_text="控烟政策建议",
            topic_identifier=self.topic_identifier,
            start="2025-08-01",
            end="2025-08-31",
            mode="fast",
        )
        evidence = EvidenceCardPage.model_validate(
            retrieve_evidence_cards_payload(
                normalized_task_json=json.dumps(normalized["normalized_task"], ensure_ascii=False),
                intent="risk",
                limit=6,
            )
        )

        self.assertTrue(evidence.result)
        first = evidence.result[0]
        self.assertTrue(hasattr(first, "raw_contents"))
        self.assertTrue(hasattr(first, "raw_polarity"))
        self.assertTrue(hasattr(first, "content_quality_hint"))
        self.assertTrue(hasattr(first, "official_source_hint"))
        self.assertTrue(hasattr(first, "source_kind_hint"))
        self.assertTrue(hasattr(first, "actor_salience_score"))
        self.assertTrue(hasattr(first, "eventness_score"))
        self.assertTrue(hasattr(first, "risk_salience_score"))
        self.assertTrue(hasattr(first, "risk_facets"))
        self.assertGreaterEqual(evidence.coverage.raw_matched_count, evidence.coverage.deduped_candidate_count)
        self.assertEqual(evidence.coverage.returned_card_count, len(evidence.result))
        self.assertTrue(evidence.trace.rerank_policy)
        self.assertTrue(isinstance(evidence.trace.dominant_signals, list))

    def test_intent_aware_rerank_prefers_actor_timeline_and_risk_signals(self) -> None:
        normalized = normalize_task_payload(
            task_text="控烟政策建议",
            topic_identifier=self.topic_identifier,
            start="2025-08-01",
            end="2025-08-31",
            mode="fast",
        )
        overview = EvidenceCardPage.model_validate(
            retrieve_evidence_cards_payload(
                normalized_task_json=json.dumps(normalized["normalized_task"], ensure_ascii=False),
                intent="overview",
                limit=4,
            )
        )
        timeline = EvidenceCardPage.model_validate(
            retrieve_evidence_cards_payload(
                normalized_task_json=json.dumps(normalized["normalized_task"], ensure_ascii=False),
                intent="timeline",
                limit=4,
            )
        )
        actors = EvidenceCardPage.model_validate(
            retrieve_evidence_cards_payload(
                normalized_task_json=json.dumps(normalized["normalized_task"], ensure_ascii=False),
                intent="actors",
                limit=4,
            )
        )
        risk = EvidenceCardPage.model_validate(
            retrieve_evidence_cards_payload(
                normalized_task_json=json.dumps(normalized["normalized_task"], ensure_ascii=False),
                intent="risk",
                limit=4,
            )
        )

        self.assertTrue(any(card.risk_facets for card in risk.result))
        self.assertTrue(any(card.eventness_score >= 0.4 for card in timeline.result))
        self.assertTrue(any(card.actor_salience_score >= 0.35 for card in actors.result))
        self.assertNotEqual(
            [card.source_id for card in overview.result[:3]],
            [card.source_id for card in actors.result[:3]],
        )
        self.assertTrue(
            any("投诉" in (card.title or "") or "谣言" in (card.title or "") or "争议" in (card.title or "") for card in risk.result[:3])
        )

    def test_missing_contract_id_fails_instead_of_fallback_guess(self) -> None:
        coverage = CorpusCoverageResult.model_validate(
            get_corpus_coverage_payload(
                contract_id="",
                retrieval_scope_json=json.dumps({"policy": "within_contract", "start": "2025-05-01", "end": "2025-06-30"}, ensure_ascii=False),
                filters_json=json.dumps({"platforms": ["新闻"]}, ensure_ascii=False),
            )
        )
        evidence = EvidenceCardPage.model_validate(
            retrieve_evidence_cards_payload(
                contract_id="",
                retrieval_scope_json=json.dumps({"policy": "within_contract", "start": "2025-05-01", "end": "2025-06-30"}, ensure_ascii=False),
                filters_json=json.dumps({"platforms": ["新闻"]}, ensure_ascii=False),
                intent="overview",
            )
        )

        self.assertEqual(coverage.coverage.source_resolution, "contract_binding_failed")
        self.assertIn("contract_binding_failed", coverage.coverage.readiness_flags)
        self.assertEqual(evidence.coverage.source_resolution, "contract_binding_failed")
        self.assertIn("contract_binding_failed", evidence.coverage.readiness_flags)
        self.assertIn("contract_id", coverage.coverage.field_gaps)
        self.assertEqual(evidence.trace.contract_id, "")

    def test_legacy_normalized_task_input_maps_but_is_marked_as_legacy(self) -> None:
        normalized = NormalizedTaskResult.model_validate(
            normalize_task_payload(
                task_text="2025控烟舆情分析报告",
                topic_identifier=self.topic_identifier,
                start="2025-01-15",
                end="2025-12-31",
                mode="fast",
            )
        )
        coverage = get_corpus_coverage_payload(
            normalized_task_json=json.dumps(normalized.model_dump(), ensure_ascii=False),
            retrieval_scope_json=json.dumps({"policy": "within_contract", "start": "2025-05-01", "end": "2025-06-30"}, ensure_ascii=False),
            filters_json=json.dumps({"platforms": ["新闻"]}, ensure_ascii=False),
        )

        self.assertTrue(coverage["legacy_adapter_hit"])
        self.assertIn("normalized_task_json", coverage["legacy_input_kind"])
        self.assertFalse(coverage["contract_binding_failed"])
        self.assertEqual(coverage["contract_value"]["topic_identifier"], self.topic_identifier)
        self.assertEqual(coverage["trace"]["contract_id"], normalized.task_contract.contract_id)

    def test_contract_registry_preserves_authority_and_appends_derivation_history(self) -> None:
        normalized = NormalizedTaskResult.model_validate(
            normalize_task_payload(
                task_text="2025控烟舆情分析报告",
                topic_identifier=self.topic_identifier,
                start="2025-01-15",
                end="2025-12-31",
                mode="fast",
            )
        )
        first_bundle = persist_task_contract_bundle(
            task_contract=normalized.task_contract.model_dump(),
            task_derivation=normalized.task_derivation.model_dump(),
            proposal_snapshot=normalized.proposal_snapshot,
        )
        conflicting_contract = normalized.task_contract.model_dump()
        conflicting_contract["topic_identifier"] = "wrong-topic"
        conflicting_derivation = normalized.task_derivation.model_dump()
        conflicting_derivation["derivation_id"] = f"{conflicting_derivation['derivation_id']}-2"
        second_bundle = persist_task_contract_bundle(
            task_contract=conflicting_contract,
            task_derivation=conflicting_derivation,
            proposal_snapshot=normalized.proposal_snapshot,
        )

        self.assertEqual(first_bundle["task_contract"]["topic_identifier"], self.topic_identifier)
        self.assertEqual(second_bundle["task_contract"]["topic_identifier"], self.topic_identifier)
        self.assertEqual(len(second_bundle["task_derivations"]), 2)

    def test_evidence_timeline_and_section_packet_contracts(self) -> None:
        normalized = normalize_task_payload(
            task_text="控烟政策分析",
            topic_identifier=self.topic_identifier,
            start="2025-08-01",
            end="2025-08-31",
            mode="fast",
        )
        evidence = EvidenceCardPage.model_validate(
            retrieve_evidence_cards_payload(
                normalized_task_json=json.dumps(normalized["normalized_task"], ensure_ascii=False),
                intent="overview",
                limit=6,
            )
        )
        retrieval_plan = build_retrieval_plan_payload(
            normalized_task_json=json.dumps(normalized["normalized_task"], ensure_ascii=False),
            intent="overview",
        )
        timeline = TimelineBuildResult.model_validate(
            build_event_timeline_payload(
                normalized_task_json=json.dumps(normalized["normalized_task"], ensure_ascii=False),
                evidence_ids_json=json.dumps([item.model_dump() for item in evidence.result], ensure_ascii=False),
                max_nodes=5,
            )
        )
        conflict_map = build_discourse_conflict_map_payload(
            normalized_task_json=json.dumps(normalized["normalized_task"], ensure_ascii=False),
            evidence_ids_json=json.dumps([item.model_dump() for item in evidence.result], ensure_ascii=False),
        )
        typed_conflict = ClaimActorConflictResult.model_validate(
            build_claim_actor_conflict_payload(
                normalized_task_json=json.dumps(normalized["normalized_task"], ensure_ascii=False),
                evidence_ids_json=json.dumps([item.model_dump() for item in evidence.result], ensure_ascii=False),
            )
        )
        agenda = AgendaFrameMapResult.model_validate(
            build_agenda_frame_map_payload(
                normalized_task_json=json.dumps(normalized["normalized_task"], ensure_ascii=False),
                evidence_ids_json=json.dumps([item.model_dump() for item in evidence.result], ensure_ascii=False),
                actor_positions_json=json.dumps([item.model_dump() for item in typed_conflict.result.actor_positions], ensure_ascii=False),
                conflict_map_json=json.dumps(typed_conflict.result.model_dump(), ensure_ascii=False),
                timeline_nodes_json=json.dumps([item.model_dump() for item in timeline.result], ensure_ascii=False),
            )
        )
        mechanism = MechanismSummaryResult.model_validate(
            build_mechanism_summary_payload(
                normalized_task_json=json.dumps(normalized["normalized_task"], ensure_ascii=False),
                evidence_ids_json=json.dumps([item.model_dump() for item in evidence.result], ensure_ascii=False),
                timeline_nodes_json=json.dumps([item.model_dump() for item in timeline.result], ensure_ascii=False),
                conflict_map_json=json.dumps(typed_conflict.result.model_dump(), ensure_ascii=False),
            )
        )
        packet = SectionPacketResult.model_validate(
            build_section_packet_payload(
                normalized_task_json=json.dumps(normalized["normalized_task"], ensure_ascii=False),
                section_id="risk",
                evidence_ids_json=json.dumps([item.model_dump() for item in evidence.result], ensure_ascii=False),
            )
        )
        self.assertTrue(evidence.result)
        self.assertIn("source_ids", evidence.trace.model_dump())
        self.assertTrue(evidence.trace.rewrite_queries)
        self.assertTrue(evidence.trace.retrieval_strategy)
        self.assertTrue(evidence.trace.compression_applied)
        self.assertTrue(all(item.stance_hint for item in evidence.result))
        self.assertTrue(all(item.claimability for item in evidence.result))
        self.assertEqual(retrieval_plan["schema_version"], "2.2")
        self.assertTrue(retrieval_plan["result"]["router_facets"][0]["task_goal"])
        self.assertTrue(retrieval_plan["result"]["router_facets"][0]["risk_sensitivity"])
        self.assertTrue(retrieval_plan["result"]["dispatch_plan"]["quality_ledger"])
        self.assertTrue(retrieval_plan["result"]["dispatch_quality_ledger"])
        self.assertTrue(all(node.support_evidence_ids or node.conflict_evidence_ids for node in timeline.result))
        self.assertIn("schema_version", conflict_map)
        self.assertTrue(typed_conflict.result.claims)
        self.assertTrue(typed_conflict.result.resolution_summary)
        self.assertTrue(all(item.proposition_slots for item in typed_conflict.result.claims))
        self.assertTrue(all(item.source_diversity >= 1 for item in typed_conflict.result.claims))
        self.assertTrue(all(item.organization_type for item in typed_conflict.result.actor_positions))
        self.assertTrue(typed_conflict.result.targets)
        self.assertTrue(typed_conflict.result.arguments)
        self.assertTrue(typed_conflict.result.support_edges or typed_conflict.result.attack_edges)
        self.assertTrue(all(edge.confidence >= 0.0 for edge in typed_conflict.result.edges))
        self.assertTrue(agenda.result.issues)
        self.assertTrue(agenda.result.frames)
        self.assertTrue(agenda.result.issue_attribute_edges)
        self.assertTrue(mechanism.result.trigger_events or mechanism.result.amplification_paths)
        self.assertTrue(mechanism.result.bridge_nodes or mechanism.result.cross_platform_bridges)
        self.assertTrue(mechanism.result.cause_candidates)
        self.assertTrue(mechanism.result.cross_platform_transfers or mechanism.result.narrative_carriers)
        self.assertTrue(all(path.confidence >= 0.0 for path in mechanism.result.amplification_paths))
        self.assertTrue(packet.section_packet.section_id)
        self.assertTrue(packet.section_packet.uncertainty_notes or packet.section_packet.evidence_cards)

    def test_decision_utility_payload_enforces_typed_decision(self) -> None:
        normalized = normalize_task_payload(
            task_text="控烟政策建议",
            topic_identifier=self.topic_identifier,
            start="2025-08-01",
            end="2025-08-31",
            mode="fast",
        )
        evidence = EvidenceCardPage.model_validate(
            retrieve_evidence_cards_payload(
                normalized_task_json=json.dumps(normalized["normalized_task"], ensure_ascii=False),
                intent="overview",
                limit=6,
            )
        )
        timeline = TimelineBuildResult.model_validate(
            build_event_timeline_payload(
                normalized_task_json=json.dumps(normalized["normalized_task"], ensure_ascii=False),
                evidence_ids_json=json.dumps([item.model_dump() for item in evidence.result], ensure_ascii=False),
                max_nodes=5,
            )
        )
        conflict = ClaimActorConflictResult.model_validate(
            build_claim_actor_conflict_payload(
                normalized_task_json=json.dumps(normalized["normalized_task"], ensure_ascii=False),
                evidence_ids_json=json.dumps([item.model_dump() for item in evidence.result], ensure_ascii=False),
            )
        )
        agenda = AgendaFrameMapResult.model_validate(
            build_agenda_frame_map_payload(
                normalized_task_json=json.dumps(normalized["normalized_task"], ensure_ascii=False),
                evidence_ids_json=json.dumps([item.model_dump() for item in evidence.result], ensure_ascii=False),
                actor_positions_json=json.dumps([item.model_dump() for item in conflict.result.actor_positions], ensure_ascii=False),
                conflict_map_json=json.dumps(conflict.result.model_dump(), ensure_ascii=False),
                timeline_nodes_json=json.dumps([item.model_dump() for item in timeline.result], ensure_ascii=False),
            )
        )
        mechanism = MechanismSummaryResult.model_validate(
            build_mechanism_summary_payload(
                normalized_task_json=json.dumps(normalized["normalized_task"], ensure_ascii=False),
                evidence_ids_json=json.dumps([item.model_dump() for item in evidence.result], ensure_ascii=False),
                timeline_nodes_json=json.dumps([item.model_dump() for item in timeline.result], ensure_ascii=False),
                conflict_map_json=json.dumps(conflict.result.model_dump(), ensure_ascii=False),
            )
        )
        utility = UtilityAssessmentResult.model_validate(
            judge_decision_utility_payload(
                normalized_task_json=json.dumps(normalized["normalized_task"], ensure_ascii=False),
                risk_signals_json=json.dumps(
                    [{"risk_id": "risk-1", "spread_condition": "争议会继续扩散", "severity": "medium"}],
                    ensure_ascii=False,
                ),
                recommendation_candidates_json=json.dumps(
                    [{"action": "补充回应口径", "rationale": "抑制争议扩散", "priority": "high"}],
                    ensure_ascii=False,
                ),
                unresolved_points_json=json.dumps([{"item_id": "uv-1", "statement": "截图待核验", "reason": "链路不完整"}], ensure_ascii=False),
                agenda_frame_map_json=json.dumps(agenda.result.model_dump(), ensure_ascii=False),
                conflict_map_json=json.dumps(conflict.result.model_dump(), ensure_ascii=False),
                mechanism_summary_json=json.dumps(mechanism.result.model_dump(), ensure_ascii=False),
            )
        )
        self.assertIn(utility.result.decision, {"pass", "fallback_recompile", "require_semantic_review"})
        self.assertTrue(utility.result.next_action)
        self.assertTrue(hasattr(utility.result, "recommendation_has_preconditions"))
        self.assertTrue(isinstance(utility.result.fallback_trace, list))
        self.assertTrue(hasattr(utility.result, "has_issue_frame_context"))
        self.assertTrue(hasattr(utility.result, "has_mechanism_explanation"))
        self.assertTrue(isinstance(utility.result.improvement_trace, list))

    def test_verify_claim_contract(self) -> None:
        normalized = normalize_task_payload(
            task_text="控烟政策核验",
            topic_identifier=self.topic_identifier,
            start="2025-08-01",
            end="2025-08-31",
            mode="fast",
        )
        checks = ClaimVerificationPage.model_validate(
            verify_claim_payload(
                normalized_task_json=json.dumps(normalized["normalized_task"], ensure_ascii=False),
                claims_json=json.dumps(["市卫健委发布控烟通知"], ensure_ascii=False),
            )
        )
        self.assertEqual(len(checks.result), 1)
        self.assertIn(checks.result[0].status, {"supported", "partially_supported", "unsupported", "contradicted"})

    def test_registry_exports_only_v2_tools(self) -> None:
        catalog_ids = {item.tool_id for item in get_report_tool_catalog()}
        coordinator_names = {tool.name for tool in select_report_tools(runtime_target="deep_report_coordinator")}
        self.assertIn("retrieve_evidence_cards", catalog_ids)
        self.assertIn("build_agenda_frame_map", catalog_ids)
        self.assertIn("build_claim_actor_conflict", catalog_ids)
        self.assertIn("build_mechanism_summary", catalog_ids)
        self.assertIn("judge_decision_utility", catalog_ids)
        self.assertIn("retrieve_evidence_cards", coordinator_names)
        self.assertNotIn("query_documents", coordinator_names)

    def test_decision_utility_fallback_trace_is_typed_when_structure_is_missing(self) -> None:
        normalized = normalize_task_payload(
            task_text="控烟政策建议",
            topic_identifier=self.topic_identifier,
            start="2025-08-01",
            end="2025-08-31",
            mode="fast",
        )
        utility = UtilityAssessmentResult.model_validate(
            judge_decision_utility_payload(
                normalized_task_json=json.dumps(normalized["normalized_task"], ensure_ascii=False),
                risk_signals_json=json.dumps([{"risk_id": "risk-1", "spread_condition": "争议扩散", "severity": "high"}], ensure_ascii=False),
                recommendation_candidates_json=json.dumps([{"action": "补充回应", "rationale": "降低扩散"}], ensure_ascii=False),
                unresolved_points_json=json.dumps([], ensure_ascii=False),
                agenda_frame_map_json=json.dumps({}, ensure_ascii=False),
                conflict_map_json=json.dumps({}, ensure_ascii=False),
                mechanism_summary_json=json.dumps({}, ensure_ascii=False),
                actor_positions_json=json.dumps([], ensure_ascii=False),
            )
        )
        self.assertEqual(utility.result.decision, "fallback_recompile")
        self.assertTrue(utility.result.missing_dimensions)
        self.assertTrue(any(item in utility.result.missing_dimensions for item in ("empty_evidence", "insufficient_structure")))
        self.assertTrue(utility.result.next_action)
        self.assertTrue(any(item.dimension in {"empty_evidence", "insufficient_structure"} for item in utility.result.fallback_trace))

    def test_decision_utility_accepts_wrapped_objects(self) -> None:
        normalized = normalize_task_payload(
            task_text="控烟政策建议",
            topic_identifier=self.topic_identifier,
            start="2025-08-01",
            end="2025-08-31",
            mode="fast",
        )
        utility = UtilityAssessmentResult.model_validate(
            judge_decision_utility_payload(
                normalized_task_json=json.dumps(normalized["normalized_task"], ensure_ascii=False),
                risk_signals_json=json.dumps(
                    {"result": [{"risk_id": "risk-1", "spread_condition": "争议扩散", "severity": "high"}]},
                    ensure_ascii=False,
                ),
                recommendation_candidates_json=json.dumps(
                    [{"action": "补充回应", "rationale": "降低扩散", "target": "公众", "preconditions": "统一口径", "side_effects": "可能引发二次讨论"}],
                    ensure_ascii=False,
                ),
                unresolved_points_json=json.dumps([{"item_id": "uv-1", "statement": "截图待核验", "reason": "链路不完整"}], ensure_ascii=False),
                agenda_frame_map_json=json.dumps({"result": {"issues": [{"issue_id": "issue-1", "label": "控烟争议"}], "frames": [{"frame_id": "frame-1", "issue_id": "issue-1", "problem_definition": "公共场所禁烟"}]}}, ensure_ascii=False),
                conflict_map_json=json.dumps({"result": {"claims": [{"claim_id": "claim-1", "proposition": "应全面禁烟", "source_ids": ["新闻"], "verification_status": "sustained_conflict", "evidence_density": 0.8}], "actor_positions": [{"actor_id": "actor-1", "name": "市卫健委"}], "edges": [{"edge_id": "edge-1", "claim_a_id": "claim-1", "claim_b_id": "claim-1", "conflict_type": "direct_contradiction", "actor_scope": ["actor-1"], "time_scope": ["2025-08-20"], "evidence_refs": ["ev-1"], "evidence_density": 0.8, "confidence": 0.9}], "resolution_summary": [{"claim_id": "claim-1", "status": "sustained_conflict"}]}}, ensure_ascii=False),
                mechanism_summary_json=json.dumps({"result": {"trigger_events": [{"event_id": "event-1", "label": "政策发布"}], "amplification_paths": [{"path_id": "path-1", "path_label": "媒体扩散"}], "cause_candidates": [{"cause_id": "cause-1", "label": "解释分歧"}]}}, ensure_ascii=False),
                actor_positions_json=json.dumps({"result": [{"actor_id": "actor-1", "name": "市卫健委"}]}, ensure_ascii=False),
            )
        )

        self.assertTrue(utility.result.has_key_actors)
        self.assertTrue(utility.result.has_primary_contradiction)
        self.assertTrue(utility.result.has_mechanism_explanation)

    def test_empty_conflict_and_mechanism_surfaces_are_explanatory(self) -> None:
        normalized = normalize_task_payload(
            task_text="控烟政策建议",
            topic_identifier=f"{self.topic_identifier}-missing",
            start="2025-08-01",
            end="2025-08-31",
            mode="fast",
        )
        empty_conflict = ClaimActorConflictResult.model_validate(
            build_claim_actor_conflict_payload(
                normalized_task_json=json.dumps(normalized["normalized_task"], ensure_ascii=False),
                evidence_ids_json=json.dumps([], ensure_ascii=False),
                actor_positions_json=json.dumps([], ensure_ascii=False),
                timeline_nodes_json=json.dumps([], ensure_ascii=False),
            )
        )
        empty_mechanism = MechanismSummaryResult.model_validate(
            build_mechanism_summary_payload(
                normalized_task_json=json.dumps(normalized["normalized_task"], ensure_ascii=False),
                evidence_ids_json=json.dumps([], ensure_ascii=False),
                timeline_nodes_json=json.dumps([], ensure_ascii=False),
                conflict_map_json=json.dumps({}, ensure_ascii=False),
            )
        )

        self.assertEqual(empty_conflict.result.summary, "当前未形成可回链争议轴。")
        self.assertEqual(empty_mechanism.result.confidence_summary, "机制判断因证据不足跳过。")

    def test_extract_actor_positions_fallback_uses_overview_intent(self) -> None:
        normalized = normalize_task_payload(
            task_text="控烟政策建议",
            topic_identifier=self.topic_identifier,
            start="2025-08-01",
            end="2025-08-31",
            mode="fast",
        )

        with patch("src.report.deep_report.payloads.retrieve_evidence_cards_payload") as mocked_retrieve:
            mocked_retrieve.return_value = {"result": []}
            extract_actor_positions_payload(
                normalized_task_json=json.dumps(normalized["normalized_task"], ensure_ascii=False),
                evidence_ids_json="[]",
                actor_limit=6,
            )

        self.assertEqual(mocked_retrieve.call_args.kwargs["intent"], "overview")

    def test_claim_actor_conflict_fallback_uses_overview_intent(self) -> None:
        normalized = normalize_task_payload(
            task_text="控烟政策建议",
            topic_identifier=self.topic_identifier,
            start="2025-08-01",
            end="2025-08-31",
            mode="fast",
        )

        with patch("src.report.deep_report.payloads.retrieve_evidence_cards_payload") as mocked_retrieve:
            mocked_retrieve.return_value = {"result": []}
            build_claim_actor_conflict_payload(
                normalized_task_json=json.dumps(normalized["normalized_task"], ensure_ascii=False),
                evidence_ids_json="[]",
                actor_positions_json=json.dumps([], ensure_ascii=False),
                timeline_nodes_json=json.dumps([], ensure_ascii=False),
            )

        self.assertEqual(mocked_retrieve.call_args.kwargs["intent"], "overview")


if __name__ == "__main__":
    unittest.main()
