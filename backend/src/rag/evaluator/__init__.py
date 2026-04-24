"""RAG 评估：EvaluationData、Precision/Recall、LLM Judge。"""
from .core import (
    EvaluationData,
    EvaluationDataItem,
    load_evaluation_data,
    run_evaluation,
)
from .utils import (
    build_judge_prompt,
    call_judge_sync,
    compute_precision_recall,
    extract_retrieved_doc_ids,
    find_relevant_docs_by_keywords,
    load_corpus_doc_texts,
    parse_judge_result,
)

__all__ = [
    "EvaluationData",
    "EvaluationDataItem",
    "load_evaluation_data",
    "run_evaluation",
    "build_judge_prompt",
    "call_judge_sync",
    "compute_precision_recall",
    "extract_retrieved_doc_ids",
    "find_relevant_docs_by_keywords",
    "load_corpus_doc_texts",
    "parse_judge_result",
]
