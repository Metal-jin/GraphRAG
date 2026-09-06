"""纯向量检索基线。

它只根据问题与文本块的向量相似度排序，不使用知识图谱关系。
该方法是后续 GraphRAG 方法的对照组，因此故意保持简单、可解释。
"""

from typing import Any, Dict, Optional

from core.interfaces import Answer, QAMethod
from core.registry import register
from retrieve.vector_utils import embed_and_search


@register("vector")
class VectorMethod(QAMethod):
    name = "vector"

    def __init__(self, data_loader: Any = None, chunks=None):
        self.data_loader = data_loader
        self.chunks = chunks

    def ask(self, question: str, top_k: int = 5) -> Answer:
        if not isinstance(question, str) or not question.strip():
            raise ValueError("question 必须是非空字符串")
        hits = embed_and_search(question, top_k, self.chunks, self.data_loader)
        context = "\n\n".join(str(item.get("text", item.get("content", item.get("chunk", "")))) for item in hits)
        return Answer(answer_text=context or "未检索到相关内容。", method_name=self.name,
                      evidence=hits, debug_info={"top_k": top_k, "hit_count": len(hits), "uses_graph": False},
                      raw_context=context)
