from __future__ import annotations

import json
from typing import List

from langchain.tools import tool

from .payloads import (
    build_basic_analysis_insight_payload,
    build_bertopic_insight_payload,
    build_agenda_frame_map_payload,
    build_claim_actor_conflict_payload,
    build_event_timeline_payload,
    build_mechanism_summary_payload,
    build_section_packet_payload,
    compute_report_metrics_payload,
    detect_risk_signals_payload,
    extract_actor_positions_payload,
    get_basic_analysis_snapshot_payload,
    get_corpus_coverage_payload,
    get_bertopic_snapshot_payload,
    judge_decision_utility_payload,
    normalize_task_payload,
    retrieve_evidence_cards_payload,
    verify_claim_payload,
)


@tool
def normalize_task(task_text: str, topic_identifier: str, start: str, end: str, mode: str, hints_json: str = "{}") -> str:
    """冻结任务边界并生成可复用的 task contract，不执行原始文档检索。"""
    return json.dumps(
        normalize_task_payload(
            task_text=str(task_text or "").strip(),
            topic_identifier=str(topic_identifier or "").strip(),
            start=str(start or "").strip(),
            end=str(end or "").strip(),
            mode=str(mode or "fast").strip().lower() or "fast",
            hints_json=str(hints_json or "{}"),
        ),
        ensure_ascii=False,
        indent=2,
    )


@tool
def get_corpus_coverage(
    contract_id: str,
    retrieval_scope_json: str = "{}",
    filters_json: str = "{}",
    include_samples: bool = False,
    limit: int = 20,
) -> str:
    """诊断 contract 绑定专题在当前 scope 下的覆盖与缺口。专题身份固定由 contract_id 解析，时间窗口只作为受控 scope 参数。"""
    return json.dumps(
        get_corpus_coverage_payload(
            contract_id=str(contract_id or "").strip(),
            retrieval_scope_json=str(retrieval_scope_json or "{}"),
            filters_json=str(filters_json or "{}"),
            include_samples=bool(include_samples),
            limit=max(1, min(int(limit or 20), 30)),
        ),
        ensure_ascii=False,
        indent=2,
    )


@tool
def retrieve_evidence_cards(
    contract_id: str,
    retrieval_scope_json: str = "{}",
    intent: str = "",
    filters_json: str = "{}",
    sort_by: str = "relevance",
    limit: int = 12,
    cursor: str = "",
) -> str:
    """按意图返回分页证据卡。专题身份固定由 contract_id 解析，时间范围通过 retrieval_scope 做受控裁剪。"""
    return json.dumps(
        retrieve_evidence_cards_payload(
            contract_id=str(contract_id or "").strip(),
            retrieval_scope_json=str(retrieval_scope_json or "{}"),
            intent=str(intent or "").strip(),
            filters_json=str(filters_json or "{}"),
            sort_by=str(sort_by or "relevance").strip(),
            limit=max(1, min(int(limit or 12), 20)),
            cursor=str(cursor or "").strip(),
        ),
        ensure_ascii=False,
        indent=2,
    )


@tool
def build_event_timeline(normalized_task_json: str, evidence_ids_json: str = "[]", max_nodes: int = 8) -> str:
    """将证据卡压缩成时间线节点，节点必须带支持或冲突证据。"""
    return json.dumps(
        build_event_timeline_payload(
            normalized_task_json=str(normalized_task_json or "{}"),
            evidence_ids_json=str(evidence_ids_json or "[]"),
            max_nodes=max(1, min(int(max_nodes or 8), 12)),
        ),
        ensure_ascii=False,
        indent=2,
    )


@tool
def compute_report_metrics(normalized_task_json: str, metric_scope: str = "overview", evidence_ids_json: str = "[]") -> str:
    """生成强分类、chart-ready 的指标对象，不直接输出自然语言结论。"""
    return json.dumps(
        compute_report_metrics_payload(
            normalized_task_json=str(normalized_task_json or "{}"),
            metric_scope=str(metric_scope or "overview").strip(),
            evidence_ids_json=str(evidence_ids_json or "[]"),
        ),
        ensure_ascii=False,
        indent=2,
    )


@tool
def extract_actor_positions(normalized_task_json: str, evidence_ids_json: str = "[]", actor_limit: int = 10) -> str:
    """抽取主体、立场、冲突关系，不负责最终 prose 写作。"""
    return json.dumps(
        extract_actor_positions_payload(
            normalized_task_json=str(normalized_task_json or "{}"),
            evidence_ids_json=str(evidence_ids_json or "[]"),
            actor_limit=max(1, min(int(actor_limit or 10), 16)),
        ),
        ensure_ascii=False,
        indent=2,
    )


@tool
def build_agenda_frame_map(normalized_task_json: str, evidence_ids_json: str = "[]", actor_positions_json: str = "[]", conflict_map_json: str = "{}", timeline_nodes_json: str = "[]") -> str:
    """构建议题-属性-框架图，只输出 typed analysis artifact。"""
    return json.dumps(
        build_agenda_frame_map_payload(
            normalized_task_json=str(normalized_task_json or "{}"),
            evidence_ids_json=str(evidence_ids_json or "[]"),
            actor_positions_json=str(actor_positions_json or "[]"),
            conflict_map_json=str(conflict_map_json or "{}"),
            timeline_nodes_json=str(timeline_nodes_json or "[]"),
        ),
        ensure_ascii=False,
        indent=2,
    )


@tool
def build_claim_actor_conflict(normalized_task_json: str, evidence_ids_json: str = "[]", actor_positions_json: str = "[]", timeline_nodes_json: str = "[]") -> str:
    """构建断言-主体冲突图，只输出 typed judgment objects。"""
    return json.dumps(
        build_claim_actor_conflict_payload(
            normalized_task_json=str(normalized_task_json or "{}"),
            evidence_ids_json=str(evidence_ids_json or "[]"),
            actor_positions_json=str(actor_positions_json or "[]"),
            timeline_nodes_json=str(timeline_nodes_json or "[]"),
        ),
        ensure_ascii=False,
        indent=2,
    )


@tool
def build_mechanism_summary(normalized_task_json: str, evidence_ids_json: str = "[]", timeline_nodes_json: str = "[]", conflict_map_json: str = "{}", metric_refs_json: str = "[]") -> str:
    """提炼传播路径、触发事件与阶段跃迁，不直接输出 prose。"""
    return json.dumps(
        build_mechanism_summary_payload(
            normalized_task_json=str(normalized_task_json or "{}"),
            evidence_ids_json=str(evidence_ids_json or "[]"),
            timeline_nodes_json=str(timeline_nodes_json or "[]"),
            conflict_map_json=str(conflict_map_json or "{}"),
            metric_refs_json=str(metric_refs_json or "[]"),
        ),
        ensure_ascii=False,
        indent=2,
    )


@tool
def detect_risk_signals(normalized_task_json: str, evidence_ids_json: str = "[]", metric_refs_json: str = "[]", discourse_conflict_map_json: str = "", actor_positions_json: str = "[]") -> str:
    """输出风险项对象，优先基于 evidence/metrics/conflict map，而不是直接写建议。"""
    return json.dumps(
        detect_risk_signals_payload(
            normalized_task_json=str(normalized_task_json or "{}"),
            evidence_ids_json=str(evidence_ids_json or "[]"),
            metric_refs_json=str(metric_refs_json or "[]"),
            discourse_conflict_map_json=str(discourse_conflict_map_json or ""),
            actor_positions_json=str(actor_positions_json or "[]"),
        ),
        ensure_ascii=False,
        indent=2,
    )


@tool
def judge_decision_utility(normalized_task_json: str, risk_signals_json: str = "[]", recommendation_candidates_json: str = "[]", unresolved_points_json: str = "[]", agenda_frame_map_json: str = "{}", conflict_map_json: str = "{}", mechanism_summary_json: str = "{}", actor_positions_json: str = "[]") -> str:
    """评估当前判断对象是否已具备进入正式文稿的决策可用性。"""
    return json.dumps(
        judge_decision_utility_payload(
            normalized_task_json=str(normalized_task_json or "{}"),
            risk_signals_json=str(risk_signals_json or "[]"),
            recommendation_candidates_json=str(recommendation_candidates_json or "[]"),
            unresolved_points_json=str(unresolved_points_json or "[]"),
            agenda_frame_map_json=str(agenda_frame_map_json or "{}"),
            conflict_map_json=str(conflict_map_json or "{}"),
            mechanism_summary_json=str(mechanism_summary_json or "{}"),
            actor_positions_json=str(actor_positions_json or "[]"),
        ),
        ensure_ascii=False,
        indent=2,
    )


@tool
def verify_claim_v2(normalized_task_json: str, claims_json: str, evidence_ids_json: str = "[]", strictness: str = "balanced") -> str:
    """对句级断言做回链校验，返回支持、反证和缺口。"""
    return json.dumps(
        verify_claim_payload(
            normalized_task_json=str(normalized_task_json or "{}"),
            claims_json=str(claims_json or "[]"),
            evidence_ids_json=str(evidence_ids_json or "[]"),
            strictness=str(strictness or "balanced").strip(),
        ),
        ensure_ascii=False,
        indent=2,
    )


@tool
def get_basic_analysis_snapshot(topic_identifier: str, start: str, end: str = "", topic_label: str = "") -> str:
    """读取基础分析归档快照，只做能力诊断和归档读取。"""
    return json.dumps(
        get_basic_analysis_snapshot_payload(
            topic_identifier=str(topic_identifier or "").strip(),
            start=str(start or "").strip(),
            end=str(end or "").strip() or str(start or "").strip(),
            topic_label=str(topic_label or "").strip(),
        ),
        ensure_ascii=False,
        indent=2,
    )


@tool
def build_basic_analysis_insight(snapshot_json: str) -> str:
    """把基础分析快照转换成报告可消费的章节洞察对象。"""
    return json.dumps(
        build_basic_analysis_insight_payload(snapshot_json=str(snapshot_json or "{}")),
        ensure_ascii=False,
        indent=2,
    )


@tool
def get_bertopic_snapshot(topic_identifier: str, start: str, end: str = "", topic_label: str = "") -> str:
    """读取 BERTopic 归档快照，只做能力诊断和归档读取。"""
    return json.dumps(
        get_bertopic_snapshot_payload(
            topic_identifier=str(topic_identifier or "").strip(),
            start=str(start or "").strip(),
            end=str(end or "").strip() or str(start or "").strip(),
            topic_label=str(topic_label or "").strip(),
        ),
        ensure_ascii=False,
        indent=2,
    )


@tool
def build_bertopic_insight(snapshot_json: str) -> str:
    """把 BERTopic 快照转换成报告可消费的主题演化章节洞察对象。"""
    return json.dumps(
        build_bertopic_insight_payload(snapshot_json=str(snapshot_json or "{}")),
        ensure_ascii=False,
        indent=2,
    )


@tool
def build_section_packet(normalized_task_json: str, section_id: str, section_goal: str = "", evidence_ids_json: str = "[]", metric_refs_json: str = "[]", claim_ids_json: str = "[]") -> str:
    """组装章节材料包，作为 writer 的直接输入。"""
    return json.dumps(
        build_section_packet_payload(
            normalized_task_json=str(normalized_task_json or "{}"),
            section_id=str(section_id or "").strip(),
            section_goal=str(section_goal or "").strip(),
            evidence_ids_json=str(evidence_ids_json or "[]"),
            metric_refs_json=str(metric_refs_json or "[]"),
            claim_ids_json=str(claim_ids_json or "[]"),
        ),
        ensure_ascii=False,
        indent=2,
    )
