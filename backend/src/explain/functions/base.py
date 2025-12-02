"""
解读功能基础模块
"""
import json
import asyncio
import yaml
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from ...utils.logging.logging import setup_logger, log_success, log_error
from ...utils.setting.paths import bucket, get_project_root
from types import SimpleNamespace
from ...utils.rag.tagrag.tag_retrieve_data import tag_retrieve
from ...utils.rag.ragrouter.router_retrieve_data import AdvancedRAGSearcher, SearchParams
from ...utils.setting.paths import get_configs_root
from ...utils.setting.env_loader import get_api_key


class ExplainBase:
    """解读功能基类"""
    
    # 功能名映射：英文名 -> 中文名
    FUNCTION_MAPPING = {
        'volume': '声量分析',
        'attitude': '情感态度', 
        'trends': '趋势分析',
        'keywords': '关键词分析',
        'geography': '地域分析',
        'publishers': '发布者分析',
        'classification': '话题分类',
        'contentanalyze': '内容分析',
        'bertopic': '主题分析'
    }
    
    def __init__(self, topic: str, logger=None):
        """
        初始化解读基类
        
        Args:
            topic (str): 专题名称
            logger: 日志记录器
        """
        self.topic = topic
        self.logger = logger or setup_logger("Explain", "default")
        self._tagrag_cache = {}  # 缓存TagRAG结果
        
        # 加载LLM配置
        self.llm_config = self._load_llm_config()
        # 移除并发控制，所有阶段顺序执行
        
        
    def _load_llm_config(self) -> Dict[str, Any]:
        """
        加载LLM配置
        
        Returns:
            Dict[str, Any]: LLM配置
        """
        try:
            project_root = get_project_root()
            llm_config_file = project_root / "configs" / "llm.yaml"
            
            with open(llm_config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            explain_config = config.get('explain_llm', {})
            return explain_config
            
        except Exception as e:
            log_error(self.logger, f"加载LLM配置失败: {e}", "Explain")
            # 返回默认配置
            return {
                'provider': 'qwen',
                'model': 'qwen-plus',
                'qps': 50,
                'batch_size': 32,
                'max_tokens': 2000
            }
        
    def load_analysis_data(self, func_name: str, target: str, date: str, end_date: str = None) -> Optional[Dict]:
        """
        加载分析数据
        
        Args:
            func_name (str): 功能名称
            target (str): 目标类型（总体/渠道）
            date (str): 日期
            end_date (str, optional): 结束日期
            
        Returns:
            Optional[Dict]: 分析数据
        """
        try:
            # 构建数据路径
            if end_date:
                folder_name = f"{date}_{end_date}"
            else:
                folder_name = date
                
            analyze_dir = bucket("analyze", self.topic, folder_name)
            
            if target == "总体":
                data_file = analyze_dir / func_name / "总体" / f"{func_name}.json"
                
                # 检查文件是否存在
                if not data_file.exists():
                    log_error(self.logger, f"分析结果文件不存在: {data_file}", "Explain")
                    return None
                
                log_success(self.logger, f"找到分析结果文件: {data_file}", "Explain")
                
                with open(data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                # 检查数据是否为空
                if not data or not data.get('data'):
                    log_error(self.logger, f"分析结果数据为空: {func_name}", "Explain")
                    return None
                    
                log_success(self.logger, f"分析数据加载成功: {func_name} | 数据条数: {len(data.get('data', []))}", "Explain")
                return data
                
            else:
                # 渠道数据需要遍历所有渠道文件夹
                channel_dir = analyze_dir / func_name
                if not channel_dir.exists():
                    log_error(self.logger, f"渠道分析目录不存在: {channel_dir}", "Explain")
                    return None
                    
                # 获取所有渠道文件夹
                channel_dirs = [d for d in channel_dir.iterdir() if d.is_dir() and d.name != "总体"]
                if not channel_dirs:
                    log_error(self.logger, f"未找到任何渠道分析结果: {func_name}", "Explain")
                    return None
                
                log_success(self.logger, f"发现渠道分析目录: {len(channel_dirs)}个", "Explain")
                    
                # 合并所有渠道数据
                all_data = []
                valid_channels = []
                for channel_dir in channel_dirs:
                    channel_file = channel_dir / f"{func_name}.json"
                    if channel_file.exists():
                        try:
                            with open(channel_file, 'r', encoding='utf-8') as f:
                                channel_data = json.load(f)
                                if 'data' in channel_data and channel_data['data']:
                                    all_data.extend(channel_data['data'])
                                    valid_channels.append(channel_dir.name)
                                    log_success(self.logger, f"渠道数据有效: {channel_dir.name} | 条数: {len(channel_data['data'])}", "Explain")
                                else:
                                    log_error(self.logger, f"渠道数据为空: {channel_dir.name}", "Explain")
                        except Exception as e:
                            log_error(self.logger, f"读取渠道数据失败: {channel_dir.name} | {e}", "Explain")
                    else:
                        log_error(self.logger, f"渠道分析文件不存在: {channel_file}", "Explain")
                
                if not all_data:
                    log_error(self.logger, f"所有渠道分析数据都为空: {func_name}", "Explain")
                    return None
                
                log_success(self.logger, f"渠道数据合并成功: {func_name} | 有效渠道: {len(valid_channels)} | 总条数: {len(all_data)}", "Explain")
                return {"data": all_data}
                
        except Exception as e:
            log_error(self.logger, f"加载分析数据失败: {e}", "Explain")
            return None
    
    def load_contentanalyze_data(self, date: str, end_date: str = None) -> Optional[Dict]:
        """
        加载内容分析数据（特殊处理，因为contentanalyze在单独的文件夹）
        
        Args:
            date (str): 日期
            end_date (str, optional): 结束日期
            
        Returns:
            Optional[Dict]: 内容分析数据
        """
        try:
            if end_date:
                folder_name = f"{date}_{end_date}"
            else:
                folder_name = date
                
            contentanalyze_dir = bucket("contentanalyze", self.topic, folder_name)
            data_file = contentanalyze_dir / "contentanalysis.json"
            
            # 检查文件是否存在
            if not data_file.exists():
                log_error(self.logger, f"内容分析文件不存在: {data_file}", "Explain")
                return None
            
            log_success(self.logger, f"找到内容分析文件: {data_file}", "Explain")
            
            with open(data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 检查数据是否为空
            if not data:
                log_error(self.logger, f"内容分析数据为空", "Explain")
                return None
            
            log_success(self.logger, f"内容分析数据加载成功 | 数据字段: {list(data.keys())}", "Explain")
            return data
                
        except Exception as e:
            log_error(self.logger, f"加载内容分析数据失败: {e}", "Explain")
            return None
    
    def load_bertopic_data(self, date: str, end_date: str = None) -> Optional[Dict]:
        """
        加载主题分析数据（BERTopic结果）
        
        Args:
            date (str): 日期
            end_date (str, optional): 结束日期
            
        Returns:
            Optional[Dict]: 主题分析数据，包含再聚类结果和主题关键词
        """
        try:
            if end_date:
                folder_name = f"{date}_{end_date}"
            else:
                folder_name = date
                
            topic_dir = bucket("topic", self.topic, folder_name)
            
            # 加载两个JSON文件
            recluster_file = topic_dir / "4大模型再聚类结果.json"
            keywords_file = topic_dir / "5大模型主题关键词.json"
            
            # 检查文件是否存在
            if not recluster_file.exists():
                log_error(self.logger, f"主题再聚类结果文件不存在: {recluster_file}", "Explain")
                return None
            
            if not keywords_file.exists():
                log_error(self.logger, f"主题关键词文件不存在: {keywords_file}", "Explain")
                return None
            
            log_success(self.logger, f"找到主题分析文件: {recluster_file}", "Explain")
            log_success(self.logger, f"找到主题关键词文件: {keywords_file}", "Explain")
            
            # 读取文件
            with open(recluster_file, 'r', encoding='utf-8') as f:
                recluster_data = json.load(f)
            
            with open(keywords_file, 'r', encoding='utf-8') as f:
                keywords_data = json.load(f)
            
            # 检查数据是否为空
            if not recluster_data:
                log_error(self.logger, f"主题再聚类数据为空", "Explain")
                return None
            
            if not keywords_data:
                log_error(self.logger, f"主题关键词数据为空", "Explain")
                return None
            
            # 合并数据
            combined_data = {
                "再聚类结果": recluster_data,
                "主题关键词": keywords_data
            }
            
            log_success(self.logger, f"主题分析数据加载成功 | 主题数量: {len(recluster_data)}", "Explain")
            return combined_data
                
        except Exception as e:
            log_error(self.logger, f"加载主题分析数据失败: {e}", "Explain")
            return None
    
    def load_prompt(self, func_name: str) -> Optional[Dict[str, str]]:
        """
        加载提示词配置
        
        Args:
            func_name (str): 功能名称
            
        Returns:
            Optional[Dict[str, str]]: 提示词配置
        """
        try:
            # 使用统一的路径获取方法
            project_root = get_project_root()
            prompt_file = project_root / "configs" / "prompt" / "explain" / f"{self.topic}.yaml"
            
            if not prompt_file.exists():
                log_error(self.logger, f"未找到专题 {self.topic} 的提示词文件: {prompt_file}", "Explain")
                return None
            
            import yaml
            with open(prompt_file, 'r', encoding='utf-8') as f:
                prompt_config = yaml.safe_load(f)
            
            if 'prompts' not in prompt_config:
                log_error(self.logger, f"提示词文件格式错误，缺少prompts字段", "Explain")
                return None
                
            prompts = prompt_config['prompts']
            if func_name not in prompts:
                log_error(self.logger, f"未找到功能 {func_name} 的提示词配置", "Explain")
                return None
                
            return prompts[func_name]
            
        except Exception as e:
            log_error(self.logger, f"加载提示词失败: {e}", "Explain")
            return None
    
    async def get_tagrag_context(self, func_name: str, top_k: int = 3) -> str:
        """
        获取TagRAG上下文
        
        Args:
            func_name (str): 功能名称（英文）
            top_k (int): 返回数量
            
        Returns:
            str: TagRAG上下文
        """
        # 检查缓存
        if func_name in self._tagrag_cache:
            return self._tagrag_cache[func_name]
        
        try:
            # 使用功能名映射获取中文名
            chinese_name = self.FUNCTION_MAPPING.get(func_name, func_name)
            
            result = tag_retrieve(
                query=chinese_name,
                topic_name=self.topic,
                search_column='tag_vec',
                top_k=1,  # 固定召回1条结果
                return_columns=None  # 不限制返回列，避免字段缺失问题
            )
            
            if result['status'] == 'success' and result['results']:
                context_texts = []
                for item in result['results']:
                    # 检查item的结构，可能是{'data': {'text': '...'}} 或直接 {'text': '...'}
                    if 'data' in item and isinstance(item['data'], dict) and 'text' in item['data']:
                        context_texts.append(item['data']['text'])
                    elif 'text' in item:
                        context_texts.append(item['text'])
                    else:
                        log_error(self.logger, f"TagRAG结果缺少text字段: {item}", "Explain")
                
                if context_texts:
                    context = "\n\n".join(context_texts)
                    # 缓存结果
                    self._tagrag_cache[func_name] = context
                    return context
                else:
                    log_error(self.logger, "TagRAG检索结果中没有有效的text字段", "Explain")
                    return ""
            else:
                log_error(self.logger, f"TagRAG检索失败: {result.get('error', '未知错误')}", "Explain")
                return ""
                
        except Exception as e:
            log_error(self.logger, f"TagRAG检索异常: {e}", "Explain")
            return ""

    def _to_single_line(self, obj: Any) -> str:
        """
        将对象折叠为单行字符串，用于减少提示词体积并避免多行JSON。

        Args:
            obj (Any): 任意可序列化对象

        Returns:
            str: 单行字符串表示

        说明:
            - 对于字典/列表，使用紧凑的JSON编码（无空格、无缩进）。
            - 对于其他类型，转换为字符串并折叠多余空白为单个空格。
        """
        try:
            if isinstance(obj, (dict, list)):
                return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str)
            text = str(obj)
            # 折叠所有连续空白为单空格，确保为单行
            return " ".join(text.split())
        except Exception as e:
            log_error(self.logger, f"折叠数据为单行字符串失败: {e}", "Explain")
            return str(obj)

    async def _llm_call(self, system_prompt: str, user_prompt: str, model: str,
                         max_tokens: Optional[int] = None, retry: int = 3) -> Optional[str]:
        """
        直接通过DashScope HTTP接口调用LLM（顺序执行，含重试与详细日志）。

        Args:
            system_prompt (str): 系统提示词
            user_prompt (str): 用户提示词
            model (str): 模型名称
            max_tokens (Optional[int]): 最大生成token
            retry (int): 重试次数

        Returns:
            Optional[str]: 返回纯文本内容，如失败则返回None
        """
        import asyncio
        import aiohttp
        import traceback

        api_key = get_api_key()
        if not api_key:
            log_error(self.logger, "未配置DASHSCOPE_API_KEY，无法调用LLM", "Explain")
            return None

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        params = {"max_tokens": max_tokens or int(self.llm_config.get("max_tokens", 2000))}
        payload = {
            "model": model,
            "input": {"messages": messages},
            "parameters": params
        }

        # 读取超时与重试配置
        try:
            cfg_retry = int(self.llm_config.get("retry", retry))
        except Exception:
            cfg_retry = retry
        try:
            timeout_total = int(self.llm_config.get("timeout_total", 180))
            timeout_connect = int(self.llm_config.get("timeout_connect", 10))
            timeout_read = int(self.llm_config.get("timeout_read", max(30, timeout_total - timeout_connect - 20)))
        except Exception:
            timeout_total, timeout_connect, timeout_read = 180, 10, 120

        for attempt in range(cfg_retry):
            try:
                timeout = aiohttp.ClientTimeout(total=timeout_total, connect=timeout_connect, sock_read=timeout_read)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(
                        "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation",
                        json=payload,
                        headers=headers
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            text = data.get("output", {}).get("text")
                            if text and isinstance(text, str) and text.strip():
                                return text
                            else:
                                log_error(self.logger, f"LLM返回200但text为空 (尝试 {attempt+1}/{cfg_retry})", "Explain")
                        else:
                            body = await resp.text()
                            log_error(self.logger, f"HTTP {resp.status} (尝试 {attempt+1}/{cfg_retry})", "Explain")
                            log_error(self.logger, f"错误片段: {body[:300]}", "Explain")
            except asyncio.TimeoutError:
                # 提示请求规模，便于排查
                log_error(self.logger, f"LLM调用超时 (尝试 {attempt+1}/{cfg_retry})，system:{len(system_prompt)}字，user:{len(user_prompt)}字", "Explain")
            except Exception as e:
                if attempt == cfg_retry - 1:
                    log_error(self.logger, f"LLM调用异常: {e}", "Explain")
                    log_error(self.logger, f"完整堆栈: {traceback.format_exc()}", "Explain")
                else:
                    log_error(self.logger, f"LLM调用异常(尝试 {attempt+1}/{cfg_retry}): {e}", "Explain")

            if attempt < cfg_retry - 1:
                # 指数退避 + 抖动
                import random
                backoff = min(8, 2 ** attempt)
                await asyncio.sleep(backoff + random.uniform(0, 0.5))

        return None

    def _parse_llm_text(self, text: str) -> Dict[str, str]:
        """
        解析LLM返回文本，优先解析为JSON，提取'explain'或'analysis'。

        Args:
            text (str): 原始文本

        Returns:
            Dict[str, str]: 规范化的结果字典，形如{"explain": "..."}
        """
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                if 'explain' in parsed and isinstance(parsed['explain'], str):
                    return {"explain": parsed['explain']}
                if 'analysis' in parsed and isinstance(parsed['analysis'], str):
                    return {"explain": parsed['analysis']}
                if 'data' in parsed:
                    return {"explain": parsed['data'] if isinstance(parsed['data'], str) else str(parsed['data'])}
                return {"explain": str(parsed)}
            return {"explain": str(parsed)}
        except json.JSONDecodeError:
            return {"explain": text}
    
    async def generate_explanation(self, func_name: str, data: Dict, target: str, channel_name: str = None) -> Optional[Dict]:
        """
        生成解读内容
        
        Args:
            func_name (str): 功能名称
            data (Dict): 分析数据
            target (str): 目标类型
            channel_name (str, optional): 渠道名称
            
        Returns:
            Optional[Dict]: 解读结果
        """
        try:
            
            # 加载提示词
            prompt_config = self.load_prompt(func_name)
            if not prompt_config:
                log_error(self.logger, f"未找到{func_name}的提示词配置", "Explain")
                return None
                        
            # 获取TagRAG上下文（使用功能名映射）
            context = await self.get_tagrag_context(func_name)
            
            # 构建完整提示词
            system_prompt = prompt_config['system']
            # 将数据折叠为单行字符串，避免多行JSON带来的提示冗长
            data_compact = self._to_single_line(data)
            user_prompt = prompt_config['user'].format(data=data_compact)
            
            # 添加分析目标类型信息
            if channel_name:
                user_prompt += f"\n\n当前分析渠道：{channel_name}的信息"
            else:
                user_prompt += f"\n\n当前分析范围：所有渠道的信息"
            
            if context:
                user_prompt += f"\n\n仿照下面的格式进行生成：\n{context}"
            
            
            # 使用LLM配置调用大模型（顺序执行）
            model = self.llm_config.get('model', 'qwen-plus')
            text = await self._llm_call(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=model,
                max_tokens=int(self.llm_config.get('max_tokens', 2000)),
                retry=int(self.llm_config.get('retry', 3)),
            )
            if not text:
                log_error(self.logger, f"大模型调用失败，响应为空: {func_name}", "Explain")
                log_error(self.logger, "可能原因: 1)API密钥无效 2)网络连接问题 3)API限流 4)模型服务异常", "Explain")
                log_error(self.logger, "请检查: 1)环境变量DASHSCOPE_API_KEY 2)网络连接 3)API使用量", "Explain")
                return None
            return self._parse_llm_text(text)
                
        except Exception as e:
            log_error(self.logger, f"生成解读失败: {e}", "Explain")
            return None
    
    def save_explanation(self, func_name: str, target: str, explanation: Dict, date: str, end_date: str = None, channel_name: str = None, rag_enhanced: bool = False):
        """
        保存解读结果
        
        Args:
            func_name (str): 功能名称
            target (str): 目标类型
            explanation (Dict): 解读结果
            date (str): 日期
            end_date (str, optional): 结束日期
            channel_name (str, optional): 渠道名称
            rag_enhanced (bool, optional): 是否为RAG增强解读
        """
        try:
            # 构建输出路径
            if end_date:
                folder_name = f"{date}_{end_date}"
            else:
                folder_name = date
                
            explain_dir = bucket("explain", self.topic, folder_name)
            
            if target == "总体":
                output_dir = explain_dir / func_name / "总体"
            else:
                output_dir = explain_dir / func_name / channel_name
            
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # 保存文件（RAG增强解读使用不同的文件名）
            if rag_enhanced:
                output_file = output_dir / f"{func_name}_rag_enhanced.json"
            else:
                output_file = output_dir / f"{func_name}.json"
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(explanation, f, ensure_ascii=False, indent=2)
            
            # 根据目标类型显示不同的完成日志
            if rag_enhanced:
                if target == "总体":
                    log_success(self.logger, f"总体RAG增强解读：{func_name} | 保存成功", "Explain")
                else:
                    log_success(self.logger, f"渠道RAG增强解读：{func_name} | {channel_name} | 保存成功", "Explain")
            else:
                if target == "总体":
                    log_success(self.logger, f"总体解读：{func_name} | 解读成功", "Explain")
                else:
                    log_success(self.logger, f"渠道解读：{func_name} | {channel_name} | 解读成功", "Explain")
            
        except Exception as e:
            log_error(self.logger, f"保存解读结果失败: {e}", "Explain")
    
    def load_rag_prompt(self) -> Optional[Dict[str, str]]:
        """
        加载RAG二次解读提示词配置
        
        Returns:
            Optional[Dict[str, str]]: 提示词配置
        """
        try:
            project_root = get_project_root()
            prompt_file = project_root / "configs" / "prompt" / "explain_rag" / f"{self.topic}.yaml"
            
            if not prompt_file.exists():
                log_error(self.logger, f"未找到专题 {self.topic} 的RAG解读提示词文件: {prompt_file}", "Explain")
                return None
            
            import yaml
            with open(prompt_file, 'r', encoding='utf-8') as f:
                prompt_config = yaml.safe_load(f)
            
            if 'prompts' not in prompt_config:
                log_error(self.logger, f"RAG解读提示词文件格式错误，缺少prompts字段", "Explain")
                return None
                
            prompts = prompt_config['prompts']
            if 'rag_explain' not in prompts:
                log_error(self.logger, f"未找到rag_explain的提示词配置", "Explain")
                return None
                
            return prompts['rag_explain']
            
        except Exception as e:
            log_error(self.logger, f"加载RAG解读提示词失败: {e}", "Explain")
            return None
    
    async def generate_rag_enhanced_explanation(self, func_name: str, first_explanation: Dict, data: Dict, target: str, channel_name: str = None) -> Optional[Dict]:
        """
        基于RAG检索生成增强解读（二次解读）
        
        Args:
            func_name (str): 功能名称
            first_explanation (Dict): 第一次生成的解读结果
            data (Dict): 原始分析数据
            target (str): 目标类型
            channel_name (str, optional): 渠道名称
            
        Returns:
            Optional[Dict]: 增强后的解读结果
        """
        try:
            # 提取第一次解读的文本作为查询
            explain_text = first_explanation.get('explain', '')
            if not explain_text:
                log_error(self.logger, f"第一次解读结果为空，无法进行RAG检索", "Explain")
                return None
            
            log_success(self.logger, f"开始RAG检索增强解读: {func_name}", "Explain")
            
            # 使用解读文本作为查询，进行RAG检索与增强解读（顺序执行）
            # 参数：实体数量20，句子数量10，文本块数量5，启用LLM整理，扩展性模式，只返回LLM
            try:
                # 加载LLM配置
                llm_config_path = get_configs_root() / "llm.yaml"
                with open(llm_config_path, 'r', encoding='utf-8') as f:
                    llm_config = yaml.safe_load(f)
                
                # 获取router_retrieve配置
                router_config = llm_config.get('router_retrieve_llm', {})
                embedding_config = llm_config.get('embedding_llm', {})
                
                llm_model = router_config.get('model', 'qwen-plus')
                embedding_model = embedding_config.get('model', 'text-embedding-v4')
                
                # 提示词文件由topic自动确定
                prompts_file = f"{self.topic}.yaml"
                
                # 创建检索器，传入仅含api_key的轻量对象，避免使用系统Qwen客户端
                qwen_stub = SimpleNamespace(api_key=get_api_key())
                searcher = AdvancedRAGSearcher(
                    topic=self.topic,
                    logger=self.logger,
                    qwen_client=qwen_stub,
                    llm_model=llm_model,
                    embedding_model=embedding_model,
                    prompts_file=prompts_file
                )
                
                # 设置检索参数
                params = SearchParams(
                    query_topic=self.topic,
                    query_text=explain_text,
                    search_mode="mixed",  # 混合检索模式
                    topk_graphrag=20,  # 实体数量20
                    topk_normalrag=10,  # 句子数量10
                    topk_tagrag=5,  # 文本块数量5
                    enable_llm_summary=True,  # 启用LLM整理
                    llm_summary_mode="supplement",  # 扩展性模式
                    return_format="llm_only"  # 只返回LLM整理结果
                )
                
                # 执行异步检索
                rag_result = await searcher.search(params)
            
            except Exception as e:
                log_error(self.logger, f"RAG检索异常: {e}", "Explain")
                import traceback
                log_error(self.logger, f"完整堆栈: {traceback.format_exc()}", "Explain")
                return None
            
            # 检查返回结果
            if not rag_result or 'llm_summary' not in rag_result:
                log_error(self.logger, f"RAG检索未返回有效的LLM整理结果", "Explain")
                return None
            
            # 获取LLM整理的资料
            llm_summary = rag_result.get('llm_summary', '')
            if not llm_summary or llm_summary == "未启用LLM整理，无法返回LLM结果":
                log_error(self.logger, f"RAG检索未返回有效的LLM整理结果", "Explain")
                return None
            
            log_success(self.logger, f"RAG检索成功，获取到LLM整理资料", "Explain")
            
            # 加载RAG解读提示词
            rag_prompt_config = self.load_rag_prompt()
            if not rag_prompt_config:
                log_error(self.logger, f"未找到RAG解读提示词配置", "Explain")
                return None
            
            # 构建二次解读提示词
            system_prompt = rag_prompt_config.get('system', '')
            user_prompt_template = rag_prompt_config.get('user', '')
            
            # 格式化提示词
            user_prompt = user_prompt_template.format(
                first_explanation=explain_text,
                rag_materials=llm_summary,
                analysis_data=self._to_single_line(data)
            )
            
            # 添加分析目标类型信息
            if channel_name:
                user_prompt += f"\n\n当前分析渠道：{channel_name}的信息"
            else:
                user_prompt += f"\n\n当前分析范围：所有渠道的信息"
            
            # 使用LLM配置调用大模型（顺序执行）
            model = self.llm_config.get('model', 'qwen-plus')
            text = await self._llm_call(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=model,
                max_tokens=int(self.llm_config.get('max_tokens', 2000)),
                retry=int(self.llm_config.get('retry', 3)),
            )
            if not text:
                log_error(self.logger, f"RAG增强解读大模型调用失败，响应为空: {func_name}", "Explain")
                return None
            return self._parse_llm_text(text)
                
        except Exception as e:
            log_error(self.logger, f"生成RAG增强解读失败: {e}", "Explain")
            import traceback
            log_error(self.logger, f"完整堆栈: {traceback.format_exc()}", "Explain")
            return None
