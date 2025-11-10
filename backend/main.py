"""
OpinionSystem 舆情分析系统主程序
"""
import json
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
@click.option('--json', 'show_json', is_flag=True, help='以JSON格式输出完整结果')
@click.option(
    '--save',
    'save_path',
    type=click.Path(dir_okay=False, writable=True, resolve_path=True),
    help='将查询结果写入指定JSON文件',
)
def query(show_json, save_path):
    """
    查询数据库信息
    """
    from src.query import run_query

    result = run_query()
    success = _as_success(result)
    _log_project_event("GLOBAL", "query", {"source": "cli"}, success)
    if not success:
        print("查询失败")
        if isinstance(result, dict):
            message = result.get("message")
            if message:
                print(f"详情: {message}")
        return

    if isinstance(result, dict):
        summary = result.get("summary") or {}
        db_count = summary.get("database_count", 0)
        table_count = summary.get("table_count", 0)
        row_count = summary.get("row_count", 0)
        print(f"成功查询 {db_count} 个数据库，{table_count} 张表，共 {row_count} 条记录")

        databases = result.get("databases") or []
        max_preview = 10
        if databases:
            print("数据库概览:")
            for database in databases[:max_preview]:
                db_name = database.get("name", "<unknown>")
                table_total = database.get("table_count", len(database.get("tables") or []))
                row_total = database.get("total_rows", 0)
                print(f"- {db_name}: {table_total} 表 / {row_total} 行")
            if len(databases) > max_preview:
                print(f"... 其余 {len(databases) - max_preview} 个数据库已省略，使用 --json 查看全部内容。")

    if show_json or save_path:
        try:
            payload = json.dumps(result, ensure_ascii=False, indent=2)
        except TypeError as exc:
            print(f"结果JSON序列化失败: {exc}")
            payload = None
        if payload:
            if show_json:
                print(payload)
            if save_path:
                target = Path(save_path)
                try:
                    target.write_text(payload, encoding="utf-8")
                    print(f"已写入查询结果到 {target}")
                except OSError as exc:
                    print(f"写入 {target} 失败: {exc}")


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


@cli.command('FetchAvailability')
@click.option('--topic', required=True, help='专题名称（数据库名）')
@click.option('--table', help='可选渠道表名，仅查看该表的可用区间')
@click.option('--json', 'show_json', is_flag=True, help='以JSON格式输出结果')
def fetch_availability(topic, table, show_json):
    """
    查看各渠道或专题的可用日期区间
    """
    from src.fetch import get_available_date_range, get_topic_available_date_range

    payload = {}
    message = None
    success = True

    try:
        if table:
            start, end = get_available_date_range(topic, table)
            payload = {"topic": topic, "table": table, "start": start, "end": end}
            if not start and not end:
                message = f"表 {topic}.{table} 无可用 published_at 数据"
        else:
            payload = get_topic_available_date_range(topic) or {}
            tables = payload.get("tables") or {}
            if not tables:
                message = f"专题 {topic} 未找到包含 published_at 字段的表"
    except Exception as exc:
        success = False
        message = f"查询失败: {exc}"

    _log_project_event(
        topic,
        "fetch_availability",
        {"table": table, "source": "cli"},
        success,
    )

    if not success:
        print(message or "可用日期区间查询失败")
        return

    if show_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        if message:
            print(message)
        return

    if table:
        start = payload.get("start") or "-"
        end = payload.get("end") or "-"
        print(f"{topic}.{table} 可用日期: {start} ~ {end}")
    else:
        start = payload.get("start") or "-"
        end = payload.get("end") or "-"
        print(f"专题 {topic} 可用日期: {start} ~ {end}")
        tables = payload.get("tables") or {}
        if tables:
            print("包含的表:")
            for name in sorted(tables.keys()):
                info = tables[name] or {}
                t_start = info.get("start") or "-"
                t_end = info.get("end") or "-"
                print(f"- {name}: {t_start} ~ {t_end}")

    if message:
        print(message)


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
