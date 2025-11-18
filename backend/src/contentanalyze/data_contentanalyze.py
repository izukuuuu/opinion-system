"""
新闻内容编码分析
"""
import asyncio
import aiohttp
import json
import pandas as pd
import yaml
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from datetime import datetime
from ..utils.setting.paths import get_project_root, get_configs_root, ensure_bucket, get_relative_path
from ..utils.setting.settings import settings
from ..utils.setting.env_loader import get_api_key
from ..utils.logging.logging import setup_logger, log_success, log_error, log_module_start
from ..utils.io.excel import read_csv


class ContentAnalyze:
    """内容分析器"""
    
    def __init__(self, topic: str, start_date: str, end_date: str):
        """
        初始化内容分析器
        
        Args:
            topic (str): 专题名称
            start_date (str): 开始日期字符串
            end_date (str): 结束日期字符串
        """
        self.topic = topic
        self.start_date = start_date
        self.end_date = end_date
        self.date_range = f"{start_date}_{end_date}"
        self.logger = setup_logger(f"ContentAnalyze_{topic}", self.date_range)
        
        # 获取API配置
        self.api_key = get_api_key()
        if not self.api_key:
            raise ValueError("千问API密钥未配置，请在配置文件 credentials.qwen_api_key 中设置")
        
        # 获取LLM配置
        llm_config = settings.get('llm.content_analysis_llm', {})
        self.model = llm_config.get('model', 'qwen-plus')
        self.qps = llm_config.get('qps', 50)
        self.batch_size = llm_config.get('batch_size', 32)
        
        # 加载提示词配置
        self.prompt_config = self._load_prompt_config()
        
        # 动态字段管理
        self.available_fields = set()
        self.field_mappings = {}
        
        # 结果存储
        self.results = []
        
    def _load_prompt_config(self) -> Dict[str, str]:
        """
        加载提示词配置
        
        Returns:
            Dict[str, str]: 提示词配置
        """
        try:
            configs_root = get_configs_root()
            contentanalysis_dir = configs_root / "prompt" / "contentanalysis"
            
            if not contentanalysis_dir.exists():
                raise FileNotFoundError(f"提示词配置目录不存在: {get_relative_path(contentanalysis_dir)}")
            
            # 列出所有yaml文件
            yaml_files = list(contentanalysis_dir.glob("*.yaml"))
            
            # 尝试找到匹配的文件
            prompt_file = None
            for yaml_file in yaml_files:
                if yaml_file.stem == self.topic:
                    prompt_file = yaml_file
                    break
            
            if not prompt_file:
                # 如果没找到精确匹配，尝试使用第一个文件
                if yaml_files:
                    prompt_file = yaml_files[0]
                else:
                    raise FileNotFoundError(f"未找到任何yaml配置文件")
                        
            with open(prompt_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            return config
        except Exception as e:
            log_error(self.logger, f"加载提示词配置失败: {e}", "ContentAnalyze")
            raise
    
    def _analyze_result_fields(self, result: Dict[str, Any]) -> None:
        """
        分析结果字段，更新可用字段集合
        
        Args:
            result (Dict[str, Any]): 分析结果
        """
        if not result:
            return
        
        for key, value in result.items():
            self.available_fields.add(key)
            
            # 如果是列表类型，记录为多选字段
            if isinstance(value, list):
                self.field_mappings[key] = 'multi_select'
            else:
                self.field_mappings[key] = 'single_select'
    
    def _extract_field_value(self, result: Dict[str, Any], field: str) -> str:
        """
        提取字段值，处理多选和单选字段
        
        Args:
            result (Dict[str, Any]): 分析结果
            field (str): 字段名
            
        Returns:
            str: 格式化后的字段值
        """
        if not result or field not in result:
            return ''
        
        value = result[field]
        if isinstance(value, list):
            return ','.join(str(v) for v in value)
        else:
            return str(value)
    
    async def _call_qwen_api(self, session: aiohttp.ClientSession, text: str) -> Optional[Dict[str, Any]]:
        """
        调用千问API进行内容分析
        
        Args:
            session (aiohttp.ClientSession): HTTP会话
            text (str): 待分析文本
            
        Returns:
            Optional[Dict[str, Any]]: 分析结果，失败时返回None
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # 构建完整提示词
        full_prompt = f"{self.prompt_config['system_prompt']}\n\n{self.prompt_config['analysis_prompt']}\n\n请分析以下文本：\n{text}"
        
        data = {
            "model": self.model,
            "input": {
                "messages": [
                    {"role": "user", "content": full_prompt}
                ]
            },
            "parameters": {
                "max_tokens": 2000
            }
        }
        
        try:
            timeout = aiohttp.ClientTimeout(total=60, connect=10, sock_read=30)
            async with session.post(
                "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation",
                json=data,
                headers=headers,
                timeout=timeout
            ) as resp:
                if resp.status == 200:
                    response_data = await resp.json()
                    text_response = response_data.get('output', {}).get('text', '')
                    
                    # 尝试解析JSON结果
                    try:
                        # 提取JSON部分
                        json_start = text_response.find('{')
                        json_end = text_response.rfind('}') + 1
                        if json_start != -1 and json_end > json_start:
                            json_str = text_response[json_start:json_end]
                            result = json.loads(json_str)
                            return result
                        else:
                            log_error(self.logger, f"无法找到有效JSON: {text_response[:200]}", "ContentAnalyze")
                            return None
                    except json.JSONDecodeError as e:
                        log_error(self.logger, f"JSON解析失败: {e}, 响应: {text_response[:200]}", "ContentAnalyze")
                        return None
                else:
                    log_error(self.logger, f"API调用失败，状态码: {resp.status}", "ContentAnalyze")
                    return None
        except asyncio.TimeoutError:
            log_error(self.logger, "API调用超时", "ContentAnalyze")
            return None
        except Exception as e:
            log_error(self.logger, f"API调用异常: {e}", "ContentAnalyze")
            return None
    
    async def _process_batch(self, session: aiohttp.ClientSession, texts: List[str], start_idx: int) -> List[Optional[Dict[str, Any]]]:
        """
        处理一批文本
        
        Args:
            session (aiohttp.ClientSession): HTTP会话
            texts (List[str]): 文本列表
            start_idx (int): 起始索引
            
        Returns:
            List[Optional[Dict[str, Any]]]: 分析结果列表
        """
        tasks = []
        for i, text in enumerate(texts):
            task = self._call_qwen_api(session, text)
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理异常结果
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                log_error(self.logger, f"处理第{start_idx + i}条文本时发生异常: {result}", "ContentAnalyze")
                processed_results.append(None)
            else:
                # 分析字段结构
                if result:
                    self._analyze_result_fields(result)
                processed_results.append(result)
        
        return processed_results
    
    async def analyze_texts(self, texts: List[str]) -> List[Optional[Dict[str, Any]]]:
        """
        分析文本列表
        
        Args:
            texts (List[str]): 待分析文本列表
            
        Returns:
            List[Optional[Dict[str, Any]]]: 分析结果列表
        """
        # 计算批次信息
        total_batches = (len(texts) - 1) // self.batch_size + 1
        
        all_results = []
        
        # 创建HTTP会话
        connector = aiohttp.TCPConnector(limit=100, limit_per_host=20)
        async with aiohttp.ClientSession(connector=connector) as session:
            # 分批处理
            for i in range(0, len(texts), self.batch_size):
                batch_texts = texts[i:i + self.batch_size]
                current_batch = i // self.batch_size + 1
                log_success(self.logger, f"处理批次 {current_batch}/{total_batches}，本批次{len(batch_texts)}条", "ContentAnalyze")
                
                batch_results = await self._process_batch(session, batch_texts, i)
                all_results.extend(batch_results)
                
                # 控制QPS
                if i + self.batch_size < len(texts):
                    await asyncio.sleep(1.0 / self.qps * self.batch_size)
        
        # 统计结果
        success_count = sum(1 for r in all_results if r is not None)
        log_success(self.logger, f"分析完成: 成功{success_count}/{len(texts)}条", "ContentAnalyze")
        
        return all_results
    
    def _save_to_excel(self, results: List[Optional[Dict[str, Any]]], texts: List[str]) -> str:
        """
        保存结果到Excel文件
        
        Args:
            results (List[Optional[Dict[str, Any]]]): 分析结果
            texts (List[str]): 原始文本
            
        Returns:
            str: 保存的文件路径
        """
        # 准备数据
        excel_data = []
        for i, (text, result) in enumerate(zip(texts, results)):
            row = {
                '序号': i + 1,
                '原始文本': text,
                '分析状态': '成功' if result else '失败'
            }
            
            # 动态添加所有可用字段
            for field in self.available_fields:
                row[field] = self._extract_field_value(result, field)
            
            excel_data.append(row)
        
        # 保存到Excel
        output_dir = ensure_bucket('contentanalyze', self.topic, self.date_range)
        excel_file = output_dir / 'contentanalysis.xlsx'
        
        df = pd.DataFrame(excel_data)
        df.to_excel(excel_file, index=False, engine='openpyxl')
        
        return str(excel_file)
    
    def _save_to_json(self, results: List[Optional[Dict[str, Any]]]) -> str:
        """
        保存统计结果到JSON文件
        
        Args:
            results (List[Optional[Dict[str, Any]]]): 分析结果
            
        Returns:
            str: 保存的文件路径
        """
        # 初始化统计结构 - 只保留字段统计
        stats = {}
        
        # 动态统计各字段
        for field in self.available_fields:
            stats[field] = {
                '类型': self.field_mappings.get(field, 'unknown'),
                '分布': {}
            }
        
        # 统计各字段的分布
        for result in results:
            if not result:
                continue
                
            for field in self.available_fields:
                if field not in result:
                    continue
                
                value = result[field]
                field_stats = stats[field]['分布']
                
                if isinstance(value, list):
                    # 多选字段：统计每个选项的出现次数
                    for item in value:
                        item_str = str(item)
                        field_stats[item_str] = field_stats.get(item_str, 0) + 1
                else:
                    # 单选字段：统计值的分布
                    value_str = str(value)
                    field_stats[value_str] = field_stats.get(value_str, 0) + 1
        
        # 保存到JSON
        output_dir = ensure_bucket('contentanalyze', self.topic, self.date_range)
        json_file = output_dir / 'contentanalysis.json'
        
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        
        return str(json_file)
    
    async def run_analysis(self) -> bool:
        """
        运行完整的内容分析流程
        
        Returns:
            bool: 是否成功
        """
        try:
            log_module_start(self.logger, "ContentAnalyze") 

            data_dir = get_project_root() / "data" / "fetch" / self.topic / self.date_range
            news_file = data_dir / "新闻.csv"

            if not news_file.exists():
                # 列出目录内容
                if data_dir.exists():
                    files = list(data_dir.glob("*.csv"))
                    
                    # 尝试找到新闻文件（可能是不同的名称）
                    for csv_file in files:
                        if "新闻" in csv_file.name or "news" in csv_file.name.lower():
                            news_file = csv_file
                            break
                
                if not news_file.exists():
                    log_error(self.logger, f"新闻文件不存在: {get_relative_path(news_file)}", "ContentAnalyze")
                    return False
            
            # 读取CSV文件
            try:
                df = read_csv(str(news_file))
                if df.empty:
                    log_error(self.logger, "新闻数据为空", "ContentAnalyze")
                    return False
                log_success(self.logger, f"成功读取新闻数据，共{len(df)}条", "ContentAnalyze")
            except Exception as e:
                log_error(self.logger, f"读取CSV文件失败: {e}", "ContentAnalyze")
                return False
            
            # 获取文段列（假设列名为'content'或'文段'）
            content_column = None
            for col in ['contents', '文段', '正文', '内容']:
                if col in df.columns:
                    content_column = col
                    break
            
            if not content_column:
                log_error(self.logger, "未找到文段列", "ContentAnalyze")
                return False
            
            texts = df[content_column].dropna().astype(str).tolist()
            
            # 2. 分析文本
            results = await self.analyze_texts(texts)
            
            # 保存Excel
            excel_file = self._save_to_excel(results, texts)
            
            # 保存JSON统计
            json_file = self._save_to_json(results)
            
            return True
            
        except Exception as e:
            log_error(self.logger, f"内容分析失败: {e}", "ContentAnalyze")
            return False


async def run_content_analysis(topic: str, start_date: str, end_date: str) -> bool:
    """
    运行内容分析
    
    Args:
        topic (str): 专题名称
        start_date (str): 开始日期字符串
        end_date (str): 结束日期字符串
        
    Returns:
        bool: 是否成功
    """
    analyzer = ContentAnalyze(topic, start_date, end_date)
    return await analyzer.run_analysis()


def run_content_analysis_sync(topic: str, start_date: str, end_date: str) -> bool:
    """
    同步运行内容分析
    
    Args:
        topic (str): 专题名称
        start_date (str): 开始日期字符串
        end_date (str): 结束日期字符串
        
    Returns:
        bool: 是否成功
    """
    return asyncio.run(run_content_analysis(topic, start_date, end_date))
