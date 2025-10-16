"""
Excel和文件读写工具模块
"""
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd


def read_excel(file_path: Union[str, Path], **kwargs) -> pd.DataFrame:
    """
    读取Excel文件
    
    Args:
        file_path (Union[str, Path]): 文件路径
        **kwargs: 传递给pd.read_excel的参数
    
    Returns:
        pd.DataFrame: 读取的数据
    """
    return pd.read_excel(file_path, **kwargs)


def write_excel(df: pd.DataFrame, file_path: Union[str, Path], **kwargs) -> None:
    """
    写入Excel文件
    
    Args:
        df (pd.DataFrame): 要保存的数据框
        file_path (Union[str, Path]): 文件路径
        **kwargs: 传递给df.to_excel的参数
    """
    Path(file_path).parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(file_path, index=False, **kwargs)


def read_parquet(file_path: Union[str, Path], **kwargs) -> pd.DataFrame:
    """
    读取Parquet文件
    
    Args:
        file_path: 文件路径
        **kwargs: 传递给pd.read_parquet的参数
    
    Returns:
        pd.DataFrame: 读取的数据
    """
    return pd.read_parquet(file_path, **kwargs)


def write_parquet(df: pd.DataFrame, file_path: Union[str, Path], **kwargs) -> None:
    """
    写入Parquet文件
    
    Args:
        df: 要保存的数据框
        file_path: 文件路径
        **kwargs: 传递给df.to_parquet的参数
    """
    Path(file_path).parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(file_path, index=False, **kwargs)


def read_csv(file_path: Union[str, Path], **kwargs) -> pd.DataFrame:
    """
    读取CSV文件
    
    Args:
        file_path: 文件路径
        **kwargs: 传递给pd.read_csv的参数
    
    Returns:
        pd.DataFrame: 读取的数据
    """
    return pd.read_csv(file_path, **kwargs)


def write_csv(df: pd.DataFrame, file_path: Union[str, Path], **kwargs) -> None:
    """
    写入CSV文件
    
    Args:
        df: 要保存的数据框
        file_path: 文件路径
        **kwargs: 传递给df.to_csv的参数
    """
    Path(file_path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(file_path, index=False, encoding="utf-8-sig", **kwargs)


def read_jsonl(file_path: Union[str, Path], **kwargs) -> pd.DataFrame:
    """
    读取JSON Lines文件
    
    Args:
        file_path: 文件路径
        **kwargs: 额外传递给pd.read_json的参数
    
    Returns:
        pd.DataFrame: 读取的数据
    """
    params = {"lines": True}
    params.update(kwargs)
    return pd.read_json(file_path, **params)


def write_jsonl(df: pd.DataFrame, file_path: Union[str, Path], **kwargs) -> None:
    """
    写入JSON Lines文件
    
    Args:
        df: 要保存的数据框
        file_path: 文件路径
        **kwargs: 额外传递给df.to_json的参数
    """
    params = {"orient": "records", "lines": True, "force_ascii": False}
    params.update(kwargs)
    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_json(file_path, **params)


def generate_id(segment: str, url: str = "", published_at: str = "") -> str:
    """
    生成数据指纹ID
    
    Args:
        segment (str): 文本片段
        url (str, optional): URL
        published_at (str, optional): 发布时间
    
    Returns:
        str: SHA1哈希值
    """
    if url and published_at:
        content = f"{url}{published_at}"
    else:
        content = segment
    
    return hashlib.sha1(content.encode("utf-8")).hexdigest()


def get_standard_table_schema() -> Dict[str, str]:
    """
    获取标准表结构定义（锁死格式，按最大容量设计）
    
    Returns:
        Dict[str, str]: 字段名到MySQL类型的映射
    """
    return {
        "id": "VARCHAR(64) PRIMARY KEY",
        "title": "LONGTEXT",
        "contents": "LONGTEXT",
        "platform": "VARCHAR(50)",
        "author": "LONGTEXT",
        "published_at": "DATETIME",
        "url": "LONGTEXT",
        "region": "VARCHAR(100)",
        "hit_words": "TEXT",
        "polarity": "VARCHAR(20)",
        "classification": "VARCHAR(100)",
    }


def sanitize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    清理和规范化DataFrame
    
    Args:
        df (pd.DataFrame): 原始数据框
    
    Returns:
        pd.DataFrame: 清理后的数据框
    """
    # 1. 清理列名
    new_cols = []
    for c in df.columns:
        col = str(c).strip()
        col = col.replace(" ", "_")
        col = col.replace("-", "_")
        new_cols.append(col)
    df.columns = new_cols
    
    # 2. 处理时间字段
    if "published_at" in df.columns:
        df["published_at"] = pd.to_datetime(df["published_at"], errors="coerce")
    
    # 3. 处理分类字段
    if "classification" in df.columns:
        df["classification"] = df["classification"].astype(str).str.strip()
        df["classification"] = df["classification"].replace(["", "nan", "None", "null"], "未知")
    else:
        df["classification"] = "未知"
    
    # 4. 确保所有字段都是字符串类型（除了时间字段）
    for col in df.columns:
        if col not in ["published_at", "id"]:
            df[col] = df[col].astype(str)
    
    # 5. 移除完全空白的行
    df = df.dropna(how="all")
    
    return df
