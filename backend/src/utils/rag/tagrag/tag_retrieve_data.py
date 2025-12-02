"""
向量数据库召回程序，支持基于查询语句的相似性检索。
"""
import os
import json
import numpy as np
import lancedb
from openai import OpenAI
from typing import List, Dict, Any, Optional
import pickle
from pathlib import Path
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

class Retriever:
    """向量检索器类。"""
    
    def __init__(self, topic_name: str = "控烟", db_path: str = None, logger=None):
        """
        初始化向量检索器。
        
        Args:
            topic_name: RAG主题名称（如"控烟"），用于指定读取哪个向量表
            db_path: 向量数据库路径，如果为None则使用默认路径
            logger: 日志记录器
        """
        self.logger = logger
        self.topic_name = topic_name
        # 将主题名称转换为拼音作为表名（lance不支持中文表名）
        self.table_name = to_pinyin(topic_name)
        self.data = []
        
        # 设置数据库路径
        if db_path is None:
            project_root = get_project_root()
            self.db_path = str(project_root / "src" / "utils" / "rag" / "tagrag" / "vector_db")
        else:
            self.db_path = db_path
        
        if self.logger:
            pass  # 日志初始化完成
        
        # 初始化OpenAI客户端
        self._init_client()
        self._load_database()
    
    def _init_client(self):
        """初始化OpenAI客户端。"""
        try:
            # 从配置文件获取LLM配置
            llm_config = settings.get_llm_config()
            embedding_config = llm_config.get('embedding_llm', {})
            
            # 使用统一的环境变量加载器获取API密钥
            api_key = get_api_key()
            base_url = embedding_config.get('base_url', "https://dashscope.aliyuncs.com/compatible-mode/v1")
            
            if not api_key:
                if self.logger:
                    log_error(self.logger, "未找到API密钥，请在配置文件的 credentials.qwen_api_key 中设置", "Retriever")
                raise ValueError("API密钥未配置")
            
            self.client = OpenAI(
                api_key=api_key,
                base_url=base_url
            )
            
            if self.logger:
                pass  # OpenAI客户端初始化成功
        except Exception as e:
            if self.logger:
                log_error(self.logger, f"OpenAI客户端初始化失败: {e}", "Retriever")
            raise
    
    def _load_database(self) -> None:
        """加载向量数据库。"""
        try:
            db = lancedb.connect(self.db_path)
            if self.table_name in db.table_names():
                table = db.open_table(self.table_name)
                # 将LanceDB表转换为列表格式
                self.data = []
                # 使用to_pandas()方法获取所有数据
                df = table.to_pandas()
                for _, row in df.iterrows():
                    self.data.append({
                        'id': int(row['id']),
                        'text': str(row['text']),
                        'tag_vec': row['tag_vec'].tolist() if hasattr(row['tag_vec'], 'tolist') else list(row['tag_vec'])
                    })
                if self.logger:
                    pass  # 向量记录加载成功
            else:
                if self.logger:
                    log_error(self.logger, f"表 {self.table_name} 不存在", "Retriever")
                self.data = []
        except Exception as e:
            if self.logger:
                log_error(self.logger, f"加载数据库失败: {e}", "Retriever")
            self.data = []
    
    def _get_query_embedding(self, query: str) -> List[float]:
        """
        获取查询语句的向量表示。
        
        Args:
            query: 查询语句
            
        Returns:
            查询语句的向量表示
        """
        try:
            response = self.client.embeddings.create(
                model="text-embedding-v4",
                input=query
            )
            return response.data[0].embedding
        except Exception as e:
            if self.logger:
                log_error(self.logger, f"查询向量化失败: {e}", "Retriever")
            return [0.0] * 1024  # 返回零向量
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """
        计算两个向量的余弦相似度。
        
        Args:
            vec1: 向量1
            vec2: 向量2
            
        Returns:
            余弦相似度值
        """
        vec1 = np.array(vec1)
        vec2 = np.array(vec2)
        
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (norm1 * norm2)
    
    def retrieve(self, 
                 query: str, 
                 top_k: int = 5, 
                 search_column: str = "tag_vec",
                 min_similarity: float = 0.0,
                 return_columns: List[str] = None) -> List[Dict[str, Any]]:
        """
        基于查询语句检索相似数据。
        
        Args:
            query: 查询语句
            top_k: 召回数量
            search_column: 召回列（text_vec 或 tag_vec）
            min_similarity: 最小相似度阈值
            return_columns: 返回的列名列表，None表示返回所有列
            
        Returns:
            检索结果列表，按相似度降序排列
        """
        if not self.data:
            if self.logger:
                log_error(self.logger, "数据库为空，无法进行检索", "Retriever")
            return []
        
        if search_column not in ["text_vec", "tag_vec"]:
            if self.logger:
                log_error(self.logger, f"不支持的搜索列: {search_column}", "Retriever")
            return []
        
        # 获取查询向量
        query_vector = self._get_query_embedding(query)
        
        # 计算相似度
        similarities = []
        for i, item in enumerate(self.data):
            if search_column in item:
                similarity = self._cosine_similarity(query_vector, item[search_column])
                if similarity >= min_similarity:  # 过滤低相似度结果
                    similarities.append({
                        'index': i,
                        'similarity': similarity,
                        'data': item
                    })
        
        # 按相似度排序
        similarities.sort(key=lambda x: x['similarity'], reverse=True)
        
        # 返回前k个结果
        results = similarities[:top_k]
        
        # 如果指定了返回列，则过滤结果
        if return_columns:
            filtered_results = []
            for result in results:
                filtered_data = {col: result['data'].get(col) for col in return_columns if col in result['data']}
                filtered_results.append({
                    'index': result['index'],
                    'similarity': result['similarity'],
                    'data': filtered_data
                })
            results = filtered_results
        
        return results
    
    def get_result_details(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        获取检索结果的详细信息。
        
        Args:
            results: 检索结果列表
            
        Returns:
            包含详细信息的检索结果
        """
        detailed_results = []
        for i, result in enumerate(results):
            detailed_result = {
                'id': result['data']['id'],
                'text': result['data']['text']
            }
            detailed_results.append(detailed_result)
        
        return detailed_results
    
    def search(self, 
               query: str, 
               top_k: int = 5, 
               search_column: str = "tag_vec",
               min_similarity: float = 0.0,
               return_columns: List[str] = None,
               show_details: bool = True) -> List[Dict[str, Any]]:
        """
        便捷的搜索方法，整合了检索和结果格式化。
        
        Args:
            query: 查询语句
            top_k: 召回数量
            search_column: 召回列（text_vec 或 tag_vec）
            min_similarity: 最小相似度阈值
            return_columns: 返回的列名列表，None表示返回所有列
            show_details: 是否显示详细信息
            
        Returns:
            检索结果列表
        """
        # 执行检索
        results = self.retrieve(
            query=query,
            top_k=top_k,
            search_column=search_column,
            min_similarity=min_similarity,
            return_columns=return_columns
        )
        
        if show_details:
            return self.get_result_details(results)
        else:
            return results

def tag_retrieve(query: str,
                 topic_name: str = "控烟",
                 search_column: str = "tag_vec", 
                 top_k: int = 5, 
                 return_columns: List[str] = None) -> Dict[str, Any]:
    """
    向量检索包装函数，返回JSON格式的检索结果。
    """
    # 初始化logger，使用主题名称作为日志标识
    logger = setup_logger(f"TagRetrieve_{topic_name}", "default")
    
    try:
        # 初始化检索器
        retriever = Retriever(topic_name=topic_name, logger=logger)
        
        # 执行检索
        results = retriever.search(
            query=query,
            top_k=top_k,
            search_column=search_column,
            min_similarity=0.0,
            return_columns=return_columns,
            show_details=True
        )
        
        # 构建返回结果
        response_data = {
            "status": "success",
            "results": results
        }
        
        return response_data
        
    except Exception as e:
        log_error(logger, f"检索失败: {e}", "TagRetrieve")
        return {
            "status": "error",
            "error": str(e),
            "results": []
        }
