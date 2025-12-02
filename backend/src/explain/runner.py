"""
解读运行器模块
"""
import asyncio
import json
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional
from ..utils.setting.paths import bucket, get_project_root
from ..utils.logging.logging import setup_logger, log_module_start, log_success, log_error
from .functions.volume import explain_volume_overall, explain_volume_by_channel
from .functions.attitude import explain_attitude_overall, explain_attitude_by_channel
from .functions.trends import explain_trends_overall, explain_trends_by_channel
from .functions.geography import explain_geography_overall, explain_geography_by_channel
from .functions.publishers import explain_publishers_overall, explain_publishers_by_channel
from .functions.keywords import explain_keywords_overall, explain_keywords_by_channel
from .functions.classification import explain_classification_overall, explain_classification_by_channel
from .functions.contentanalyze import explain_contentanalyze_by_channel
from .functions.bertopic import explain_bertopic_overall
from .functions.base import ExplainBase


async def run_Explain(topic: str, date: str, logger=None, only_function: str = None, end_date: str = None, only_overall: bool = False) -> bool:
    """
    运行解读任务
    
    Args:
        topic (str): 专题名称
        date (str): 日期字符串
        logger: 日志记录器
        only_function (str, optional): 仅运行指定解读函数
        end_date (str, optional): 结束日期
        only_overall (bool, optional): 仅运行总体类型的解读任务（不包括渠道）
    
    Returns:
        bool: 是否成功
    """
    if logger is None:
        logger = setup_logger(topic, date)
    
    log_module_start(logger, "Explain")
        
    # 获取解读函数配置
    project_root = get_project_root()
    explain_config_file = project_root / "configs" / "explain.yaml"
    
    if not explain_config_file.exists():
        log_error(logger, f"未找到解读配置文件: {explain_config_file}", "Explain")
        return False
        
    with open(explain_config_file, 'r', encoding='utf-8') as f:
        explain_config = yaml.safe_load(f)
    
    functions = explain_config.get('functions', [])
    
    if not functions:
        log_error(logger, "未配置解读函数", "Explain")
        return False
        
    # 若仅运行单功能，先做一次过滤（支持别名与大小写不敏感）
    if only_function:
        alias = only_function.strip()
        alias_norm = alias.lower()
        before = len(functions)
        functions = [f for f in functions if (f.get('name','').strip().lower() == alias_norm)]
        if not functions:
            log_error(logger, f"--func 未匹配到任何解读项：{only_function}", "Explain")
            return False
    
    # 若仅运行总体类型，过滤掉渠道类型的任务（但保留contentanalyze）
    if only_overall:
        before_count = len(functions)
        functions = [f for f in functions if f.get('target') == '总体' or f.get('name') == 'contentanalyze']
        if not functions:
            log_error(logger, f"未找到任何总体类型的解读任务", "Explain")
            return False
        log_success(logger, f"仅运行总体类型解读 | 过滤前: {before_count} 个任务，过滤后: {len(functions)} 个任务（包含contentanalyze）", "Explain")

    # 创建输出目录
    if end_date:
        folder_name = f"{date}_{end_date}"
    else:
        folder_name = date
    explain_root = bucket("explain", topic, folder_name)
    explain_root.mkdir(parents=True, exist_ok=True)
    
    success_count = 0
    config_tasks = len(functions)  # 配置中的任务数
    completed_tasks = 0
        
    # 显示任务列表
    task_list = []
    for i, func_config in enumerate(functions, 1):
        func_name = func_config.get('name')
        target = func_config.get('target')
        task_list.append(f"{i}. {func_name} ({target})")
        
    # 第一阶段：准备所有任务的提示词
    prepared_tasks = []
    
    for func_config in functions:
        func_name = func_config.get('name')
        target = func_config.get('target')
        
        log_success(logger, f"识别任务: {func_name} | {target}", "Explain")
        
        try:
            if target == '总体':
                if func_name == 'bertopic':
                    # 主题分析特殊处理 - 数据来源是topic目录
                    topic_dir = bucket("topic", topic, folder_name)
                    recluster_file = topic_dir / "4大模型再聚类结果.json"
                    keywords_file = topic_dir / "5大模型主题关键词.json"
                    
                    if not recluster_file.exists() or not keywords_file.exists():
                        log_error(logger, f"主题分析文件不存在: {recluster_file} 或 {keywords_file}", "Explain")
                        continue
                    
                    # 检查文件内容是否有效
                    try:
                        with open(recluster_file, 'r', encoding='utf-8') as f:
                            recluster_data = json.load(f)
                        with open(keywords_file, 'r', encoding='utf-8') as f:
                            keywords_data = json.load(f)
                        if not recluster_data or not keywords_data:
                            log_error(logger, f"主题分析数据为空", "Explain")
                            continue
                    except Exception as e:
                        log_error(logger, f"主题分析文件读取失败: {e}", "Explain")
                        continue
                    
                    # 准备总体解读任务
                    prepared_tasks.append({
                        'type': 'overall',
                        'func_name': func_name,
                        'data': {
                            "再聚类结果": recluster_data,
                            "主题关键词": keywords_data
                        },
                        'target': target
                    })
                else:
                    # 其他功能的总体处理
                    # 检查总体分析结果是否存在
                    analyze_dir = bucket("analyze", topic, folder_name)
                    overall_file = analyze_dir / func_name / "总体" / f"{func_name}.json"
                    
                    if not overall_file.exists():
                        log_error(logger, f"总体分析结果文件不存在: {overall_file}", "Explain")
                        continue
                    
                    # 检查文件内容是否有效
                    try:
                        with open(overall_file, 'r', encoding='utf-8') as f:
                            overall_data = json.load(f)
                            if not overall_data or not overall_data.get('data'):
                                log_error(logger, f"总体分析数据为空: {func_name}", "Explain")
                                continue
                    except Exception as e:
                        log_error(logger, f"总体分析文件读取失败: {func_name} | {e}", "Explain")
                        continue
                    
                    # 准备总体解读任务
                    prepared_tasks.append({
                        'type': 'overall',
                        'func_name': func_name,
                        'data': overall_data,
                        'target': target
                    })
                
            elif target == '渠道':
                if func_name == 'contentanalyze':
                    # 内容分析特殊处理
                    contentanalyze_file = project_root / "data" / "contentanalyze" / topic / folder_name / "contentanalysis.json"
                    
                    if not contentanalyze_file.exists():
                        log_error(logger, f"内容分析文件不存在: {contentanalyze_file}", "Explain")
                        continue
                    
                    # 检查文件内容是否有效
                    try:
                        with open(contentanalyze_file, 'r', encoding='utf-8') as f:
                            contentanalyze_data = json.load(f)
                        if not contentanalyze_data:
                            log_error(logger, f"内容分析数据为空", "Explain")
                            continue
                    except Exception as e:
                        log_error(logger, f"内容分析文件读取失败: {e}", "Explain")
                        continue
                    
                    # 如果使用--only-overall，将contentanalyze作为总体任务处理
                    if only_overall:
                        prepared_tasks.append({
                            'type': 'overall',
                            'func_name': func_name,
                            'data': contentanalyze_data,
                            'target': '总体'
                        })
                    else:
                        # 内容分析只准备一个任务，保存到新闻目录
                        prepared_tasks.append({
                            'type': 'channel',
                            'func_name': func_name,
                            'channel_name': '新闻',
                            'target': target
                        })
                else:
                    # 其他功能的渠道处理
                    analyze_dir = bucket("analyze", topic, folder_name)
                    if not analyze_dir.exists():
                        log_error(logger, f"未找到分析数据目录: {analyze_dir}", "Explain")
                        continue
                    
                    # 检查功能分析目录是否存在
                    func_analyze_dir = analyze_dir / func_name
                    if not func_analyze_dir.exists():
                        log_error(logger, f"功能分析目录不存在: {func_analyze_dir}", "Explain")
                        continue
                    
                    # 获取所有渠道文件夹
                    channel_dirs = set()
                    for channel_dir in func_analyze_dir.iterdir():
                        if channel_dir.is_dir() and channel_dir.name != "总体":
                            channel_file = channel_dir / f"{func_name}.json"
                            if channel_file.exists():
                                # 检查文件内容是否有效
                                try:
                                    with open(channel_file, 'r', encoding='utf-8') as f:
                                        channel_data = json.load(f)
                                        if channel_data and channel_data.get('data'):
                                            channel_dirs.add(channel_dir.name)
                                        else:
                                            log_error(logger, f"渠道分析数据为空: {channel_dir.name}", "Explain")
                                except Exception as e:
                                    log_error(logger, f"渠道分析文件读取失败: {channel_dir.name} | {e}", "Explain")
                            else:
                                log_error(logger, f"渠道分析文件不存在: {channel_file}", "Explain")
                    
                    if not channel_dirs:
                        log_error(logger, f"未找到任何有效的渠道分析结果: {func_name}", "Explain")
                        continue
                                        
                    # 准备渠道解读任务
                    for channel_name in channel_dirs:
                        prepared_tasks.append({
                            'type': 'channel',
                            'func_name': func_name,
                            'channel_name': channel_name,
                            'target': target
                        })
                    
        except Exception as e:
            log_error(logger, f"{func_name}_{target}: {e}", "Explain")
            continue
    
    # 分离总体和渠道任务
    overall_tasks = [task for task in prepared_tasks if task['type'] == 'overall']
    channel_tasks = [task for task in prepared_tasks if task['type'] == 'channel']
    
    log_success(logger, f"任务统计：共计 {len(prepared_tasks)} 个任务 | 总体任务 {len(overall_tasks)} 个，渠道任务 {len(channel_tasks)} 个", "Explain")
    
    # 第二阶段：并发执行所有任务
    # 创建ExplainBase实例用于并发任务
    explainer = ExplainBase(topic, logger)
        
    # 准备并发任务
    completed_count = 0
    total_count = len(prepared_tasks)
    
    async def execute_task(task_info):
        nonlocal completed_count
        try:
            if task_info['type'] == 'overall':
                # 执行总体解读
                func_name = task_info['func_name']
                data = task_info['data']
                
                explanation = await explainer.generate_explanation(func_name, data, "总体")
                if explanation:
                    explainer.save_explanation(func_name, "总体", explanation, date, end_date)
                    
                    # 生成RAG增强解读（二次解读）
                    try:
                        enhanced_explanation = await explainer.generate_rag_enhanced_explanation(
                            func_name, explanation, data, "总体"
                        )
                        if enhanced_explanation:
                            # 保存增强解读到单独的文件
                            explainer.save_explanation(func_name, "总体", enhanced_explanation, date, end_date, rag_enhanced=True)
                            log_success(logger, f"RAG增强解读生成成功: {func_name}", "Explain")
                    except Exception as e:
                        log_error(logger, f"RAG增强解读失败: {func_name} | {e}", "Explain")
                        # RAG增强失败不影响主流程
                    
                    completed_count += 1
                    progress = (completed_count / total_count) * 100
                    log_success(logger, f"任务进度: {completed_count}/{total_count} ({progress:.1f}%)", "Explain")
                    return True
                return False
                
            elif task_info['type'] == 'channel':
                # 执行渠道解读 - 直接加载特定渠道数据
                func_name = task_info['func_name']
                channel_name = task_info['channel_name']
                
                if func_name == 'contentanalyze':
                    # 内容分析特殊处理
                    if end_date:
                        folder_name = f"{date}_{end_date}"
                    else:
                        folder_name = date
                    
                    contentanalyze_file = project_root / "data" / "contentanalyze" / topic / folder_name / "contentanalysis.json"
                    
                    if not contentanalyze_file.exists():
                        return False
                    
                    try:
                        with open(contentanalyze_file, 'r', encoding='utf-8') as f:
                            contentanalyze_data = json.load(f)
                        if not contentanalyze_data:
                            return False
                    except Exception as e:
                        return False
                    
                    explanation = await explainer.generate_explanation(func_name, contentanalyze_data, "渠道", channel_name)
                    if explanation:
                        explainer.save_explanation(func_name, "渠道", explanation, date, end_date, channel_name)
                        
                        # 生成RAG增强解读（二次解读）
                        try:
                            enhanced_explanation = await explainer.generate_rag_enhanced_explanation(
                                func_name, explanation, contentanalyze_data, "渠道", channel_name
                            )
                            if enhanced_explanation:
                                # 保存增强解读到单独的文件
                                explainer.save_explanation(func_name, "渠道", enhanced_explanation, date, end_date, channel_name, rag_enhanced=True)
                                log_success(logger, f"RAG增强解读生成成功: {func_name} | {channel_name}", "Explain")
                        except Exception as e:
                            log_error(logger, f"RAG增强解读失败: {func_name} | {channel_name} | {e}", "Explain")
                            # RAG增强失败不影响主流程
                        
                        completed_count += 1
                        progress = (completed_count / total_count) * 100
                        log_success(logger, f"任务进度: {completed_count}/{total_count} ({progress:.1f}%)", "Explain")
                        return True
                    return False
                else:
                    # 其他功能的渠道解读
                    if end_date:
                        folder_name = f"{date}_{end_date}"
                    else:
                        folder_name = date
                    
                    analyze_dir = project_root / "data" / "analyze" / topic / folder_name
                    channel_file = analyze_dir / func_name / channel_name / f"{func_name}.json"
                    
                    if not channel_file.exists():
                        return False
                    
                    try:
                        with open(channel_file, 'r', encoding='utf-8') as f:
                            channel_data = json.load(f)
                        if not channel_data or not channel_data.get('data'):
                            return False
                    except Exception as e:
                        return False
                    
                    explanation = await explainer.generate_explanation(func_name, channel_data, "渠道", channel_name)
                    if explanation:
                        explainer.save_explanation(func_name, "渠道", explanation, date, end_date, channel_name)
                        
                        # 生成RAG增强解读（二次解读）
                        try:
                            enhanced_explanation = await explainer.generate_rag_enhanced_explanation(
                                func_name, explanation, channel_data, "渠道", channel_name
                            )
                            if enhanced_explanation:
                                # 保存增强解读到单独的文件
                                explainer.save_explanation(func_name, "渠道", enhanced_explanation, date, end_date, channel_name, rag_enhanced=True)
                                log_success(logger, f"RAG增强解读生成成功: {func_name} | {channel_name}", "Explain")
                        except Exception as e:
                            log_error(logger, f"RAG增强解读失败: {func_name} | {channel_name} | {e}", "Explain")
                            # RAG增强失败不影响主流程
                        
                        completed_count += 1
                        progress = (completed_count / total_count) * 100
                        log_success(logger, f"渠道任务进度: {completed_count}/{total_count} ({progress:.1f}%)", "Explain")
                        return True
                    return False
                
        except Exception as e:
            log_error(logger, f"任务执行失败: {task_info.get('func_name', 'unknown')} | {e}", "Explain")
            return False
    
    # 并发执行所有任务
    if prepared_tasks:
        
        # 使用LLM配置中的qps作为并发限制
        semaphore = asyncio.Semaphore(explainer.llm_config.get('qps', 10))
        
        async def limited_task(task_info):
            async with semaphore:
                return await execute_task(task_info)
        
        # 执行所有任务
        results = await asyncio.gather(*[limited_task(task) for task in prepared_tasks], return_exceptions=True)
        
        # 统计成功数量
        successful_results = [r for r in results if r is True]
        failed_results = [r for r in results if isinstance(r, Exception)]
        
        success_count = len(successful_results)
        completed_tasks = len(prepared_tasks)
        
        log_success(logger, f"并发执行完成 | 配置功能: {config_tasks} | 实际任务: {completed_tasks} | 成功: {success_count} | 失败: {completed_tasks - success_count} | 成功率: {(success_count/completed_tasks)*100:.1f}%", "Explain")
    
    # 返回是否成功（至少有一个函数成功）
    return success_count > 0
