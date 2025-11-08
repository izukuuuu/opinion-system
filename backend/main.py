"""
OpinionSystem 舆情分析系统主程序
"""
import sys
import click
import asyncio
import warnings
from pathlib import Path

# 抑制 openpyxl 的默认样式警告
warnings.filterwarnings("ignore", message="workbook contains no default style, apply openpyxl's default")


def _ensure_src_on_path() -> None:
    """确保src目录在Python路径中"""
    project_root = Path(__file__).resolve().parent
    src_dir = project_root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))


def _as_success(result) -> bool:
    """将步骤执行结果转换为布尔值。"""

    if isinstance(result, bool):
        return result
    if isinstance(result, dict):
        status = result.get("status")
        if status is not None:
            return status != "error"
        return True
    return result is not None


def _log_project_event(project: str, operation: str, params=None, success: bool = True) -> None:
    """记录项目操作信息。"""

    if not project:
        return

    try:
        from src.project import get_project_manager  # type: ignore

        manager = get_project_manager()
        manager.log_operation(project, operation, params=params, success=bool(success))
    except Exception as exc:  # pragma: no cover - 日志失败不影响主流程
        warnings.warn(f"项目日志写入失败: {exc}")


def main() -> None:
    """主程序入口"""
    _ensure_src_on_path()
    cli()


@click.group()
def cli():
    """
    OpinionSystem 舆情分析系统命令行工具
    """
    pass

@cli.command('Merge')
@click.option('--topic', required=True, help='专题名称')
@click.option('--date', required=True, help='日期 (YYYY-MM-DD)')
def trs_merge(topic, date):
    """
    合并TRS Excel文件
    """
    from src.merge import run_merge

    result = run_merge(topic, date)
    _log_project_event(topic, "merge", {"date": date, "source": "cli"}, _as_success(result))
    if not _as_success(result):
        print(f"合并失败: {topic} - {date}")


@cli.command('Clean')
@click.option('--topic', required=True, help='专题名称')
@click.option('--date', required=True, help='日期 (YYYY-MM-DD)')
def clean(topic, date):
    """
    清洗数据
    """
    from src.clean import run_clean

    result = run_clean(topic, date)
    _log_project_event(topic, "clean", {"date": date, "source": "cli"}, _as_success(result))
    if not _as_success(result):
        print(f"清洗失败: {topic} - {date}")


@cli.command('Filter')
@click.option('--topic', required=True, help='专题名称')
@click.option('--date', required=True, help='日期 (YYYY-MM-DD)')
def ai_filter(topic, date):
    """
    AI相关性筛选
    """
    from src.filter import run_filter

    result = run_filter(topic, date)
    _log_project_event(topic, "filter", {"date": date, "source": "cli"}, _as_success(result))
    if not _as_success(result):
        print(f"筛选失败: {topic} - {date}")


@cli.command('Upload')
@click.option('--topic', required=True, help='专题名称')
@click.option('--date', required=True, help='日期 (YYYY-MM-DD)')
def upload(topic, date):
    """
    上传数据到数据库
    """
    from src.update import run_update

    result = run_update(topic, date)
    _log_project_event(topic, "upload", {"date": date, "source": "cli"}, _as_success(result))
    if not _as_success(result):
        extra = ""
        if isinstance(result, dict):
            message = result.get("message")
            if message:
                extra = f" - {message}"
        print(f"上传失败: {topic} - {date}{extra}")


@cli.command('Query')
def query():
    """
    查询数据库信息
    """
    from src.query import run_query

    result = run_query()
    _log_project_event("GLOBAL", "query", {"source": "cli"}, _as_success(result))
    if not _as_success(result):
        print("查询失败")


@cli.command('Fetch')
@click.option('--topic', required=True, help='专题名称')
@click.option('--start', required=True, help='开始日期 (YYYY-MM-DD)')
@click.option('--end', required=True, help='结束日期 (YYYY-MM-DD)')
def fetch(topic, start, end):
    """
    从数据库获取数据
    """
    from src.fetch import run_fetch

    result = run_fetch(topic, start, end)
    _log_project_event(
        topic,
        "fetch",
        {"start": start, "end": end, "source": "cli"},
        _as_success(result),
    )
    if not _as_success(result):
        print(f"提取失败: {topic} - {start} 到 {end}")


@cli.command('Analyze')
@click.option('--topic', required=True, help='专题名称')
@click.option('--start', required=True, help='开始日期 (YYYY-MM-DD)')
@click.option('--end', required=True, help='结束日期 (YYYY-MM-DD)')
@click.option('--func', help='指定分析函数')
def analyze(topic, start, end, func):
    """
    运行数据分析
    """
    from src.analyze import run_Analyze

    result = run_Analyze(topic, start, end_date=end, only_function=func)
    _log_project_event(
        topic,
        "analyze",
        {"start": start, "end": end, "function": func, "source": "cli"},
        _as_success(result),
    )
    if not _as_success(result):
        print(f"分析失败: {topic} - {start} 到 {end}")


@cli.command('DataPipeline')
@click.option('--topic', required=True, help='专题名称')
@click.option('--date', required=True, help='日期 (YYYY-MM-DD)')
def data_pipeline(topic, date):
    """
    数据清洗和存储流水线（使用单日期）
    """
    from src.merge import run_merge
    from src.clean import run_clean
    from src.filter import run_filter
    from src.update import run_update
        
    # 1. 合并TRS数据
    merge_success = run_merge(topic, date)
    _log_project_event(topic, "merge", {"date": date, "source": "pipeline"}, _as_success(merge_success))
    if not merge_success:
        print("合并步骤失败")
        return False

    # 2. 数据清洗
    clean_success = run_clean(topic, date)
    _log_project_event(topic, "clean", {"date": date, "source": "pipeline"}, _as_success(clean_success))
    if not clean_success:
        print("清洗步骤失败")
        return False

    # 3. AI筛选
    filter_success = run_filter(topic, date)
    _log_project_event(topic, "filter", {"date": date, "source": "pipeline"}, _as_success(filter_success))
    if not filter_success:
        print("筛选步骤失败")
        return False

    # 4. 数据上传
    upload_success = run_update(topic, date)
    _log_project_event(topic, "upload", {"date": date, "source": "pipeline"}, _as_success(upload_success))
    if not upload_success:
        print("上传步骤失败")
        return False

    return True


@cli.command('AnalyzePipeline')
@click.option('--topic', required=True, help='专题名称')
@click.option('--start', required=True, help='开始日期 (YYYY-MM-DD)')
@click.option('--end', required=True, help='结束日期 (YYYY-MM-DD)')
def analysis_pipeline(topic, start, end):
    """
    数据分析流水线（使用时间范围）
    """
    from src.fetch import run_fetch
    from src.analyze import run_Analyze
        
    # 1. 提数
    fetch_success = run_fetch(topic, start, end)
    _log_project_event(
        topic,
        "fetch",
        {"start": start, "end": end, "source": "analysis_pipeline"},
        _as_success(fetch_success),
    )
    if not fetch_success:
        print("提取步骤失败")
        return False

    # 2. 数据分析
    analyze_success = run_Analyze(topic, start, end_date=end)
    _log_project_event(
        topic,
        "analyze",
        {"start": start, "end": end, "source": "analysis_pipeline"},
        _as_success(analyze_success),
    )
    if not analyze_success:
        print("分析步骤失败")
        return False

    return True


@cli.command('Projects')
def show_projects():
    """列出当前已记录的项目及其最近状态"""

    _ensure_src_on_path()
    from src.project import get_project_manager  # type: ignore

    manager = get_project_manager()
    projects = manager.list_projects()
    if not projects:
        click.echo("暂无项目记录。")
        return

    for project in projects:
        click.echo(f"- {project['name']} ({project['status']}) 更新于 {project['updated_at']}")
        if project.get('description'):
            click.echo(f"  描述: {project['description']}")
        dates = project.get('dates') or []
        if dates:
            click.echo(f"  涉及日期: {', '.join(dates)}")
        last = project.get('last_operation')
        if last:
            status = "成功" if last.get('success') else "失败"
            click.echo(
                f"  最近操作: {last.get('operation')} ({status}) @ {last.get('timestamp')}"
            )
        click.echo("")


if __name__ == "__main__":
    main()

