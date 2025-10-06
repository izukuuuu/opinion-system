"""
统一路径管理模块
"""
import os
from pathlib import Path
from typing import Literal, Optional

# 目录层级类型
LAYERS = Literal['raw', 'merge', 'clean', 'filter', 'fetch', 'analyze', 'reports', 'results']

def get_project_root() -> Path:
    """
    获取项目根目录，支持多种检测方式：
    1. 自动检测（基于当前文件位置）
    2. 当前工作目录
    
    Returns:
        Path: 项目根目录路径
    """
    # 方式1: 自动检测（基于当前文件位置）
    current_file = Path(__file__).resolve()
    
    # 尝试多种可能的项目结构
    possible_roots = [
        current_file.parents[2],  # src/utils -> src -> <repo_root>
        current_file.parents[1],  # src/utils -> <repo_root>
        current_file.parents[3],  # src/utils -> src -> <repo_root> -> <parent>
    ]
    
    for root in possible_roots:
        if _is_project_root(root):
            return root
    
    # 方式2: 当前工作目录
    cwd = Path.cwd().resolve()
    if _is_project_root(cwd):
        return cwd
    
    # 方式3: 向上查找项目根目录
    for parent in cwd.parents:
        if _is_project_root(parent):
            return parent
    
    # 如果都找不到，使用当前文件的上两级目录作为默认值
    default_root = current_file.parents[2]
    print(f"⚠️  警告: 无法自动检测项目根目录，使用默认值: {default_root}")
    return default_root


def _is_project_root(path: Path) -> bool:
    """
    判断是否为项目根目录
    
    Args:
        path (Path): 待检查的路径
    
    Returns:
        bool: 是否为项目根目录
    """
    if not path.exists() or not path.is_dir():
        return False
    
    # 检查特征文件和目录
    characteristic_files = ['README.md', 'requirements.txt', 'cli.py']
    characteristic_dirs = ['src', 'configs', 'data', 'logs']
    
    has_files = any((path / f).exists() for f in characteristic_files)
    has_dirs = any((path / d).exists() for d in characteristic_dirs)
    
    return has_files and has_dirs


def get_data_root() -> Path:
    """
    获取数据根目录。

    优先使用 backend/data 目录，以便与仓库分离管理。如果 backend
    目录不存在，则回退到项目根目录下的 data 目录。

    Returns:
        Path: 数据根目录路径
    """
    project_root = get_project_root()
    backend_dir = project_root / "backend"
    if backend_dir.exists():
        backend_data = backend_dir / "data"
        backend_data.mkdir(parents=True, exist_ok=True)
        return backend_data

    data_dir = project_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_logs_root() -> Path:
    """
    获取日志根目录
    
    Returns:
        Path: 日志根目录路径
    """
    # 使用项目根目录下的logs文件夹
    project_root = get_project_root()
    return project_root / "logs"


def get_configs_root() -> Path:
    """
    获取配置根目录
    
    Returns:
        Path: 配置根目录路径
    """
    # 使用项目根目录下的configs文件夹
    project_root = get_project_root()
    return project_root / "configs"


def bucket(layer: LAYERS, topic: str, date: str) -> Path:
    """
    获取指定层级的数据桶路径
    
    Args:
        layer (LAYERS): 数据层级
        topic (str): 专题名称
        date (str): 日期字符串
    
    Returns:
        Path: 数据桶路径
    """
    data_root = get_data_root()
    return data_root / layer / topic / date


def ensure_bucket(layer: LAYERS, topic: str, date: str) -> Path:
    """
    获取指定层级的数据桶路径，并确保目录存在
    
    Args:
        layer (LAYERS): 数据层级
        topic (str): 专题名称
        date (str): 日期字符串
    
    Returns:
        Path: 数据桶路径
    """
    path = bucket(layer, topic, date)
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_bucket(topic: str, date: str) -> Path:
    """
    获取日志桶路径
    
    Args:
        topic (str): 专题名称
        date (str): 日期字符串
    
    Returns:
        Path: 日志桶路径
    """
    logs_root = get_logs_root()
    return logs_root / topic / date


def get_relative_path(absolute_path: Path) -> str:
    """
    获取相对于项目根目录的路径
    
    Args:
        absolute_path (Path): 绝对路径
    
    Returns:
        str: 相对路径字符串
    """
    try:
        project_root = get_project_root()
        return str(absolute_path.relative_to(project_root))
    except ValueError:
        return str(absolute_path)

