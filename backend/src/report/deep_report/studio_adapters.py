"""LangGraph Studio 适配器：将现有图包装为 Studio 可调试的格式"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

# 添加 backend/src 到 sys.path 以支持绝对导入
backend_src_path = Path(__file__).parent.parent.parent.parent / "src"
if str(backend_src_path) not in sys.path:
    sys.path.insert(0, str(backend_src_path))

from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.sqlite import SqliteSaver

from report.runtime_infra import get_shared_report_checkpointer
from report.deep_report.orchestrator_graph import _OrchestratorState
from report.deep_report.graph_runtime import _GraphState


def build_orchestrator_graph_for_studio():
    """为 LangGraph Studio 构建根编排图

    Studio 要求：
    1. 返回 CompiledGraph 对象
    2. 使用持久化 checkpointer
    3. 状态 schema 必须明确
    """
    checkpointer, _ = get_shared_report_checkpointer(purpose="studio-orchestrator")

    graph = StateGraph(_OrchestratorState)

    # 简化版节点（用于可视化调试）
    def planning_node(state: _OrchestratorState) -> Dict[str, Any]:
        return {"status": "running", "message": "根图已启动"}

    def exploration_node(state: _OrchestratorState) -> Dict[str, Any]:
        # 在 Studio 中，这里可以手动触发子图
        return {
            "exploration_bundle": {},
            "structured_payload": state.get("request", {}),
            "status": "completed",
            "message": "探索完成（Studio 模式）",
        }

    def compile_node(state: _OrchestratorState) -> Dict[str, Any]:
        return {
            "status": "completed",
            "message": "编译完成（Studio 模式）",
            "full_payload": state.get("structured_payload", {}),
        }

    # 添加节点
    graph.add_node("planning", planning_node)
    graph.add_node("exploration", exploration_node)
    graph.add_node("compile", compile_node)

    # 添加边
    graph.add_edge(START, "planning")
    graph.add_edge("planning", "exploration")
    graph.add_edge("exploration", "compile")
    graph.add_edge("compile", END)

    # 编译图
    return graph.compile(checkpointer=checkpointer)


def build_compilation_graph_for_studio():
    """为 LangGraph Studio 构建编译图

    包含完整的修复循环逻辑，可以在 Studio 中可视化：
    - section_realizer 并发执行
    - validator 检查
    - repair 循环
    """
    checkpointer, _ = get_shared_report_checkpointer(purpose="studio-compilation")

    graph = StateGraph(_GraphState)

    # 简化版节点
    def planner_node(state: _GraphState) -> Dict[str, Any]:
        """规划节点：生成 section 计划"""
        payload = state.get("payload", {})
        report_ir = payload.get("report_ir", {})
        placement = report_ir.get("placement_plan", {})
        entries = placement.get("entries", [])

        # 生成 planner_slots
        slots = [
            {"section_id": entry.get("section_id"), "section_role": entry.get("section_role")}
            for entry in entries[:3]  # Studio 模式限制数量
        ]

        return {
            "planner_slots": slots,
            "section_batches": [],  # 重置累加器
            "repair_batches": [],
        }

    def section_worker_node(state: _GraphState) -> Dict[str, Any]:
        """Section worker：处理单个 section"""
        slot = state.get("planner_slot", {})
        section_id = slot.get("section_id", "unknown")

        # 模拟生成 draft
        return {
            "section_batches": [{
                "section_id": section_id,
                "units": [
                    {
                        "unit_id": f"unit:{section_id}:1",
                        "text": f"这是 {section_id} 的内容",
                    }
                ]
            }]
        }

    def section_finalize_node(state: _GraphState) -> Dict[str, Any]:
        """合并所有 section 结果"""
        batches = state.get("section_batches", [])
        all_units = []
        for batch in batches:
            all_units.extend(batch.get("units", []))

        return {
            "draft_bundle_v2": {
                "units": all_units,
                "section_order": [b.get("section_id") for b in batches],
            }
        }

    def validator_node(state: _GraphState) -> Dict[str, Any]:
        """验证节点：检查 draft 质量"""
        draft = state.get("draft_bundle_v2", {})
        units = draft.get("units", [])

        # 模拟验证失败（用于测试修复循环）
        repair_count = state.get("repair_count", 0)
        if repair_count < 1 and len(units) > 0:
            return {
                "validation_result_v2": {
                    "passed": False,
                    "failures": [
                        {
                            "failure_id": "test-failure-1",
                            "target_unit_id": units[0].get("unit_id"),
                            "failure_type": "missing_evidence",
                            "message": "缺少证据支持",
                            "patchable": True,
                        }
                    ],
                    "gate": "repair",
                    "next_node": "repair_patch_planner",
                }
            }

        return {
            "validation_result_v2": {
                "passed": True,
                "failures": [],
                "gate": "pass",
                "next_node": "markdown_compiler",
            }
        }

    def repair_planner_node(state: _GraphState) -> Dict[str, Any]:
        """修复规划节点"""
        validation = state.get("validation_result_v2", {})
        failures = validation.get("failures", [])

        return {
            "repair_plan_v2": {
                "patches": [
                    {"patch_id": f.get("failure_id"), "target_unit_id": f.get("target_unit_id")}
                    for f in failures[:2]  # 限制数量
                ]
            },
            "repair_batches": [],  # 重置累加器
        }

    def repair_worker_node(state: _GraphState) -> Dict[str, Any]:
        """修复 worker：处理单个 patch"""
        patch = state.get("repair_patch", {})
        return {
            "repair_batches": [{
                "patch_id": patch.get("patch_id"),
                "status": "fixed",
            }]
        }

    def repair_finalize_node(state: _GraphState) -> Dict[str, Any]:
        """应用所有修复"""
        return {
            "repair_count": state.get("repair_count", 0) + 1,
            "draft_bundle_v2": state.get("draft_bundle_v2", {}),  # 模拟修复后的 draft
        }

    def markdown_compiler_node(state: _GraphState) -> Dict[str, Any]:
        """最终编译为 Markdown"""
        draft = state.get("draft_bundle_v2", {})
        units = draft.get("units", [])
        markdown = "\n\n".join(u.get("text", "") for u in units)

        return {
            "markdown": markdown,
            "final_output": {"status": "completed", "markdown": markdown},
        }

    # 添加节点
    graph.add_node("planner", planner_node)
    graph.add_node("section_worker", section_worker_node)
    graph.add_node("section_finalize", section_finalize_node)
    graph.add_node("validator", validator_node)
    graph.add_node("repair_planner", repair_planner_node)
    graph.add_node("repair_worker", repair_worker_node)
    graph.add_node("repair_finalize", repair_finalize_node)
    graph.add_node("markdown_compiler", markdown_compiler_node)

    # 添加边
    graph.add_edge(START, "planner")

    # Section 并发处理（简化版，Studio 中手动触发）
    graph.add_edge("planner", "section_worker")
    graph.add_edge("section_worker", "section_finalize")
    graph.add_edge("section_finalize", "validator")

    # 条件边：验证通过 → 编译，失败 → 修复
    def should_repair(state: _GraphState) -> str:
        validation = state.get("validation_result_v2", {})
        if validation.get("passed"):
            return "markdown_compiler"
        return "repair_planner"

    graph.add_conditional_edges("validator", should_repair)

    # 修复循环
    graph.add_edge("repair_planner", "repair_worker")
    graph.add_edge("repair_worker", "repair_finalize")

    # 条件边：检查是否超过最大修复次数
    def should_continue_repair(state: _GraphState) -> str:
        repair_count = state.get("repair_count", 0)
        if repair_count >= 2:  # Studio 模式限制
            return "markdown_compiler"
        return "validator"

    graph.add_conditional_edges("repair_finalize", should_continue_repair)

    graph.add_edge("markdown_compiler", END)

    # 编译图
    return graph.compile(checkpointer=checkpointer)
