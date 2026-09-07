"""调库 GraphRAG 基线。

优先调用 B 数据接口中的 ``search_by_vector``（它应封装 neo4j-graphrag 的
向量检索器）。这样 C 不需要重复编写数据库连接和 Cypher 查询；在数据库
尚未准备好时自动退回同一套本地向量检索，方便先完成联调和测试。
"""

from typing import Any

from core.interfaces import Answer, QAMethod
from core.registry import register
from retrieve.vector_utils import embed_and_search


@register("library_graphrag")
class LibraryGraphRAGMethod(QAMethod):
    name = "library_graphrag"

    def __init__(self, data_loader: Any = None, chunks=None):
        self.data_loader = data_loader
        self.chunks = chunks

    def ask(self, question: str, top_k: int = 5) -> Answer:
        if not isinstance(question, str) or not question.strip():
            raise ValueError("question 必须是非空字符串")
        hits = embed_and_search(question, top_k, self.chunks, self.data_loader)
        context = "\n\n".join(str(item.get("text", item.get("content", item.get("chunk", "")))) for item in hits)
        return Answer(answer_text=context or "未检索到相关内容。", method_name=self.name,
                      evidence=hits, debug_info={"top_k": top_k, "hit_count": len(hits), "uses_graph": True,
                                                  "retriever": "data_loader.search_by_vector"},
                      raw_context=context)
