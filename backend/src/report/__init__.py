"""
报告生成功能对外接口
"""
from .data_report import run_report
from .structured_service import generate_report_payload

__all__ = ["run_report", "generate_report_payload"]

