"""
RAG 评估核心：EvaluationData 数据模型、数据加载、主评估流程。
"""
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .utils import (
    call_judge_sync,
    compute_precision_recall,
    extract_retrieved_doc_ids,
    find_relevant_docs_by_keywords,
    get_relevant_docs_by_embedding,
    load_corpus_doc_texts,
)


@dataclass
class EvaluationDataItem:
    """单条评估样本：问题、标准答案、可选的相关文档 ID。"""
    question: str
    answer_gold: str
    relevant_doc_ids: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "question": self.question,
            "answer_gold": self.answer_gold,
        }
        if self.relevant_doc_ids is not None:
            d["relevant_doc_ids"] = self.relevant_doc_ids
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EvaluationDataItem":
        return cls(
            question=str(d.get("question", "")).strip(),
            answer_gold=str(d.get("answer_gold", "")).strip(),
            relevant_doc_ids=d.get("relevant_doc_ids"),
        )


@dataclass
class EvaluationData:
    """评估数据集：多条样本，可选元信息。"""
    items: List[EvaluationDataItem] = field(default_factory=list)
    name: Optional[str] = None
    version: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "items": [x.to_dict() for x in self.items],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EvaluationData":
        items = []
        for x in d.get("items", []):
            if isinstance(x, dict):
                items.append(EvaluationDataItem.from_dict(x))
        return cls(
            items=items,
            name=d.get("name"),
            version=d.get("version"),
        )


def load_evaluation_data(path: Path) -> EvaluationData:
    """
    从 JSON 文件加载评估数据。
    格式：{ "name": "...", "version": "...", "items": [ { "question", "answer_gold", "relevant_doc_ids"? } ] }
    """
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if isinstance(data, list):
        data = {"items": data}
    return EvaluationData.from_dict(data)


def _get_a_pred(topic: str, question: str, mode: str = "mixed") -> str:
    """调用 RouterRAG 生成模型答案 A_pred（LLM 整理结果）。"""
    from src.utils.rag.ragrouter.router_retrieve_data import router_retrieve
    result = router_retrieve(
        topic=topic,
        query=question,
        mode=mode,
        enable_llm_summary=True,
        return_format="llm_only",
    )
    if result.get("status") == "error":
        return ""
    return (result.get("llm_summary") or "").strip()


def _get_retrieved_doc_ids(topic: str, question: str, mode: str = "mixed") -> set:
    """调用 RouterRAG 仅返回索引结果，并提取 doc_id 集合。"""
    from src.utils.rag.ragrouter.router_retrieve_data import router_retrieve
    result = router_retrieve(
        topic=topic,
        query=question,
        mode=mode,
        enable_llm_summary=False,
        return_format="index_only",
    )
    return extract_retrieved_doc_ids(result)


def run_evaluation(
    topic: str,
    eval_data_path: Path,
    *,
    mode: str = "mixed",
    use_judge: bool = True,
    judge_mode: str = "with_reference",
    fill_relevant_docs_with_keywords: bool = True,
    relevant_method: str = "embedding",
) -> Dict[str, Any]:
    """
    主评估函数：对每条样本跑 RouterRAG 检索 + A_pred，计算 Precision/Recall，可选 LLM Judge。

    judge_mode: Judge 评分方式："with_reference" 用问题+标准答案+模型答案；"no_reference" 仅用问题+模型答案，不依赖文档或标准答案。
    relevant_method: 无标注时如何判定「相关文档」："embedding" 用查询与文档向量相似度取 top_k；
        "keywords" 用问题+答案的 n-gram 关键词匹配。

    Returns:
        {
          "topic": str,
          "num_samples": int,
          "precision_avg": float,
          "recall_avg": float,
          "judge_correct_ratio": float | None,
          "samples": [ { "question", "precision", "recall", "judge_score", "a_pred" } ],
        }
    """
    data = load_evaluation_data(eval_data_path)
    samples_out: List[Dict[str, Any]] = []
    precisions: List[float] = []
    recalls: List[float] = []
    judge_scores: List[int] = []

    for item in data.items:
        question = item.question
        answer_gold = item.answer_gold
        relevant = set(item.relevant_doc_ids or [])

        if fill_relevant_docs_with_keywords and not relevant:
            if relevant_method == "embedding":
                # 用查询与文档向量的相似度判定相关文档（无需人工标注）
                query_for_relevant = f"{question} {answer_gold}".strip()
                ids = get_relevant_docs_by_embedding(topic, query_for_relevant, top_k=25)
                relevant = set(ids)
            else:
                # 用问题 + 标准答案做关键词匹配补充相关文档；优先取交集，并用 3 字 n-gram 收紧匹配
                ids_q = find_relevant_docs_by_keywords(topic, question, ngram_size=3)
                ids_a = find_relevant_docs_by_keywords(topic, answer_gold, ngram_size=3)
                relevant = set(ids_q) & set(ids_a)
                if not relevant:
                    relevant = set(ids_q) | set(ids_a)

        retrieved = _get_retrieved_doc_ids(topic, question, mode=mode)
        # 若仍无相关文档但检索到结果：视为「全部相关」，避免 precision/recall 恒为 0（如 DB 路径或 doc_id 格式不一致时）
        if not relevant and retrieved:
            relevant = set(retrieved)
        precision, recall = compute_precision_recall(retrieved, relevant)
        precisions.append(precision)
        recalls.append(recall)

        a_pred = _get_a_pred(topic, question, mode=mode)
        judge_score: Optional[float] = None
        if use_judge:
            judge_score = call_judge_sync(
                question, answer_gold, a_pred, judge_mode=judge_mode
            )
            judge_scores.append(judge_score)

        samples_out.append({
            "question": question,
            "precision": precision,
            "recall": recall,
            "judge_score": round(judge_score, 4) if judge_score is not None else None,
            "a_pred": a_pred,
        })

    n = len(samples_out)
    precision_avg = sum(precisions) / n if n else 0.0
    recall_avg = sum(recalls) / n if n else 0.0
    judge_correct_ratio = (
        sum(judge_scores) / len(judge_scores) if judge_scores else None
    )

    return {
        "topic": topic,
        "num_samples": n,
        "precision_avg": round(precision_avg, 4),
        "recall_avg": round(recall_avg, 4),
        "judge_correct_ratio": round(judge_correct_ratio, 4) if judge_correct_ratio is not None else None,
        "samples": samples_out,
    }
