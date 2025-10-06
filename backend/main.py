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
    if not result:
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
    if not result:
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
    if not result:
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
    if not result:
        print(f"上传失败: {topic} - {date}")


@cli.command('Query')
def query():
    """
    查询数据库信息
    """
    from src.query import run_query
    
    result = run_query()
    if not result:
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
    if not result:
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
    if not result:
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
    if not run_merge(topic, date):
        print("合并步骤失败")
        return False
    
    # 2. 数据清洗
    if not run_clean(topic, date):
        print("清洗步骤失败")
        return False
    
    # 3. AI筛选
    if not run_filter(topic, date):
        print("筛选步骤失败")
        return False
    
    # 4. 数据上传
    if not run_update(topic, date):
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
    if not run_fetch(topic, start, end):
        print("提取步骤失败")
        return False
    
    # 2. 数据分析
    if not run_Analyze(topic, start, end_date=end):
        print("分析步骤失败")
        return False
    
    return True


if __name__ == "__main__":
    main()


