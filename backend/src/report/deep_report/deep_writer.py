"""
deep_report/deep_writer.py
===========================
LLM深度写作模块，复刻BettaFish的章节生成能力。

核心能力：
- 每章节独立调用LLM，而非确定性数据拼接
- 使用模板和证据构建写作prompt
- 内容密度验证（最少字数约束）
- JSON解析修复机制
- 输出DraftUnitV2结构化单元
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Tuple

from .schemas import (
    DraftBundleV2,
    DraftUnitV2,
    TraceRef,
    SectionPlan,
    CompilerSectionPlanItem,
    CompilerSceneProfile,
)
from .report_ir import ReportIR

logger = logging.getLogger(__name__)


# 内容密度阈值（借鉴BettaFish，已增强）
_MIN_SECTION_BODY_CHARACTERS = 800   # 每章节最少800字（从400提升）
_MIN_NARRATIVE_CHARACTERS = 400      # 叙事部分最少400字（从200提升）
_MIN_QUOTE_COUNT = 5                  # 最少5条具体引用
_MIN_DATA_POINTS = 10                 # 最少10个数据点
_MAX_RETRY_ATTEMPTS = 3               # 最大重试次数（从2提升到3）
_MAX_REFLECTION_ROUNDS = 2            # 反思循环轮数（借鉴BettaFish）
# BettaFish 关键章节必须含表格
_REQUIRED_TABLE_SECTIONS = {
    "事件演变", "传播路径", "舆论立场与结构", "影响与动作", "附录",
    "timeline", "mechanism", "actors", "risks", "ledger",
}


class DeepWriterError(Exception):
    """深度写作失败异常"""
    pass


class SectionContentTooSparseError(DeepWriterError):
    """章节内容稀疏异常"""
    def __init__(self, section_id: str, body_chars: int, narrative_chars: int, quote_count: int):
        super().__init__(
            f"章节 {section_id} 内容密度不足: "
            f"正文{body_chars}字（要求≥{_MIN_SECTION_BODY_CHARACTERS}），"
            f"叙事{narrative_chars}字（要求≥{_MIN_NARRATIVE_CHARACTERS}），"
            f"引用{quote_count}条（要求≥{_MIN_QUOTE_COUNT})"
        )
        self.section_id = section_id
        self.body_chars = body_chars
        self.narrative_chars = narrative_chars
        self.quote_count = quote_count


class InsufficientQuotesError(DeepWriterError):
    """引用不足异常"""
    def __init__(self, section_id: str, quote_count: int):
        super().__init__(
            f"章节 {section_id} 引用不足: 仅{quote_count}条引用（要求≥{_MIN_QUOTE_COUNT}）"
        )
        self.section_id = section_id
        self.quote_count = quote_count


def _get_llm_client() -> Any:
    """获取报告写作LLM客户端（使用项目统一的LangChain配置）"""
    from ...utils.ai import build_langchain_chat_model
    llm, _ = build_langchain_chat_model(task="report", model_role="report", temperature=0.2, max_tokens=2000)
    if llm is None:
        raise DeepWriterError("未找到可用的 LangChain 模型配置")
    return llm


def _load_skill_instructions(skill_keys: List[str]) -> str:
    """加载skill指导内容"""
    from ..skills import resolve_report_skill
    instructions = []
    for key in skill_keys:
        try:
            skill = resolve_report_skill(key)
            if isinstance(skill, dict):
                content = skill.get("instructionsMarkdown", "") or skill.get("instructions_markdown", "")
                if content:
                    instructions.append(f"【{key}】\n{content[:2000]}")
        except Exception as e:
            logger.warning(f"加载skill {key} 失败: {e}")
    return "\n\n".join(instructions) if instructions else ""


def _extract_evidence_for_section(
    report_ir: ReportIR,
    section_id: str,
) -> List[Dict[str, Any]]:
    """提取章节相关的证据卡（含 BettaFish 深度引证字段）"""
    payload = report_ir if isinstance(report_ir, ReportIR) else ReportIR.model_validate(report_ir)

    relevant_evidence = []
    for entry in payload.evidence_ledger.entries[:20]:
        evidence_dict = {
            "evidence_id": entry.evidence_id,
            "finding": getattr(entry, "finding", ""),
            "subject": getattr(entry, "subject", ""),
            "stance": getattr(entry, "stance", ""),
            "time_label": getattr(entry, "time_label", ""),
            "source_summary": getattr(entry, "source_summary", ""),
            "confidence": entry.confidence,
            "snippet": getattr(entry, "snippet", ""),
            "platform": getattr(entry, "platform", ""),
            # BettaFish 深度引证字段
            "author": getattr(entry, "author", ""),
            "sentiment_label": getattr(entry, "sentiment_label", ""),
            "raw_quote": getattr(entry, "raw_quote", ""),
            "emotion_signals": getattr(entry, "emotion_signals", []),
            "engagement_views": getattr(entry, "engagement_views", 0),
        }
        relevant_evidence.append(evidence_dict)

    return relevant_evidence


def _extract_claims_for_section(
    report_ir: ReportIR,
    section_id: str,
) -> List[Dict[str, Any]]:
    """提取章节相关的断言"""
    payload = report_ir if isinstance(report_ir, ReportIR) else ReportIR.model_validate(report_ir)

    claims = []
    for claim in payload.claim_set.claims[:15]:  # 最多15条
        claim_dict = {
            "claim_id": claim.claim_id,
            "proposition": claim.proposition,
            "verification_status": claim.verification_status,
            "source_ids": claim.source_ids,
        }
        claims.append(claim_dict)

    return claims


def _extract_bettafish_context(
    report_ir: ReportIR,
    section_title: str,
    section_id: str,
) -> Dict[str, Any]:
    """
    按章节标题/ID 按需提取 BettaFish 数据结构，注入写作 prompt。
    返回结构化字典，key 对应各 BettaFish 数据类型。
    """
    payload = report_ir if isinstance(report_ir, ReportIR) else ReportIR.model_validate(report_ir)
    ctx: Dict[str, Any] = {}

    title_lower = section_title.lower()
    id_lower = section_id.lower()

    is_timeline = any(k in title_lower or k in id_lower for k in ["事件演变", "timeline", "事件脉络"])
    is_mechanism = any(k in title_lower or k in id_lower for k in ["传播路径", "mechanism", "传播链"])
    is_actors = any(k in title_lower or k in id_lower for k in ["舆论立场", "actors", "group", "群体", "主体"])
    is_risk = any(k in title_lower or k in id_lower for k in ["影响与动作", "风险", "risk", "recommendations", "建议"])

    # 1. 事件爆点（事件演变章节）
    if is_timeline and payload.event_flashpoints:
        ctx["flashpoints"] = [
            {
                "time": f.time_label,
                "event": f.event_title,
                "peak_readership": f.peak_readership,
                "emotion_keywords": f.core_emotion_keywords,
            }
            for f in payload.event_flashpoints[:8]
        ]

    # 2. 平台情绪雷达（传播路径章节 + 概览所有章节）
    if payload.platform_emotion_profiles:
        ctx["platform_profiles"] = [
            {
                "platform": p.platform,
                "dominant_emotion": p.dominant_emotion,
                "representative_quotes": p.representative_quotes[:2],
                "discussion_style": p.discussion_style,
                "emotion_dist": p.emotion_distribution,
            }
            for p in payload.platform_emotion_profiles[:6]
        ]

    # 3. 情绪传导公式（传播路径章节）
    if is_mechanism and payload.emotion_conduction_formula:
        ctx["emotion_formula"] = payload.emotion_conduction_formula

    # 4. 群体诉求（舆论立场章节）
    if is_actors and payload.group_demands:
        ctx["group_demands"] = [
            {
                "group": g.group_name,
                "demands": g.high_freq_demands,
                "golden_quotes": g.golden_quotes[:2],
            }
            for g in payload.group_demands[:8]
        ]

    # 5. 风险三色灯（影响与动作章节）
    if is_risk and payload.risk_traffic_lights:
        color_map = {"red": "🔴红灯", "yellow": "🟡黄灯", "green": "🟢绿灯"}
        ctx["traffic_lights"] = [
            {
                "color_label": color_map.get(t.light_color, t.light_color),
                "prediction": t.flashpoint_prediction,
                "threshold": t.trigger_threshold,
                "action": t.preemptive_action,
                "risk_id": t.risk_id,
            }
            for t in payload.risk_traffic_lights[:5]
        ]

    # 6. 网民金句（所有章节可用）
    if payload.netizen_quotes:
        ctx["netizen_quotes"] = payload.netizen_quotes[:8]

    return ctx


def _build_section_writer_prompt(
    section: CompilerSectionPlanItem,
    report_ir: ReportIR,
    scene_profile: CompilerSceneProfile,
    skill_instructions: str,
) -> tuple:
    """构建 BettaFish 质量章节写作 prompt（含结构化表格数据注入）"""
    payload = report_ir if isinstance(report_ir, ReportIR) else ReportIR.model_validate(report_ir)

    evidence = _extract_evidence_for_section(payload, section.section_id)
    claims = _extract_claims_for_section(payload, section.section_id)
    bettafish_ctx = _extract_bettafish_context(payload, section.title, section.section_id)

    system_prompt = """你是舆情报告深度写作代理，负责产出媲美BettaFish的专业舆情分析报告章节。

**写作原则（必须严格遵守）**：
1. 锚定现象 → 交代机制 → 点出含义（禁止单纯数据堆砌）
2. 证据校准：语气强度匹配证据确定性
3. 必须嵌入具体原文引用（格式: > "原文..." —— 来源/平台/作者）
4. 提供了表格数据时，必须输出对应 Markdown 表格
5. 禁止伪造数据（无数据的列留空或省略该列，不得捏造数字）
6. 禁止暴露系统字段名、工具名、模块名
7. 禁止写"网友认为"，必须直接引用具体原文

**输出格式（JSON）**：
```json
{
  "section_id": "xxx",
  "title": "章节标题",
  "blocks": [
    {"type": "heading", "text": "二级标题", "anchor": "anchor-id"},
    {"type": "paragraph", "text": "完整段落正文（≥80字）..."},
    {"type": "table", "markdown": "| 列1 | 列2 |\\n|---|---|\\n| 值1 | 值2 |"},
    {"type": "quote", "text": "引用原文内容", "attribution": "来源/作者/平台"},
    {"type": "list", "items": ["条目1", "条目2"]},
    {"type": "callout", "text": "风险提示", "tone": "warning"},
    {"type": "hr"}
  ],
  "evidence_refs": ["ev-xxx"],
  "claim_refs": ["claim-xxx"]
}
```
block类型: heading / paragraph(≥80字) / table(Markdown格式) / quote(原文+归因) / list / callout / hr
"""

    parts: List[str] = [
        "## 章节写作任务",
        f"- section_id: {section.section_id}",
        f"- 标题: {section.title}",
        f"- 目标字数: {section.target_words}字",
        "",
        "## 章节写作要求（必须满足）",
        section.goal or "按模板要求进行深度分析",
        "",
    ]

    # --- 注入 BettaFish 结构化数据 ---

    if bettafish_ctx.get("flashpoints"):
        parts.append("## 事件爆点数据（必须生成事件全景速览表格）")
        parts.append("| 时间 | 爆点事件 | 传播量级 | 核心情绪关键词 |")
        parts.append("|---|---|---|---|")
        for f in bettafish_ctx["flashpoints"]:
            kw = "、".join(f["emotion_keywords"]) if f["emotion_keywords"] else "—"
            peak = f["peak_readership"] or "—"
            parts.append(f"| {f['time'] or '—'} | {f['event'] or '—'} | {peak} | {kw} |")
        parts.append("")

    if bettafish_ctx.get("platform_profiles"):
        parts.append("## 平台情绪数据（必须生成平台情绪雷达表格）")
        parts.append("| 平台 | 主导情绪 | 代表性评论（引用原文） | 讨论风格 |")
        parts.append("|---|---|---|---|")
        for p in bettafish_ctx["platform_profiles"]:
            quote_sample = ""
            if p["representative_quotes"]:
                quote_sample = p["representative_quotes"][0][:60].replace("|", "｜")
            parts.append(
                f"| {p['platform']} | {p['dominant_emotion'] or '—'} "
                f"| {quote_sample or '—'} | {p['discussion_style'] or '—'} |"
            )
        parts.append("")

    if bettafish_ctx.get("emotion_formula"):
        parts.append("## 情绪传导公式（必须引用到传播路径分析中）")
        parts.append(bettafish_ctx["emotion_formula"])
        parts.append("")

    if bettafish_ctx.get("group_demands"):
        parts.append("## 群体诉求数据（必须生成多元群体诉求清单表格）")
        parts.append("| 群体 | 高频诉求 | 金句（引用原文） |")
        parts.append("|---|---|---|")
        for g in bettafish_ctx["group_demands"]:
            demands = "；".join(g["demands"][:2]) if g["demands"] else "—"
            quote = g["golden_quotes"][0][:60].replace("|", "｜") if g["golden_quotes"] else "—"
            parts.append(f"| {g['group']} | {demands} | {quote} |")
        parts.append("")

    if bettafish_ctx.get("traffic_lights"):
        parts.append("## 风险三色灯数据（必须生成高风险三色灯表格）")
        parts.append("| 等级 | 风险描述 | 爆点预测 | 触发阈值 | 提前干预 |")
        parts.append("|---|---|---|---|---|")
        for t in bettafish_ctx["traffic_lights"]:
            prediction = (t["prediction"] or "待分析")[:60].replace("|", "｜")
            threshold = (t["threshold"] or "待分析")[:40].replace("|", "｜")
            action = (t["action"] or "待补充")[:60].replace("|", "｜")
            parts.append(
                f"| {t['color_label']} | {prediction} | {prediction} | {threshold} | {action} |"
            )
        parts.append("")

    # --- 注入网民金句（所有章节均可嵌入）---
    if bettafish_ctx.get("netizen_quotes"):
        parts.append("## 可用网民金句（必须在正文中直接引用，使用 > '原文' —— 来源 格式）")
        for q in bettafish_ctx["netizen_quotes"][:6]:
            parts.append(f'> "{q}"')
        parts.append("")

    # --- 证据素材 ---
    parts.append("## 证据素材（必须引用，在正文中嵌入原文）")
    for ev in evidence[:10]:
        raw_q = ev.get("raw_quote") or ev.get("snippet") or ""
        if len(raw_q) > 120:
            raw_q = raw_q[:120] + "..."
        sentiment = f"[{ev['sentiment_label']}]" if ev.get("sentiment_label") else ""
        platform = f"@{ev['platform']}" if ev.get("platform") else ""
        author = f" —— {ev['author']}" if ev.get("author") else ""
        parts.append(
            f"- [{ev['evidence_id']}]{sentiment}{platform}: {raw_q}{author}"
        )
    parts.append("")

    # --- 相关断言 ---
    if claims:
        parts.append("## 相关断言（判断依据）")
        for c in claims[:5]:
            parts.append(f"- [{c['claim_id']}] {c['proposition']}")
        parts.append("")

    # --- 写作方法论 ---
    if skill_instructions:
        parts.append("## 写作方法论指导（参考执行）")
        parts.append(skill_instructions[:2000])
        parts.append("")

    # --- 专题背景 ---
    task = payload.meta
    topic_label = getattr(task, "topic_label", "") or getattr(task, "topic_identifier", "")
    time_scope = getattr(task, "time_scope", None)
    if time_scope:
        start = getattr(time_scope, "start", "") or ""
        end = getattr(time_scope, "end", "") or ""
    else:
        start = end = ""
    parts.extend([
        "## 专题背景",
        f"- 专题: {topic_label}",
        f"- 时间范围: {start} 至 {end}",
        "",
        "请输出符合上述格式的JSON章节内容，务必包含表格（若有数据）和原文金句引用。",
    ])

    return system_prompt, "\n".join(parts)


def _parse_llm_response_to_blocks(
    raw_response: str,
    section: CompilerSectionPlanItem,
) -> Tuple[List[Dict[str, Any]], List[str], List[str]]:
    """解析LLM响应为blocks结构"""

    # 尝试提取JSON
    json_match = re.search(r'\{[\s\S]*\}', raw_response)
    if not json_match:
        # 尝试从markdown代码块提取
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', raw_response)
        if json_match:
            json_str = json_match.group(1)
        else:
            # 创建fallback blocks
            logger.warning(f"无法从响应中提取JSON，创建fallback blocks")
            blocks = [
                {"type": "heading", "text": section.title, "anchor": section.section_id},
                {"type": "paragraph", "text": raw_response[:500] if raw_response else "（内容生成失败）"},
            ]
            return blocks, [], []
    else:
        json_str = json_match.group(0)

    # 解析JSON
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        # 尝试修复常见问题
        json_str_fixed = json_str.replace('\n', '\\n').replace('\t', '\\t')
        try:
            data = json.loads(json_str_fixed)
        except:
            logger.warning(f"JSON解析失败，创建fallback blocks")
            blocks = [
                {"type": "heading", "text": section.title, "anchor": section.section_id},
                {"type": "paragraph", "text": raw_response[:500] if raw_response else "（内容解析失败）"},
            ]
            return blocks, [], []

    # 提取blocks
    blocks = data.get("blocks", [])
    if not blocks:
        # 如果没有blocks但有content/text字段，转换为paragraph
        if data.get("content"):
            blocks = [{"type": "paragraph", "text": data["content"]}]
        elif data.get("text"):
            blocks = [{"type": "paragraph", "text": data["text"]}]

    # 确保开头有heading
    if not blocks or blocks[0].get("type") != "heading":
        blocks.insert(0, {"type": "heading", "text": section.title, "anchor": section.section_id})

    evidence_refs = data.get("evidence_refs", [])
    claim_refs = data.get("claim_refs", [])

    return blocks, evidence_refs, claim_refs


def _validate_content_density(
    blocks: List[Dict[str, Any]],
    section_id: str,
    evidence_refs: List[str] = None,
    section_title: str = "",
) -> None:
    """验证内容密度（BettaFish 增强版：含表格密度、引用计数）"""
    body_chars = 0
    narrative_chars = 0
    quote_count = 0
    table_count = 0

    for block in blocks:
        block_type = block.get("type", "")
        text = block.get("text", "")

        if block_type == "paragraph":
            body_chars += len(text)
            narrative_chars += len(text)
            if ">" in text or "——" in text or "\u201c" in text or "\u201d" in text:
                quote_count += 1
        elif block_type == "list":
            for item in (block.get("items") or []):
                if isinstance(item, str):
                    body_chars += len(item)
                    narrative_chars += len(item)
                    if ">" in item or "——" in item:
                        quote_count += 1
        elif block_type == "table":
            table_count += 1
            # 表格 markdown 内容计入 body_chars
            md = block.get("markdown", "")
            body_chars += len(md)
            # table rows 格式
            for row in (block.get("rows") or []):
                for cell in (row.get("cells") or []):
                    if isinstance(cell, dict):
                        body_chars += len(cell.get("text", ""))
                    elif isinstance(cell, str):
                        body_chars += len(cell)
        elif block_type in {"quote", "callout"}:
            quote_count += 1
            body_chars += len(text)

    if evidence_refs:
        quote_count += len(evidence_refs)

    if body_chars < _MIN_SECTION_BODY_CHARACTERS:
        raise SectionContentTooSparseError(section_id, body_chars, narrative_chars, quote_count)
    if quote_count < _MIN_QUOTE_COUNT:
        raise InsufficientQuotesError(section_id, quote_count)

    # BettaFish 关键章节必须含表格（仅重试一次，不硬性阻塞）
    check_key = section_title or section_id
    if check_key in _REQUIRED_TABLE_SECTIONS and table_count == 0:
        logger.warning(
            f"章节 {section_id}（{section_title}）属于必须含表格的章节，"
            f"但当前 table_count=0，建议重试。"
        )
        # 不抛出异常，只警告，由调用方决定是否重试

    logger.info(
        f"章节 {section_id} 内容密度验证通过: 正文{body_chars}字, "
        f"引用{quote_count}条, 表格{table_count}个"
    )


def _blocks_to_draft_units(
    blocks: List[Dict[str, Any]],
    section: CompilerSectionPlanItem,
    evidence_refs: List[str],
    claim_refs: List[str],
    report_ir: ReportIR,
) -> List[DraftUnitV2]:
    """将blocks转换为DraftUnitV2"""
    units = []
    known_ids = _known_trace_ids(report_ir)

    for idx, block in enumerate(blocks):
        block_type = block.get("type", "paragraph")
        text = block.get("text", "")

        if not text.strip() and block_type not in {"hr"}:
            continue

        # 确定unit_type
        unit_type = "finding"
        if block_type == "heading":
            unit_type = "heading"
        elif block_type == "paragraph":
            unit_type = "finding"

        # 构建trace_refs
        trace_refs = []
        for ev_id in evidence_refs:
            if ev_id in known_ids.get("evidence", set()):
                trace_refs.append(TraceRef(
                    trace_id=ev_id,
                    trace_kind="evidence",
                    support_level="direct"
                ))
        for claim_id in claim_refs:
            if claim_id in known_ids.get("claim", set()):
                trace_refs.append(TraceRef(
                    trace_id=claim_id,
                    trace_kind="claim",
                    support_level="direct"
                ))

        # 如果没有trace_refs，添加section_context
        if not trace_refs:
            trace_refs.append(TraceRef(
                trace_id=section.section_id,
                trace_kind="section_context",
                support_level="structural"
            ))

        unit_id = f"unit:{section.section_id}:{idx}"

        units.append(DraftUnitV2(
            unit_id=unit_id,
            section_id=section.section_id,
            unit_type=unit_type,
            text=text,
            trace_refs=trace_refs,
            derived_from=list(claim_refs[:3]),
            support_level="direct" if trace_refs else "structural",
            context_ref=section.section_id,
            render_template_id=f"{section.section_id}:{unit_type}",
            validation_status="pending",
            metadata={
                "block_type": block_type,
                "original_anchor": block.get("anchor", ""),
                "evidence_refs": evidence_refs,
                "claim_refs": claim_refs,
            },
        ))

    return units


def _known_trace_ids(report_ir: ReportIR) -> Dict[str, set[str]]:
    """获取已知trace ID集合"""
    payload = report_ir if isinstance(report_ir, ReportIR) else ReportIR.model_validate(report_ir)
    return {
        "claim": {c.claim_id for c in payload.claim_set.claims},
        "evidence": {e.evidence_id for e in payload.evidence_ledger.entries},
        "risk": {r.risk_id for r in payload.risk_register.risks},
        "timeline": {t.event_id for t in payload.timeline.events},
    }


def generate_section_with_llm(
    section: CompilerSectionPlanItem,
    report_ir: ReportIR,
    scene_profile: CompilerSceneProfile,
    skill_keys: List[str] = None,
    retry_count: int = 0,
    reflection_round: int = 0,
) -> List[DraftUnitV2]:
    """使用LLM生成章节内容（带反思循环）"""

    skill_keys = skill_keys or [
        "report-writing-framework",
        "sentiment-analysis-methodology",
    ]

    skill_instructions = _load_skill_instructions(skill_keys)

    system_prompt, user_prompt = _build_section_writer_prompt(
        section, report_ir, scene_profile, skill_instructions
    )

    llm = _get_llm_client()

    # 调用LLM
    try:
        response = llm.invoke([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ])
        raw_response = response.content if hasattr(response, 'content') else str(response)
    except Exception as e:
        logger.error(f"LLM调用失败: {e}")
        if retry_count < _MAX_RETRY_ATTEMPTS:
            logger.info(f"重试生成章节 {section.section_id}")
            return generate_section_with_llm(
                section, report_ir, scene_profile, skill_keys, retry_count + 1, reflection_round
            )
        raise DeepWriterError(f"章节 {section.section_id} LLM生成失败: {e}")

    # 解析响应
    blocks, evidence_refs, claim_refs = _parse_llm_response_to_blocks(raw_response, section)

    # 验证内容密度（包含引用计数）
    try:
        _validate_content_density(blocks, section.section_id, evidence_refs, section.title)
    except (SectionContentTooSparseError, InsufficientQuotesError) as e:
        # 反思循环：如果内容密度不足且还有反思轮次，尝试补充
        if reflection_round < _MAX_REFLECTION_ROUNDS:
            logger.warning(f"章节 {section.section_id} 内容密度不足（反思轮{reflection_round+1}/{_MAX_REFLECTION_ROUNDS}），尝试补充写作")
            # 构建补充prompt，强调引用和密度
            supplement_prompt = user_prompt + "\n\n**补充要求**（因为上次内容密度不足）:\n- 必须增加更多具体原文引用（至少5条）\n- 正文长度必须≥800字\n- 使用引用格式：> \"原文内容\" —— 发言者（互动数据）"
            try:
                response = llm.invoke([
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": supplement_prompt},
                ])
                raw_response = response.content if hasattr(response, 'content') else str(response)
                blocks, evidence_refs, claim_refs = _parse_llm_response_to_blocks(raw_response, section)
                _validate_content_density(blocks, section.section_id, evidence_refs, section.title)
            except Exception as supp_e:
                logger.warning(f"反思补充失败: {supp_e}")
                if retry_count < _MAX_RETRY_ATTEMPTS:
                    return generate_section_with_llm(
                        section, report_ir, scene_profile, skill_keys, retry_count + 1, reflection_round + 1
                    )
        else:
            logger.warning(f"章节 {section.section_id} 反思循环结束，使用当前版本")

    # 转换为DraftUnitV2
    units = _blocks_to_draft_units(blocks, section, evidence_refs, claim_refs, report_ir)

    return units


def compile_draft_units_with_llm(
    report_ir: ReportIR,
    section_plan: SectionPlan,
    scene_profile: CompilerSceneProfile,
) -> DraftBundleV2:
    """使用LLM深度写作替代确定性拼接"""
    payload = report_ir if isinstance(report_ir, ReportIR) else ReportIR.model_validate(report_ir)
    plan = section_plan if isinstance(section_plan, SectionPlan) else SectionPlan.model_validate(section_plan)

    all_units: List[DraftUnitV2] = []

    for section in plan.sections:
        try:
            logger.info(f"LLM生成章节: {section.section_id} - {section.title}")
            units = generate_section_with_llm(
                section, payload, scene_profile,
                skill_keys=[
                    "report-writing-framework",
                    "sentiment-analysis-methodology",
                    "chart-interpretation-guidelines",
                ]
            )
            all_units.extend(units)
            logger.info(f"章节 {section.section_id} 生成完成，{len(units)}个单元")
        except DeepWriterError as e:
            logger.error(f"章节 {section.section_id} 生成失败: {e}")
            # 创建fallback单元
            fallback_unit = DraftUnitV2(
                unit_id=f"unit:{section.section_id}:fallback",
                section_id=section.section_id,
                unit_type="finding",
                text=f"## {section.title}\n\n（本章节内容生成失败，请检查上游数据）",
                trace_refs=[TraceRef(
                    trace_id=section.section_id,
                    trace_kind="section_context",
                    support_level="structural"
                )],
                derived_from=[],
                support_level="structural",
                context_ref=section.section_id,
                render_template_id=f"{section.section_id}:finding",
                validation_status="failed",
                metadata={"error": str(e)},
            )
            all_units.append(fallback_unit)

    return DraftBundleV2(
        source_artifact_id="draft_bundle.llm.v2",
        policy_version="policy.v2",
        schema_version="draft-bundle.llm.v2",
        units=all_units,
        section_order=[s.section_id for s in plan.sections],
        metadata={
            "generation_mode": "llm_deep_writer",
            "section_count": len(plan.sections),
            "unit_count": len(all_units),
        },
    )