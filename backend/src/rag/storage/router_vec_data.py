"""
向量化处理系统 - 完整一体化程序
功能：文本处理、映射管理、两阶段实体关系提取、向量生成、LanceDB存储
特性：全局唯一ID（纯数字）、两阶段提取、无需ID映射、数据一致性保证
"""
import asyncio
import aiohttp
import json
import re
import yaml
import lancedb
import traceback
import pyarrow as pa
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from collections import defaultdict
from colorama import Fore, Style, init
from ...setting.paths import get_project_root, get_configs_root
from ...setting.env_loader import get_api_key
from ...setting.settings import settings
from ...logging.logging import setup_logger, log_success, log_error, log_module_start

init(autoreset=True)

class TokenCounter:
    """Token计数器 - 统计API调用的Token使用量"""
    
    def __init__(self, logger=None):
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.call_count = 0
        self.logger = logger
    
    def add_tokens(self, input_tokens: int, output_tokens: int) -> None:
        """添加Token统计"""
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.call_count += 1
    
    def print_summary(self) -> None:
        """打印Token使用统计"""
        if self.call_count == 0:
            return
        
        if self.logger:
            log_success(
                self.logger,
                f"Token统计：调用次数-{self.call_count:,} | 输入-{self.total_input_tokens:,} | 输出-{self.total_output_tokens:,} | 总计-{self.total_input_tokens + self.total_output_tokens:,}",
                "RouterVectorize"
            )

class TextProcessor:
    """文本处理器 - 清洗、合并、切割、建立映射"""
    
    def __init__(self, base_path: Path, logger=None):
        self.base_path = base_path
        self.normal_db = base_path / "normal_db"
        self.text_db = self.normal_db / "text_db"
        self.doc_db = self.normal_db / "doc_db"
        self.sentence_db = self.normal_db / "sentence_db"
        self.entities_db = self.normal_db / "entities_db"
        self.relationships_db = self.normal_db / "relationships_db"
        self.log_db = self.normal_db / "log_db"
        
        self.log_db.mkdir(parents=True, exist_ok=True)
        
        self.doc_mapping = {}
        self.text_mapping = {}
        self.all_mapping = {}  # 统一的映射结构
        
        self.processed_docs = set()  # 已处理的文档ID集合
        self.new_doc_ids = []  # 本次新增的文档ID
        
        self.logger = logger
    
    def clean_text(self, text: str) -> str:
        """清洗文本：去除多余空格和换行"""
        cleaned = re.sub(r'\s+', '', text).strip()
        return cleaned
    
    def extract_doc_name_from_file(self, filename: str) -> Tuple[str, int]:
        """从文件名提取文档名和编号"""
        # 格式1: doc#_文档名_text#
        match = re.match(r'doc\d+_(.+)_text(\d+)$', filename)
        if match:
            return match.group(1), int(match.group(2))
        
        # 格式2: 原文档名_数字
        match = re.match(r'(.+)_(\d+)$', filename)
        if match:
            return match.group(1), int(match.group(2))
        
        return filename, 1
    
    def _split_sentences(self) -> None:
        """切割句子并建立映射（增量：只切割新文档）"""
        # 读取已有句子，恢复sentence_id_counter
        sentence_id_counter = 1
        all_sentences = []
        
        sentence_file = self.sentence_db / "sentences.json"
        if sentence_file.exists():
            try:
                with open(sentence_file, 'r', encoding='utf-8') as f:
                    all_sentences = json.load(f)
                if all_sentences:
                    sentence_id_counter = max(int(s['sentence_id']) for s in all_sentences) + 1
            except Exception as e:
                log_error(self.logger, f"读取句子文件失败: {e}", "RouterVectorize")
        
        # 只切割新文档
        new_sentences = []
        for doc_file in sorted(self.doc_db.glob("doc*.txt")):
            match = re.match(r'doc(\d+)_(.+)$', doc_file.stem)
            if not match:
                continue
            
            doc_id, doc_name = match.group(1), match.group(2)
            
            # 只处理新文档
            if doc_id not in self.new_doc_ids:
                continue
            
            with open(doc_file, 'r', encoding='utf-8') as f:
                doc_text = f.read()
            
            sentences = re.split(r'[。！？；]', doc_text)
            sentences = [s.strip() for s in sentences if s.strip()]
            
            if doc_id not in self.doc_mapping:
                self.doc_mapping[doc_id] = {'sentence_ids': []}
            
            for sentence_text in sentences:
                sentence_id = str(sentence_id_counter)
                
                new_sentences.append({
                    "sentence_id": sentence_id,
                    "sentence_text": sentence_text,
                    "doc_id": doc_id,
                    "doc_name": doc_name
                })
                
                if 'sentence_ids' not in self.doc_mapping[doc_id]:
                    self.doc_mapping[doc_id]['sentence_ids'] = []
                self.doc_mapping[doc_id]['sentence_ids'].append(sentence_id)
                sentence_id_counter += 1
        
        # 追加到已有句子
        all_sentences.extend(new_sentences)
        
        with open(self.sentence_db / "sentences.json", 'w', encoding='utf-8') as f:
            json.dump(all_sentences, f, ensure_ascii=False, indent=2)
            
    def _save_mappings(self) -> None:
        """保存统一的映射到log_db（单个JSON文件，支持增量更新）"""
        # 如果all_mapping不存在，则初始化
        if not hasattr(self, 'all_mapping') or not self.all_mapping:
            self.all_mapping = {
                "documents": {},
                "texts": {},
                "entities": {
                    "last_id": 0,
                    "count": 0
                },
                "relationships": {
                    "last_id": 0,
                    "count": 0
                },
                "processed_docs": []
            }
        
        # 更新文档映射（追加新文档）
        for doc_id, doc_info in self.doc_mapping.items():
            self.all_mapping["documents"][doc_id] = {
                "doc_name": doc_info['name'],
                "text_ids": doc_info['text_ids'],
                "text_count": len(doc_info['text_ids'])
            }
        
        # 更新文本映射（追加新文本）
        for text_id, text_info in self.text_mapping.items():
            self.all_mapping["texts"][text_id] = {
                "doc_id": text_info['doc_id'],
                "doc_name": text_info['doc_name'],
                "original_file": text_info['original_file'],
                "text_num_in_doc": text_info['text_num_in_doc'],
                "text_content": text_info.get('text_content', '')  # 添加文本内容
            }
        
        # 保存到单个JSON文件
        mapping_file = self.log_db / "data_mapping.json"
        with open(mapping_file, 'w', encoding='utf-8') as f:
            json.dump(self.all_mapping, f, ensure_ascii=False, indent=2)

    def process_all(self) -> None:
        """执行完整的文本处理流程（增量模式：只处理新文档）"""
        
        # 读取已有映射，获取已处理的文档和计数器
        mapping_file = self.log_db / "data_mapping.json"
        doc_id_counter = 1
        text_id_counter = 1
        
        if mapping_file.exists():
            try:
                with open(mapping_file, 'r', encoding='utf-8') as f:
                    existing_mapping = json.load(f)
                
                # 恢复已处理的文档
                self.processed_docs = set(existing_mapping.get('processed_docs', []))
                
                # 恢复映射
                self.all_mapping = existing_mapping
                self.doc_mapping = {k: {'name': v['doc_name'], 'texts_name': [], 'text_ids': v['text_ids'], 'sentence_ids': []} 
                                   for k, v in existing_mapping.get('documents', {}).items()}
                self.text_mapping = existing_mapping.get('texts', {})
                
                # 恢复计数器
                if self.doc_mapping:
                    doc_id_counter = max(int(k) for k in self.doc_mapping.keys()) + 1
                if self.text_mapping:
                    text_id_counter = max(int(k) for k in self.text_mapping.keys()) + 1

            except Exception as e:
                if self.logger:
                    log_error(self.logger, f"读取映射文件失败: {e}", "RouterVectorize")
        
        text_files = sorted(self.text_db.glob("*.txt"))
        if not text_files:
            log_error(self.logger, "没有文本文件", "RouterVectorize")
            return
                
        # 按文档名分组
        doc_groups = defaultdict(list)
        for text_file in text_files:
            doc_name, text_num = self.extract_doc_name_from_file(text_file.stem)
            doc_groups[doc_name].append((text_num, text_file))
        
        # 过滤出新文档
        new_doc_groups = {}
        for doc_name in doc_groups.keys():
            # 检查该文档是否已处理（通过文档名匹配）
            already_processed = False
            for processed_id in self.processed_docs:
                existing_doc_name = self.doc_mapping.get(processed_id, {}).get('name', '')
                if existing_doc_name == doc_name:
                    already_processed = True
                    break
            
            if not already_processed:
                new_doc_groups[doc_name] = doc_groups[doc_name]
        
        if not new_doc_groups:
            log_success(self.logger, "暂无新文档需要处理", "RouterVectorize")
            return
        
        log_success(self.logger, f"新增待处理文档:共 {len(new_doc_groups)} 项", "RouterVectorize")
        
        # 建立映射（只处理新文档）
        for doc_name in sorted(new_doc_groups.keys()):
            doc_id = str(doc_id_counter)
            text_files_in_doc = sorted(new_doc_groups[doc_name], key=lambda x: x[0])
            
            self.doc_mapping[doc_id] = {
                'name': doc_name,
                'texts_name': [],
                'text_ids': [],
                'sentence_ids': []
            }
            
            doc_texts = []
            for text_num, text_file in text_files_in_doc:
                with open(text_file, 'r', encoding='utf-8') as f:
                    text = self.clean_text(f.read())
                
                text_id = str(text_id_counter)
                
                self.text_mapping[text_id] = {
                    'original_file': text_file.name,
                    'doc_id': doc_id,
                    'doc_name': doc_name,
                    'text_num_in_doc': len(doc_texts) + 1,
                    'text_content': text  # 保存文本内容
                }
                
                self.doc_mapping[doc_id]['texts_name'].append(text_file.name)
                self.doc_mapping[doc_id]['text_ids'].append(text_id)
                doc_texts.append(text)
                
                text_id_counter += 1
            
            # 合并文档
            merged_text = ''.join(doc_texts)
            doc_file = self.doc_db / f"doc{doc_id}_{doc_name}.txt"
            with open(doc_file, 'w', encoding='utf-8') as f:
                f.write(merged_text)

            log_success(self.logger, f"文档命名：doc{doc_id}-{doc_name[:30]} | 文本块:共{len(doc_texts)}份 | 长度:{len(merged_text)}字", "RouterVectorize")
            
            # 记录新增的文档ID
            self.new_doc_ids.append(doc_id)
            
            doc_id_counter += 1
        
        # 切割句子
        self._split_sentences()
        
        # 保存映射
        self._save_mappings()    

class EntityRelationExtractor:
    """实体关系提取器 - 使用Qwen-Plus模型（高并发）"""
    
    def __init__(self, api_key: str, prompts_file: str, qps: int = 50, model: str = "qwen-plus", logger=None):
        self.api_url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
        self.api_key = api_key
        self.model = model
        self.qps = qps
        self.token_counter = TokenCounter(logger)
        self.logger = logger
        
        # 加载提示词
        try:
            with open(prompts_file, 'r', encoding='utf-8') as f:
                self.prompts = yaml.safe_load(f)
        except Exception as e:
            log_error(self.logger, f"加载提示词失败: {e}", "RouterVectorize")
            raise
    
    async def call_api(self, prompt: str, session: aiohttp.ClientSession, 
                      task_name: str = "", max_retries: int = 3) -> Tuple[str, int, int]:
        """调用API（带重试机制）"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": self.model,
            "input": {"messages": [{"role": "user", "content": prompt}]}
        }
        
        for attempt in range(max_retries):
            try:
                async with session.post(self.api_url, json=data, headers=headers,
                                       timeout=aiohttp.ClientTimeout(total=120)) as resp:
                    result = await resp.json()
                    
                    if resp.status != 200:
                        if attempt < max_retries - 1:
                            await asyncio.sleep(2 ** attempt)
                            continue
                        raise Exception(f"HTTP {resp.status}")
                    
                    content = result.get("output", {}).get("text", "")
                    usage = result.get("usage", {})
                    
                    self.token_counter.add_tokens(
                        usage.get("input_tokens", 0), 
                        usage.get("output_tokens", 0)
                    )
                    return content, usage.get("input_tokens", 0), usage.get("output_tokens", 0)
                    
            except asyncio.TimeoutError:
                self.logger.warning(f"[api] timeout {task_name} (尝试 {attempt+1}/{max_retries})")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise
            except Exception as e:
                self.logger.warning(f"[api] error {task_name}: {str(e)[:50]} (尝试 {attempt+1}/{max_retries})")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise
        
        return "", 0, 0
    
    def parse_json(self, response: str) -> List[Dict]:
        """解析JSON响应"""
        try:
            json_match = re.search(r'\[\s*\{.*\}\s*\]', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
            return json.loads(response)
        except:
            return []
    
    async def extract_time_from_doc(self, doc_name: str, session: aiohttp.ClientSession) -> str:
        """使用LLM提取文档时间范围"""
        prompt = self.prompts['document_time_extraction_prompt'].format(doc_name=doc_name)
        response, _, _ = await self.call_api(prompt, session, f"时间提取-{doc_name[:20]}")
        time_str = response.strip()
        return time_str if time_str else "未知"
    
    async def generate_text_tag(self, text: str, session: aiohttp.ClientSession, text_id: str) -> str:
        """使用LLM生成文本标签"""
        prompt = self.prompts['text_tag_generation_prompt'].format(text=text[:500])  # 限制长度
        response, _, _ = await self.call_api(prompt, session, f"标签生成-text{text_id}")
        tag = response.strip()
        result = tag if tag else "未标注"
        return result
    
    async def extract_entities(self, text: str, text_id: str, session: aiohttp.ClientSession, 
                              entity_id_start: int) -> Tuple[List[Dict], int]:
        """提取实体"""
        prompt = self.prompts['entity_extraction_prompt'].format(text=text)
        response, in_tok, out_tok = await self.call_api(prompt, session, f"实体-text{text_id}")
        entities = self.parse_json(response)
        
        current_id = entity_id_start
        for entity in entities:
            entity['entity_id'] = str(current_id)
            entity['text_id'] = text_id
            current_id += 1
        
        return entities, current_id
    
    async def extract_relations(self, text: str, entities: List[Dict], text_id: str, 
                                session: aiohttp.ClientSession, relation_id_start: int) -> Tuple[List[Dict], int]:
        """提取关系"""
        if not entities:
            return [], relation_id_start
        
        entities_str = "\n".join([f"- {e['entity_name']} ({e['type']})" for e in entities])
        prompt = self.prompts['relation_extraction_prompt'].format(text=text, entities=entities_str)
        response, in_tok, out_tok = await self.call_api(prompt, session, f"关系-text{text_id}")
        relations = self.parse_json(response)
        
        entity_name_to_id = {e['entity_name']: e['entity_id'] for e in entities}
        
        valid_relations = []
        current_id = relation_id_start
        for relation in relations:
            src, tgt = relation.get('source', ''), relation.get('target', '')
            
            if src in entity_name_to_id and tgt in entity_name_to_id:
                relation['relationship_id'] = str(current_id)
                relation['source'] = entity_name_to_id[src]
                relation['target'] = entity_name_to_id[tgt]
                relation['text_id'] = text_id
                valid_relations.append(relation)
                current_id += 1
        
        return valid_relations, current_id
    
    async def process_batch_high_qps(self, text_files: List[Path], entities_db: Path, 
                                     relationships_db: Path, text_mapping: Dict, 
                                     start_entity_id: int = 1, start_relation_id: int = 1) -> Tuple[Dict[str, str], int, int]:
        """批量处理（两阶段：先提取实体，再提取关系）"""
        
        file_to_text_id = {info['original_file']: tid for tid, info in text_mapping.items()}
        
        # 从指定的ID开始分配（支持增量更新）
        entity_id_counter = start_entity_id
        relation_id_counter = start_relation_id
        
        text_tags = {}  # text_id -> tag
        text_data = {}  # text_id -> (text_content, doc_id)
        text_entities = {}  # text_id -> entities
        
        async with aiohttp.ClientSession() as session:
            
            total_tasks = len(text_files)
            completed = 0
            
            for i in range(0, len(text_files), self.qps):
                batch_files = text_files[i:i+self.qps]
                tasks = []
                
                for text_file in batch_files:
                    async def extract_entities_phase(tf=text_file):
                        nonlocal completed
                        
                        try:
                            with open(tf, 'r', encoding='utf-8') as f:
                                text = f.read().strip()
                            
                            text_id = file_to_text_id.get(tf.name, tf.stem)
                            doc_id = text_mapping.get(text_id, {}).get('doc_id', '1')
                            
                            # 并发执行：生成标签、提取实体
                            tag_task = self.generate_text_tag(text, session, text_id)
                            entities_task = self.extract_entities(text, text_id, session, 0)  # 临时ID，后续重新分配
                            
                            tag, (entities, _) = await asyncio.gather(tag_task, entities_task)
                            
                            completed += 1
                            log_success(self.logger, f"实体识别结果：text{text_id}-{len(entities)}实体 | TAG标签已生成 | 当前进度[{completed}/{total_tasks}]", "RouterVectorize")
                            
                            return text_id, doc_id, text, entities, tag
                            
                        except Exception as e:
                            log_error(self.logger, f"{tf.name}: {str(e)[:50]}", "error")
                            completed += 1
                            return text_id, doc_id, text, [], "处理失败"
                    
                    tasks.append(extract_entities_phase())
                
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # 收集结果并分配全局实体ID
                for result in batch_results:
                    if isinstance(result, tuple):
                        text_id, doc_id, text, entities, tag = result
                        
                        # 重新分配全局实体ID（无前缀）
                        for entity in entities:
                            entity['entity_id'] = str(entity_id_counter)
                            entity_id_counter += 1
                        
                        text_data[text_id] = (text, doc_id)
                        text_entities[text_id] = entities
                        text_tags[text_id] = tag
                
                # QPS控制
                if i + self.qps < len(text_files):
                    await asyncio.sleep(1)
            
            log_success(self.logger, f"实体识别完成，共提取实体{entity_id_counter - 1}条", "RouterVectorize")
            
            completed = 0
            text_relations = {}  # text_id -> relations
            
            text_ids = list(text_data.keys())
            for i in range(0, len(text_ids), self.qps):
                batch_text_ids = text_ids[i:i+self.qps]
                tasks = []
                
                for text_id in batch_text_ids:
                    async def extract_relations_phase(tid=text_id):
                        nonlocal completed
                        
                        try:
                            text, doc_id = text_data[tid]
                            entities = text_entities[tid]
                            
                            if not entities:
                                completed += 1
                                return tid, []
                            
                            # 提取关系
                            relations, _ = await self.extract_relations(
                                text, entities, tid, session, 0  # 临时ID，后续重新分配
                            )
                            
                            completed += 1
                            log_success(self.logger, f"关系抽取结果：text{tid}-{len(relations)}关系 | 当前进度[{completed}/{len(text_ids)}]", "RouterVectorize")
                            
                            return tid, relations
                            
                        except Exception as e:
                            if self.logger:
                                log_error(self.logger, f"text{tid}: {str(e)[:50]}", "error")
                            completed += 1
                            return tid, []
                    
                    tasks.append(extract_relations_phase())
                
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # 收集结果并分配全局关系ID
                for result in batch_results:
                    if isinstance(result, tuple):
                        text_id, relations = result
                        
                        # 重新分配全局关系ID（无前缀）
                        for relation in relations:
                            relation['relationship_id'] = str(relation_id_counter)
                            relation_id_counter += 1
                        
                        text_relations[text_id] = relations
                
                # QPS控制
                if i + self.qps < len(text_ids):
                    await asyncio.sleep(1)
            
            log_success(self.logger, f"关系抽取完成，共提取关系{relation_id_counter - 1}条", "RouterVectorize")
        
        # 收集当前批次的原始实体和关系（带来源信息）
        current_batch_entities = []
        current_batch_relations = []
        
        for text_id in text_data.keys():
            doc_id = text_data[text_id][1]
            
            # 获取原始text文件名和doc名称
            original_file = text_mapping.get(text_id, {}).get('original_file', f'text{text_id}')
            doc_name = text_mapping.get(text_id, {}).get('doc_name', '')
            
            entities = text_entities.get(text_id, [])
            relations = text_relations.get(text_id, [])
            
            # 为每个实体添加来源信息
            for entity in entities:
                entity['texts_name'] = [original_file]
                entity['doc_name'] = doc_name
                current_batch_entities.append(entity)
            
            # 为每个关系添加来源信息
            for relation in relations:
                relation['texts_name'] = [original_file]
                relation['doc_name'] = doc_name
                current_batch_relations.append(relation)
        
        self.token_counter.print_summary()
        
        # 返回：text_tags, 最后实体ID, 最后关系ID, 当前批次数据
        return text_tags, entity_id_counter - 1, relation_id_counter - 1, current_batch_entities, current_batch_relations

class EmbeddingGenerator:
    """向量生成器 - 使用text-embedding-v4（高并发）"""
    
    def __init__(self, api_key: str, max_concurrent: int = 100, model: str = "text-embedding-v4", logger=None):
        self.api_url = "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding"
        self.api_key = api_key
        self.model = model
        self.max_concurrent = max_concurrent
        self.token_counter = TokenCounter(logger)
        self.logger = logger
    
    async def generate_embedding(self, text: str, session: aiohttp.ClientSession, 
                                task_name: str = "", max_retries: int = 5) -> Optional[List[float]]:
        """生成单个向量（带重试）"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": self.model,
            "input": {"texts": [text]}
        }
        
        for attempt in range(max_retries):
            try:
                async with session.post(self.api_url, json=data, headers=headers,
                                       timeout=aiohttp.ClientTimeout(total=90)) as resp:
                    result = await resp.json()
                    
                    if resp.status != 200:
                        if attempt < max_retries - 1:
                            await asyncio.sleep(1)
                            continue
                        return None
                    
                    embeddings = result.get("output", {}).get("embeddings", [])
                    if embeddings:
                        usage = result.get("usage", {})
                        self.token_counter.add_tokens(usage.get("total_tokens", 0), 0)
                        return embeddings[0].get("embedding", [])
                    return None
                    
            except (asyncio.TimeoutError, Exception):
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                return None
        
        return None
    
    async def generate_batch(self, texts: List[str], desc: str = "向量") -> List[Optional[List[float]]]:
        """批量生成向量（高并发）"""        
        async with aiohttp.ClientSession() as session:
            semaphore = asyncio.Semaphore(self.max_concurrent)
            
            async def gen_one(text: str, idx: int):
                async with semaphore:
                    vec = await self.generate_embedding(text, session, f"{desc}{idx}")
                    return vec
            
            vecs = await asyncio.gather(*[gen_one(t, i) for i, t in enumerate(texts)])
            
            success = sum(1 for v in vecs if v is not None)
            success_rate = (success*100//len(texts)) if len(texts) > 0 else 0
            
            return vecs

class LanceDBManager:
    """LanceDB管理器 - 管理向量数据库"""
    
    def __init__(self, db_path: str, logger=None):
        self.db_path = Path(db_path)
        self.db_path.mkdir(parents=True, exist_ok=True)
        self.db = lancedb.connect(str(self.db_path))
        self.logger = logger
            
    def save_table(self, table_name: str, data: List[Dict], schema: pa.Schema, mode: str = "auto") -> None:
        """保存表（支持auto/append/overwrite模式）"""
        if not data:
            self.logger.warning(f"[lancedb] {table_name} 无数据")
            return
        
        try:
            # auto模式：自动判断
            if mode == "auto":
                mode = "append" if table_name in self.db.table_names() else "overwrite"
            
            if mode == "append":
                table = self.db.open_table(table_name)
                table.add(data)
                total = table.count_rows()
            else:
                self.db.create_table(table_name, data=data, schema=schema, mode="overwrite")
        except Exception as e:
            log_error(self.logger, f"{table_name} 保存失败: {str(e)}", "RouterVectorize")

class VectorizationPipeline:
    """向量化处理流水线 - 完整流程管理"""
    
    def __init__(self, topic_name: str = "控烟", logger=None):
        """
        初始化向量化流水线
        
        Args:
            topic_name: 主题名称
            logger: 日志记录器
        """
        self.logger = logger
        self.topic_name = topic_name
        
        # 从配置文件读取配置
        llm_config = settings.get_llm_config()
        ragrouter_config = llm_config.get('router_vec_llm', {})
        embedding_config = llm_config.get('embedding_llm', {})
        
        # 获取API密钥
        api_key = get_api_key()
        if not api_key:
            raise ValueError("未配置千问 API 密钥，请在 credentials.qwen_api_key 设置")
        
        # 获取项目路径 - 每个主题有独立的数据库目录
        project_root = get_project_root()
        base_path = project_root / "src" / "utils" / "rag" / "ragrouter" / f"{topic_name}数据库"
        
        # 获取提示词文件路径
        prompts_file = get_configs_root() / "prompt" / "router_vec" / f"{topic_name}.yaml"
        if not prompts_file.exists():
            prompts_file = get_configs_root() / "prompt" / "router_vec" / "默认.yaml"
        
        # 初始化各组件（各组件负责自己的目录创建）
        self.text_processor = TextProcessor(base_path, logger)
        self.entity_extractor = EntityRelationExtractor(
            api_key, 
            str(prompts_file),
            qps=ragrouter_config.get('qps', 50),
            model=ragrouter_config.get('model', 'qwen-plus'),
            logger=logger
        )
        self.embedding_generator = EmbeddingGenerator(
            api_key, 
            max_concurrent=30,
            model=embedding_config.get('model', 'text-embedding-v4'),
            logger=logger
        )
        self.lancedb_manager = LanceDBManager(str(base_path / "vector_db"), logger)
        
        # 运行时数据（非持久化）
        self.doc_time_mapping = {}  # 文档时间映射
        self.text_tags = {}  # 文本标签映射
        self.current_batch_entities = []  # 当前批次实体
        self.current_batch_relations = []  # 当前批次关系
    
    async def run(self, skip_check: bool = False) -> None:
        """运行完整流水线"""
        
        try:
            # 步骤1: 文本处理与映射
            self.text_processor.process_all()
            
            # 步骤2: 提取时间（使用LLM，只提取新文档）
            if not self.text_processor.new_doc_ids:
                log_success(self.logger, "暂无新文档需要提取时间", "RouterVectorize")
            else:
                async with aiohttp.ClientSession() as session:
                    tasks = []
                    # 只提取新文档的时间
                    for doc_id in self.text_processor.new_doc_ids:
                        doc_info = self.text_processor.doc_mapping.get(doc_id)
                        if doc_info:
                            tasks.append(self._extract_time_for_doc(doc_id, doc_info['name'], session))
                    
                    await asyncio.gather(*tasks)
                            
            # 步骤3: 实体关系提取（两阶段处理）
            # 读取现有的last_id，用于增量更新
            start_entity_id = 1
            start_relation_id = 1
            mapping_file = self.text_processor.log_db / "data_mapping.json"
            
            if mapping_file.exists():
                try:
                    with open(mapping_file, 'r', encoding='utf-8') as f:
                        existing_mapping = json.load(f)
                    start_entity_id = existing_mapping.get('entities', {}).get('last_id', 0) + 1
                    start_relation_id = existing_mapping.get('relationships', {}).get('last_id', 0) + 1
                except:
                    pass
            
            last_entity_id = 0
            last_relation_id = 0
            
            # 只处理新文档的文本文件
            new_text_files = []
            all_text_files = sorted(self.text_processor.text_db.glob("*.txt"))
            
            for text_file in all_text_files:
                # 从文件名提取text_id，判断是否属于新文档
                file_to_text_id = {info['original_file']: tid for tid, info in self.text_processor.text_mapping.items()}
                text_id = file_to_text_id.get(text_file.name)
                
                if text_id:
                    doc_id = self.text_processor.text_mapping[text_id]['doc_id']
                    if doc_id in self.text_processor.new_doc_ids:
                        new_text_files.append(text_file)
            
            current_batch_entities = []
            current_batch_relations = []
            
            if not new_text_files:
                log_success(self.logger, "暂无新文档需要提取实体关系", "RouterVectorize")
            else:
                self.text_tags, last_entity_id, last_relation_id, current_batch_entities, current_batch_relations = await self.entity_extractor.process_batch_high_qps(
                    new_text_files,
                    self.text_processor.entities_db,
                    self.text_processor.relationships_db,
                    self.text_processor.text_mapping,
                    start_entity_id,
                    start_relation_id
                )
            
            # 保存当前批次数据供后续使用
            self.current_batch_entities = current_batch_entities
            self.current_batch_relations = current_batch_relations
            
            # 步骤4: 生成向量并存LanceDB
            # 调用向量化，返回去重后的最大ID
            final_entity_last_id, final_relation_last_id = await self._generate_and_save()
            
            # 更新映射文件（last_id = count = 去重后的最大ID）
            entity_count = 0
            relation_count = 0
            try:
                if "graphrag_entities" in self.lancedb_manager.db.table_names():
                    entity_count = self.lancedb_manager.db.open_table("graphrag_entities").count_rows()
                if "graphrag_relationships" in self.lancedb_manager.db.table_names():
                    relation_count = self.lancedb_manager.db.open_table("graphrag_relationships").count_rows()
            except:
                pass
            
            # last_id和count都是去重后的最大ID
            self._update_mapping(final_entity_last_id, final_relation_last_id, entity_count, relation_count)
            
        except Exception as e:
            log_error(self.logger, f"处理失败: {str(e)}", "RouterVectorize")
            traceback.print_exc()
            raise
    
    async def _extract_time_for_doc(self, doc_id: str, doc_name: str, session: aiohttp.ClientSession) -> None:
        """为单个文档提取时间"""
        time_str = await self.entity_extractor.extract_time_from_doc(doc_name, session)
        self.doc_time_mapping[doc_id] = time_str
        log_success(self.logger, f"时间标签提取完成：{time_str}", "RouterVectorize")
    
    async def _generate_and_save(self) -> Tuple[int, int]:
        """生成向量并存LanceDB，返回去重后的最大ID"""
        
        # 1. 句子向量（增量：只处理新文档的句子）
        sentence_file = self.text_processor.sentence_db / "sentences.json"
        with open(sentence_file, 'r', encoding='utf-8') as f:
            all_sentences = json.load(f)
        
        # 只处理新文档的句子
        new_doc_ids = set(self.text_processor.new_doc_ids)
        new_sentences = [s for s in all_sentences if s['doc_id'] in new_doc_ids]
        
        if not new_sentences:
            log_success(self.logger, "暂无新句子需要向量化", "RouterVectorize")
        else:
            log_success(self.logger, f"Sentence向量化：新增{len(new_sentences)}条", "RouterVectorize")
            
            texts = [s['sentence_text'] for s in new_sentences]
            vecs = await self.embedding_generator.generate_batch(texts, "句子向量")
            
            normalrag_data = []
            for s, v in zip(new_sentences, vecs):
                if v:
                    normalrag_data.append({
                        "sentence_id": s["sentence_id"],
                        "sentence_text": s["sentence_text"],
                        "sentence_vec": v,
                        "doc_id": s["doc_id"],
                        "doc_name": s["doc_name"],
                        "time": self.doc_time_mapping.get(s["doc_id"], "未知")
                    })
            
            if normalrag_data:
                vec_dim = len(normalrag_data[0]["sentence_vec"])
                schema = pa.schema([
                    pa.field("sentence_id", pa.string()),
                    pa.field("sentence_text", pa.string()),
                    pa.field("sentence_vec", pa.list_(pa.float32(), vec_dim)),
                    pa.field("doc_id", pa.string()),
                    pa.field("doc_name", pa.string()),
                    pa.field("time", pa.string())
                ])
                self.lancedb_manager.save_table("normalrag", normalrag_data, schema, mode="auto")
        
        # 2. 读取实体、合并新旧、按文档去重、增量向量化
        # 读取已有的去重后实体（从entities.json）
        existing_entities = []
        merged_entities_file = self.text_processor.entities_db / "entities.json"
        if merged_entities_file.exists():
            try:
                with open(merged_entities_file, 'r', encoding='utf-8') as f:
                    existing_entities = json.load(f)
            except Exception as e:
                log_error(self.logger, f"读取已有实体失败: {e}", "RouterVectorize")
        
        # 合并当前批次的新实体
        all_entities_raw = existing_entities + self.current_batch_entities
        
        # 按文档分组
        doc_entities = defaultdict(list)
        for e in all_entities_raw:
            text_id = e.get('text_id', '')
            if text_id in self.text_processor.text_mapping:
                doc_id = self.text_processor.text_mapping[text_id]['doc_id']
                doc_name = self.text_processor.text_mapping[text_id].get('doc_name', e.get('doc_name', ''))
                e['doc_id'] = doc_id
                e['doc_name'] = doc_name
                e['time'] = self.doc_time_mapping.get(doc_id, '未知')
                doc_entities[doc_id].append(e)
        
        # 按文档去重（每个文档内按entity_name + type去重）
        unique_entities = []
        total_duplicates = 0
        old_to_new_id = {}
        
        for doc_id in sorted(doc_entities.keys()):
            seen = set()
            for e in doc_entities[doc_id]:
                key = (e['entity_name'], e.get('type', ''))
                if key not in seen:
                    seen.add(key)
                    unique_entities.append(e)
                else:
                    total_duplicates += 1
                
        # 从LanceDB读取已有实体的向量（通过doc_name+entity_name+type匹配，同文档去重）
        existing_entity_vectors = {}  # key=(doc_name, entity_name, type) -> (name_vec, desc_vec)
        
        try:
            if "graphrag_entities" in self.lancedb_manager.db.table_names():
                table = self.lancedb_manager.db.open_table("graphrag_entities")
                df = table.to_pandas()
                for _, row in df.iterrows():
                    key = (row['doc_name'], row['entity_name'], row['type'])
                    existing_entity_vectors[key] = (
                        row['entity_name_vec'].tolist() if hasattr(row['entity_name_vec'], 'tolist') else list(row['entity_name_vec']),
                        row['description_vec'].tolist() if hasattr(row['description_vec'], 'tolist') else list(row['description_vec'])
                    )
        except:
            pass
        
        # 判断哪些实体需要向量化
        entities_need_vec = []
        entities_has_vec = []
        
        for e in unique_entities:
            key = (e.get('doc_name', ''), e.get('entity_name', ''), e.get('type', ''))
            if key in existing_entity_vectors:
                # 已有向量，直接使用
                e['entity_name_vec'] = existing_entity_vectors[key][0]
                e['description_vec'] = existing_entity_vectors[key][1]
                entities_has_vec.append(e)
            else:
                # 需要向量化
                entities_need_vec.append(e)
        
        if len(entities_need_vec) > 0:
            log_success(self.logger, f"entity向量化：新增{len(entities_need_vec)}条 | 复用{len(entities_has_vec)}条", "RouterVectorize")
        else:
            log_success(self.logger, f"entity向量化：实体向量全部复用共{len(entities_has_vec)}条", "RouterVectorize")
        
        # 只对需要的实体生成向量
        if entities_need_vec:
            entity_names = [e['entity_name'] for e in entities_need_vec]
            entity_descs = [e.get('description', '') for e in entities_need_vec]
            
            name_vecs = await self.embedding_generator.generate_batch(entity_names, "实体名称向量")
            desc_vecs = await self.embedding_generator.generate_batch(entity_descs, "实体描述向量")
            
            # 添加向量到新实体
            for e, name_vec, desc_vec in zip(entities_need_vec, name_vecs, desc_vecs):
                if name_vec and desc_vec:
                    e['entity_name_vec'] = name_vec
                    e['description_vec'] = desc_vec
        
        # 合并所有实体（已有向量+新向量化）
        all_unique_entities = entities_has_vec + entities_need_vec
        
        # 重新分配全局连续ID
        entities_data = []
        entities_for_save = []  # 保存到entities.json的数据
        new_entity_id = 1
        
        for e in all_unique_entities:
            if 'entity_name_vec' in e and 'description_vec' in e:
                # 重新分配连续ID
                old_to_new_id[e.get('entity_id', '')] = str(new_entity_id)
                
                # 准备LanceDB数据
                entities_data.append({
                    "entity_id": str(new_entity_id),
                    "entity_name": e['entity_name'],
                    "entity_name_vec": e['entity_name_vec'],
                    "type": e.get('type', ''),
                    "description": e.get('description', ''),
                    "description_vec": e['description_vec'],
                    "time": e.get('time', '未知'),
                    "doc_name": e.get('doc_name', ''),
                    "text_ids": json.dumps([e.get('text_id', '')], ensure_ascii=False),
                    "doc_ids": json.dumps([e.get('doc_id', '')], ensure_ascii=False)
                })
                
                # 准备保存到entities.json的数据（不含向量，节省空间）
                entities_for_save.append({
                    "entity_id": str(new_entity_id),
                    "entity_name": e['entity_name'],
                    "type": e.get('type', ''),
                    "description": e.get('description', ''),
                    "time": e.get('time', '未知'),
                    "doc_name": e.get('doc_name', ''),
                    "texts_name": e.get('texts_name', []),
                    "text_id": e.get('text_id', ''),
                    "doc_id": e.get('doc_id', '')
                })
                
                new_entity_id += 1
        
        final_entity_last_id = new_entity_id - 1
        
        # 保存去重后的实体到entities.json（不含向量）
        if entities_for_save:
            entities_file = self.text_processor.entities_db / "entities.json"
            with open(entities_file, 'w', encoding='utf-8') as f:
                json.dump(entities_for_save, f, ensure_ascii=False, indent=2)
        
        # 保存到LanceDB
        if entities_data:
            vec_dim = len(entities_data[0]["description_vec"])
            schema = pa.schema([
                pa.field("entity_id", pa.string()),
                pa.field("entity_name", pa.string()),
                pa.field("entity_name_vec", pa.list_(pa.float32(), vec_dim)),
                pa.field("type", pa.string()),
                pa.field("description", pa.string()),
                pa.field("description_vec", pa.list_(pa.float32(), vec_dim)),
                pa.field("time", pa.string()),
                pa.field("doc_name", pa.string()),
                pa.field("text_ids", pa.string()),
                pa.field("doc_ids", pa.string())
            ])
            self.lancedb_manager.save_table("graphrag_entities", entities_data, schema, mode="overwrite")
        
        # 3. 读取关系、合并新旧、按文档去重、增量向量化
        
        # 读取已有的去重后关系（从relationships.json）
        existing_relations = []
        merged_relations_file = self.text_processor.relationships_db / "relationships.json"
        if merged_relations_file.exists():
            try:
                with open(merged_relations_file, 'r', encoding='utf-8') as f:
                    existing_relations = json.load(f)
            except Exception as e:
                log_error(self.logger, f"读取已有关系失败: {e}", "RouterVectorize")
        
        # 合并当前批次的新关系
        all_relations_raw = existing_relations + self.current_batch_relations
        
        # 按文档分组并更新实体ID映射
        doc_relations = defaultdict(list)
        filtered_no_entities = 0
        
        for r in all_relations_raw:
            text_id = r.get('text_id', '')
            if text_id in self.text_processor.text_mapping:
                doc_id = self.text_processor.text_mapping[text_id]['doc_id']
                doc_name = self.text_processor.text_mapping[text_id].get('doc_name', r.get('doc_name', ''))
                r['doc_id'] = doc_id
                r['doc_name'] = doc_name
                r['time'] = self.doc_time_mapping.get(doc_id, '未知')
                
                # 实体ID映射（去重后ID会变）
                old_src = r.get('source', '')
                old_tgt = r.get('target', '')
                new_src = old_to_new_id.get(old_src, old_src)
                new_tgt = old_to_new_id.get(old_tgt, old_tgt)
                r['source'] = new_src
                r['target'] = new_tgt
                
                # 只保留实体都存在的关系
                if new_src in old_to_new_id.values() and new_tgt in old_to_new_id.values():
                    doc_relations[doc_id].append(r)
                else:
                    filtered_no_entities += 1
        
        # 按文档去重（每个文档内按source + target去重）
        unique_relations = []
        total_duplicates = 0
        
        for doc_id in sorted(doc_relations.keys()):
            seen = set()
            for r in doc_relations[doc_id]:
                key = (r.get('source', ''), r.get('target', ''))
                if key not in seen:
                    seen.add(key)
                    unique_relations.append(r)
                else:
                    total_duplicates += 1
        
        
        # 从LanceDB读取已有关系的向量（通过doc_name+source+target匹配，同文档去重）
        existing_relation_vectors = {}  # key=(doc_name, source, target) -> description_vec
        
        try:
            if "graphrag_relationships" in self.lancedb_manager.db.table_names():
                table = self.lancedb_manager.db.open_table("graphrag_relationships")
                df = table.to_pandas()
                for _, row in df.iterrows():
                    key = (row['doc_name'], row['source'], row['target'])
                    existing_relation_vectors[key] = row['description_vec'].tolist() if hasattr(row['description_vec'], 'tolist') else list(row['description_vec'])
        except:
            pass
        
        # 判断哪些关系需要向量化
        relations_need_vec = []
        relations_has_vec = []
        
        for r in unique_relations:
            key = (r.get('doc_name', ''), r.get('source', ''), r.get('target', ''))
            if key in existing_relation_vectors:
                # 已有向量，直接使用
                r['description_vec'] = existing_relation_vectors[key]
                relations_has_vec.append(r)
            else:
                # 需要向量化
                relations_need_vec.append(r)
        
        if len(relations_need_vec) > 0:
            log_success(self.logger, f"relationships向量化：新增{len(relations_need_vec)}条 | 复用{len(relations_has_vec)}条", "RouterVectorize")
        else:
            log_success(self.logger, f"relationships向量化：关系向量全部复用共{len(relations_has_vec)}个", "RouterVectorize")
        
        # 只对需要的关系生成向量
        if relations_need_vec:
            rel_descs = [r.get('description', '') for r in relations_need_vec]
            rel_vecs = await self.embedding_generator.generate_batch(rel_descs, "关系向量")
            
            # 添加向量到新关系
            for r, vec in zip(relations_need_vec, rel_vecs):
                if vec:
                    r['description_vec'] = vec
        
        # 合并所有关系（已有向量+新向量化）
        all_unique_relations = relations_has_vec + relations_need_vec
        
        # 重新分配全局连续ID
        relations_data = []
        relations_for_save = []
        new_relation_id = 1
        
        for r in all_unique_relations:
            if 'description_vec' in r:
                # 准备LanceDB数据
                relations_data.append({
                    "relationship_id": str(new_relation_id),
                    "source": r.get('source', ''),
                    "target": r.get('target', ''),
                    "description": r.get('description', ''),
                    "description_vec": r['description_vec'],
                    "time": r.get('time', '未知'),
                    "doc_name": r.get('doc_name', ''),
                    "text_ids": json.dumps([r.get('text_id', '')], ensure_ascii=False),
                    "doc_ids": json.dumps([r.get('doc_id', '')], ensure_ascii=False)
                })
                
                # 准备保存到relationships.json的数据（不含向量，节省空间）
                relations_for_save.append({
                    "relationship_id": str(new_relation_id),
                    "source": r.get('source', ''),
                    "target": r.get('target', ''),
                    "description": r.get('description', ''),
                    "time": r.get('time', '未知'),
                    "doc_name": r.get('doc_name', ''),
                    "texts_name": r.get('texts_name', []),
                    "text_id": r.get('text_id', ''),
                    "doc_id": r.get('doc_id', '')
                })
                
                new_relation_id += 1
        
        final_relation_last_id = new_relation_id - 1
        
        # 保存去重后的关系到relationships.json（不含向量）
        if relations_for_save:
            relations_file = self.text_processor.relationships_db / "relationships.json"
            with open(relations_file, 'w', encoding='utf-8') as f:
                json.dump(relations_for_save, f, ensure_ascii=False, indent=2)
        
        # 保存到LanceDB
        if relations_data:
            vec_dim = len(relations_data[0]["description_vec"])
            schema = pa.schema([
                pa.field("relationship_id", pa.string()),
                pa.field("source", pa.string()),
                pa.field("target", pa.string()),
                pa.field("description", pa.string()),
                pa.field("description_vec", pa.list_(pa.float32(), vec_dim)),
                pa.field("time", pa.string()),
                pa.field("doc_name", pa.string()),
                pa.field("text_ids", pa.string()),
                pa.field("doc_ids", pa.string())
            ])
            self.lancedb_manager.save_table("graphrag_relationships", relations_data, schema, mode="overwrite")
        
        # 4. 文本表（新增text、text_tag、text_tag_vec字段）
        # 收集每个文本的实体ID（使用新ID）
        text_entities = defaultdict(set)
        for e in entities_data:
            text_ids_str = e.get('text_ids', '[]')
            text_ids = json.loads(text_ids_str)
            for tid in text_ids:
                text_entities[tid].add(e['entity_id'])
        
        # 收集每个文本的关系ID（使用新ID）
        text_relations = defaultdict(set)
        for r in relations_data:
            text_ids_str = r.get('text_ids', '[]')
            text_ids = json.loads(text_ids_str)
            for tid in text_ids:
                text_relations[tid].add(r['relationship_id'])
        
        # 只对新批次的文本生成标签向量
        new_doc_ids = set(self.text_processor.new_doc_ids)
        tag_texts = []
        tag_text_ids = []
        
        for text_id, info in self.text_processor.text_mapping.items():
            # 只处理新批次文档的文本
            if info['doc_id'] in new_doc_ids:
                tag = self.text_tags.get(text_id, "未标注")
                tag_texts.append(tag)
                tag_text_ids.append(text_id)
        
        if not tag_texts:
            log_success(self.logger, "暂无新文本需要处理", "RouterVectorize")
        else:
            
            tag_vecs = await self.embedding_generator.generate_batch(tag_texts, "文本标签向量")
            
            tag_vec_map = {tid: vec for tid, vec in zip(tag_text_ids, tag_vecs) if vec}
            
            texts_data = []
            for text_id in tag_text_ids:
                info = self.text_processor.text_mapping[text_id]
                tag = self.text_tags.get(text_id, "未标注")
                tag_vec = tag_vec_map.get(text_id, None)
                
                if tag_vec:  # 只保存有向量的
                    texts_data.append({
                        "text_id": text_id,
                        "text": info.get('text_content', ''),
                        "text_tag": tag,
                        "text_tag_vec": tag_vec,
                        "doc_id": info['doc_id'],
                        "doc_name": info['doc_name'],
                        "time": self.doc_time_mapping.get(info['doc_id'], '未知'),
                        "entity_ids": json.dumps(sorted(list(text_entities.get(text_id, set()))), ensure_ascii=False),
                        "relationship_ids": json.dumps(sorted(list(text_relations.get(text_id, set()))), ensure_ascii=False)
                    })
        
            log_success(self.logger, f"text向量化: 新增{len(texts_data)}条", "RouterVectorize")
            
            if texts_data:
                vec_dim = len(texts_data[0]["text_tag_vec"])
                schema = pa.schema([
                    pa.field("text_id", pa.string()),
                    pa.field("text", pa.string()),
                    pa.field("text_tag", pa.string()),
                    pa.field("text_tag_vec", pa.list_(pa.float32(), vec_dim)),
                    pa.field("doc_id", pa.string()),
                    pa.field("doc_name", pa.string()),
                    pa.field("time", pa.string()),
                    pa.field("entity_ids", pa.string()),
                    pa.field("relationship_ids", pa.string())
                ])
                self.lancedb_manager.save_table("graphrag_texts", texts_data, schema, mode="auto")
        
        # 返回去重后的最大ID
        return final_entity_last_id, final_relation_last_id
    
    def _update_mapping(self, last_entity_id: int, last_relation_id: int, 
                       entity_count: int, relation_count: int) -> None:
        """更新映射文件（last_id = count = 去重后的最大ID）"""
        mapping_file = self.text_processor.log_db / "data_mapping.json"
        
        # 读取现有映射
        with open(mapping_file, 'r', encoding='utf-8') as f:
            all_mapping = json.load(f)
        
        # last_id 和 count 都是去重后的最大ID（保持一致）
        all_mapping['entities']['last_id'] = last_entity_id
        all_mapping['entities']['count'] = entity_count
        all_mapping['relationships']['last_id'] = last_relation_id
        all_mapping['relationships']['count'] = relation_count
        
        # 更新已处理的文档列表
        if 'processed_docs' not in all_mapping:
            all_mapping['processed_docs'] = []
        
        current_doc_ids = list(self.text_processor.doc_mapping.keys())
        for doc_id in current_doc_ids:
            if doc_id not in all_mapping['processed_docs']:
                all_mapping['processed_docs'].append(doc_id)
        
        # 保存更新后的映射
        with open(mapping_file, 'w', encoding='utf-8') as f:
            json.dump(all_mapping, f, ensure_ascii=False, indent=2)
        
        log_success(
            self.logger,
            f"映射更新完成 :实体-{entity_count} | 关系-{relation_count} | 文档-{len(all_mapping['processed_docs'])}",
            "RouterVectorize"
        )

def run_ragrouter(topic_name: str = "默认") -> bool:
    """
    命令行接口，运行RagRouter向量化处理
    
    Args:
        topic_name: 主题名称
    
    Returns:
        bool: 是否成功
    """
    try:
        # 设置logger
        date_str = datetime.now().strftime("%Y-%m-%d")
        logger = setup_logger(f"RouterVectorize_{topic_name}", date_str)
        
        log_module_start(logger, "RouterVectorize", f"开始向量化 - 主题: {topic_name}")
        
        # 创建流水线
        pipeline = VectorizationPipeline(topic_name=topic_name, logger=logger)
        
        # 运行完整流程
        asyncio.run(pipeline.run(skip_check=False))
        
        return True
        
    except Exception as e:
        if 'logger' in locals():
            log_error(logger, f"处理失败: {e}", "RouterVectorize")
        traceback.print_exc()
        return False
