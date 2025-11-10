"""
生成专题时间范围的解读报告（DOCX）
"""
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import json

from ..utils.setting.paths import bucket, ensure_bucket
from ..utils.logging.logging import (
    setup_logger,
    log_module_start,
    log_success,
    log_error,
    log_save_success,
)


def _get_date_folder(start_date: str, end_date: Optional[str]) -> str:
    """
    获取日期文件夹名，兼容单日与范围
    
    Args:
        start_date (str): 开始日期
        end_date (Optional[str]): 结束日期
    
    Returns:
        str: 形如 YYYY-MM-DD 或 YYYY-MM-DD_YYYY-MM-DD
    """
    return f"{start_date}_{end_date}" if end_date else start_date


def _ordered_functions() -> List[Tuple[str, str]]:
    """
    返回功能的读取顺序及中文名称
    
    Returns:
        List[Tuple[str, str]]: [(功能文件夹英文, 中文显示名)]
    """
    return [
        ("volume", "声量"),
        ("trends", "发布趋势"),
        ("classification", "分类"),
        ("attitude", "态度"),
        ("publishers", "发布者"),
        ("geography", "地域"),
        ("keywords", "关键词"),
        ("contentanalyze", "内容分析"),
    ]


def _ordered_channels() -> List[str]:
    """
    返回渠道读取顺序
    
    Returns:
        List[str]: 渠道列表
    """
    return ["总体", "微信", "新闻", "微博", "自媒体号", "论坛", "视频"]


def _read_explain_text(explain_file: Path) -> Optional[str]:
    """
    读取解读JSON中的文字部分
    
    Args:
        explain_file (Path): 解读文件路径
    
    Returns:
        Optional[str]: 文本，读取失败或字段缺失返回None
    """
    try:
        if not explain_file.exists():
            return None
        with open(explain_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        text = data.get("explain")
        if isinstance(text, str) and text.strip():
            return text.strip()
        return None
    except Exception:
        return None


def _build_doc(topic: str, date_folder: str, sections: List[Tuple[str, str, str]], output_path: Path, logger) -> bool:
    """
    构建并保存DOCX文档
    
    Args:
        topic (str): 专题
        date_folder (str): 日期文件夹名
        sections (List[Tuple[str, str, str]]): (功能中文, 渠道中文, 正文) 列表
        output_path (Path): 输出文件路径
        logger: 日志器
    
    Returns:
        bool: 保存是否成功
    """
    try:
        # 延迟导入以避免无依赖时报错影响模块加载
        from docx import Document
        from docx.shared import Pt
        from docx.oxml.ns import qn

        doc = Document()

        # 全局正文字体：宋体 5号（约10.5pt）
        normal_style = doc.styles["Normal"].font
        normal_style.name = "宋体"
        normal_style.size = Pt(10.5)
        try:
            normal_style.element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
        except Exception:
            pass

        # 大标题：宋体 4号（约14pt） 加粗
        title_para = doc.add_paragraph()
        run = title_para.add_run(f"{topic}/{date_folder}分析")
        run.bold = True
        run.font.name = "宋体"
        run.font.size = Pt(14)
        try:
            run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
        except Exception:
            pass

        # 空行
        doc.add_paragraph("")

        # 各章节
        for func_cn, channel_cn, body in sections:
            # 子标题：宋体 4号 加粗
            h_para = doc.add_paragraph()
            h_run = h_para.add_run(f"{func_cn} - {channel_cn}")
            h_run.bold = True
            h_run.font.name = "宋体"
            h_run.font.size = Pt(14)
            try:
                h_run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
            except Exception:
                pass

            # 正文：宋体 5号
            p = doc.add_paragraph(body)
            for r in p.runs:
                r.font.name = "宋体"
                r.font.size = Pt(10.5)
                try:
                    r._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
                except Exception:
                    pass

            # 段落后空行
            doc.add_paragraph("")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(output_path))
        return True
    except ImportError as e:
        log_error(logger, f"缺少依赖 python-docx，请先安装: {e}", "Report")
        return False
    except Exception as e:
        log_error(logger, f"生成DOCX失败: {e}", "Report")
        return False


def run_report(topic: str, start_date: str, end_date: Optional[str] = None) -> bool:
    """
    生成专题报告（DOCX）
    
    Args:
        topic (str): 专题名称
        start_date (str): 开始日期 (YYYY-MM-DD)
        end_date (Optional[str]): 结束日期 (YYYY-MM-DD)
    
    Returns:
        bool: 是否成功
    """
    date_folder = _get_date_folder(start_date, end_date)
    logger = setup_logger(f"Report_{topic}", date_folder)

    try:
        log_module_start(logger, "Report")

        explain_root = bucket("explain", topic, date_folder)
        if not explain_root.exists():
            log_error(logger, f"未找到解读目录: {explain_root}", "Report")
            return False

        sections: List[Tuple[str, str, str]] = []
        for func_en, func_cn in _ordered_functions():
            func_dir = explain_root / func_en
            if not func_dir.exists():
                continue

            for channel in _ordered_channels():
                # 路径规则：总体放在/总体/func.json，其它渠道放在/渠道名/func.json
                if channel == "总体":
                    explain_file = func_dir / "总体" / f"{func_en}.json"
                else:
                    explain_file = func_dir / channel / f"{func_en}.json"

                text = _read_explain_text(explain_file)
                if text:
                    sections.append((func_cn, channel, text))

        if not sections:
            log_error(logger, "未找到任何可用的解读结果，报告未生成", "Report")
            return False

        output_dir = ensure_bucket("reports", topic, date_folder)
        output_path = output_dir / f"{topic}_{date_folder}_报告.docx"

        ok = _build_doc(topic, date_folder, sections, output_path, logger)
        if ok:
            log_success(logger, f"报告生成完成，共 {len(sections)} 节", "Report")
        return ok

    except Exception as e:
        log_error(logger, f"报告生成失败: {e}", "Report")
        return False


