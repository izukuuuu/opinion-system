from __future__ import annotations

import json
import shutil
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server_support.topic_context import TopicContext
from src.report.capability_manifest import (
    get_report_capability,
    get_report_capability_catalog,
    select_runtime_capability_ids,
    select_runtime_skill_ids,
)
from src.report.capability_adapters import (
    ANALYZE_FILE_MAP,
    BERTOPIC_FILE_MAP,
    build_basic_analysis_insight,
    build_bertopic_insight,
    collect_basic_analysis_snapshot,
    collect_bertopic_snapshot,
    ensure_bertopic_results,
)
from src.report.deep_report.payloads import (
    build_basic_analysis_insight_payload,
    build_bertopic_insight_payload,
    get_basic_analysis_snapshot_payload,
    get_bertopic_snapshot_payload,
)
from src.report.deep_report.schemas import (
    BasicAnalysisInsightResult,
    BasicAnalysisSnapshotResult,
    BertopicInsightResult,
    BertopicSnapshotResult,
)
from src.report.skills.loader import build_report_skill_runtime_assets, discover_report_skills, resolve_report_skill, select_report_skill_sources
from src.report.tools import get_report_tool, get_report_tool_catalog, select_report_tools, validate_skill_tool_ids
from src.utils.setting.paths import get_data_root


class ReportCapabilityAdaptersTests(unittest.TestCase):
    def setUp(self) -> None:
        self.topic_identifier = f"cap-{uuid.uuid4().hex[:8]}"
        self.project_root = get_data_root() / "projects" / self.topic_identifier
        self.analyze_root = self.project_root / "analyze" / "2025-01-01_2025-01-31"
        self.topic_root = self.project_root / "topic" / "2025-01-01_2025-01-31"
        for func_name, filename in ANALYZE_FILE_MAP.items():
            path = self.analyze_root / func_name / "总体" / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            if func_name == "volume":
                payload = {"total": 24, "data": [{"name": "总体", "value": 24}]}
            elif func_name == "attitude":
                payload = {"positive": 8, "neutral": 10, "negative": 6}
            elif func_name == "trends":
                payload = {"data": [{"date": "2025-01-03", "value": 6}, {"date": "2025-01-09", "value": 11}]}
            elif func_name == "classification":
                payload = {"data": [{"name": "收费争议", "value": 12}, {"name": "官方回应", "value": 7}]}
            elif func_name == "keywords":
                payload = {"data": [{"name": "收费", "value": 9}, {"name": "整改", "value": 5}]}
            elif func_name == "publishers":
                payload = {"data": [{"name": "媒体", "value": 10}, {"name": "网友", "value": 8}]}
            else:
                payload = {"data": [{"name": "上海", "value": 6}, {"name": "北京", "value": 5}]}
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        self.topic_root.mkdir(parents=True, exist_ok=True)
        (self.topic_root / BERTOPIC_FILE_MAP["summary"]).write_text(
            json.dumps(
                {
                    "主题文档统计": {
                        "主题0": {"文档数": 10, "文档ID": [1, 2]},
                        "主题1": {"文档数": 6, "文档ID": [3, 4]},
                    }
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        (self.topic_root / BERTOPIC_FILE_MAP["llm_clusters"]).write_text(
            json.dumps(
                {
                    "价格争议": {"主题命名": "价格争议", "原始主题集合": ["主题0"], "主题描述": "围绕价格与收费讨论", "文档数": 10},
                    "回应与整改": {"主题命名": "回应与整改", "原始主题集合": ["主题1"], "主题描述": "围绕回应与整改讨论", "文档数": 6},
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        (self.topic_root / BERTOPIC_FILE_MAP["llm_keywords"]).write_text(
            json.dumps({"价格争议": ["收费", "价格"], "回应与整改": ["回应", "整改"]}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (self.topic_root / BERTOPIC_FILE_MAP["temporal"]).write_text(
            json.dumps({"time_nodes": [{"date": "2025-01-01", "label": "01-01", "total": 4}, {"date": "2025-01-07", "label": "01-07", "total": 8}]}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.project_root, ignore_errors=True)

    def test_collect_snapshots_and_build_insights(self) -> None:
        basic_snapshot = collect_basic_analysis_snapshot(self.topic_identifier, "2025-01-01", "2025-01-31", topic_label="示例专题")
        bertopic_snapshot = collect_bertopic_snapshot(self.topic_identifier, "2025-01-01", "2025-01-31", topic_label="示例专题")

        self.assertTrue(basic_snapshot["available"])
        self.assertIn("volume", basic_snapshot["available_functions"])
        self.assertTrue(bertopic_snapshot["available"])
        self.assertEqual(bertopic_snapshot["llm_clusters"][0]["name"], "价格争议")

        basic_insight = build_basic_analysis_insight(basic_snapshot)
        bertopic_insight = build_bertopic_insight(bertopic_snapshot)

        self.assertEqual(basic_insight["section_id"], "basic-analysis-insight")
        self.assertIn("volume.overall", basic_insight["chart_refs"])
        self.assertEqual(bertopic_insight["section_id"], "bertopic-evolution")
        self.assertIn("bertopic.clusters", bertopic_insight["chart_refs"])

    def test_missing_snapshots_are_stable(self) -> None:
        missing_basic = collect_basic_analysis_snapshot("missing-topic", "2025-01-01", "2025-01-31")
        missing_bertopic = collect_bertopic_snapshot("missing-topic", "2025-01-01", "2025-01-31")

        self.assertFalse(missing_basic["available"])
        self.assertIn("archive_missing", missing_basic["trace"]["availability_flags"])
        self.assertFalse(missing_bertopic["available"])
        self.assertIn("archive_missing", missing_bertopic["trace"]["availability_flags"])

    def test_tool_payload_contracts_and_registry(self) -> None:
        basic_snapshot = BasicAnalysisSnapshotResult.model_validate(
            get_basic_analysis_snapshot_payload(
                topic_identifier=self.topic_identifier,
                start="2025-01-01",
                end="2025-01-31",
                topic_label="示例专题",
            )
        )
        basic_insight = BasicAnalysisInsightResult.model_validate(
            build_basic_analysis_insight_payload(snapshot_json=json.dumps(basic_snapshot.result.model_dump(), ensure_ascii=False))
        )
        bertopic_snapshot = BertopicSnapshotResult.model_validate(
            get_bertopic_snapshot_payload(
                topic_identifier=self.topic_identifier,
                start="2025-01-01",
                end="2025-01-31",
                topic_label="示例专题",
            )
        )
        bertopic_insight = BertopicInsightResult.model_validate(
            build_bertopic_insight_payload(snapshot_json=json.dumps(bertopic_snapshot.result.model_dump(), ensure_ascii=False))
        )

        tool_names = {getattr(tool, "name", "") for tool in select_report_tools(runtime_target="deep_report_coordinator")}
        subagent_tools = {
            getattr(tool, "name", "")
            for tool in select_report_tools(runtime_target="deep_report_subagent", agent_name="propagation_analyst")
        }
        bertopic_subagent_tools = {
            getattr(tool, "name", "")
            for tool in select_report_tools(runtime_target="deep_report_subagent", agent_name="bertopic_evolution_analyst")
        }

        self.assertEqual(basic_insight.result.section_title, "基础分析洞察")
        self.assertEqual(bertopic_insight.result.section_title, "BERTopic 主题演化")
        self.assertIn("get_basic_analysis_snapshot", tool_names)
        self.assertIn("build_basic_analysis_insight", tool_names)
        self.assertIn("get_bertopic_snapshot", tool_names)
        self.assertIn("build_bertopic_insight", tool_names)
        self.assertIn("build_basic_analysis_insight", subagent_tools)
        self.assertIn("build_bertopic_insight", bertopic_subagent_tools)

    def test_skill_catalog_discovers_new_frameworks(self) -> None:
        catalog = discover_report_skills("示例专题")
        skill_names = {str(item.get("agentSkillName") or "") for item in catalog}
        basic_skill = resolve_report_skill("basic-analysis-framework", topic="示例专题")
        bertopic_skill = resolve_report_skill("bertopic-evolution-framework", topic="示例专题")

        self.assertIn("basic-analysis-framework", skill_names)
        self.assertIn("bertopic-evolution-framework", skill_names)
        self.assertIn("get_basic_analysis_snapshot", basic_skill.get("toolNames") or [])
        self.assertIn("get_bertopic_snapshot", bertopic_skill.get("toolNames") or [])

    def test_skill_loader_enforces_registered_tool_ids(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown skill tool id"):
            validate_skill_tool_ids(["missing_tool"])
        with self.assertRaisesRegex(ValueError, "not allowed for autonomous runtime"):
            validate_skill_tool_ids(["append_expert_judgement"])

    def test_skill_runtime_sources_follow_available_tool_slice(self) -> None:
        skill_assets = build_report_skill_runtime_assets("示例专题")
        retrieval_sources = select_report_skill_sources(
            skill_assets,
            available_tool_ids=[tool.name for tool in select_report_tools(runtime_target="deep_report_subagent", agent_name="retrieval_router")],
            preferred_skill_keys=["retrieval-router-rules", "sentiment-analysis-methodology"],
        )
        sentiment_sources = select_report_skill_sources(
            skill_assets,
            available_tool_ids=[tool.name for tool in select_report_tools(runtime_target="deep_report_coordinator")],
            preferred_skill_keys=["sentiment-analysis-methodology"],
        )
        self.assertEqual(len(retrieval_sources), 1)
        self.assertIn("retrieval-router-rules", retrieval_sources[0])
        self.assertEqual(len(sentiment_sources), 1)
        self.assertIn("sentiment-analysis-methodology", sentiment_sources[0])

    def test_canonical_catalog_excludes_manual_mutation_from_default_surfaces(self) -> None:
        catalog = {item.tool_id: item for item in get_report_tool_catalog()}
        coordinator_names = {tool.name for tool in select_report_tools(runtime_target="deep_report_coordinator")}
        self.assertIn("append_expert_judgement", catalog)
        self.assertNotIn("append_expert_judgement", coordinator_names)

    def test_runtime_surfaces_resolve_shared_tools_from_canonical_registry(self) -> None:
        coordinator_tools = {tool.name: tool for tool in select_report_tools(runtime_target="deep_report_coordinator")}
        self.assertIs(coordinator_tools["build_basic_analysis_insight"], get_report_tool("build_basic_analysis_insight"))
        self.assertIs(coordinator_tools["verify_claim_v2"], get_report_tool("verify_claim_v2"))

    def test_capability_manifest_aligns_with_audit_ledger(self) -> None:
        capability_ids = {item.ability_id for item in get_report_capability_catalog()}
        self.assertIn("evidence.normalize_retrieve_verify", capability_ids)
        self.assertIn("semantic.agenda_frame_builder", capability_ids)
        self.assertIn("semantic.utility_gate", capability_ids)
        agenda = get_report_capability("semantic.agenda_frame_builder")
        self.assertEqual(agenda.framework_layer, "subagent")
        self.assertIn("AgendaFrameMap", agenda.owned_artifacts)
        self.assertIn("agenda_frame_builder", agenda.entrypoints)

    def test_specialist_runtime_slices_map_to_declared_capability_owners(self) -> None:
        specialist_agents = [
            "retrieval_router",
            "archive_evidence_organizer",
            "timeline_analyst",
            "stance_conflict",
            "agenda_frame_builder",
            "claim_actor_conflict",
            "propagation_analyst",
            "bertopic_evolution_analyst",
            "decision_utility_judge",
            "validator",
        ]
        for agent_name in specialist_agents:
            self.assertTrue(
                select_runtime_capability_ids(runtime_target="deep_report_subagent", agent_name=agent_name),
                msg=f"{agent_name} should resolve to at least one capability owner",
            )

    def test_runtime_skill_defaults_follow_capability_contracts(self) -> None:
        self.assertIn("retrieval-router-rules", select_runtime_skill_ids(runtime_target="deep_report_subagent", agent_name="retrieval_router"))
        self.assertIn(
            "chart-interpretation-guidelines",
            select_runtime_skill_ids(runtime_target="deep_report_subagent", agent_name="propagation_analyst"),
        )
        self.assertIn(
            "sentiment-analysis-methodology",
            select_runtime_skill_ids(runtime_target="deep_report_coordinator"),
        )

    def test_guidance_only_skills_attach_only_to_compatible_runtime_slice(self) -> None:
        skill_assets = build_report_skill_runtime_assets("示例专题")
        propagation_sources = select_report_skill_sources(
            skill_assets,
            available_tool_ids=[
                tool.name
                for tool in select_report_tools(runtime_target="deep_report_subagent", agent_name="propagation_analyst")
            ],
            runtime_target="deep_report_subagent",
            agent_name="propagation_analyst",
        )
        retrieval_sources = select_report_skill_sources(
            skill_assets,
            available_tool_ids=[
                tool.name
                for tool in select_report_tools(runtime_target="deep_report_subagent", agent_name="retrieval_router")
            ],
            runtime_target="deep_report_subagent",
            agent_name="retrieval_router",
        )
        self.assertTrue(any("chart-interpretation-guidelines" in item for item in propagation_sources))
        self.assertFalse(any("chart-interpretation-guidelines" in item for item in retrieval_sources))

    def test_ensure_bertopic_results_can_prepare_missing_archive(self) -> None:
        shutil.rmtree(self.topic_root, ignore_errors=True)
        ctx = TopicContext(identifier=self.topic_identifier, display_name="示例专题", log_project=self.topic_identifier, aliases=[self.topic_identifier])

        def _fake_run_topic_bertopic_job(payload):
            self.topic_root.mkdir(parents=True, exist_ok=True)
            (self.topic_root / BERTOPIC_FILE_MAP["summary"]).write_text(
                json.dumps({"主题文档统计": {"主题0": {"文档数": 3}}}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return {"status": "ok", "message": "done"}

        with patch("src.topic.api.run_topic_bertopic_job", side_effect=_fake_run_topic_bertopic_job):
            state = ensure_bertopic_results(
                self.topic_identifier,
                start="2025-01-01",
                end="2025-01-31",
                ctx=ctx,
                run_if_missing=True,
            )

        self.assertTrue(state["ready"])
        self.assertTrue(state["prepared"])


if __name__ == "__main__":
    unittest.main()
