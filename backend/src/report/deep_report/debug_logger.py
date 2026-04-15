"""调试日志工具：本地开发时记录图执行轨迹，生产环境禁用"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


class GraphDebugLogger:
    """图执行调试日志记录器

    环境变量控制：
    - DEEP_REPORT_DEBUG=1: 启用调试日志
    - DEEP_REPORT_DEBUG_DIR: 日志目录（默认 backend/data/_debug）
    """

    def __init__(self, session_id: str, graph_name: str):
        self.enabled = os.getenv("DEEP_REPORT_DEBUG") == "1"
        if not self.enabled:
            return

        debug_dir = Path(os.getenv("DEEP_REPORT_DEBUG_DIR", "backend/data/_debug"))
        debug_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = debug_dir / f"{graph_name}_{session_id}_{timestamp}.jsonl"
        self.session_id = session_id
        self.graph_name = graph_name

    def log_event(self, event_type: str, data: Dict[str, Any], **extra):
        """记录图事件"""
        if not self.enabled:
            return

        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "session_id": self.session_id,
            "graph": self.graph_name,
            "event_type": event_type,
            "data": data,
            **extra
        }

        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def log_node_start(self, node_name: str, state_snapshot: Optional[Dict] = None):
        """记录节点开始"""
        self.log_event("node_start", {"node": node_name, "state": state_snapshot})

    def log_node_end(self, node_name: str, updates: Optional[Dict] = None):
        """记录节点结束"""
        self.log_event("node_end", {"node": node_name, "updates": updates})

    def log_node_error(self, node_name: str, error: Exception):
        """记录节点错误"""
        self.log_event("node_error", {
            "node": node_name,
            "error_type": type(error).__name__,
            "error_message": str(error)
        })

    def log_interrupt(self, node_name: str, interrupt_value: Any):
        """记录中断"""
        self.log_event("interrupt", {
            "node": node_name,
            "interrupt_value": interrupt_value
        })

    def log_state_transition(self, from_node: str, to_node: str, state_diff: Optional[Dict] = None):
        """记录状态转换"""
        self.log_event("state_transition", {
            "from": from_node,
            "to": to_node,
            "diff": state_diff
        })

    def log_llm_call(self, node_name: str, model: str, prompt_tokens: int, completion_tokens: int):
        """记录 LLM 调用（用于成本分析）"""
        self.log_event("llm_call", {
            "node": node_name,
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens
        })


def create_debug_logger(session_id: str, graph_name: str) -> GraphDebugLogger:
    """工厂函数"""
    return GraphDebugLogger(session_id, graph_name)
