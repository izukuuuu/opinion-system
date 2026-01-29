"""
RAG检索系统
功能：时间智能过滤、三种检索策略（GraphRAG/NormalRAG/TagRAG）、多跳查询、可配置参数
"""
import asyncio
import json
import lancedb
import yaml
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from ...setting.paths import get_project_root, get_configs_root
from ...setting.env_loader import get_api_key
from ...logging.logging import setup_logger, log_success, log_error, log_module_start
from ...ai.qwen import QwenClient


def get_available_router_topics():
    """
    获取可用的RouterRAG专题列表。

    Returns:
        List[str]: 专题名称列表
    """
    topics = []
    try:
        router_dir = get_project_root() / "src" / "utils" / "rag" / "ragrouter"
        if router_dir.exists():
            topics = [d.name for d in router_dir.iterdir()
                     if d.is_dir() and (d / "normal_db").exists()]
            log_success(None, f"Found {len(topics)} RouterRAG topics: {topics}", "RouterRAG")
        else:
            log_error(None, f"RouterRAG directory not found: {router_dir}", "RouterRAG")
    except Exception as e:
        log_error(None, f"Failed to get RouterRAG topics: {e}", "RouterRAG")

    return topics


@dataclass
class TimeRange:
    """时间范围"""
    has_time: bool
    time_text: str
    matched_docs: List[str]


@dataclass
class SearchParams:
    """检索参数
    
    说明：
    - 所有检索使用向量距离（cosine distance）
    - 距离值越小表示越相似（0表示完全相同，1表示完全不相关）
    - 所有结果已按距离从小到大排序
    """
    query_topic: str
    query_text: str
    search_mode: str  # mixed/graphrag/normalrag/tagrag
    topk_graphrag: int = 3  # GraphRAG返回的核心实体数量（固定前3个，扩展其所有关系）
    topk_normalrag: int = 5
    topk_tagrag: int = 5
    enable_query_expansion: bool = True  # 是否启用查询扩展/重写
    enable_llm_summary: bool = True  # 是否启用LLM整理结果
    llm_summary_mode: str = "strict"  # strict(严格模式)/supplement(补充模式)
    return_format: str = "both"  # both(都返回)/llm_only(仅LLM整理)/index_only(仅索引结果)


@dataclass
class GraphRAGResult:
    """GraphRAG检索结果"""
    entities: List[Dict]
    relationships: List[Dict]
    multi_hop_paths: List[Dict]


@dataclass
class NormalRAGResult:
    """NormalRAG检索结果"""
    sentences: List[Dict]


@dataclass
class TagRAGResult:
    """TagRAG检索结果"""
    text_blocks: List[Dict]

class LLMHelper:
    """LLM辅助类 - 用于时间提取、匹配和结果整理"""
    
    def __init__(self, qwen_client: QwenClient, logger, model: str, prompts_file: str):
        self.qwen_client = qwen_client
        self.logger = logger
        self.model = model
        
        # 加载提示词配置
        self.prompts = self._load_prompts(prompts_file)
    
    def _load_prompts(self, prompts_file: str) -> Dict[str, Any]:
        """加载提示词配置文件"""
        try:
            # 使用相对于configs的路径
            prompts_path = get_configs_root() / "prompt" / "router_retrieve" / prompts_file
            if prompts_path.exists():
                with open(prompts_path, 'r', encoding='utf-8') as f:
                    prompts = yaml.safe_load(f)
                    return prompts
            else:
                log_error(self.logger, f"提示词文件不存在: {prompts_file}，使用默认配置", "llm")
                return {}
        except Exception as e:
            log_error(self.logger, f"加载提示词配置失败: {str(e)}", "llm")
            return {}
    
    async def call_api(self, prompt: str, max_tokens: int = 2000, retry: int = 3) -> str:
        """调用API（使用系统QwenClient，支持重试，增加超时时间）"""
        import asyncio
        import aiohttp
        
        for attempt in range(retry):
            try:                
                # 由于QwenClient超时设置较短（60秒），对于大量数据的总结可能不够
                # 这里直接调用API，使用更长的超时时间（180秒）
                headers = {
                    "Authorization": f"Bearer {self.qwen_client.api_key}",
                    "Content-Type": "application/json"
                }
                data = {
                    "model": self.model,
                    "input": {"messages": [{"role": "user", "content": prompt}]},
                    "parameters": {"max_tokens": max_tokens}
                }
                
                # 使用更长的超时时间
                timeout = aiohttp.ClientTimeout(total=180, connect=10, sock_read=120)
                
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(
                        "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation",
                        json=data,
                        headers=headers
                    ) as resp:
                        if resp.status == 200:
                            response_data = await resp.json()
                            text = response_data.get('output', {}).get('text', '')
                            usage = response_data.get('usage', {})
                            
                            if text:
                                return text
                            else:
                                log_error(self.logger, "API返回200但text为空", "llm")
                                return ""
                        else:
                            # 非200状态码
                            error_body = await resp.text()
                            if attempt < retry - 1:
                                wait_time = (attempt + 1) * 5
                                log_error(self.logger, f"HTTP {resp.status}（尝试{attempt+1}/{retry}），{wait_time}秒后重试...", "llm")
                                log_error(self.logger, f"错误: {error_body[:300]}", "llm")
                                await asyncio.sleep(wait_time)
                                continue
                            else:
                                log_error(self.logger, f"HTTP {resp.status}，已重试{retry}次", "llm")
                                log_error(self.logger, f"错误详情: {error_body}", "llm")
                                return ""
                        
            except asyncio.TimeoutError:
                if attempt < retry - 1:
                    wait_time = (attempt + 1) * 5
                    log_error(self.logger, f"请求超时（尝试{attempt+1}/{retry}），{wait_time}秒后重试...", "llm")
                    log_error(self.logger, f"提示：当前提示词{len(prompt)}字符，如果持续超时请减少topk参数", "llm")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    log_error(self.logger, f"请求超时，已重试{retry}次（超时限制：180秒）", "llm")
                    log_error(self.logger, f"提示词长度: {len(prompt)}字符，可能过长导致处理超时", "llm")
                    log_error(self.logger, "建议：1.减少topk参数 2.使用--no-llm-summary跳过LLM整理", "llm")
                    return ""
                    
            except Exception as e:
                if attempt < retry - 1:
                    wait_time = (attempt + 1) * 5
                    log_error(self.logger, f"调用异常: {str(e)}，{wait_time}秒后重试...", "llm")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    log_error(self.logger, f"调用失败，已重试{retry}次: {str(e)}", "llm")
                    import traceback
                    log_error(self.logger, traceback.format_exc(), "llm")
                    return ""
        
        return ""
    
    async def summarize_results(self, query: str, search_results: Dict[str, Any], mode: str = "strict") -> str:
        """使用LLM整理检索结果为结构化资料
        
        Args:
            query: 用户查询
            search_results: 检索结果
            mode: 总结模式
                - strict: 严格模式，只根据检索到的资料回答
                - supplement: 补充模式，可以结合资料库进行合理补充
        """
        # 构建上下文
        context_parts = []
        
        # GraphRAG结果
        if 'graphrag' in search_results and search_results['graphrag']:
            graphrag = search_results['graphrag']
            entities = graphrag.get('entities', {})
            relationships = graphrag.get('relationships', {})
            
            # 核心实体（使用完整描述）
            core_entities = entities.get('core', []) if isinstance(entities, dict) else entities
            if core_entities:
                context_parts.append("【核心实体】")
                for i, e in enumerate(core_entities, 1):
                    desc = e.get('description', '')
                    desc_text = desc if isinstance(desc, str) else str(desc)
                    context_parts.append(f"\n实体{i}: {e['name']}（{e['type']}）")
                    context_parts.append(f"描述: {desc_text}")  # 完整描述
            
            # 扩展实体（使用完整描述，数量不限制，全部传递）
            extended_entities = entities.get('extended', []) if isinstance(entities, dict) else []
            if extended_entities:
                context_parts.append("\n【扩展实体】")
                for i, e in enumerate(extended_entities, 1):  # 使用所有扩展实体
                    desc = e.get('description', '')
                    desc_text = desc if isinstance(desc, str) else str(desc)
                    context_parts.append(f"\n扩展实体{i}: {e['name']}（{e['type']}）")
                    context_parts.append(f"描述: {desc_text}")  # 完整描述
            
            # Top3关系（使用完整描述）
            top3_relationships = relationships.get('top3', []) if isinstance(relationships, dict) else []
            if top3_relationships:
                context_parts.append("\n【关键关系】")
                for i, r in enumerate(top3_relationships, 1):
                    src = r.get('source_entity', {})
                    tgt = r.get('target_entity', {})
                    rel_desc = r.get('description', '')
                    rel_desc_text = rel_desc if isinstance(rel_desc, str) else str(rel_desc)
                    context_parts.append(f"\n关系{i}: {src.get('name', '')} → {tgt.get('name', '')}")
                    context_parts.append(f"关系描述: {rel_desc_text}")  # 完整描述
                    context_parts.append(f"源实体描述: {src.get('description', '')}")
                    context_parts.append(f"目标实体描述: {tgt.get('description', '')}")
        
        # NormalRAG结果（使用所有topk个句子）
        if 'normalrag' in search_results and search_results['normalrag']:
            sentences = search_results['normalrag'].get('sentences', [])
            if sentences:
                context_parts.append("\n【相关句子】")
                for i, s in enumerate(sentences, 1):  # 使用所有topk个句子
                    context_parts.append(f"\n句子{i}: {s['text']}")
                    context_parts.append(f"来源: {s.get('doc_name', '')} (文档ID:{s.get('doc_id', '')})")
        
        # TagRAG结果
        if 'tagrag' in search_results and search_results['tagrag']:
            text_blocks = search_results['tagrag'].get('text_blocks', [])
            if text_blocks:
                context_parts.append("\n【相关文本块】")
                for i, t in enumerate(text_blocks, 1):  # 使用所有topk个文本块
                    context_parts.append(f"\n文本块{i}:")
                    context_parts.append(f"标签: {t.get('text_tag', '')}")
                    context_parts.append(f"完整内容: {t.get('text', '')}")  # 使用完整text
                    context_parts.append(f"来源: {t.get('doc_name', '')} (文档ID:{t.get('doc_id', '')})")
        
        context = "\n".join(context_parts)
        
        # 根据模式选择不同的提示词
        if mode == "strict":
            prompt_template = self.prompts.get('result_summary_strict', {}).get('prompt', '')
            mode_text = "严格模式"
        else:  # supplement
            prompt_template = self.prompts.get('result_summary_supplement', {}).get('prompt', '')
            mode_text = "补充模式"
        
        if not prompt_template:
            log_error(self.logger, f"未找到{mode}模式的提示词配置", "llm")
            return ""
        
        prompt = prompt_template.format(query=query, context=context)
        
        summary = await self.call_api(prompt, max_tokens=3000)
        
        if summary:
            log_success(self.logger, f"资料整理完成：共 ({len(summary)}字)", "RouterRetrieve")
        else:
            log_error(self.logger, "资料整理失败", "RouterRetrieve")
        
        return summary
    
    async def extract_time_from_query(self, query: str) -> Dict[str, Any]:
        """从查询中提取时间标签"""
        # 从配置文件加载提示词
        prompt_template = self.prompts.get('time_extraction', {}).get('prompt', '')
        if not prompt_template:
            log_error(self.logger, "未找到time_extraction提示词配置", "llm")
            return {"has_time": False, "time_text": ""}
        
        prompt = prompt_template.format(query=query)
        response = await self.call_api(prompt)
        try:
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
            return {"has_time": False, "time_text": ""}
        except:
            return {"has_time": False, "time_text": ""}
    
    async def match_time_with_docs(self, query_time: str, doc_times: Dict[str, str]) -> List[str]:
        """匹配查询时间与文档时间范围"""
        doc_time_list = "\n".join([f"- ID={doc_id}: {time}" for doc_id, time in doc_times.items()])
        
        # 从配置文件加载提示词
        prompt_template = self.prompts.get('time_matching', {}).get('prompt', '')
        if not prompt_template:
            log_error(self.logger, "未找到time_matching提示词配置", "llm")
            return []
        
        prompt = prompt_template.format(query_time=query_time, doc_time_list=doc_time_list)
        response = await self.call_api(prompt)
        try:
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(0))
                matched = result.get("matched_doc_ids", [])
                matched = [str(doc_id).strip() for doc_id in matched]
                return matched
            return []
        except:
            return []
    
    async def expand_query(self, original_query: str) -> str:
        """查询扩展/重写：将用户查询扩展为更完整、更适合检索的查询
        
        Args:
            original_query: 原始用户查询
            
        Returns:
            str: 扩展后的查询文本
        """
        # 从配置文件加载提示词，如果没有则使用默认提示词
        prompt_template = self.prompts.get('query_expansion', {}).get('prompt', '')
        
        if not prompt_template:
            # 使用默认提示词
            prompt_template = """你是一个专业的查询扩展助手。请将用户查询扩展为更适合信息检索的查询文本。

要求：
1. 保持原查询的核心意图不变
2. 补充相关的同义词、近义词和相关概念
3. 将口语化表达转换为更规范的检索查询
4. 如果查询已经很完整，可以保持原样或稍作优化
5. 扩展后的查询应该更有利于在知识库中检索到相关信息

用户查询：{query}

请直接返回扩展后的查询文本，不要添加任何解释或说明。"""
        
        prompt = prompt_template.format(query=original_query)
        expanded_query = await self.call_api(prompt, max_tokens=500)
        
        if expanded_query:
            # 清理返回结果（去除可能的格式标记）
            expanded_query = expanded_query.strip()
            # 如果返回的是JSON格式，尝试提取
            try:
                json_match = re.search(r'\{.*\}', expanded_query, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group(0))
                    expanded_query = result.get('expanded_query', expanded_query)
            except:
                pass
            
            log_success(self.logger, f"查询扩展完成: {original_query[:50]}... -> {expanded_query[:50]}...", "QueryExpansion")
            return expanded_query
        else:
            log_error(self.logger, "查询扩展失败，使用原始查询", "QueryExpansion")
            return original_query

class EmbeddingGenerator:
    """向量生成器 - 使用text-embedding-v4"""
    
    def __init__(self, logger, model: str = "text-embedding-v4"):
        import aiohttp
        self.api_url = "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding"
        self.api_key = get_api_key()
        self.model = model
        self.logger = logger
        
        if not self.api_key:
            raise ValueError("API密钥未配置")
    
    async def generate_embedding(self, text: str) -> Optional[List[float]]:
        """生成单个向量"""
        import aiohttp
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": self.model,
            "input": {"texts": [text]}
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.api_url, json=data, headers=headers,
                                       timeout=aiohttp.ClientTimeout(total=60)) as resp:
                    result = await resp.json()
                    
                    if resp.status != 200:
                        return None
                    
                    embeddings = result.get("output", {}).get("embeddings", [])
                    if embeddings:
                        return embeddings[0].get("embedding", [])
                    return None
        except Exception as e:
            log_error(self.logger, f"向量生成失败: {str(e)}", "embedding")
            return None


class AdvancedRAGSearcher:
    """高级RAG检索系统 - 支持时间过滤、三种检索策略、多跳查询、多主题数据库"""
    
    def __init__(self, topic: str, logger, qwen_client: QwenClient, 
                 llm_model: str, embedding_model: str, prompts_file: str,
                 db_base_path: Optional[Path] = None):
        self.topic = topic
        self.logger = logger
        self.qwen_client = qwen_client
        
        # 根据主题确定数据库路径：{base}/{主题}数据库/vector_db
        if db_base_path is None:
            rag_base = Path(__file__).parent
            self.db_path = rag_base / f"{topic}数据库" / "vector_db"
        else:
            self.db_path = db_base_path / "vector_db"
        
        if not self.db_path.exists():
            log_error(self.logger, f"数据库不存在: {self.db_path}", "searcher")
            raise FileNotFoundError(f"数据库不存在: {self.db_path}")
        
        # 初始化辅助工具
        self.embedding_gen = EmbeddingGenerator(logger, embedding_model)
        self.llm_helper = LLMHelper(qwen_client, logger, llm_model, prompts_file)
        
        # 连接数据库
        self.db = lancedb.connect(str(self.db_path))
        
        # 缓存表
        self.tables = {}
        self._load_tables()
        
        # 加载文档时间映射
        self.doc_times = self._load_doc_times()
    
    def _load_tables(self) -> None:
        """加载所有表"""
        table_names = ["normalrag", "graphrag_entities", "graphrag_relationships", "graphrag_texts"]
        for name in table_names:
            try:
                self.tables[name] = self.db.open_table(name)
                count = self.tables[name].count_rows()
                log_success(self.logger, f"载入表: {name} ({count}条)", "RouterRetrieve")
            except Exception as e:
                log_error(self.logger, f"无法加载表 {name}: {str(e)}", "searcher")
    
    def _load_doc_times(self) -> Dict[str, str]:
        """加载文档时间映射"""
        doc_times = {}
        try:
            texts_table = self.tables.get("graphrag_texts")
            if texts_table:
                df = texts_table.to_pandas()
                for _, row in df.iterrows():
                    doc_id = row['doc_id']
                    time = row['time']
                    if doc_id not in doc_times:
                        doc_times[doc_id] = time
                
        except Exception as e:
            log_error(self.logger, f"无法加载文档时间: {str(e)}", "searcher")
        
        return doc_times
    
    async def _process_time_filter(self, query: str) -> TimeRange:
        """处理时间过滤"""
        
        # 1. 提取查询中的时间
        time_info = await self.llm_helper.extract_time_from_query(query)
        has_time = time_info.get("has_time", False)
        time_text = time_info.get("time_text", "")
        
        if not has_time:
            return TimeRange(has_time=False, time_text="", matched_docs=[])
        
        log_success(self.logger, f"查询包含时间范围: {time_text}", "RouterRetrieve")
        
        # 2. 与文档时间进行匹配
        if not self.doc_times:
            log_error(self.logger, "无文档时间信息，将进行全库检索", "time")
            return TimeRange(has_time=False, time_text=time_text, matched_docs=[])
        
        matched_doc_ids = await self.llm_helper.match_time_with_docs(time_text, self.doc_times)
        
        if not matched_doc_ids:
            return TimeRange(has_time=False, time_text=time_text, matched_docs=[])
        
        log_success(self.logger, f"文档匹配完成: {', '.join(matched_doc_ids)}", "RouterRetrieve")
        
        return TimeRange(has_time=True, time_text=time_text, matched_docs=matched_doc_ids)
    
    async def _graphrag_search(self, query_vec: List[float], time_range: TimeRange, topk: int) -> GraphRAGResult:
        """
        GraphRAG检索：联合实体向量+描述向量，扩展核心实体的所有关系
        """
        
        entity_table = self.tables.get("graphrag_entities")
        rel_table = self.tables.get("graphrag_relationships")
        texts_table = self.tables.get("graphrag_texts")
        
        if not entity_table or not rel_table:
            log_error(self.logger, "表不存在", "graphrag")
            return GraphRAGResult(entities=[], relationships=[], multi_hop_paths=[])
        
        # 加载完整的实体和关系数据
        entities_df = entity_table.to_pandas()
        relations_df = rel_table.to_pandas()
        
        # 1. 联合检索：实体名称向量 + 实体描述向量（支持时间过滤）
        try:
            # 如果有时间过滤，先筛选全库样本
            if time_range.has_time and time_range.matched_docs:
                # 1. 从全库中筛选符合时间范围的实体
                time_filtered_entity_ids = []
                for _, entity_row in entities_df.iterrows():
                    doc_ids = json.loads(entity_row.get('doc_ids', '[]'))
                    if any(doc_id in time_range.matched_docs for doc_id in doc_ids):
                        time_filtered_entity_ids.append(entity_row['entity_id'])
                
                total_entities = len(entities_df)
                filtered_count = len(time_filtered_entity_ids)
                
                
                # 如果没有符合时间的实体，返回空结果
                if not time_filtered_entity_ids:
                    log_error(self.logger, "  未找到符合时间范围的实体", "graphrag")
                    core_entity_ids = []
                else:
                    # 2. 在筛选后的样本上进行向量检索
                    # 获取全库检索结果
                    name_results = entity_table.search(query_vec, vector_column_name="entity_name_vec").limit(total_entities).to_list()
                    desc_results = entity_table.search(query_vec, vector_column_name="description_vec").limit(total_entities).to_list()
                    
                    # 只保留符合时间范围的结果
                    name_results = [e for e in name_results if e['entity_id'] in time_filtered_entity_ids]
                    desc_results = [e for e in desc_results if e['entity_id'] in time_filtered_entity_ids]
                                        
                    # 合并结果并综合排序（保存详细的距离信息）
                    entity_scores = {}  # entity_id -> {total_score, name_dist, desc_dist}
                    for e in name_results:
                        eid = e['entity_id']
                        if eid not in entity_scores:
                            entity_scores[eid] = {'name_dist': None, 'desc_dist': None}
                        entity_scores[eid]['name_dist'] = e.get('_distance', 1.0)
                    
                    for e in desc_results:
                        eid = e['entity_id']
                        if eid not in entity_scores:
                            entity_scores[eid] = {'name_dist': None, 'desc_dist': None}
                        entity_scores[eid]['desc_dist'] = e.get('_distance', 1.0)
                    
                    # 计算综合分数（取两者平均，如果只有一个就用一个）
                    for eid in entity_scores:
                        name_d = entity_scores[eid]['name_dist']
                        desc_d = entity_scores[eid]['desc_dist']
                        if name_d is not None and desc_d is not None:
                            entity_scores[eid]['total'] = (name_d + desc_d) / 2
                        elif name_d is not None:
                            entity_scores[eid]['total'] = name_d
                        else:
                            entity_scores[eid]['total'] = desc_d
                    
                    # 按综合分数排序（距离越小越相似）
                    sorted_items = sorted(entity_scores.items(), key=lambda x: x[1]['total'])
                    core_entity_ids = [item[0] for item in sorted_items[:topk]]
                    
                    # 输出详细日志
                    for i, (eid, scores) in enumerate(sorted_items[:topk], 1):
                        entity_name = entities_df[entities_df['entity_id'] == eid].iloc[0]['entity_name']
            else:
                # 无时间过滤，正常检索
                name_results = entity_table.search(query_vec, vector_column_name="entity_name_vec").limit(topk * 2).to_list()
                desc_results = entity_table.search(query_vec, vector_column_name="description_vec").limit(topk * 2).to_list()
                
                # 合并结果并综合排序（保存详细的距离信息）
                entity_scores = {}  # entity_id -> {total_score, name_dist, desc_dist}
                for e in name_results:
                    eid = e['entity_id']
                    if eid not in entity_scores:
                        entity_scores[eid] = {'name_dist': None, 'desc_dist': None}
                    entity_scores[eid]['name_dist'] = e.get('_distance', 1.0)
                
                for e in desc_results:
                    eid = e['entity_id']
                    if eid not in entity_scores:
                        entity_scores[eid] = {'name_dist': None, 'desc_dist': None}
                    entity_scores[eid]['desc_dist'] = e.get('_distance', 1.0)
                
                # 计算综合分数（取两者平均，如果只有一个就用一个）
                for eid in entity_scores:
                    name_d = entity_scores[eid]['name_dist']
                    desc_d = entity_scores[eid]['desc_dist']
                    if name_d is not None and desc_d is not None:
                        entity_scores[eid]['total'] = (name_d + desc_d) / 2
                    elif name_d is not None:
                        entity_scores[eid]['total'] = name_d
                    else:
                        entity_scores[eid]['total'] = desc_d
                
                # 按综合分数排序（距离越小越相似）
                sorted_items = sorted(entity_scores.items(), key=lambda x: x[1]['total'])
                core_entity_ids = [item[0] for item in sorted_items[:topk]]
                
                # 输出详细日志
                for i, (eid, scores) in enumerate(sorted_items[:topk], 1):
                    entity_name = entities_df[entities_df['entity_id'] == eid].iloc[0]['entity_name']
            
        except Exception as e:
            log_error(self.logger, f"[entity_search] 失败: {str(e)}", "graphrag")
            core_entity_ids = []
        
        # 2. 扩展核心实体：查找所有相关实体和关系
        expanded_entities = {}  # entity_id -> entity_info
        expanded_relationships = []  # list of relationship_info
        
        try:
            for core_id in core_entity_ids:
                # 添加核心实体
                core_entity = entities_df[entities_df['entity_id'] == core_id].iloc[0]
                expanded_entities[core_id] = core_entity
                
                # 查找所有相关关系
                related_rels = relations_df[
                    (relations_df['source'] == core_id) | 
                    (relations_df['target'] == core_id)
                ]
                
                for _, rel in related_rels.iterrows():
                    src_id = rel['source']
                    tgt_id = rel['target']
                    
                    # 添加关系
                    expanded_relationships.append(rel)
                    
                    # 添加相关实体
                    if src_id not in expanded_entities:
                        src_entity = entities_df[entities_df['entity_id'] == src_id]
                        if not src_entity.empty:
                            expanded_entities[src_id] = src_entity.iloc[0]
                    
                    if tgt_id not in expanded_entities:
                        tgt_entity = entities_df[entities_df['entity_id'] == tgt_id]
                        if not tgt_entity.empty:
                            expanded_entities[tgt_id] = tgt_entity.iloc[0]
            
        except Exception as e:
            log_error(self.logger, f"[entity_expand] 失败: {str(e)}", "graphrag")
        
        # 3. 检索关系Top3，并获取对应的两个实体
        top_relations = []
        try:
            # 如果有时间过滤，先筛选全库样本
            if time_range.has_time and time_range.matched_docs:
                # 1. 从全库中筛选符合时间范围的关系
                time_filtered_rel_ids = []
                for _, rel_row in relations_df.iterrows():
                    try:
                        doc_ids = json.loads(rel_row.get('doc_ids', '[]'))
                        if any(doc_id in time_range.matched_docs for doc_id in doc_ids):
                            time_filtered_rel_ids.append(rel_row['relationship_id'])
                    except:
                        continue
                
                total_relations = len(relations_df)
                filtered_count = len(time_filtered_rel_ids)
                
                
                if filtered_count == 0:
                    log_error(self.logger, "  未找到符合时间范围的关系", "graphrag")
                    rel_results = []
                else:
                    # 2. 在筛选后的样本上进行向量检索
                    # 获取全库检索结果
                    all_rel_results = rel_table.search(query_vec, vector_column_name="description_vec").limit(total_relations).to_list()
                    
                    # 只保留符合时间范围的结果
                    rel_results = [r for r in all_rel_results if r['relationship_id'] in time_filtered_rel_ids]
                    
            else:
                # 无时间过滤，正常检索
                rel_results = rel_table.search(query_vec, vector_column_name="description_vec").limit(10).to_list()
            
            # 按距离重新排序（确保距离小的在前面）
            rel_results = sorted(rel_results, key=lambda x: x.get('_distance', 1.0))
            
            # 获取前3个关系及对应的两个实体
            for i, r in enumerate(rel_results[:3], 1):
                src_id = r['source']
                tgt_id = r['target']
                
                # 获取源实体和目标实体
                src_entity = entities_df[entities_df['entity_id'] == src_id]
                tgt_entity = entities_df[entities_df['entity_id'] == tgt_id]
                
                if not src_entity.empty and not tgt_entity.empty:
                    src_name = src_entity.iloc[0]['entity_name']
                    tgt_name = tgt_entity.iloc[0]['entity_name']
                    distance = r.get('_distance', 1.0)
                    
                    top_relations.append({
                        'relation': r,
                        'source_entity': src_entity.iloc[0],
                        'target_entity': tgt_entity.iloc[0]
                    })

        except Exception as e:
            log_error(self.logger, f"[relation_search] 失败: {str(e)}", "graphrag")
        
        # 4. 整理实体和关系的详细信息
        try:
            # 统计信息
            total_core_entities = len(core_entity_ids)
            total_expanded_entities = len([e for e in expanded_entities.keys() if e not in core_entity_ids])
            total_relations = len(expanded_relationships)
            
            
            # 输出核心实体的详细信息
            for i, eid in enumerate(core_entity_ids[:5], 1):
                if eid in expanded_entities:
                    e = expanded_entities[eid]
                    desc = e['description']
                    desc_text = desc if isinstance(desc, str) else str(desc)
            
            # 输出关键关系的详细信息
            for i, rel in enumerate(expanded_relationships[:5], 1):
                src_id = rel['source']
                tgt_id = rel['target']
                if src_id in expanded_entities and tgt_id in expanded_entities:
                    src_name = expanded_entities[src_id]['entity_name']
                    tgt_name = expanded_entities[tgt_id]['entity_name']
                    rel_desc = rel['description']
                    rel_desc_text = rel_desc if isinstance(rel_desc, str) else str(rel_desc)
        except Exception as e:
            log_error(self.logger, f"[info_summary] 失败: {str(e)}", "graphrag")
        
        # 格式化结果
        entities = []
        for entity_id in core_entity_ids:
            if entity_id in expanded_entities:
                e = expanded_entities[entity_id]
                entities.append({
                    "entity_id": e['entity_id'],
                    "name": e['entity_name'],
                    "type": e['type'],
                    "description": e['description'],
                    "doc_ids": json.loads(e.get('doc_ids', '[]')),
                    "text_ids": json.loads(e.get('text_ids', '[]'))
                })
        
        # 扩展的实体（非核心）
        extended_entities = []
        for entity_id, e in expanded_entities.items():
            if entity_id not in core_entity_ids:
                extended_entities.append({
                    "entity_id": e['entity_id'],
                    "name": e['entity_name'],
                    "type": e['type'],
                    "description": e['description'],
                    "doc_ids": json.loads(e.get('doc_ids', '[]')),
                    "text_ids": json.loads(e.get('text_ids', '[]'))
                })
        
        # 关系
        relationships = []
        for r in expanded_relationships:
            relationships.append({
                "relationship_id": r['relationship_id'],
                "source": r['source'],
                "target": r['target'],
                "description": r['description'],
                "doc_ids": json.loads(r.get('doc_ids', '[]')),
                "text_ids": json.loads(r.get('text_ids', '[]'))
            })
        
        # Top3关系（含对应实体）
        top3_relations = []
        for item in top_relations:
            r = item['relation']
            src = item['source_entity']
            tgt = item['target_entity']
            top3_relations.append({
                "relationship_id": r['relationship_id'],
                "source_entity": {
                    "entity_id": src['entity_id'],
                    "name": src['entity_name'],
                    "type": src['type'],
                    "description": src['description']
                },
                "target_entity": {
                    "entity_id": tgt['entity_id'],
                    "name": tgt['entity_name'],
                    "type": tgt['type'],
                    "description": tgt['description']
                },
                "description": r['description'],
                "doc_ids": json.loads(r.get('doc_ids', '[]')),
                "score": round(r.get('_distance', 0.0), 4)
            })
        
        # 构建知识图谱摘要（用于LLM整理）
        graph_summary = {
            "core_entities_count": len(entities),
            "extended_entities_count": len(extended_entities),
            "total_relationships": len(relationships),
            "top3_relationships": len(top3_relations)
        }
        
        # 打印召回统计
        log_success(self.logger, f"[GraphRAG]召回: 实体数-{len(entities) + len(extended_entities)} | 关系数-{len(relationships)}", "RouterRetrieve")
        
        return GraphRAGResult(
            entities={
                "core": entities,
                "extended": extended_entities
            },
            relationships={
                "all": relationships,
                "top3": top3_relations
            },
            multi_hop_paths=graph_summary
        )
    
    async def _normalrag_search(self, query_vec: List[float], time_range: TimeRange, 
                                topk: int) -> NormalRAGResult:
        """NormalRAG检索：句子向量检索，获取前5条"""
        
        sentence_table = self.tables.get("normalrag")
        if not sentence_table:
            log_error(self.logger, "表不存在", "normalrag")
            return NormalRAGResult(sentences=[])
        
        try:
            # 如果有时间过滤，先筛选全库样本
            if time_range.has_time and time_range.matched_docs:
                # 1. 从全库中筛选符合时间范围的句子
                sentences_df = sentence_table.to_pandas()
                time_filtered_sentences = sentences_df[
                    sentences_df['doc_id'].isin(time_range.matched_docs)
                ]
                total_sentences = len(sentences_df)
                filtered_count = len(time_filtered_sentences)
                                
                if filtered_count == 0:
                    log_error(self.logger, "  未找到符合时间范围的句子", "normalrag")
                    return NormalRAGResult(sentences=[])
                
                # 2. 在筛选后的样本上进行向量检索
                # 由于LanceDB不支持预过滤，需要获取所有结果然后手动筛选
                all_results = sentence_table.search(query_vec, vector_column_name="sentence_vec").limit(total_sentences).to_list()
                
                # 只保留符合时间范围的
                results = [s for s in all_results if s.get('doc_id', '') in time_range.matched_docs]
                
                # 按距离排序
                results = sorted(results, key=lambda x: x.get('_distance', 1.0))
                
            else:
                # 无时间过滤，正常检索
                results = sentence_table.search(query_vec, vector_column_name="sentence_vec").limit(topk * 2).to_list()
                results = sorted(results, key=lambda x: x.get('_distance', 1.0))
            
            # 获取前topk条
            results = results[:topk]
            
            sentences = []
            for i, s in enumerate(results, 1):
                distance = s.get('_distance', 0.0)
                sentences.append({
                    "sentence_id": s.get('sentence_id', ''),
                    "text": s['sentence_text'],
                    "doc_id": s['doc_id'],
                    "doc_name": s.get('doc_name', ''),
                    "score": round(distance, 4)
                })
            
            # 打印召回统计
            log_success(self.logger, f"[NormalRAG]召回: 句子数-{len(sentences)}", "RouterRetrieve")
            
            return NormalRAGResult(sentences=sentences)
            
        except Exception as e:
            log_error(self.logger, f"失败: {str(e)}", "normalrag")
            return NormalRAGResult(sentences=[])
    
    async def _tagrag_search(self, query_vec: List[float], time_range: TimeRange, 
                            topk: int) -> TagRAGResult:
        """TagRAG检索：文本标签向量检索，获取前5条"""
        
        texts_table = self.tables.get("graphrag_texts")
        if not texts_table:
            log_error(self.logger, "表不存在", "tagrag")
            return TagRAGResult(text_blocks=[])
        
        try:
            # 如果有时间过滤，先筛选全库样本
            if time_range.has_time and time_range.matched_docs:
                # 1. 从全库中筛选符合时间范围的文本块
                texts_df = texts_table.to_pandas()
                time_filtered_texts = texts_df[
                    texts_df['doc_id'].isin(time_range.matched_docs)
                ]
                total_texts = len(texts_df)
                filtered_count = len(time_filtered_texts)
                                
                if filtered_count == 0:
                    log_error(self.logger, "  未找到符合时间范围的文本块", "tagrag")
                    return TagRAGResult(text_blocks=[])
                
                # 2. 在筛选后的样本上进行向量检索
                # 由于LanceDB不支持预过滤，需要获取所有结果然后手动筛选
                all_results = texts_table.search(query_vec, vector_column_name="text_tag_vec").limit(total_texts).to_list()
                
                # 只保留符合时间范围的
                results = [t for t in all_results if t.get('doc_id', '') in time_range.matched_docs]
                
                # 按距离排序
                results = sorted(results, key=lambda x: x.get('_distance', 1.0))
                
            else:
                # 无时间过滤，正常检索
                results = texts_table.search(query_vec, vector_column_name="text_tag_vec").limit(topk * 2).to_list()
                results = sorted(results, key=lambda x: x.get('_distance', 1.0))
            
            # 获取前topk个
            results = results[:topk]
            
            text_blocks = []
            for i, t in enumerate(results, 1):
                distance = t.get('_distance', 0.0)
                text_blocks.append({
                    "text_id": t.get('text_id', ''),
                    "text": t['text'],
                    "text_tag": t.get('text_tag', ''),
                    "doc_id": t['doc_id'],
                    "doc_name": t.get('doc_name', ''),
                    "score": round(distance, 4)
                })
            
            # 打印召回统计
            log_success(self.logger, f"[TagRAG]召回: 文本块数-{len(text_blocks)}", "RouterRetrieve")
            
            return TagRAGResult(text_blocks=text_blocks)
            
        except Exception as e:
            log_error(self.logger, f"失败: {str(e)}", "tagrag")
            return TagRAGResult(text_blocks=[])
    
    async def search(self, params: SearchParams) -> Dict[str, Any]:
        """主检索函数"""
        
        # 步骤0: 查询扩展/重写（提升检索准确率，可选）
        original_query = params.query_text
        if params.enable_query_expansion:
            expanded_query = await self.llm_helper.expand_query(original_query)
            # 使用扩展后的查询进行后续检索
            # 但保留原始查询用于结果展示和时间过滤（时间过滤使用原始查询更准确）
            effective_query = expanded_query if expanded_query != original_query else original_query
            if effective_query != original_query:
                log_success(self.logger, f"查询已扩展: {original_query[:50]}... -> {effective_query[:50]}...", "RouterRetrieve")
        else:
            effective_query = original_query
            log_success(self.logger, f"查询扩展已禁用，使用原始查询", "RouterRetrieve")
        
        # 步骤1: 时间过滤（使用原始查询，因为时间信息提取更准确）
        time_range = await self._process_time_filter(original_query)
        
        # 步骤2: 生成查询向量（使用扩展后的查询）
        query_vec = await self.embedding_gen.generate_embedding(effective_query)
        if not query_vec:
            log_error(self.logger, "查询向量生成失败", "search")
            return {"error": "查询向量生成失败"}
                
        # 步骤3: 根据模式执行检索
        results = {
            "query_topic": params.query_topic,
            "query_text": original_query,  # 保留原始查询用于展示
            "expanded_query": effective_query if effective_query != original_query else None,  # 扩展后的查询
            "search_mode": params.search_mode,
            "time_filter": {
                "has_time": time_range.has_time,
                "time_text": time_range.time_text,
                "matched_docs": time_range.matched_docs
            }
        }
        
        if params.search_mode == "mixed":
            
            graphrag_result, normalrag_result, tagrag_result = await asyncio.gather(
                self._graphrag_search(query_vec, time_range, params.topk_graphrag),
                self._normalrag_search(query_vec, time_range, params.topk_normalrag),
                self._tagrag_search(query_vec, time_range, params.topk_tagrag)
            )
            
            results["graphrag"] = {
                "entities": graphrag_result.entities,
                "relationships": graphrag_result.relationships,
                "summary": graphrag_result.multi_hop_paths
            }
            results["normalrag"] = {
                "sentences": normalrag_result.sentences
            }
            results["tagrag"] = {
                "text_blocks": tagrag_result.text_blocks
            }
        
        elif params.search_mode == "graphrag":
            graphrag_result = await self._graphrag_search(
                query_vec, time_range, params.topk_graphrag
            )
            results["graphrag"] = {
                "entities": graphrag_result.entities,
                "relationships": graphrag_result.relationships,
                "summary": graphrag_result.multi_hop_paths
            }
        
        elif params.search_mode == "normalrag":
            normalrag_result = await self._normalrag_search(query_vec, time_range, params.topk_normalrag)
            results["normalrag"] = {
                "sentences": normalrag_result.sentences
            }
        
        elif params.search_mode == "tagrag":
            tagrag_result = await self._tagrag_search(query_vec, time_range, params.topk_tagrag)
            results["tagrag"] = {
                "text_blocks": tagrag_result.text_blocks
            }
                
        # 步骤4: 使用LLM整理检索结果（可选）
        if params.enable_llm_summary:
            # 使用原始查询进行结果整理，因为用户更关心原始查询的答案
            summary = await self.llm_helper.summarize_results(original_query, results, params.llm_summary_mode)
            
            if summary:
                results["llm_summary"] = summary
        
        # 根据return_format参数返回不同格式的结果
        if params.return_format == "llm_only":
            # 仅返回LLM整理结果
            if "llm_summary" in results:
                return {
                    "query_topic": params.query_topic,
                    "query_text": original_query,
                    "expanded_query": results.get("expanded_query"),
                    "llm_summary": results["llm_summary"]
                }
            else:
                log_error(self.logger, "return_format=llm_only但未启用LLM整理，返回空结果", "return")
                return {
                    "query_topic": params.query_topic,
                    "query_text": original_query,
                    "expanded_query": results.get("expanded_query"),
                    "llm_summary": "未启用LLM整理，无法返回LLM结果"
                }
        
        elif params.return_format == "index_only":
            # 仅返回索引检索结果（移除llm_summary）
            filtered_results = {k: v for k, v in results.items() if k != "llm_summary"}
            filtered_results["return_format"] = "index_only"
            return filtered_results
        
        else:  # both (默认)
            # 返回完整结果（索引结果 + LLM整理）
            results["return_format"] = "both"
        return results
    

def router_retrieve(
    topic: str,
    query: str,
    mode: str = "mixed",
    topk_graphrag: int = 3,
    topk_normalrag: int = 5,
    topk_tagrag: int = 5,
    enable_query_expansion: bool = True,
    enable_llm_summary: bool = True,
    llm_summary_mode: str = "strict",
    return_format: str = "both",
    db_base_path: Optional[Path] = None
) -> Dict[str, Any]:
    """
    RAG检索包装函数，返回JSON格式的检索结果
    
    Args:
        topic: 主题名称
        query: 查询文本
        mode: 检索模式 (mixed/graphrag/normalrag/tagrag)
        topk_graphrag: GraphRAG返回的核心实体数量
        topk_normalrag: NormalRAG返回的句子数量
        topk_tagrag: TagRAG返回的文本块数量
        enable_query_expansion: 是否启用查询扩展/重写（默认True）
        enable_llm_summary: 是否启用LLM整理结果
        llm_summary_mode: LLM整理模式 (strict/supplement)
        return_format: 返回格式 (both/llm_only/index_only)
    """
    try:
        # 引入logger（使用主题和当前日期）
        current_date = datetime.now().strftime("%Y-%m-%d")
        logger = setup_logger(f"RagRouter_{topic}", current_date)

        log_module_start(logger, "RouterRetrieve", f"正在进行Router检索 - 主题: {topic}")

        # 加载LLM配置
        llm_config_path = get_configs_root() / "llm.yaml"
        with open(llm_config_path, 'r', encoding='utf-8') as f:
            llm_config = yaml.safe_load(f)
        
        # 获取router_retrieve配置
        router_config = llm_config.get('router_retrieve_llm', {})
        embedding_config = llm_config.get('embedding_llm', {})
        
        llm_model = router_config.get('model', 'qwen-plus')
        embedding_model = embedding_config.get('model', 'text-embedding-v4')
        
        # 创建QwenClient
        qwen_client = QwenClient()
        
        # 提示词文件由topic自动确定
        prompts_file = f"{topic}.yaml"
        
        # 创建检索器
        searcher = AdvancedRAGSearcher(
            topic=topic,
            logger=logger,
            qwen_client=qwen_client,
            llm_model=llm_model,
            embedding_model=embedding_model,
            prompts_file=prompts_file,
            db_base_path=db_base_path
        )
        
        # 设置检索参数
        params = SearchParams(
            query_topic=topic,
            query_text=query,
            search_mode=mode,
            topk_graphrag=topk_graphrag,
            topk_normalrag=topk_normalrag,
            topk_tagrag=topk_tagrag,
            enable_query_expansion=enable_query_expansion,
            enable_llm_summary=enable_llm_summary,
            llm_summary_mode=llm_summary_mode,
            return_format=return_format
        )
        
        
        # 执行检索（需要使用asyncio运行）
        results = asyncio.run(searcher.search(params))
        
        return results
        
    except Exception as e:
        import traceback
        return {
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc()
        }


def retrieve_documents(
    query: str,
    topic: str,
    top_k: int = 10,
    threshold: float = 0.0,
    mode: str = "normalrag",
    db_base_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """
    Adapter for API usage. Normalizes RouterRAG results into a flat list with
    `text` and `score` for the frontend retrieval views.
    """
    payload = router_retrieve(
        topic=topic,
        query=query,
        mode=mode,
        topk_normalrag=top_k,
        topk_tagrag=top_k,
        enable_llm_summary=False,
        return_format="index_only",
        db_base_path=db_base_path,
    )

    if not isinstance(payload, dict):
        return []

    results: List[Dict[str, Any]] = []

    if mode == "tagrag":
        items = payload.get("tagrag", {}).get("text_blocks", [])
        for item in items:
            distance = float(item.get("score", 1.0))
            similarity = max(0.0, 1.0 - distance)
            if similarity < threshold:
                continue
            results.append({
                "id": item.get("text_id") or item.get("doc_id"),
                "text": item.get("text", ""),
                "score": round(similarity, 4),
                "metadata": {
                    "doc_id": item.get("doc_id"),
                    "doc_name": item.get("doc_name"),
                    "text_tag": item.get("text_tag"),
                },
            })
        return results

    # Default: normalrag
    items = payload.get("normalrag", {}).get("sentences", [])
    for item in items:
        distance = float(item.get("score", 1.0))
        similarity = max(0.0, 1.0 - distance)
        if similarity < threshold:
            continue
        results.append({
            "id": item.get("sentence_id") or item.get("doc_id"),
            "text": item.get("text", ""),
            "score": round(similarity, 4),
            "metadata": {
                "doc_id": item.get("doc_id"),
                "doc_name": item.get("doc_name"),
            },
        })

    return results
