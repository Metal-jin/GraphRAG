"""向量检索公共工具（任务 03 / 04 / 29 / 30）。

历史问题：
- 这里有一套 sha256 哈希嵌入，build_kg 里还有一套内置 hash() 嵌入，两者算出的
  向量语义不同，入库与查询不一致；
- 远程嵌入失败时按单条文本退回本地哈希，同一次检索里可能混用不同模型的向量；
- 每次检索都重新嵌入全部文本块。

现在统一改为调用 core.embedding 的进程级 EmbeddingService：

- 同一份算法、同一份缓存、同一份 spec；
- 远程失败默认直接报错（不静默降级），显式配置才允许整批降级；
- search_chunks 用 embed_documents 批量嵌入并命中缓存。
"""
from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional

from core.embedding import EmbeddingService, get_embedder, local_hash_embed
from core.errors import DataUnavailableError, EmbeddingError


def _text_of(item: Dict[str, Any]) -> str:
    """从文本块字典中取出正文（兼容联调早期的多种键名）。"""
    for key in ("text", "content", "chunk", "page_content"):
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return ""


class Embedder:
    """统一嵌入器（薄封装，真正实现在 core.embedding）。

    embedder= 参数主要给测试和离线实验使用；传入一个函数即可注入任意模型。
    """

    def __init__(self, embedder=None, service: Optional[EmbeddingService] = None):
        self._custom = embedder
        self._service = service or get_embedder()

    @property
    def spec(self):
        return self._service.spec

    def embed(self, text: str) -> List[float]:
        if self._custom:
            return list(self._custom(text))
        return self._service.embed_query(text)

    def embed_many(self, texts: List[str]) -> List[List[float]]:
        if self._custom:
            return [list(self._custom(t)) for t in texts]
        return self._service.embed_documents(texts)


def cosine_similarity(left: List[float], right: List[float]) -> float:
    """计算余弦相似度；向量为空或维度不一致时返回 0。"""
    if not left or len(left) != len(right):
        return 0.0
    denominator = math.sqrt(sum(x * x for x in left) * sum(y * y for y in right))
    return sum(x * y for x, y in zip(left, right)) / denominator if denominator else 0.0


def search_chunks(question: str, chunks: Iterable[Dict[str, Any]], top_k: int = 5,
                  embedder: Optional[Embedder] = None) -> List[Dict[str, Any]]:
    """在文本块列表里返回最相似的前 top_k 个（批量嵌入 + 缓存）。"""
    if top_k <= 0:
        return []
    items = list(chunks or [])
    if not items:
        return []
    encoder = embedder or Embedder()
    query_vector = encoder.embed(question)
    chunk_vectors = encoder.embed_many([_text_of(item) for item in items])
    scored = []
    for position, (item, vector) in enumerate(zip(items, chunk_vectors)):
        scored_item = dict(item)
        scored_item["score"] = cosine_similarity(query_vector, vector)
        scored_item["_position"] = position
        scored.append(scored_item)
    scored.sort(key=lambda item: (-item["score"], item["_position"]))
    return [{k: v for k, v in item.items() if k != "_position"} for item in scored[:top_k]]


def embed_and_search(question: str, top_k: int = 5,
                     chunks: Optional[Iterable[Dict[str, Any]]] = None,
                     data_loader: Any = None) -> List[Dict[str, Any]]:
    """优先用数据源接口做向量检索，失败时**显式**退回本地文本块检索。

    与旧实现的区别：数据库异常不再被静默吞掉后"看似成功"，而是记录
    degraded 信息（通过返回值里的 score/source 字段无法表达，故用模块级状态）。
    """
    if chunks is not None and data_loader is None:
        return search_chunks(question, chunks, top_k)

    loader = data_loader
    if loader is None:
        try:
            from ingest import data_loader as loader  # type: ignore
        except ImportError:
            loader = None

    if loader is not None and hasattr(loader, "search_by_vector"):
        try:
            return list(loader.search_by_vector(question, top_k))
        except Exception as exc:  # 数据库/索引不可用
            global _last_degrade_reason
            _last_degrade_reason = f"vector-search degraded: {type(exc).__name__}: {exc}"
            if chunks is None and hasattr(loader, "get_chunks"):
                try:
                    chunks = loader.get_chunks()
                except Exception:
                    chunks = None
            if chunks is None:
                raise DataUnavailableError("向量检索不可用且没有可回退的文本块",
                                           detail=str(exc)) from exc

    if chunks is None and loader is not None and hasattr(loader, "get_chunks"):
        chunks = loader.get_chunks()
    return search_chunks(question, chunks or [], top_k)


_last_degrade_reason: str = ""


def last_degrade_reason() -> str:
    return _last_degrade_reason


__all__ = ["Embedder", "cosine_similarity", "search_chunks", "embed_and_search",
           "last_degrade_reason", "local_hash_embed"]
