"""
解读功能基础模块
"""
import json
import asyncio
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional
from ...utils.logging.logging import setup_logger, log_success, log_error
from ...utils.setting.paths import bucket, get_project_root
from ...utils.ai.qwen import QwenClient
from ...utils.rag.tagrag.tag_retrieve_data import tag_retrieve


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
        'contentanalyze': '内容分析'
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
        self.qwen_client = QwenClient()
        self._tagrag_cache = {}  # 缓存TagRAG结果
        
        # 加载LLM配置
        self.llm_config = self._load_llm_config()
        
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
            user_prompt = prompt_config['user'].format(data=json.dumps(data, ensure_ascii=False, indent=2))
            
            # 添加分析目标类型信息
            if channel_name:
                user_prompt += f"\n\n当前分析渠道：{channel_name}的信息"
            else:
                user_prompt += f"\n\n当前分析范围：所有渠道的信息"
            
            if context:
                user_prompt += f"\n\n仿照下面的格式进行生成：\n{context}"            
            
            # 使用LLM配置调用大模型
            model = self.llm_config.get('model', 'qwen-plus')
            
            # 重试机制
            max_retries = 3
            response = None
            
            for attempt in range(max_retries):
                try:
                    response = await self.qwen_client.call(
                        prompt=f"系统提示：{system_prompt}\n\n用户请求：{user_prompt}",
                        model=model
                    )
                    if response and 'text' in response and response['text'].strip():
                        break
                    else:
                        log_error(self.logger, f"大模型返回空响应: {func_name} (尝试 {attempt + 1}/{max_retries})", "Explain")
                        if attempt < max_retries - 1:
                            # 等待一段时间再重试
                            await asyncio.sleep(1)
                except Exception as e:
                    log_error(self.logger, f"大模型调用异常: {func_name} | {str(e)} (尝试 {attempt + 1}/{max_retries})", "Explain")
                    if attempt < max_retries - 1:
                        # 等待一段时间再重试
                        await asyncio.sleep(1)
                    if attempt == max_retries - 1:
                        raise e
            
            if response and 'text' in response:
                try:
                    # 尝试解析JSON响应
                    explanation = json.loads(response['text'])
                    
                    # 提取分析语言，只保留大模型的分析结果
                    if isinstance(explanation, dict):
                        if 'analysis' in explanation:
                            # 如果有analysis字段，使用analysis内容
                            return {"explain": explanation['analysis']}
                        elif 'explain' in explanation:
                            # 如果有explain字段，直接使用
                            return {"explain": explanation['explain']}
                        elif 'data' in explanation:
                            # 如果data字段是字符串，直接使用
                            if isinstance(explanation['data'], str):
                                return {"explain": explanation['data']}
                            else:
                                # 如果data是数组或其他格式，转换为字符串
                                return {"explain": str(explanation['data'])}
                        else:
                            # 如果没有找到合适字段，使用整个响应
                            return {"explain": str(explanation)}
                    else:
                        return {"explain": str(explanation)}
                except json.JSONDecodeError as e:
                    # 如果不是JSON格式，包装成explain格式
                    return {
                        "explain": response['text']
                    }
            else:
                log_error(self.logger, f"大模型调用失败，响应为空: {func_name}", "Explain")
                log_error(self.logger, f"可能原因: 1)API密钥无效 2)网络连接问题 3)API限流 4)模型服务异常", "Explain")
                log_error(self.logger, f"请检查: 1)环境变量DASHSCOPE_API_KEY 2)网络连接 3)API使用量", "Explain")
                return None
                
        except Exception as e:
            log_error(self.logger, f"生成解读失败: {e}", "Explain")
            return None
    
    def save_explanation(self, func_name: str, target: str, explanation: Dict, date: str, end_date: str = None, channel_name: str = None):
        """
        保存解读结果
        
        Args:
            func_name (str): 功能名称
            target (str): 目标类型
            explanation (Dict): 解读结果
            date (str): 日期
            end_date (str, optional): 结束日期
            channel_name (str, optional): 渠道名称
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
            
            # 保存文件
            output_file = output_dir / f"{func_name}.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(explanation, f, ensure_ascii=False, indent=2)
            
            # 根据目标类型显示不同的完成日志
            if target == "总体":
                log_success(self.logger, f"总体解读：{func_name} | 解读成功", "Explain")
            else:
                log_success(self.logger, f"渠道解读：{func_name} | {channel_name} | 解读成功", "Explain")
            
        except Exception as e:
            log_error(self.logger, f"保存解读结果失败: {e}", "Explain")
