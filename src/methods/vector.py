"""纯向量检索基线（对照组）。

只根据问题与文本块的向量相似度排序，不使用任何图结构。
嵌入统一走 core.embedding / retrieve.vector_utils，与入库保持同一 spec。
"""

from typing import Any, Dict, List, Optional

from core.interfaces import Answer, QAMethod
from core.query import normalize_top_k
from core.registry import register
from core.evidence import normalize_evidence
from retrieve.vector_utils import _text_of, embed_and_search


@register("vector")
class VectorMethod(QAMethod):
    name = "vector"

    def __init__(self, data_loader: Any = None, chunks=None):
        self.data_loader = data_loader
        self.chunks = chunks

    def ask(self, question: str, top_k: int = 5) -> Answer:
        if not isinstance(question, str) or not question.strip():
            raise ValueError("question 必须是非空字符串")
        top_k = normalize_top_k(top_k)
        try:
            hits = embed_and_search(question, top_k, self.chunks, self.data_loader)
        except Exception as exc:
            return Answer(
                answer_text=f"向量检索失败（数据源不可用）：{type(exc).__name__}: {exc}",
                method_name=self.name, evidence=[],
                debug_info={"question": question, "error": str(exc),
                            "status": "error", "degraded": "data_unavailable"},
                raw_context="")
        context = "\n\n".join(_text_of(item) for item in hits)
        return Answer(
            answer_text=context or "未检索到相关内容。",
            method_name=self.name,
            evidence=normalize_evidence(self.name, hits),
            debug_info={"top_k": top_k, "hit_count": len(hits), "uses_graph": False,
                        "retriever": "vector-similarity", "status": "ok"},
            raw_context=context)


__all__ = ["VectorMethod"]
