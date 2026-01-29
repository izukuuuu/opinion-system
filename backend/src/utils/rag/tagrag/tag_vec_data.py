"""
将format.json中的数据进行向量化并存储到LanceDB数据库。
"""
import os
import json
import lancedb
import numpy as np
from pathlib import Path
from openai import OpenAI
from typing import List, Dict, Any
from pypinyin import lazy_pinyin, Style
from ...setting.settings import settings
from ...setting.env_loader import get_api_key
from ...setting.paths import get_project_root
from ...logging.logging import setup_logger, log_success, log_error, log_module_start

def to_pinyin(text: str) -> str:
    """
    将中文文本转换为拼音（小写，无空格）。
    
    Args:
        text: 中文文本
    
    Returns:
        str: 拼音字符串
    """
    pinyin_list = lazy_pinyin(text, style=Style.NORMAL)
    return ''.join(pinyin_list).lower()

def load_data(json_file: str, logger) -> List[Dict[str, Any]]:
    """加载JSON数据文件。"""
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data['data']
    except Exception as e:
        log_error(logger, f"加载数据文件失败: {e}", "Tagvectorize")
        raise

def get_embeddings(texts: List[str], client: OpenAI, logger, dimension: int = 1024) -> List[List[float]]:
    """使用千问模型获取文本向量。"""
    embeddings = []
    for i, text in enumerate(texts):
        try:
            response = client.embeddings.create(
                model="text-embedding-v4",
                input=text
            )
            embeddings.append(response.data[0].embedding)
            if (i + 1) % 10 == 0 or i == len(texts) - 1:  # 每10个或最后一个显示进度
                log_success(logger, f"向量化进度: {i+1}/{len(texts)}", "Tagvectorize")
        except Exception as e:
            log_error(logger, f"向量化失败: {e}", "Tagvectorize")
            # 如果失败，使用零向量
            embeddings.append([0.0] * dimension)
    return embeddings

def get_existing_ids(db_path: str, table_name: str, logger) -> set:
    """获取已存在数据库中的ID集合。"""
    try:
        db = lancedb.connect(db_path)
        if table_name in db.table_names():
            table = db.open_table(table_name)
            existing_ids = set()
            # 使用to_pandas()方法获取数据
            df = table.to_pandas()
            existing_ids = set(df['id'].tolist())
            return existing_ids
        return set()
    except Exception as e:
        log_error(logger, f"读取现有数据库失败: {e}", "Tagvectorize")
        return set()

def vectorize_and_store(
    topic_name: str = "控烟",
    format_json_path: str = None,
    vector_db_path: str = None,
):
    """
    主函数：向量化数据并存储到LanceDB数据库。
    
    Args:
        topic_name: RAG主题名称（如"控烟"），用于指定读取哪个JSON文件和生成对应的表
    """
    # 初始化logger，使用主题名称作为日志标识
    logger = setup_logger(f"Tagvectorize_{topic_name}", "default")
    log_module_start(logger, "Tagvectorize", f"开始向量化数据 - 主题: {topic_name}")
    
    try:
        # 从配置文件获取LLM配置
        llm_config = settings.get_llm_config()
        embedding_config = llm_config.get('embedding_llm', {})
        
        # 初始化OpenAI客户端
        # 使用统一的环境变量加载器获取API密钥
        api_key = get_api_key()
        base_url = embedding_config.get('base_url', "https://dashscope.aliyuncs.com/compatible-mode/v1")
        
        if not api_key:
            log_error(logger, "未找到API密钥，请在配置文件的 credentials.qwen_api_key 中设置", "TagRAG")
            raise ValueError("API密钥未配置")
        
        client = OpenAI(
            api_key=api_key,
            base_url=base_url
        )
        log_success(logger, "OpenAI客户端初始化成功", "Tagvectorize")
        
        # 加载数据
        # 使用绝对路径定位主题JSON文件（允许外部传入）
        if format_json_path:
            format_json_path = Path(format_json_path)
        else:
            project_root = get_project_root()
            format_json_path = project_root / "src" / "utils" / "rag" / "tagrag" / "format_db" / f"{topic_name}.json"

        if not format_json_path.exists():
            log_error(logger, f"主题数据文件不存在: {format_json_path}", "Tagvectorize")
            raise FileNotFoundError(f"主题数据文件不存在: {format_json_path}")

        data = load_data(str(format_json_path), logger)
        
        # 确保数据目录存在
        if vector_db_path:
            vector_db_path = Path(vector_db_path)
        else:
            project_root = get_project_root()
            vector_db_path = project_root / "src" / "utils" / "rag" / "tagrag" / "vector_db"
        os.makedirs(vector_db_path, exist_ok=True)
        db_path = str(vector_db_path)
        
        # 将主题名称转换为拼音作为表名（lance不支持中文表名）
        table_name = to_pinyin(topic_name)
        log_success(logger, f"使用表名: {table_name} (对应主题: {topic_name})", "Tagvectorize")
        
        # 获取已存在的ID
        existing_ids = get_existing_ids(db_path, table_name, logger)
        
        # 筛选需要处理的新数据
        new_data = []
        for i, item in enumerate(data):
            if i not in existing_ids:
                new_data.append((i, item))
        
        if not new_data:
            db = lancedb.connect(db_path)
            return db.open_table(table_name)
            
        # 准备向量化数据
        texts = []
        for _, item in new_data:
            texts.append(item['tag'])  # 只对tag进行向量化
        
        # 获取标签向量
        dimension = embedding_config.get('dimension', 1024)
        tag_embeddings = get_embeddings(texts, client, logger, dimension)
        
        # 准备存储数据
        records = []
        for (i, item), tag_vec in zip(new_data, tag_embeddings):
            record = {
                'id': i,
                'text': item['text'],
                'tag_vec': tag_vec
            }
            records.append(record)
        
        # 写入或追加到LanceDB数据库
        
        # 连接数据库
        db = lancedb.connect(db_path)
        
        if existing_ids:
            # 追加模式
            table = db.open_table(table_name)
            table.add(records)
        else:
            # 创建新模式
            if table_name in db.table_names():
                # 如果表已存在但为空，先删除再创建
                db.drop_table(table_name)
            table = db.create_table(table_name, records)
        return table
        
    except Exception as e:
        log_error(logger, f"向量化处理失败: {e}", "Tagvectorize")
        raise
