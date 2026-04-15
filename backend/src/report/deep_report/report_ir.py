from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple, Type, get_origin

from pydantic import BaseModel

from .schemas import (
    AgendaFrameMap,
    ArtifactManifest,
    ArtifactRecord,
    ConflictMap,
    EventFlashpoint,
    FigureArtifactRecord,
    FigureBlock,
    GroupDemand,
    MechanismSummary,
    PlacementPlan,
    PlatformEmotionProfile,
    ReportIR,
    ReportIRActor,
    ReportIRClaim,
    ReportIREvent,
    ReportIREvidenceEntry,
    ReportIRRecommendationCandidate,
    ReportIRRisk,
    ReportIRStanceRow,
    ReportIRUnresolvedPoint,
    RiskTrafficLight,
    StructuredReport,
    UtilityAssessment,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


_T = Type[BaseModel]


def _coerce_validate(model_cls: _T, data: Dict[str, Any]) -> Any:
    """model_validate 的防御性包装：把 LLM 可能输出的 null 在 List 字段上强制转成 []，
    避免 Pydantic v2 抛出 'Input should be a valid list'。不修改任何模型定义。"""
    if not isinstance(data, dict):
        return model_cls.model_validate(data)
    coerced = dict(data)
    for field_name, field_info in model_cls.model_fields.items():
        if get_origin(field_info.annotation) is list and coerced.get(field_name) is None:
            coerced[field_name] = []
    return model_cls.model_validate(coerced)


def _source_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    report_data = payload.get("report_data")
    if isinstance(report_data, dict):
        return report_data
    return payload if isinstance(payload, dict) else {}


def _citation_index(source: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    citations = source.get("citations") if isinstance(source.get("citations"), list) else []
    return {
        str(item.get("citation_id") or "").strip(): item
        for item in citations
        if isinstance(item, dict) and str(item.get("citation_id") or "").strip()
    }


def _collect_keywords(source: Dict[str, Any]) -> List[str]:
    keywords: List[str] = []
    for item in source.get("key_evidence") or []:
        if not isinstance(item, dict):
            continue
        subject = str(item.get("subject") or "").strip()
        stance = str(item.get("stance") or "").strip()
        for token in (subject, stance):
            if token and token not in keywords:
                keywords.append(token)
    return keywords[:12]


def _collect_entities(source: Dict[str, Any]) -> List[str]:
    names: List[str] = []
    for item in source.get("subjects") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if name and name not in names:
            names.append(name)
    for item in source.get("key_evidence") or []:
        if not isinstance(item, dict):
            continue
        subject = str(item.get("subject") or "").strip()
        if subject and subject not in names:
            names.append(subject)
    return names


def _collect_platforms(citations: Dict[str, Dict[str, Any]]) -> List[str]:
    platforms: List[str] = []
    for item in citations.values():
        platform = str(item.get("platform") or "").strip()
        if platform and platform not in platforms:
            platforms.append(platform)
    return platforms


def _build_evidence_ledger(source: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, List[str]], Dict[str, str]]:
    citations = _citation_index(source)
    entries: List[Dict[str, Any]] = []
    citation_to_evidence: Dict[str, List[str]] = {}
    finding_to_claim: Dict[str, str] = {}
    for item in source.get("key_evidence") or []:
        if not isinstance(item, dict):
            continue
        evidence_id = str(item.get("evidence_id") or "").strip()
        if not evidence_id:
            continue
        citation_ids = [
            str(citation_id).strip()
            for citation_id in (item.get("citation_ids") or [])
            if str(citation_id or "").strip()
        ]
        citation = citations.get(citation_ids[0], {}) if citation_ids else {}
        # 优先取 raw_content 作为可引用金句，其次用 snippet
        raw_quote_src = str(
            citation.get("raw_content") or citation.get("snippet") or item.get("source_summary") or ""
        ).strip()
        entries.append(
            ReportIREvidenceEntry(
                evidence_id=evidence_id,
                source_id=str(item.get("source_id") or "").strip(),
                title=str(citation.get("title") or item.get("finding") or "").strip(),
                snippet=str(citation.get("snippet") or item.get("source_summary") or "").strip(),
                platform=str(citation.get("platform") or "").strip(),
                published_at=str(citation.get("published_at") or item.get("time_label") or "").strip(),
                url=str(citation.get("url") or "").strip(),
                entities=[str(item.get("subject") or "").strip()] if str(item.get("subject") or "").strip() else [],
                confidence=str(item.get("confidence") or "medium").strip() or "medium",
                # BettaFish 深度引证字段
                author=str(citation.get("author") or "").strip(),
                sentiment_label=str(citation.get("sentiment_label") or "").strip(),
                raw_quote=raw_quote_src[:150],
                emotion_signals=[],  # 由 _build_platform_emotion_profiles 按平台填充
                engagement_views=int((citation.get("engagement") or {}).get("views") or 0),
            ).model_dump()
        )
        for citation_id in citation_ids:
            citation_to_evidence.setdefault(citation_id, []).append(evidence_id)
        finding = str(item.get("finding") or "").strip()
        if finding:
            finding_to_claim[finding] = f"claim:{evidence_id}"
    return entries, citation_to_evidence, finding_to_claim


def _collect_referenced_evidence_ids(value: Any) -> List[str]:
    ids: List[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {
                "evidence_refs",
                "representative_evidence_ids",
                "support_evidence_ids",
                "trigger_evidence_ids",
                "related_evidence_ids",
                "source_refs",
            } and isinstance(item, list):
                for evidence_id in item:
                    text = str(evidence_id or "").strip()
                    if text and text not in ids:
                        ids.append(text)
            else:
                for evidence_id in _collect_referenced_evidence_ids(item):
                    if evidence_id not in ids:
                        ids.append(evidence_id)
    elif isinstance(value, list):
        for item in value:
            for evidence_id in _collect_referenced_evidence_ids(item):
                if evidence_id not in ids:
                    ids.append(evidence_id)
    return ids


def _append_missing_evidence_entries(entries: List[Dict[str, Any]], source: Dict[str, Any]) -> List[Dict[str, Any]]:
    known_ids = {
        str(item.get("evidence_id") or "").strip()
        for item in entries
        if isinstance(item, dict) and str(item.get("evidence_id") or "").strip()
    }
    extra_ids = _collect_referenced_evidence_ids(
        {
            "timeline": source.get("timeline"),
            "subjects": source.get("subjects"),
            "agenda_frame_map": source.get("agenda_frame_map"),
            "conflict_map": source.get("conflict_map"),
            "mechanism_summary": source.get("mechanism_summary"),
            "risk_judgement": source.get("risk_judgement"),
            "unverified_points": source.get("unverified_points"),
        }
    )
    for evidence_id in extra_ids:
        if evidence_id in known_ids:
            continue
        entries.append(
            ReportIREvidenceEntry(
                evidence_id=evidence_id,
                source_id="",
                title=f"补充证据 {evidence_id}",
                snippet="该证据仅用于保持结构化 trace 完整，正文不应额外扩写。",
                platform="",
                published_at="",
                url="",
                entities=[],
                confidence="low",
            ).model_dump()
        )
        known_ids.add(evidence_id)
    return entries


def _artifact_paths(manifest: Dict[str, Any]) -> List[str]:
    paths: List[str] = []
    versions = manifest.get("versions") if isinstance(manifest.get("versions"), list) else []
    for item in versions:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        if path and path not in paths:
            paths.append(path)
    return paths


def _ensure_manifest(manifest: ArtifactManifest | Dict[str, Any] | None) -> ArtifactManifest:
    return manifest if isinstance(manifest, ArtifactManifest) else ArtifactManifest.model_validate(manifest or {})


def _latest_version(records: List[Dict[str, Any]], artifact_id: str) -> int:
    latest = 0
    for item in records:
        if not isinstance(item, dict):
            continue
        if str(item.get("artifact_id") or "").strip() != artifact_id:
            continue
        latest = max(latest, int(item.get("version") or 0))
    return latest


def build_artifact_manifest(
    *,
    topic_identifier: str,
    thread_id: str,
    task_id: str,
    structured_path: str = "",
    basic_analysis_path: str = "",
    bertopic_path: str = "",
    agenda_path: str = "",
    conflict_path: str = "",
    mechanism_path: str = "",
    utility_path: str = "",
    draft_path: str = "",
    draft_v2_path: str = "",
    validation_path: str = "",
    repair_plan_path: str = "",
    graph_state_path: str = "",
    full_path: str = "",
    runtime_path: str = "",
    approval_path: str = "",
    ir_path: str = "",
    figure_artifacts: List[Dict[str, Any]] | List[FigureArtifactRecord] | None = None,
    generated_at: str = "",
    version: int = 1,
    policy_version: str = "policy.v1",
    graph_run_id: str = "",
    previous_manifest: ArtifactManifest | Dict[str, Any] | None = None,
) -> ArtifactManifest:
    created_at = str(generated_at or "").strip() or _utc_now()
    previous = _ensure_manifest(previous_manifest)
    previous_versions = [item.model_dump() for item in previous.versions]
    previous_figures = [
        item.model_dump() if isinstance(item, FigureArtifactRecord) else dict(item)
        for item in (previous.figures or [])
        if isinstance(item, (FigureArtifactRecord, dict))
    ]

    def _record(artifact_id: str, artifact_type: str, path: str, derived_from: List[str]) -> ArtifactRecord:
        path_text = str(path or "").strip()
        prior_version = _latest_version(previous_versions, artifact_id)
        return ArtifactRecord(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            version=max(int(version or 1), prior_version or 1),
            status="ready" if path_text else "pending",
            path=path_text,
            derived_from=derived_from,
            thread_id=str(thread_id or "").strip(),
            task_id=str(task_id or "").strip(),
            policy_version=str(policy_version or "").strip() or "policy.v1",
            graph_run_id=str(graph_run_id or "").strip(),
            parent_artifact_ids=list(derived_from),
            source_artifact_ids=list(derived_from),
            created_at=created_at,
        )

    ir = _record("ir", "ir", ir_path, ["structured_projection"])
    structured_projection = _record("structured_projection", "structured_projection", structured_path, [])
    basic_analysis_insight = _record("basic_analysis_insight", "basic_analysis_insight", basic_analysis_path, ["structured_projection"])
    bertopic_insight = _record("bertopic_insight", "bertopic_insight", bertopic_path, ["structured_projection"])
    agenda_frame_map = _record("agenda_frame_map", "agenda_frame_map", agenda_path, ["structured_projection", "ir"])
    conflict_map = _record("conflict_map", "conflict_map", conflict_path, ["agenda_frame_map", "structured_projection", "ir"])
    mechanism_summary = _record("mechanism_summary", "mechanism_summary", mechanism_path, ["conflict_map", "agenda_frame_map", "structured_projection", "ir"])
    utility_assessment = _record("utility_assessment", "utility_assessment", utility_path, ["mechanism_summary", "conflict_map", "agenda_frame_map", "structured_projection", "ir"])
    draft_bundle = _record("draft_bundle", "draft_bundle", draft_path, ["ir"])
    draft_bundle_v2 = _record("draft_bundle_v2", "draft_bundle_v2", draft_v2_path, ["draft_bundle", "ir"] if str(draft_path or "").strip() else ["ir"])
    validation_result = _record("validation_result", "validation_result", validation_path, ["draft_bundle_v2", "ir"] if str(draft_v2_path or "").strip() else ["ir"])
    repair_plan = _record("repair_plan", "repair_plan", repair_plan_path, ["validation_result", "draft_bundle_v2", "ir"] if str(validation_path or "").strip() else ["draft_bundle_v2", "ir"])
    graph_state = _record("graph_state", "graph_state", graph_state_path, ["repair_plan", "validation_result", "draft_bundle_v2", "ir"] if str(graph_state_path or "").strip() else ["validation_result", "draft_bundle_v2", "ir"])
    _full_derived: list[str] = ["ir"]
    if str(draft_path or "").strip():
        _full_derived.insert(0, "draft_bundle")
    if str(draft_v2_path or "").strip():
        _full_derived.insert(0, "draft_bundle_v2")
    if str(graph_state_path or "").strip():
        _full_derived.insert(0, "graph_state")
    full_markdown = _record("full_markdown", "full_markdown", full_path, _full_derived)
    runtime_log = _record("runtime_log", "runtime_log", runtime_path, [])
    approval_records = _record("approval_records", "approval_records", approval_path, ["runtime_log"])
    current_ready = [
        item
        for item in [
            structured_projection,
            ir,
            basic_analysis_insight,
            bertopic_insight,
            agenda_frame_map,
            conflict_map,
            mechanism_summary,
            utility_assessment,
            draft_bundle,
            draft_bundle_v2,
            validation_result,
            repair_plan,
            graph_state,
            full_markdown,
            runtime_log,
            approval_records,
        ]
        if item.path
    ]
    merged_versions = list(previous_versions)
    for item in current_ready:
        item_dump = item.model_dump()
        if not merged_versions:
            merged_versions.append(item_dump)
            continue
        duplicate = next(
            (
                existing
                for existing in reversed(merged_versions)
                if str(existing.get("artifact_id") or "").strip() == item.artifact_id
                and str(existing.get("path") or "").strip() == item.path
                and str(existing.get("status") or "").strip() == item.status
            ),
            None,
        )
        if duplicate is None:
            item.version = _latest_version(merged_versions, item.artifact_id) + 1 if _latest_version(merged_versions, item.artifact_id) else item.version
            item_dump = item.model_dump()
            merged_versions.append(item_dump)
    merged_figures: List[Dict[str, Any]] = list(previous_figures)
    for item in figure_artifacts or []:
        record = item if isinstance(item, FigureArtifactRecord) else FigureArtifactRecord.model_validate(item)
        existing = next(
            (
                candidate
                for candidate in reversed(merged_figures)
                if str(candidate.get("figure_id") or "").strip() == str(record.figure_id or "").strip()
            ),
            None,
        )
        if existing is None:
            merged_figures.append(record.model_dump())
            continue
        if (
            str(existing.get("dataset_ref") or "").strip() == str(record.dataset_ref or "").strip()
            and str(existing.get("option_ref") or "").strip() == str(record.option_ref or "").strip()
            and str(existing.get("placement_anchor") or "").strip() == str(record.placement_anchor or "").strip()
            and str(existing.get("render_status") or "").strip() == str(record.render_status or "").strip()
        ):
            continue
        record.version = int(existing.get("version") or 1) + 1
        merged_figures.append(record.model_dump())
    manifest = ArtifactManifest(
        ir=ir,
        structured_projection=structured_projection,
        basic_analysis_insight=basic_analysis_insight,
        bertopic_insight=bertopic_insight,
        agenda_frame_map=agenda_frame_map,
        conflict_map=conflict_map,
        mechanism_summary=mechanism_summary,
        utility_assessment=utility_assessment,
        draft_bundle=draft_bundle,
        draft_bundle_v2=draft_bundle_v2,
        validation_result=validation_result,
        repair_plan=repair_plan,
        graph_state=graph_state,
        full_markdown=full_markdown,
        runtime_log=runtime_log,
        approval_records=approval_records,
        figures=[FigureArtifactRecord.model_validate(item) for item in merged_figures],
        versions=[ArtifactRecord.model_validate(item) for item in merged_versions],
    )
    return manifest


def summarize_report_ir(report_ir: ReportIR | Dict[str, Any]) -> Dict[str, Any]:
    ir = report_ir if isinstance(report_ir, ReportIR) else ReportIR.model_validate(report_ir if isinstance(report_ir, dict) else {})
    return {
        "topic": ir.meta.topic_label or ir.meta.topic_identifier,
        "range": {
            "start": ir.meta.time_scope.start,
            "end": ir.meta.time_scope.end,
        },
        "summary": ir.narrative_views.executive_summary,
        "key_findings": ir.narrative_views.key_findings[:6],
        "counts": {
            "timeline": len(ir.timeline.events),
            "actors": len(ir.actor_registry.actors),
            "claims": len(ir.claim_set.claims),
            "agenda_issues": len(ir.agenda_frame_map.issues),
            "agenda_frames": len(ir.agenda_frame_map.frames),
            "conflict_edges": len(ir.conflict_map.edges),
            "mechanism_paths": len(ir.mechanism_summary.amplification_paths),
            "bridge_nodes": len(ir.mechanism_summary.bridge_nodes),
            "evidence": len(ir.evidence_ledger.entries),
            "risks": len(ir.risk_register.risks),
            "unresolved": len(ir.unresolved_points.items),
            "recommendations": len(ir.recommendation_candidates.items),
            "figures": len(ir.figures),
        },
        "utility_assessment": {
            "decision": ir.utility_assessment.decision,
            "missing_dimensions": list(ir.utility_assessment.missing_dimensions),
            "fallback_trace_count": len(ir.utility_assessment.fallback_trace),
        },
    }


def _build_agenda_frame_map(source: Dict[str, Any], actor_name_to_id: Dict[str, str]) -> Dict[str, Any]:
    existing = source.get("agenda_frame_map")
    if isinstance(existing, dict) and existing:
        return _coerce_validate(AgendaFrameMap, existing).model_dump()
    keywords = [str(item).strip() for item in (_collect_keywords(source) or []) if str(item or "").strip()]
    timeline = source.get("timeline") if isinstance(source.get("timeline"), list) else []
    issues = [
        {
            "issue_id": f"issue-{index}",
            "label": keyword,
            "salience": round(0.5 + index * 0.05, 4),
            "time_scope": [str((timeline[0] or {}).get("date") or "").strip()] if timeline else [],
            "source_refs": [],
        }
        for index, keyword in enumerate(keywords[:4], start=1)
    ]
    attributes = [
        {
            "attribute_id": f"attribute-{index}",
            "label": token,
            "attribute_type": "focus",
            "salience": round(0.45 + index * 0.05, 4),
            "source_refs": [],
        }
        for index, token in enumerate(keywords[4:8] or keywords[:2], start=1)
    ]
    edges = [
        {
            "edge_id": f"issue-attr-{index}",
            "issue_id": issues[min(index - 1, len(issues) - 1)]["issue_id"] if issues else "",
            "attribute_id": attributes[min(index - 1, len(attributes) - 1)]["attribute_id"] if attributes else "",
            "weight": 0.62,
            "time_scope": [str((timeline[0] or {}).get("date") or "").strip()] if timeline else [],
            "source_refs": [],
        }
        for index, _ in enumerate(attributes[: max(1, len(issues))], start=1)
        if issues and attributes
    ]
    frames = [
        {
            "frame_id": f"frame-{index}",
            "problem": str(item.get("finding") or "").strip(),
            "cause": "多源讨论对问题定义存在差异",
            "judgment": "讨论焦点已从事实描述转向责任与影响评估",
            "remedy": "澄清关键事实并针对核心属性回应",
            "confidence": 0.64,
            "source_refs": [str(item.get("evidence_id") or "").strip()] if str(item.get("evidence_id") or "").strip() else [],
        }
        for index, item in enumerate((source.get("key_evidence") or [])[:3], start=1)
        if isinstance(item, dict)
    ]
    frame_carriers = [
        {
            "actor_id": actor_name_to_id.get(str(item.get("name") or "").strip(), str(item.get("subject_id") or "").strip()),
            "frame_ids": [frame["frame_id"] for frame in frames[:2]],
            "role": str(item.get("role") or "carrier").strip(),
        }
        for item in (source.get("subjects") or [])[:3]
        if isinstance(item, dict)
    ]
    frame_shifts = [
        {
            "shift_id": "frame-shift-1",
            "from_frame_id": frames[0]["frame_id"],
            "to_frame_id": frames[min(1, len(frames) - 1)]["frame_id"],
            "time_anchor": str((timeline[0] or {}).get("date") or "").strip() if timeline else "",
            "trigger_refs": [],
        }
        for _ in [1]
        if len(frames) >= 2
    ]
    counter_frames = [
        {
            "frame_id": frames[min(1, len(frames) - 1)]["frame_id"],
            "counter_to_frame_id": frames[0]["frame_id"],
            "support_refs": [],
        }
        for _ in [1]
        if len(frames) >= 2
    ]
    return AgendaFrameMap.model_validate(
        {
            "issues": issues,
            "attributes": attributes,
            "issue_attribute_edges": edges,
            "frames": frames,
            "frame_carriers": frame_carriers,
            "frame_shifts": frame_shifts,
            "counter_frames": counter_frames,
            "summary": f"识别 {len(issues)} 个议题节点、{len(frames)} 条框架记录。",
        }
    ).model_dump()


def _build_conflict_map(source: Dict[str, Any], actor_name_to_id: Dict[str, str]) -> Dict[str, Any]:
    existing = source.get("conflict_map")
    if isinstance(existing, dict) and existing:
        return _coerce_validate(ConflictMap, existing).model_dump()
    conflict_points = source.get("conflict_points") if isinstance(source.get("conflict_points"), list) else []
    claims = []
    edges = []
    resolutions = []
    actors = []
    seen_actor_ids = set()
    for index, item in enumerate(conflict_points[:8], start=1):
        if not isinstance(item, dict):
            continue
        conflict_id = str(item.get("conflict_id") or f"conflict-{index}").strip()
        title = str(item.get("title") or "").strip()
        description = str(item.get("description") or "").strip()
        subjects = [str(value).strip() for value in (item.get("subjects") or []) if str(value or "").strip()]
        claim_id = f"claimrec:{conflict_id}"
        claims.append(
            {
                "claim_id": claim_id,
                "proposition": title or description,
                "proposition_slots": {"subject": subjects[0] if subjects else "", "predicate": "conflict", "object": title or description, "qualifier": "negative", "polarity": "assert"},
                "raw_spans": [value for value in [title, description] if value],
                "time_anchor": "",
                "source_ids": [],
                "verification_status": "sustained_conflict",
                "evidence_coverage": "partial",
                "source_diversity": 0,
                "temporal_confidence": 0.0,
                "evidence_density": 0.45,
            }
        )
        actor_scope = []
        for subject in subjects:
            actor_id = actor_name_to_id.get(subject, subject)
            actor_scope.append(actor_id)
            if actor_id in seen_actor_ids:
                continue
            seen_actor_ids.add(actor_id)
            actors.append(
                {
                    "actor_id": actor_id,
                    "name": subject,
                    "aliases": [subject],
                    "role_type": "public",
                    "organization_type": "community",
                    "speaker_role": "observer",
                    "relay_role": "origin",
                    "account_tier": "secondary",
                    "is_official": False,
                    "stance": "conflicted",
                    "stance_shift": description or "冲突仍在持续",
                    "claim_ids": [claim_id],
                    "representative_evidence_ids": [],
                    "conflict_actor_ids": [actor_name_to_id.get(name, name) for name in subjects if actor_name_to_id.get(name, name) != actor_id],
                    "confidence": 0.6,
                }
            )
        edges.append(
            {
                "edge_id": f"edge:{conflict_id}",
                "claim_a_id": claim_id,
                "claim_b_id": claim_id,
                "conflict_type": "evidence_conflict",
                "actor_scope": actor_scope,
                "time_scope": [],
                "evidence_refs": [],
                "evidence_density": 0.45,
                "confidence": 0.4,
            }
        )
        resolutions.append(
            {
                "claim_id": claim_id,
                "status": "sustained_conflict",
                "reason": description or "当前证据未完成收敛",
                "supporting_claim_ids": [claim_id],
                "unresolved_reason": "仍需补充更稳定来源完成裁决",
                "resolution_confidence": 0.35,
            }
        )
    return ConflictMap.model_validate(
        {
            "claims": claims,
            "actor_positions": actors,
            "edges": edges,
            "resolution_summary": resolutions,
            "summary": "；".join([str(item.get("title") or "").strip() for item in conflict_points[:4] if isinstance(item, dict)]),
            "evidence_density": 0.45 if claims else 0.0,
            "source_diversity": 0,
        }
    ).model_dump()


def _build_mechanism_summary(source: Dict[str, Any]) -> Dict[str, Any]:
    existing = source.get("mechanism_summary")
    if isinstance(existing, dict) and existing:
        return _coerce_validate(MechanismSummary, existing).model_dump()
    propagation = source.get("propagation_features") if isinstance(source.get("propagation_features"), list) else []
    timeline = source.get("timeline") if isinstance(source.get("timeline"), list) else []
    trigger_events = [
        {
            "event_id": str(item.get("event_id") or f"trigger-{index}").strip(),
            "time_anchor": str(item.get("date") or "").strip(),
            "description": str(item.get("description") or item.get("title") or "").strip(),
            "linked_claim_ids": [],
            "evidence_refs": [],
        }
        for index, item in enumerate(timeline[:3], start=1)
        if isinstance(item, dict)
    ]
    amplification_paths = [
        {
            "path_id": f"path-{index}",
            "source_actor_ids": [],
            "bridge_actor_ids": [],
            "platform_sequence": [],
            "evidence_refs": [],
        }
        for index, _item in enumerate(propagation[:1], start=1)
    ]
    phase_shifts = [
        {
            "phase_id": f"phase-{index}",
            "from_phase": "attention",
            "to_phase": "discussion",
            "reason": str(item.get("explanation") or item.get("finding") or "").strip(),
            "evidence_refs": [],
        }
        for index, item in enumerate(propagation[:2], start=1)
        if isinstance(item, dict) and str(item.get("explanation") or item.get("finding") or "").strip()
    ]
    return MechanismSummary.model_validate(
        {
            "amplification_paths": amplification_paths,
            "trigger_events": trigger_events,
            "phase_shifts": phase_shifts,
            "cross_platform_bridges": [],
            "bridge_nodes": [],
            "confidence_summary": "已根据传播特征与时间线生成基础机制摘要。",
        }
    ).model_dump()


def _build_utility_assessment(source: Dict[str, Any]) -> Dict[str, Any]:
    existing = source.get("utility_assessment")
    if isinstance(existing, dict) and existing:
        return _coerce_validate(UtilityAssessment, existing).model_dump()
    suggestions = source.get("suggested_actions") if isinstance(source.get("suggested_actions"), list) else []
    unresolved = source.get("unverified_points") if isinstance(source.get("unverified_points"), list) else []
    risks = source.get("risk_judgement") if isinstance(source.get("risk_judgement"), list) else []
    subjects = source.get("subjects") if isinstance(source.get("subjects"), list) else []
    task = source.get("task") if isinstance(source.get("task"), dict) else {}
    has_time_window = bool(str(task.get("start") or "").strip() and str(task.get("end") or "").strip())
    has_actionable_recommendations = any(
        isinstance(item, dict) and str(item.get("action") or "").strip() and str(item.get("rationale") or "").strip()
        for item in suggestions
    )
    missing_dimensions = []
    if not subjects:
        missing_dimensions.append("key_actors")
    if not risks:
        missing_dimensions.append("conditional_risk")
    if not has_actionable_recommendations:
        missing_dimensions.append("actionable_recommendations")
    if not unresolved:
        missing_dimensions.append("uncertainty_boundary")
    decision = "pass" if len(missing_dimensions) <= 1 else "fallback_recompile"
    return UtilityAssessment.model_validate(
        {
            "assessment_id": "utility-1",
            "has_object_scope": bool(subjects),
            "has_time_window": has_time_window,
            "has_key_actors": bool(subjects),
            "has_primary_contradiction": bool(source.get("conflict_map") or source.get("conflict_points")),
            "has_mechanism_explanation": bool(source.get("mechanism_summary") or source.get("propagation_features")),
            "has_issue_frame_context": bool(source.get("agenda_frame_map") or source.get("key_evidence")),
            "has_conditional_risk": bool(risks),
            "has_actionable_recommendations": has_actionable_recommendations,
            "has_uncertainty_boundary": bool(unresolved),
            "recommendation_has_object": bool(subjects),
            "recommendation_has_time": has_time_window,
            "recommendation_has_action": has_actionable_recommendations,
            "recommendation_has_preconditions": False,
            "recommendation_has_side_effects": bool(unresolved),
            "missing_dimensions": missing_dimensions,
            "fallback_trace": [],
            "improvement_trace": [],
            "decision": decision,
            "next_action": "允许进入编译层。" if decision == "pass" else "补齐缺失维度后再进入正式文稿编译。",
            "utility_confidence": 0.84 if decision == "pass" else 0.62,
            "confidence": 0.84 if decision == "pass" else 0.62,
        }
    ).model_dump()


# ---------------------------------------------------------------------------
# BettaFish 质量数据结构 builders
# ---------------------------------------------------------------------------

def _normalize_key(text: str) -> str:
    """将任意文本规范化为安全的 key 字符串。"""
    import re
    return re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff_-]+", "_", text).strip("_")[:30] or "unknown"


def _build_platform_emotion_profiles(
    event_analysis: Dict[str, Any],
    citations: Dict[str, Dict[str, Any]],
) -> List[PlatformEmotionProfile]:
    """从 event_analysis.platform_analysis 或 citations 分组构建平台情绪档案。"""
    profiles: List[PlatformEmotionProfile] = []

    # 优先从 event_analyst 的结构化输出读取
    platform_data = (
        (event_analysis.get("platform_analysis") or {}).get("platforms") or []
    )
    for plat in platform_data:
        if not isinstance(plat, dict):
            continue
        platform_name = str(plat.get("platform") or "").strip()
        if not platform_name:
            continue
        raw_dist = plat.get("emotion_dist") or {}
        emotion_dist: Dict[str, float] = {}
        for k, v in raw_dist.items():
            try:
                emotion_dist[str(k)] = float(v)
            except (TypeError, ValueError):
                pass
        quotes = [
            str(q).strip()[:100]
            for q in (plat.get("representative_quotes") or [])
            if str(q or "").strip()
        ][:5]
        profiles.append(
            PlatformEmotionProfile(
                platform=platform_name,
                dominant_emotion=str(plat.get("dominant_emotion") or "").strip(),
                emotion_distribution=emotion_dist,
                representative_quotes=quotes,
                discussion_style=str(plat.get("discussion_style") or "").strip(),
                evidence_ids=[
                    str(eid).strip()
                    for eid in (plat.get("evidence_ids") or [])
                    if str(eid or "").strip()
                ],
            )
        )

    # Fallback: 从 citations 按平台分组推断
    if not profiles:
        by_platform: Dict[str, List[Dict[str, Any]]] = {}
        for cit in citations.values():
            plat = str(cit.get("platform") or "").strip()
            if plat:
                by_platform.setdefault(plat, []).append(cit)
        for plat, cits in by_platform.items():
            # 统计情感标签分布
            from collections import Counter
            sentiment_counts: Counter = Counter()
            quotes: List[str] = []
            for cit in cits:
                sl = str(cit.get("sentiment_label") or "").strip()
                if sl:
                    sentiment_counts[sl] += 1
                q = str(cit.get("snippet") or "").strip()[:80]
                if q and len(quotes) < 3:
                    quotes.append(q)
            total = sum(sentiment_counts.values()) or 1
            emotion_dist = {k: round(v / total, 2) for k, v in sentiment_counts.most_common(3)}
            dominant = sentiment_counts.most_common(1)[0][0] if sentiment_counts else ""
            profiles.append(
                PlatformEmotionProfile(
                    platform=plat,
                    dominant_emotion=dominant,
                    emotion_distribution=emotion_dist,
                    representative_quotes=quotes,
                    evidence_ids=[
                        str(cit.get("citation_id") or "").strip()
                        for cit in cits[:5]
                        if str(cit.get("citation_id") or "").strip()
                    ],
                )
            )
    return profiles


def _build_event_flashpoints(
    timeline_events: List[Dict[str, Any]],
    citation_to_evidence: Dict[str, List[str]],
    ev_by_id: Dict[str, Dict[str, Any]],
    event_analysis: Dict[str, Any],
) -> List[EventFlashpoint]:
    """从时间线节点和 event_analysis 构建事件全景速览爆点。"""
    flashpoints: List[EventFlashpoint] = []
    for i, event in enumerate(timeline_events):
        if not isinstance(event, dict):
            continue
        event_id = str(event.get("event_id") or "").strip()
        if not event_id:
            continue
        # 将 citation_ids → evidence_ids（与主流程保持一致）
        citation_ids = [
            str(cid).strip()
            for cid in (event.get("citation_ids") or [])
            if str(cid or "").strip()
        ]
        support_ids = list({
            eid
            for cid in citation_ids
            for eid in citation_to_evidence.get(cid, [])
        })
        # 从支撑证据中聚合情绪关键词
        emotion_keywords: List[str] = []
        peak_views = 0
        for ev_id in support_ids[:5]:
            ev = ev_by_id.get(ev_id) or {}
            for kw in (ev.get("emotion_signals") or []):
                kw = str(kw).strip()
                if kw and kw not in emotion_keywords:
                    emotion_keywords.append(kw)
            peak_views = max(peak_views, int(ev.get("engagement_views") or 0))
        # 如果证据里没有情绪关键词，尝试从 summary 提取
        if not emotion_keywords:
            summary = str(event.get("summary") or event.get("title") or "").strip()
            # 简单地把高频词作为关键词候选
            if summary:
                emotion_keywords = []  # 留空，由 deep_writer 从上下文推断
        peak_readership = f"{peak_views // 10000}万" if peak_views >= 10000 else ""
        flashpoints.append(
            EventFlashpoint(
                flashpoint_id=f"flash-{i + 1}",
                time_label=str(event.get("time_label") or "").strip(),
                event_title=str(event.get("summary") or "").strip()[:80],
                peak_readership=peak_readership,
                core_emotion_keywords=emotion_keywords[:5],
                support_evidence_ids=support_ids[:5],
            )
        )
    return flashpoints


def _build_group_demands(
    event_analysis: Dict[str, Any],
    actors: List[Dict[str, Any]],
    ev_by_id: Dict[str, Dict[str, Any]],
) -> List[GroupDemand]:
    """从 event_analysis.actor_distribution 或主体注册构建群体诉求清单。"""
    demands: List[GroupDemand] = []

    # 优先从 event_analyst 结构化输出读取
    actor_list = (event_analysis.get("actor_distribution") or {}).get("actors") or []
    for actor_data in actor_list:
        if not isinstance(actor_data, dict):
            continue
        name = str(actor_data.get("name") or "").strip()
        if not name:
            continue
        key_statements = [
            str(stmt).strip()
            for stmt in (actor_data.get("key_statements") or [])
            if str(stmt or "").strip()
        ][:3]
        stance = str(actor_data.get("stance") or "").strip()
        evidence_ids = [
            str(eid).strip()
            for eid in (actor_data.get("evidence_ids") or [])
            if str(eid or "").strip()
        ]
        demands.append(
            GroupDemand(
                group_id=f"group-{_normalize_key(name)}",
                group_name=name,
                high_freq_demands=[stance] if stance else [],
                golden_quotes=key_statements,
                evidence_ids=evidence_ids,
            )
        )

    # Fallback: 从主体注册中提取基础信息
    if not demands:
        for item in actors[:8]:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            summary = str(item.get("summary") or "").strip()
            demands.append(
                GroupDemand(
                    group_id=f"group-{_normalize_key(name)}",
                    group_name=name,
                    high_freq_demands=[summary] if summary else [],
                    golden_quotes=[],
                    evidence_ids=[
                        str(cid).strip()
                        for cid in (item.get("citation_ids") or [])
                        if str(cid or "").strip()
                    ][:3],
                )
            )
    return demands


def _build_risk_traffic_lights(
    risk_judgements: List[Dict[str, Any]],
) -> List[RiskTrafficLight]:
    """将现有风险判断映射为三色灯结构。"""
    lights: List[RiskTrafficLight] = []
    for item in risk_judgements[:5]:
        if not isinstance(item, dict):
            continue
        risk_id = str(item.get("risk_id") or "").strip()
        if not risk_id:
            continue
        level = str(item.get("level") or "medium").strip().lower()
        color: str = "red" if level == "high" else "green" if level == "low" else "yellow"
        summary_text = str(item.get("summary") or item.get("label") or "").strip()
        lights.append(
            RiskTrafficLight(
                risk_id=risk_id,
                light_color=color,  # type: ignore[arg-type]
                flashpoint_prediction=summary_text[:100],
                trigger_threshold="",  # 由 deep_writer 结合上下文补充
                preemptive_action="",  # 由 deep_writer 结合上下文补充
                support_evidence_ids=[
                    str(cid).strip()
                    for cid in (item.get("citation_ids") or [])
                    if str(cid or "").strip()
                ][:3],
            )
        )
    return lights


def _extract_netizen_quotes(evidence_entries: List[Dict[str, Any]]) -> List[str]:
    """从证据账本中提取最佳原文金句（有内容、长度适中）。"""
    quotes: List[str] = []
    seen: set = set()
    for entry in evidence_entries:
        # 优先用 raw_quote，其次用 snippet
        quote = str(entry.get("raw_quote") or entry.get("snippet") or "").strip()
        if len(quote) >= 20 and quote not in seen:
            seen.add(quote)
            quotes.append(quote[:120])
        if len(quotes) >= 15:
            break
    return quotes


def build_report_ir(
    payload: StructuredReport | Dict[str, Any],
    *,
    task_id: str = "",
    artifact_manifest: ArtifactManifest | Dict[str, Any] | None = None,
    ir_version: str = "1.0",
) -> ReportIR:
    structured = payload if isinstance(payload, StructuredReport) else StructuredReport.model_validate(payload if isinstance(payload, dict) else {})
    manifest = _ensure_manifest(artifact_manifest)
    source = _source_payload(structured.model_dump())
    # 提取 event_analysis（来自 event_analyst 子代理，保留在 StructuredReport.event_analysis 字段）
    event_analysis: Dict[str, Any] = structured.event_analysis or {}
    figure_blocks = source.get("figures") if isinstance(source.get("figures"), list) else structured.model_dump().get("figures") if isinstance(structured.model_dump().get("figures"), list) else []
    placement_payload = source.get("placement_plan") if isinstance(source.get("placement_plan"), dict) else structured.model_dump().get("placement_plan") if isinstance(structured.model_dump().get("placement_plan"), dict) else {}
    task = source.get("task") if isinstance(source.get("task"), dict) else {}
    conclusion = source.get("conclusion") if isinstance(source.get("conclusion"), dict) else {}
    citations = _citation_index(source)
    evidence_entries, citation_to_evidence, _finding_to_claim = _build_evidence_ledger(source)
    evidence_entries = _append_missing_evidence_entries(evidence_entries, source)
    # 构建证据ID索引，供 BettaFish builders 使用
    ev_by_id: Dict[str, Dict[str, Any]] = {
        str(e.get("evidence_id") or "").strip(): e
        for e in evidence_entries
        if isinstance(e, dict) and str(e.get("evidence_id") or "").strip()
    }
    actors = source.get("subjects") if isinstance(source.get("subjects"), list) else []
    actor_name_to_id = {
        str(item.get("name") or "").strip(): str(item.get("subject_id") or "").strip()
        for item in actors
        if isinstance(item, dict) and str(item.get("name") or "").strip() and str(item.get("subject_id") or "").strip()
    }

    claims: List[Dict[str, Any]] = []
    for entry in evidence_entries:
        evidence_id = str(entry.get("evidence_id") or "").strip()
        snippet = str(entry.get("snippet") or "").strip()
        title = str(entry.get("title") or "").strip()
        claims.append(
            ReportIRClaim(
                claim_id=f"claim:{evidence_id}",
                text=title or snippet,
                category="evidence_finding",
                status="supported",
                write_policy="factual",
                support_evidence_ids=[evidence_id],
                counter_evidence_ids=[],
            ).model_dump()
        )
    for item in source.get("unverified_points") or []:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("item_id") or "").strip()
        statement = str(item.get("statement") or "").strip()
        if not item_id or not statement:
            continue
        claims.append(
            ReportIRClaim(
                claim_id=f"claim:{item_id}",
                text=statement,
                category="unresolved",
                status="unverified",
                write_policy="bounded",
                support_evidence_ids=[],
                counter_evidence_ids=[],
            ).model_dump()
        )
    for item in source.get("validation_notes") or []:
        if not isinstance(item, dict):
            continue
        note_id = str(item.get("note_id") or "").strip()
        message = str(item.get("message") or "").strip()
        if not note_id or not message:
            continue
        if any(existing.get("text") == message for existing in claims):
            continue
        claims.append(
            ReportIRClaim(
                claim_id=f"claim:{note_id}",
                text=message,
                category=str(item.get("category") or "validation").strip() or "validation",
                status="partially_supported",
                write_policy="bounded",
                support_evidence_ids=[],
                counter_evidence_ids=[],
            ).model_dump()
        )
    evidence_to_claim = {
        str(evidence_id).strip(): str(claim.get("claim_id") or "").strip()
        for claim in claims
        for evidence_id in (claim.get("support_evidence_ids") or [])
        if str(evidence_id or "").strip() and str(claim.get("claim_id") or "").strip()
    }

    risks: List[Dict[str, Any]] = []
    for item in source.get("risk_judgement") or []:
        if not isinstance(item, dict):
            continue
        risk_id = str(item.get("risk_id") or "").strip()
        if not risk_id:
            continue
        related_evidence = []
        for citation_id in item.get("citation_ids") or []:
            related_evidence.extend(citation_to_evidence.get(str(citation_id).strip(), []))
        related_claims = [
            claim.get("claim_id")
            for claim in claims
            if set(claim.get("support_evidence_ids") or []) & set(related_evidence)
        ]
        risks.append(
            ReportIRRisk(
                risk_id=risk_id,
                risk_type=str(item.get("label") or "").strip(),
                severity=str(item.get("level") or "medium").strip() or "medium",
                trigger_claim_ids=[str(claim_id).strip() for claim_id in related_claims if str(claim_id or "").strip()],
                trigger_evidence_ids=[str(evidence_id).strip() for evidence_id in related_evidence if str(evidence_id or "").strip()],
                spread_condition=str(item.get("summary") or "").strip(),
            ).model_dump()
        )

    recommendations: List[Dict[str, Any]] = []
    for item in source.get("suggested_actions") or []:
        if not isinstance(item, dict):
            continue
        action_id = str(item.get("action_id") or "").strip()
        if not action_id:
            continue
        support_claim_ids: List[str] = []
        for citation_id in item.get("citation_ids") or []:
            for evidence_id in citation_to_evidence.get(str(citation_id).strip(), []):
                claim_id = evidence_to_claim.get(str(evidence_id).strip(), "")
                if claim_id and claim_id not in support_claim_ids:
                    support_claim_ids.append(claim_id)
        recommendations.append(
            ReportIRRecommendationCandidate(
                candidate_id=action_id,
                action=str(item.get("action") or "").strip(),
                rationale=str(item.get("rationale") or "").strip(),
                preconditions=[str(item.get("rationale") or "").strip()] if str(item.get("rationale") or "").strip() else [],
                priority=str(item.get("priority") or "medium").strip() or "medium",
                support_claim_ids=support_claim_ids,
            ).model_dump()
        )

    unresolved_items: List[Dict[str, Any]] = []
    for item in source.get("unverified_points") or []:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("item_id") or "").strip()
        if not item_id:
            continue
        unresolved_items.append(
            ReportIRUnresolvedPoint(
                item_id=item_id,
                statement=str(item.get("statement") or "").strip(),
                reason=str(item.get("reason") or "").strip(),
                related_claim_ids=[f"claim:{item_id}"],
                related_evidence_ids=[],
            ).model_dump()
        )

    coverage: Dict[str, int] = {
        "supported": len([claim for claim in claims if claim.get("status") == "supported"]),
        "partially_supported": len([claim for claim in claims if claim.get("status") == "partially_supported"]),
        "unverified": len([claim for claim in claims if claim.get("status") == "unverified"]),
        "conflicting": len([claim for claim in claims if claim.get("status") == "conflicting"]),
    }
    traceability = {
        "claims_with_support": len([claim for claim in claims if claim.get("support_evidence_ids")]),
        "risks_with_evidence": len([risk for risk in risks if risk.get("trigger_evidence_ids")]),
        "recommendations_with_claims": len([item for item in recommendations if item.get("support_claim_ids")]),
    }
    return ReportIR(
        meta={
            "ir_version": ir_version,
            "topic_identifier": str(task.get("topic_identifier") or "").strip(),
            "topic_label": str(task.get("topic_label") or task.get("topic_identifier") or "").strip(),
            "thread_id": str(task.get("thread_id") or "").strip(),
            "task_id": str(task_id or "").strip(),
            "time_scope": {
                "start": str(task.get("start") or "").strip(),
                "end": str(task.get("end") or "").strip(),
            },
            "mode": str(task.get("mode") or "fast").strip() or "fast",
            "generated_at": _utc_now(),
            "source_artifacts": _artifact_paths(manifest.model_dump()),
        },
        topic_scope={
            "entities": _collect_entities(source),
            "platforms": _collect_platforms(citations),
            "keywords": _collect_keywords(source),
            "exclusions": [],
            "analysis_question_set": ["时间线如何演化", "主体立场如何分化", "风险如何扩散"],
        },
        timeline={
            "events": [
                ReportIREvent(
                    event_id=str(item.get("event_id") or "").strip(),
                    time_label=str(item.get("date") or "").strip(),
                    summary=str(item.get("description") or item.get("title") or "").strip(),
                    support_evidence_ids=[
                        evidence_id
                        for citation_id in (item.get("citation_ids") or [])
                        for evidence_id in citation_to_evidence.get(str(citation_id).strip(), [])
                    ],
                ).model_dump()
                for item in (source.get("timeline") or [])
                if isinstance(item, dict) and str(item.get("event_id") or "").strip()
            ]
        },
        actor_registry={
            "actors": [
                ReportIRActor(
                    actor_id=str(item.get("subject_id") or "").strip(),
                    canonical_name=str(item.get("name") or "").strip(),
                    aliases=[str(item.get("name") or "").strip()],
                    category=str(item.get("category") or "").strip(),
                ).model_dump()
                for item in actors
                if isinstance(item, dict) and str(item.get("subject_id") or "").strip()
            ]
        },
        stance_matrix={
            "rows": [
                ReportIRStanceRow(
                    actor_id=actor_name_to_id.get(str(item.get("subject") or "").strip(), str(item.get("subject") or "").strip()),
                    stance=str(item.get("stance") or "").strip(),
                    stance_shift=str(item.get("summary") or "").strip(),
                    conflict_actor_ids=[
                        actor_name_to_id.get(str(name).strip(), str(name).strip())
                        for name in (item.get("conflict_with") or [])
                        if str(name or "").strip()
                    ],
                    support_evidence_ids=[
                        evidence_id
                        for citation_id in (item.get("citation_ids") or [])
                        for evidence_id in citation_to_evidence.get(str(citation_id).strip(), [])
                    ],
                ).model_dump()
                for item in (source.get("stance_matrix") or [])
                if isinstance(item, dict) and str(item.get("subject") or "").strip()
            ]
        },
        claim_set={"claims": claims},
        evidence_ledger={"entries": evidence_entries},
        agenda_frame_map=_build_agenda_frame_map(source, actor_name_to_id),
        conflict_map=_build_conflict_map(source, actor_name_to_id),
        mechanism_summary=_build_mechanism_summary(source),
        risk_register={"risks": risks},
        unresolved_points={"items": unresolved_items},
        recommendation_candidates={"items": recommendations},
        utility_assessment=_build_utility_assessment(source),
        narrative_views={
            "executive_summary": str(conclusion.get("executive_summary") or "").strip(),
            "key_findings": [
                str(item).strip()
                for item in (conclusion.get("key_findings") or [])
                if str(item or "").strip()
            ][:8],
            "view_models": {
                "key_risks": [
                    str(item).strip()
                    for item in (conclusion.get("key_risks") or [])
                    if str(item or "").strip()
                ][:8],
                "confidence_label": str(conclusion.get("confidence_label") or "").strip(),
            },
        },
        figures=[FigureBlock.model_validate(item).model_dump() for item in figure_blocks if isinstance(item, dict)],
        placement_plan=PlacementPlan.model_validate(placement_payload or {}),
        validation={
            "notes": source.get("validation_notes") if isinstance(source.get("validation_notes"), list) else [],
            "claim_coverage": coverage,
            "traceability_stats": traceability,
        },
        # BettaFish 质量字段
        platform_emotion_profiles=_build_platform_emotion_profiles(event_analysis, citations),
        event_flashpoints=_build_event_flashpoints(
            source.get("timeline") or [],
            citation_to_evidence,
            ev_by_id,
            event_analysis,
        ),
        group_demands=_build_group_demands(event_analysis, actors, ev_by_id),
        risk_traffic_lights=_build_risk_traffic_lights(
            source.get("risk_judgement") or []
        ),
        emotion_conduction_formula=str(
            (event_analysis.get("sentiment_summary") or {}).get("overall_emotion") or ""
        ).strip(),
        netizen_quotes=_extract_netizen_quotes(evidence_entries),
    )


def attach_report_ir(
    payload: Dict[str, Any],
    *,
    artifact_manifest: ArtifactManifest | Dict[str, Any] | None = None,
    task_id: str = "",
) -> Dict[str, Any]:
    structured_model = StructuredReport.model_validate(payload if isinstance(payload, dict) else {})
    manifest = _ensure_manifest(artifact_manifest or structured_model.artifact_manifest)
    report_ir = build_report_ir(structured_model, task_id=task_id, artifact_manifest=manifest)
    structured = structured_model.model_dump()
    structured["report_ir"] = report_ir.model_dump()
    structured["artifact_manifest"] = manifest.model_dump()
    structured.setdefault("metadata", {})
    structured["metadata"]["ir_version"] = str(report_ir.meta.ir_version or "1.0").strip()
    structured["metadata"]["artifact_manifest"] = manifest.model_dump()
    structured["meta"] = {**(structured.get("meta") or {}), **structured["metadata"]}
    return structured
