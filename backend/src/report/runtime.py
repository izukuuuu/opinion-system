"""Shared report pipeline helpers for sync routes and background workers."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from server_support.archive_locator import ArchiveLocator, compose_folder_name
from server_support.topic_context import TopicContext
from src.analyze import run_Analyze
from src.utils.ai import call_langchain_chat
from src.utils.setting.paths import bucket

LOGGER = logging.getLogger(__name__)

ANALYZE_FILE_MAP: Dict[str, str] = {
    "volume": "volume.json",
    "attitude": "attitude.json",
    "trends": "trends.json",
    "geography": "geography.json",
    "publishers": "publishers.json",
    "keywords": "keywords.json",
    "classification": "classification.json",
}
ANALYZE_FUNCTION_LABELS: Dict[str, str] = {
    "volume": "声量概览",
    "attitude": "情感分析",
    "trends": "趋势洞察",
    "geography": "地域分析",
    "publishers": "发布者分析",
    "keywords": "关键词分析",
    "classification": "话题分类",
}
EXPLAIN_SECTION_FILENAME_SUFFIX = "_rag_enhanced.json"
AI_SUMMARY_FILENAME = "ai_summary.json"


def safe_async_call(coro: Any) -> Any:
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


def resolve_explain_root(ctx: TopicContext, start: str, end: Optional[str]) -> Path:
    folder = compose_folder_name(start, end)
    candidates: List[str] = []
    for value in [ctx.identifier, ctx.display_name, *(ctx.aliases or [])]:
        token = str(value or "").strip()
        if token and token not in candidates:
            candidates.append(token)
    for candidate in candidates:
        root = bucket("explain", candidate, folder)
        if root.exists():
            return root
    return bucket("explain", ctx.identifier, folder)


def collect_explain_outputs(ctx: TopicContext, start: str, end: Optional[str]) -> Dict[str, Any]:
    explain_root = resolve_explain_root(ctx, start, end)
    available_functions: List[str] = []
    sources: Dict[str, str] = {}
    for func_name in ANALYZE_FILE_MAP.keys():
        explain_file = explain_root / func_name / "总体" / f"{func_name}{EXPLAIN_SECTION_FILENAME_SUFFIX}"
        if not explain_file.exists():
            continue
        available_functions.append(func_name)
        try:
            payload = _load_json(explain_file)
            sources[func_name] = str(payload.get("source") or "legacy_rag").strip() or "legacy_rag"
        except Exception:
            sources[func_name] = "legacy_rag"
    return {
        "root": str(explain_root),
        "available_functions": available_functions,
        "available_count": len(available_functions),
        "expected_count": len(ANALYZE_FILE_MAP),
        "ready": len(available_functions) >= len(ANALYZE_FILE_MAP),
        "sources": sources,
    }


def ensure_analyze_results(
    topic_identifier: str,
    *,
    start: str,
    end: Optional[str],
    ctx: TopicContext,
) -> Dict[str, Any]:
    locator = ArchiveLocator(ctx)
    existing_root = locator.resolve_result_dir("analyze", start, end)
    if existing_root:
        return {
            "prepared": False,
            "analyze_root": str(existing_root),
            "message": "",
        }

    ok = run_Analyze(topic_identifier, start, end_date=end)
    if not ok:
        LOGGER.warning(
            "report runtime | analyze bootstrap failed | topic=%s start=%s end=%s",
            topic_identifier,
            start,
            end,
        )
        raise ValueError("当前专题缺少基础分析结果，且自动补跑 analyze 失败")

    analyze_root = locator.resolve_result_dir("analyze", start, end)
    if not analyze_root:
        raise ValueError("analyze 已执行，但未生成可供报告读取的分析目录")

    return {
        "prepared": True,
        "analyze_root": str(analyze_root),
        "message": "已自动补跑 analyze 并生成报告输入数据。",
    }


def ensure_explain_results(
    topic_identifier: str,
    *,
    start: str,
    end: Optional[str],
    ctx: TopicContext,
) -> Dict[str, Any]:
    explain_state = collect_explain_outputs(ctx, start, end)
    if explain_state["ready"]:
        return {
            "prepared": False,
            "ready": True,
            "source": _resolve_explain_source(explain_state),
            "message": "",
            "smart_fill": {"generated_count": 0, "generated_functions": []},
            **explain_state,
        }

    try:
        from src.explain import run_Explain  # type: ignore

        runner_ok = bool(
            safe_async_call(
                run_Explain(
                    topic_identifier,
                    start,
                    end_date=end,
                    only_overall=True,
                )
            )
        )
    except Exception:
        LOGGER.warning(
            "report runtime | legacy explain bootstrap raised | topic=%s start=%s end=%s",
            topic_identifier,
            start,
            end,
            exc_info=True,
        )
        runner_ok = False

    refreshed = collect_explain_outputs(ctx, start, end)
    smart_fill = {"generated_count": 0, "generated_functions": []}
    if not refreshed["ready"]:
        LOGGER.warning(
            "report runtime | explain incomplete after legacy bootstrap, start smart fill | topic=%s start=%s end=%s missing=%s",
            topic_identifier,
            start,
            end,
            [
                func_name
                for func_name in ANALYZE_FILE_MAP.keys()
                if func_name not in set(refreshed.get("available_functions") or [])
            ],
        )
        smart_fill = synthesize_missing_explain_outputs(
            topic_identifier,
            start=start,
            end=end,
            ctx=ctx,
        )
        refreshed = collect_explain_outputs(ctx, start, end)

    ready = bool(refreshed["ready"])
    source = _resolve_explain_source(refreshed)
    if ready and smart_fill["generated_count"] > 0:
        message = "已智能补齐缺失的总体文字解读，并存储到 explain 产物。"
    elif runner_ok and ready:
        message = "已自动补齐总体文字解读。"
    elif runner_ok and refreshed["available_count"] > 0:
        message = "总体文字解读已部分生成，系统将继续智能补齐缺失模块。"
    elif smart_fill["generated_count"] > 0:
        message = "传统 explain 未完成，系统已根据 AI 摘要和统计结果智能补齐总体解读。"
    else:
        message = "总体文字解读仍未补齐，当前会先用结构化报告兜底。"
        LOGGER.warning(
            "report runtime | explain still incomplete after smart fill | topic=%s start=%s end=%s available=%s/%s",
            topic_identifier,
            start,
            end,
            refreshed.get("available_count"),
            refreshed.get("expected_count"),
        )

    if smart_fill["generated_count"] > 0:
        LOGGER.warning(
            "report runtime | smart fill completed | topic=%s start=%s end=%s generated=%s",
            topic_identifier,
            start,
            end,
            smart_fill["generated_functions"],
        )

    return {
        "prepared": True,
        "ready": ready,
        "source": source,
        "message": message,
        "runner_ok": runner_ok,
        "smart_fill": smart_fill,
        **refreshed,
    }


def synthesize_missing_explain_outputs(
    topic_identifier: str,
    *,
    start: str,
    end: Optional[str],
    ctx: TopicContext,
) -> Dict[str, Any]:
    explain_state = collect_explain_outputs(ctx, start, end)
    missing_functions = [
        func_name
        for func_name in ANALYZE_FILE_MAP.keys()
        if func_name not in set(explain_state.get("available_functions") or [])
    ]
    if not missing_functions:
        return {"generated_count": 0, "generated_functions": []}

    analyze_root = ArchiveLocator(ctx).resolve_result_dir("analyze", start, end)
    if not analyze_root:
        LOGGER.warning(
            "report runtime | cannot smart fill explain because analyze root missing | topic=%s start=%s end=%s",
            topic_identifier,
            start,
            end,
        )
        return {"generated_count": 0, "generated_functions": []}

    ai_summary_map, main_finding = _load_ai_summary_context(analyze_root)
    explain_root = resolve_explain_root(ctx, start, end)
    generated_functions: List[str] = []
    for func_name in missing_functions:
        rows = _load_analyze_rows(analyze_root, func_name)
        facts = _build_function_facts(
            topic_label=ctx.display_name or ctx.identifier,
            function_name=func_name,
            function_label=ANALYZE_FUNCTION_LABELS.get(func_name, func_name),
            start=start,
            end=end or start,
            rows=rows,
            ai_summary=ai_summary_map.get(func_name, ""),
            main_finding=main_finding,
        )
        explain_text = _generate_explain_text(facts)
        if not explain_text:
            LOGGER.warning(
                "report runtime | smart fill explain skipped due empty text | topic=%s function=%s start=%s end=%s",
                topic_identifier,
                func_name,
                start,
                end,
            )
            continue
        _write_explain_output(
            explain_root=explain_root,
            function_name=func_name,
            function_label=ANALYZE_FUNCTION_LABELS.get(func_name, func_name),
            explain_text=explain_text,
            facts=facts,
        )
        generated_functions.append(func_name)
        LOGGER.warning(
            "report runtime | wrote synthetic explain artifact | topic=%s function=%s path=%s",
            topic_identifier,
            func_name,
            explain_root / func_name / "总体" / f"{func_name}{EXPLAIN_SECTION_FILENAME_SUFFIX}",
        )
    return {"generated_count": len(generated_functions), "generated_functions": generated_functions}


def _resolve_explain_source(explain_state: Dict[str, Any]) -> str:
    sources = explain_state.get("sources") if isinstance(explain_state.get("sources"), dict) else {}
    if any(str(value or "").strip() == "smart_fill" for value in sources.values()):
        return "smart_fill"
    return "legacy_rag" if explain_state.get("ready") else "fallback"


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _extract_rows(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _load_analyze_rows(analyze_root: Path, func_name: str) -> List[Dict[str, Any]]:
    path = analyze_root / func_name / "总体" / ANALYZE_FILE_MAP.get(func_name, "result.json")
    if not path.exists():
        return []
    try:
        return _extract_rows(_load_json(path))
    except Exception:
        return []


def _load_ai_summary_context(analyze_root: Path) -> tuple[Dict[str, str], str]:
    ai_summary_map: Dict[str, str] = {}
    main_finding = ""
    path = analyze_root / AI_SUMMARY_FILENAME
    if not path.exists():
        return ai_summary_map, main_finding
    try:
        payload = _load_json(path)
    except Exception:
        return ai_summary_map, main_finding
    summaries = payload.get("summaries") if isinstance(payload, dict) else None
    if isinstance(summaries, list):
        for item in summaries:
            if not isinstance(item, dict):
                continue
            func_name = str(item.get("function") or "").strip()
            summary_text = str(item.get("ai_summary") or "").strip()
            if func_name and summary_text:
                ai_summary_map[func_name] = summary_text
    if isinstance(payload, dict) and isinstance(payload.get("main_finding"), dict):
        main_finding = str(payload.get("main_finding", {}).get("summary") or "").strip()
    return ai_summary_map, main_finding


def _build_function_facts(
    *,
    topic_label: str,
    function_name: str,
    function_label: str,
    start: str,
    end: str,
    rows: List[Dict[str, Any]],
    ai_summary: str,
    main_finding: str,
) -> Dict[str, Any]:
    top_rows = rows[:8]
    numeric_rows = [
        {
            "name": str(item.get("name") or "").strip(),
            "value": _safe_int(item.get("value")),
        }
        for item in rows
        if str(item.get("name") or "").strip()
    ]
    numeric_rows = [item for item in numeric_rows if item["name"]]
    numeric_rows.sort(key=lambda item: item["value"], reverse=True)
    top_numeric_rows = numeric_rows[:6]
    peak_row = top_numeric_rows[0] if top_numeric_rows else {"name": "", "value": 0}
    total_value = sum(item["value"] for item in numeric_rows)
    return {
        "topic": topic_label,
        "function_name": function_name,
        "function_label": function_label,
        "time_range": {"start": start, "end": end},
        "row_count": len(rows),
        "total_value": total_value,
        "peak_name": str(peak_row.get("name") or "").strip(),
        "peak_value": int(peak_row.get("value") or 0),
        "top_rows": top_numeric_rows,
        "snapshot_rows": top_rows,
        "ai_summary": ai_summary,
        "main_finding": main_finding,
    }


def _generate_explain_text(facts: Dict[str, Any]) -> str:
    llm_text = _generate_explain_with_llm(facts)
    if llm_text:
        return llm_text
    return _build_explain_fallback_text(facts)


def _generate_explain_with_llm(facts: Dict[str, Any]) -> str:
    prompt = (
        "你是一名舆情分析师，需要为缺失的“总体解读”产物补写一段可直接存储的 explain 文本。\n"
        "要求：\n"
        "1) 仅基于输入事实，不得编造数字或事件；\n"
        "2) 输出 120-220 字中文自然段；\n"
        "3) 先给出总体判断，再解释最重要的统计特征或异常点；\n"
        "4) 如果该模块本身暴露数据缺口，也要明确指出；\n"
        "5) 不要输出标题、Markdown、编号或 JSON。\n\n"
        f"【事实】\n{json.dumps(facts, ensure_ascii=False, indent=2)}"
    )
    raw = safe_async_call(
        call_langchain_chat(
            [
                {
                    "role": "system",
                    "content": "你是一名严谨的中文舆情分析师，只能基于输入事实撰写简洁解释。",
                },
                {"role": "user", "content": prompt},
            ],
            task="report",
            model_role="report",
            temperature=0.2,
            max_tokens=500,
        )
    )
    text = str(raw or "").strip()
    if not text:
        LOGGER.warning(
            "report runtime | llm did not return explain text, fallback to rule-based summary | function=%s",
            str(facts.get("function_name") or "").strip(),
        )
        return ""
    return _clean_explain_text(text)


def _build_explain_fallback_text(facts: Dict[str, Any]) -> str:
    function_label = str(facts.get("function_label") or "").strip()
    ai_summary = str(facts.get("ai_summary") or "").strip()
    main_finding = str(facts.get("main_finding") or "").strip()
    top_rows = facts.get("top_rows") if isinstance(facts.get("top_rows"), list) else []
    segments: List[str] = []
    if ai_summary:
        segments.append(ai_summary)
    elif function_label == "趋势洞察":
        peak_name = str(facts.get("peak_name") or "").strip()
        peak_value = int(facts.get("peak_value") or 0)
        if peak_name:
            segments.append(f"从时间趋势看，讨论热度并非均匀分布，而是呈现明显峰值驱动特征，其中 {peak_name} 以 {peak_value} 的量级成为主要高点。")
    elif top_rows:
        top_text = "、".join(
            f"{str(item.get('name') or '').strip()}（{int(item.get('value') or 0)}）"
            for item in top_rows[:3]
            if str(item.get("name") or "").strip()
        )
        if top_text:
            segments.append(f"{function_label}的头部特征较为清晰，当前最主要的项包括 {top_text}。")
    if top_rows:
        tail_text = "、".join(
            f"{str(item.get('name') or '').strip()}（{int(item.get('value') or 0)}）"
            for item in top_rows[:5]
            if str(item.get("name") or "").strip()
        )
        if tail_text and tail_text not in " ".join(segments):
            segments.append(f"从原始统计看，头部结构主要由 {tail_text} 组成，说明该模块的关注重心已经比较集中。")
    if main_finding and main_finding not in " ".join(segments):
        segments.append(f"这一点与整体主线相呼应：{main_finding}")
    if not segments:
        segments.append(f"{function_label}模块当前已具备基础统计结果，但尚缺原始 explain 文本，系统已根据现有统计快照补齐总体解读。")
    return _clean_explain_text(" ".join(segments))


def _clean_explain_text(text: str) -> str:
    cleaned = str(text or "").replace("```", " ").replace("\r", " ").replace("\n", " ").strip()
    cleaned = " ".join(cleaned.split())
    return cleaned[:360]


def _write_explain_output(
    *,
    explain_root: Path,
    function_name: str,
    function_label: str,
    explain_text: str,
    facts: Dict[str, Any],
) -> None:
    target_dir = explain_root / function_name / "总体"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{function_name}{EXPLAIN_SECTION_FILENAME_SUFFIX}"
    payload = {
        "function": function_name,
        "function_label": function_label,
        "target": "总体",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "smart_fill",
        "explain": explain_text,
        "facts": {
            "row_count": int(facts.get("row_count") or 0),
            "peak_name": str(facts.get("peak_name") or "").strip(),
            "peak_value": int(facts.get("peak_value") or 0),
            "top_rows": facts.get("top_rows") or [],
        },
    }
    with target_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)


def _safe_int(value: Any) -> int:
    try:
        return int(float(value))
    except Exception:
        return 0


__all__ = [
    "AI_SUMMARY_FILENAME",
    "ANALYZE_FILE_MAP",
    "ANALYZE_FUNCTION_LABELS",
    "EXPLAIN_SECTION_FILENAME_SUFFIX",
    "collect_explain_outputs",
    "ensure_analyze_results",
    "ensure_explain_results",
    "resolve_explain_root",
    "safe_async_call",
    "synthesize_missing_explain_outputs",
]
