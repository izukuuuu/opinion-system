#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BERTopic + Qwen 主题分析数据处理模块
输入: data/fetch/{topic}/{date_range}/各渠道.csv（包含 contents 列，自动合并所有渠道）
依赖: configs/stopwords.txt, configs/userdict.txt(可选)
输出: data/topic/{topic}/{date_range}/{1..5}.json
"""
import re
import json
import warnings
from pathlib import Path
from typing import List, Dict, Tuple, Optional

# 严格抑制所有警告（在导入可能产生警告的库之前）
warnings.filterwarnings("ignore")  # 抑制所有警告
warnings.simplefilter("ignore")  # 设置默认过滤器为忽略
# 特别抑制 pkg_resources 相关警告
warnings.filterwarnings("ignore", message=".*pkg_resources.*")
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

import pandas as pd
import numpy as np
import jieba
import yaml
from openai import OpenAI
from bertopic import BERTopic
from umap import UMAP
from hdbscan import HDBSCAN
from sklearn.feature_extraction.text import CountVectorizer
from collections import defaultdict

# 抑制jieba的日志输出（设置为ERROR级别，减少输出）
jieba.setLogLevel(60)  # 60 = ERROR级别，可以抑制"Building prefix dict..."等信息

from ..utils.logging.logging import (
    setup_logger, log_success, log_error, log_module_start, log_save_success
)
from ..utils.setting.env_loader import get_api_key, load_env_file
from ..utils.setting.paths import get_project_root, bucket
from ..utils.io.excel import read_csv


# 配置常量
TARGET_TOPICS = 8  # 大模型合并后的目标主题数
LLM_MODEL_NAME = "qwen-plus"

def _default_paths(topic: str, start_date: str, end_date: str = None) -> Dict[str, Path]:
    project_root = get_project_root()
    configs_root = project_root / "configs"
    # 使用fetch目录，与analyze模块一致
    if end_date:
        folder_name = f"{start_date}_{end_date}"
    else:
        folder_name = start_date
    fetch_dir = bucket("fetch", topic, folder_name)
    userdict = configs_root / "userdict.txt"  # 可选：用户词典，使用项目统一配置
    stopwords = configs_root / "stopwords.txt"  # 使用项目统一配置
    # 输出路径使用相同的日期范围格式
    out_analyze = bucket("topic", topic, folder_name)  # 输出到data/topic/{topic}/{date_range}/
    return {
        "fetch_dir": fetch_dir,
        "userdict": userdict,
        "stopwords": stopwords,
        "out_analyze": out_analyze,
    }


def _load_and_merge_fetch_data(fetch_dir: Path, logger) -> pd.DataFrame:
    """
    从fetch目录读取所有CSV文件并合并（与analyze模块一致）
    
    Args:
        fetch_dir (Path): fetch目录路径
        logger: 日志记录器
    
    Returns:
        pd.DataFrame: 合并后的数据框
    """
    if not fetch_dir.exists():
        log_error(logger, f"fetch目录不存在: {fetch_dir}", "TopicBertopic")
        return pd.DataFrame()
    
    # 读取总体.csv文件（包含所有渠道数据）
    overall_file = fetch_dir / "总体.csv"
    if overall_file.exists():
        try:
            df = read_csv(overall_file)
            if not df.empty:
                log_success(logger, f"读取总体数据: {len(df)}条", "TopicBertopic")
                # 去重（基于contents字段）
                before_count = len(df)
                df = df.drop_duplicates(subset=['contents'], keep='last')
                after_count = len(df)
                if before_count != after_count:
                    log_success(logger, f"去重: {before_count} -> {after_count}", "TopicBertopic")
                log_success(logger, f"合并完成，共{len(df)}条数据", "TopicBertopic")
                return df
        except Exception as e:
            log_error(logger, f"读取总体数据失败: {e}", "TopicBertopic")
    
    # 如果没有总体.csv，则读取各渠道CSV文件并合并
    csv_files = sorted([f for f in fetch_dir.glob("*.csv") if f.name != "总体.csv"])
    if not csv_files:
        log_error(logger, f"未找到CSV文件: {fetch_dir}", "TopicBertopic")
        return pd.DataFrame()
    
    log_success(logger, f"找到{len(csv_files)}个渠道CSV文件", "TopicBertopic")
    
    # 读取并合并所有文件
    all_data = []
    for file_path in csv_files:
        try:
            df = read_csv(file_path)
            if not df.empty:
                all_data.append(df)
                log_success(logger, f"读取: {file_path.name} - {len(df)}条", "TopicBertopic")
        except Exception as e:
            log_error(logger, f"读取失败 {file_path.name}: {e}", "TopicBertopic")
            continue
    
    if not all_data:
        log_error(logger, "没有读取到任何数据", "TopicBertopic")
        return pd.DataFrame()
    
    # 合并所有数据
    merged_df = pd.concat(all_data, ignore_index=True)
    
    # 去重（基于contents字段）
    before_count = len(merged_df)
    merged_df = merged_df.drop_duplicates(subset=['contents'], keep='last')
    after_count = len(merged_df)
    
    if before_count != after_count:
        log_success(logger, f"合并后去重: {before_count} -> {after_count}", "TopicBertopic")
    
    log_success(logger, f"合并完成，共{len(merged_df)}条数据", "TopicBertopic")
    return merged_df


def _clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'[^\u4e00-\u9fa5\u3000-\u303f0-9，。！？；：、（）《》【】""''\s]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _clean_batch(texts: List[str]) -> Tuple[List[str], Dict[str, int]]:
    cleaned, seen = [], set()
    stats = {"total": 0, "duplicates": 0, "final": 0}
    for t in texts:
        stats["total"] += 1
        ct = _clean_text(t)
        if ct in seen:
            stats["duplicates"] += 1
            continue
        seen.add(ct)
        if ct:
            cleaned.append(ct)
    stats["final"] = len(cleaned)
    return cleaned, stats


def _load_stopwords(path: Path) -> List[str]:
    if path.exists():
        return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return []


def _segment(texts: List[str], stopwords: List[str], userdict: Optional[Path]) -> List[str]:
    if userdict and userdict.exists():
        jieba.load_userdict(str(userdict))
    stopset = set(stopwords)
    result: List[str] = []
    for t in texts:
        words = [w for w in jieba.cut(t) if len(w) >= 2 and not w.isdigit() and w not in stopset]
        result.append(" ".join(words))
    return result


def _embed(batch_texts: List[str], api_key: str, logger=None, base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
           model: str = "text-embedding-v4", dimensions: int = 1024, batch_size: int = 10) -> np.ndarray:
    if not batch_texts:
        return np.array([])
    
    # 处理超长文本，保留原始索引
    MAX_INPUT_LENGTH = 8192
    processed_texts = []
    valid_indices = []
    truncated_count = 0
    
    for idx, text in enumerate(batch_texts):
        if len(text) > MAX_INPUT_LENGTH:
            processed_texts.append(text[:MAX_INPUT_LENGTH])
            valid_indices.append(idx)
            truncated_count += 1
        elif len(text) == 0:
            # 跳过空文本，但记录索引
            continue
        else:
            processed_texts.append(text)
            valid_indices.append(idx)
    
    if truncated_count > 0:
        if logger:
            log_success(logger, f"{truncated_count}条文本因超长被截断", "TopicBertopic")
    
    if not processed_texts:
        return np.array([])
    
    # 生成向量
    client = OpenAI(api_key=api_key, base_url=base_url)
    all_vecs: List[List[float]] = []
    for i in range(0, len(processed_texts), batch_size):
        sub = processed_texts[i:i + batch_size]
        resp = client.embeddings.create(model=model, input=sub, dimensions=dimensions, encoding_format="float")
        all_vecs.extend([item.embedding for item in resp.data])
    
    # 如果有空文本，填充零向量
    if len(valid_indices) < len(batch_texts):
        result_vecs = np.zeros((len(batch_texts), dimensions), dtype=np.float32)
        for i, vec in enumerate(all_vecs):
            result_vecs[valid_indices[i]] = vec
        return result_vecs
    
    return np.array(all_vecs, dtype=np.float32)


def _build_bertopic() -> BERTopic:
    umap_model = UMAP(n_neighbors=15, n_components=5, min_dist=0.0, metric='cosine', random_state=42)
    hdbscan_model = HDBSCAN(min_cluster_size=15, min_samples=5, metric='euclidean')
    vectorizer_model = CountVectorizer(stop_words=['控烟', '吸烟'])
    return BERTopic(
        nr_topics=30,
        top_n_words=20,
        vectorizer_model=vectorizer_model,
        umap_model=umap_model,
        hdbscan_model=hdbscan_model,
        language="multilingual",
        calculate_probabilities=False,
        verbose=False  # 关闭BERTopic的详细日志输出
    )


def _generate_jsons(topic_model: BERTopic, documents: List[str], embeddings: np.ndarray,
                    out_dir: Path, logger) -> Dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    topic_info = topic_model.get_topic_info()
    topics = topic_model.topics_

    umap_2d = UMAP(n_neighbors=15, n_components=2, min_dist=0.0, metric='cosine', random_state=42)
    coords = umap_2d.fit_transform(embeddings)

    # 主题文档统计
    topic_docs: Dict[str, Dict] = {}
    for tid in topic_info['Topic']:
        if tid != -1:
            idxs = [i for i, t in enumerate(topics) if t == tid]
            topic_docs[f"主题{tid}"] = {"文档数": len(idxs), "文档ID": idxs}

    # 主题关键词
    topic_keywords: Dict[str, Dict] = {}
    for tid in topic_info['Topic']:
        if tid != -1:
            kws = topic_model.get_topic(tid)
            top20 = kws[:20] if len(kws) >= 20 else kws
            topic_keywords[f"主题{tid}"] = {"关键词": [[w, float(s)] for w, s in top20]}

    # 文档2D坐标
    doc_coords = [
        {"doc_id": i, "topic_id": int(topics[i]), "x": float(coords[i][0]), "y": float(coords[i][1])}
        for i in range(len(documents))
    ]

    stats_result = {
        "主题文档统计": topic_docs,
        "主题关键词": topic_keywords,
        "文档2D坐标": doc_coords,
    }

    p1 = out_dir / "1主题统计结果.json"
    p2 = out_dir / "2主题关键词.json"
    p3 = out_dir / "3文档2D坐标.json"
    p1.write_text(json.dumps(stats_result, ensure_ascii=False, indent=2), encoding="utf-8")
    p2.write_text(json.dumps(topic_keywords, ensure_ascii=False, indent=2), encoding="utf-8")
    p3.write_text(json.dumps(doc_coords, ensure_ascii=False, indent=2), encoding="utf-8")

    return stats_result


async def _call_llm_recluster(topic_stats: Dict, topic: str, logger) -> Optional[Dict]:
    """调用大模型进行主题合并"""
    try:
        client = OpenAI(api_key=get_api_key(), base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
        
        input_data = {"主题信息": {}}
        for topic_key, topic_info in topic_stats["主题文档统计"].items():
            keywords = topic_stats["主题关键词"][topic_key]["关键词"]
            input_data["主题信息"][topic_key] = {
                "文档数": topic_info["文档数"],
                "关键词": keywords[:20]
            }
        
        # 加载提示词配置：根据主题动态加载对应的yaml文件
        prompt_config = _load_prompt(f"topic_bertopic/{topic}.yaml", "topic_bertopic_recluster", logger)
        if not prompt_config:
            log_error(logger, "无法加载再聚类提示词，使用默认提示词", "TopicBertopic")
            prompt_config = {
                'system': '你是一个专业的控烟领域主题分析专家，擅长将相似的控烟相关主题进行归纳和合并，并对其进行命名。',
                'user': f"""分析以下控烟相关主题，将语义相似的主题合并为{TARGET_TOPICS}个左右的主题。\n\n输入数据：\n{{input_data}}\n\n请直接输出JSON，不要其他内容。"""
            }
        
        # 格式化提示词
        user_prompt = prompt_config['user'].format(
            TARGET_TOPICS=TARGET_TOPICS,
            input_data=json.dumps(input_data, ensure_ascii=False, indent=2)
        )
        
        response = client.chat.completions.create(
            model=LLM_MODEL_NAME,
            messages=[
                {"role": "system", "content": prompt_config['system']},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.1,
            max_tokens=4000
        )
        
        result_text = response.choices[0].message.content.strip()
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0].strip()
        elif "```" in result_text:
            result_text = result_text.split("```")[1].split("```")[0].strip()
        result_text = result_text.strip()
        
        try:
            merge_result = json.loads(result_text)
            log_success(logger, "大模型合并建议获取成功", "TopicBertopic")
            return merge_result
        except json.JSONDecodeError as e:
            log_error(logger, f"JSON解析失败: {e}", "TopicBertopic")
            log_error(logger, f"响应长度: {len(result_text)}, 前200字符: {result_text[:200]}", "TopicBertopic")
            return None
        
    except Exception as e:
        log_error(logger, f"大模型再聚类调用失败: {e}", "TopicBertopic")
        import traceback
        log_error(logger, f"完整堆栈: {traceback.format_exc()}", "TopicBertopic")
        return None


def _calculate_reclustered_keywords(topic_stats: Dict, merge_result: Dict, naming_results: Dict) -> Dict:
    """根据合并方案重新计算关键词权重"""
    reclustered_topics = {}
    
    for merge_group in merge_result["合并方案"]:
        new_topic_name = merge_group["新主题名称"]
        topic_naming = naming_results.get(new_topic_name, f"主题{len(reclustered_topics)}")
        original_topics = merge_group["原始主题集合"]
        topic_description = merge_group["主题描述"]
        
        if not re.match(r'^新主题\d+$', new_topic_name):
            new_topic_name = f"新主题{len(reclustered_topics)}"
        
        all_doc_ids = []
        keyword_weights = defaultdict(float)
        total_original_docs = 0
        
        for original_topic in original_topics:
            if original_topic in topic_stats["主题文档统计"]:
                doc_count = topic_stats["主题文档统计"][original_topic]["文档数"]
                doc_ids = topic_stats["主题文档统计"][original_topic]["文档ID"]
                keywords = topic_stats["主题关键词"][original_topic]["关键词"]
                
                all_doc_ids.extend(doc_ids)
                total_original_docs += doc_count
                
                for keyword, weight in keywords:
                    keyword_weights[keyword] += weight * doc_count
        
        new_doc_count = len(all_doc_ids)
        if new_doc_count == 0:
            continue
        
        recalculated_keywords = []
        for keyword, total_weight in keyword_weights.items():
            if total_original_docs > 0:
                new_weight = (total_weight / total_original_docs) * (total_original_docs / new_doc_count)
                recalculated_keywords.append([keyword, new_weight])
        
        recalculated_keywords.sort(key=lambda x: x[1], reverse=True)
        top_20_keywords = recalculated_keywords[:20]
        
        reclustered_topics[new_topic_name] = {
            "主题命名": topic_naming,
            "原始主题集合": original_topics,
            "文档数": new_doc_count,
            "主题描述": topic_description,
            "文档ID": all_doc_ids,
            "关键词": top_20_keywords
        }
    
    return reclustered_topics


async def _generate_reclustered_json(topic_stats: Dict, topic: str, out_dir: Path, logger) -> Optional[Dict]:
    """生成大模型再聚类结果JSON"""
    merge_result = await _call_llm_recluster(topic_stats, topic, logger)
    if not merge_result:
        log_error(logger, "无法获取大模型合并建议", "TopicBertopic")
        return None
    
    naming_results = {}
    for merge_group in merge_result["合并方案"]:
        new_topic_name = merge_group["新主题名称"]
        topic_naming = merge_group.get("主题命名", "")
        if topic_naming:
            naming_results[new_topic_name] = topic_naming
    
    reclustered_topics = _calculate_reclustered_keywords(topic_stats, merge_result, naming_results)
    
    final_result = {}
    reclustered_keywords_data = {}
    
    for topic_name, topic_info in reclustered_topics.items():
        if topic_info["文档数"] == 0:
            continue
        
        final_result[topic_name] = {
            "主题命名": topic_info["主题命名"],
            "原始主题集合": topic_info["原始主题集合"],
            "文档数": topic_info["文档数"],
            "主题描述": topic_info["主题描述"],
            "文档ID": topic_info["文档ID"],
            "关键词": topic_info["关键词"]
        }
        
        reclustered_keywords_data[topic_name] = {
            "主题命名": topic_info["主题命名"],
            "关键词": topic_info["关键词"]
        }
    
    # 保存JSON文件
    p4 = out_dir / "4大模型再聚类结果.json"
    p5 = out_dir / "5大模型主题关键词.json"
    p4.write_text(json.dumps(final_result, ensure_ascii=False, indent=2), encoding="utf-8")
    p5.write_text(json.dumps(reclustered_keywords_data, ensure_ascii=False, indent=2), encoding="utf-8")
    
    return final_result


def _load_prompt(file_path: str, prompt_key: str, logger) -> Optional[Dict[str, str]]:
    """加载提示词配置"""
    try:
        project_root = get_project_root()
        prompt_file = project_root / "configs" / "prompt" / file_path
        
        if not prompt_file.exists():
            log_error(logger, f"未找到提示词文件: {prompt_file}", "TopicBertopic")
            return None
        
        with open(prompt_file, 'r', encoding='utf-8') as f:
            prompt_config = yaml.safe_load(f)
        
        if 'prompts' not in prompt_config:
            log_error(logger, "提示词文件格式错误，缺少prompts字段", "TopicBertopic")
            return None
        
        prompts = prompt_config['prompts']
        if prompt_key not in prompts:
            log_error(logger, f"未找到{prompt_key}的提示词配置", "TopicBertopic")
            return None
        
        return prompts[prompt_key]
        
    except Exception as e:
        log_error(logger, f"加载提示词失败: {e}", "TopicBertopic")
        return None


def run_topic_bertopic(topic: str, start_date: str, end_date: str = None,
                       fetch_dir: Optional[str] = None,
                       userdict: Optional[str] = None, stopwords: Optional[str] = None) -> bool:
    # 使用日期范围格式作为日志标识
    date_range = f"{start_date}_{end_date}" if end_date else start_date
    logger = setup_logger(topic, date_range)
    log_module_start(logger, "TopicBertopic")

    paths = _default_paths(topic, start_date, end_date)
    fetch_path = Path(fetch_dir) if fetch_dir else paths["fetch_dir"]
    userdict_path = Path(userdict) if userdict else paths["userdict"]
    stopwords_path = Path(stopwords) if stopwords else paths["stopwords"]
    out_analyze = paths["out_analyze"]

    try:
        # 从fetch目录读取并合并所有CSV文件（与analyze模块一致）
        df = _load_and_merge_fetch_data(fetch_path, logger)
        if df.empty:
            log_error(logger, "未读取到任何数据", "TopicBertopic")
            return False

        # 查找contents列
        text_col = None
        for c in df.columns:
            if 'contents' in str(c).lower():
                text_col = c
                break
        if not text_col:
            log_error(logger, "CSV中未找到包含'contents'的列", "TopicBertopic")
            return False
        texts = [str(x) for x in df[text_col].tolist() if str(x).strip() and str(x).lower() not in ['nan','none','']]

        # 清洗
        cleaned, stats = _clean_batch(texts)

        # 分词
        sw = _load_stopwords(stopwords_path)
        seg = _segment(cleaned, sw, userdict_path)

        # 向量化
        load_env_file()  # 确保.env文件被加载
        api_key = get_api_key()
        if not api_key:
            log_error(logger, "未配置API密钥，请在.env文件中设置DASHSCOPE_API_KEY", "TopicBertopic")
            return False
        vecs = _embed(seg, api_key, logger)
        if vecs.size == 0:
            log_error(logger, "向量化失败", "TopicBertopic")
            return False

        # 主题建模
        model = _build_bertopic()
        model.fit_transform(seg, embeddings=vecs)

        # 生成3个JSON
        stats_json = _generate_jsons(model, seg, vecs, out_analyze, logger)

        # 大模型再聚类，生成第4、5个JSON
        import asyncio
        asyncio.run(_generate_reclustered_json(stats_json, topic, out_analyze, logger))

        log_success(logger, "主题分析完成", "TopicBertopic")
        return True
    except Exception as e:
        log_error(logger, f"异常: {e}", "TopicBertopic")
        return False


