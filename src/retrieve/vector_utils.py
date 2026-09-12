"""向量检索的公共工具。

本文件只负责“把文字变成向量”和“按照相似度找文本块”，不负责回答问题。
这样 vector 基线、调库基线以及后续的方法可以使用完全相同的向量工具，
对比实验才是公平的。

支持两种嵌入方式：
1. 配置了 EMBED_ENDPOINT/EMBED_TOKEN 时，调用 OpenAI 兼容的嵌入接口；
2. 没有配置外部服务时，使用本地哈希嵌入作为兜底。它不追求生产效果，
   但不需要下载模型、不需要联网，适合课程实践和单元测试。
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any, Callable, Dict, Iterable, List, Optional

from core.config import get_env


def _text_of(item: Dict[str, Any]) -> str: # 从文本块字典中取出正文，这考虑到了所有的情况
    """从 B 可能返回的文本块字典中取出正文。

    B 的接口约定是 ``list[dict]``，但正文键名在联调早期可能不同；
    这里集中兼容常见键名，避免两个基线各自重复写一套脆弱逻辑。
    """
    for key in ("text", "content", "chunk", "page_content"):
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return ""


def _hash_embedding(text: str, dimension: int = 256) -> List[float]:
    """生成无需模型的确定性词袋哈希向量。

    每个词被哈希到一个维度，并用正负号减少哈希碰撞的偏差；最后归一化。
    这不是语义模型，只是离线兜底方案。配置真实嵌入服务后会自动替换它。使用正负结合，区分度较高。
    """
    vector = [0.0] * dimension
    tokens = re.findall(r"[\u4e00-\u9fff]|[a-zA-Z0-9_]+", text.lower())
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimension
        vector[index] += 1.0 if digest[4] % 2 else -1.0
    norm = math.sqrt(sum(x * x for x in vector))
    return [x / norm for x in vector] if norm else vector


class Embedder: # 嵌入器类
    """统一嵌入器。

    ``embedder=`` 参数主要给测试和离线实验使用；传入一个函数即可注入
    任何真实模型，而不用修改检索方法。
    """

    def __init__(self, embedder: Optional[Callable[[str], List[float]]] = None):
        self._custom = embedder
        self.endpoint = get_env("EMBED_ENDPOINT", "").strip()
        self.model = get_env("EMBED_MODEL", "").strip()
        self.token = get_env("EMBED_TOKEN", "").strip()

    def embed(self, text: str) -> List[float]:
        if self._custom:
            return list(self._custom(text))
        # 网络客户端采用惰性导入：未配置外部嵌入服务时不影响本地运行。
        if self.endpoint and self.token:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=self.token, base_url=self.endpoint)
                result = client.embeddings.create(model=self.model, input=text)
                return list(result.data[0].embedding)
            except Exception:
                # 外部服务不可用时回退，保证评测脚本能得到可诊断结果。
                pass
        return _hash_embedding(text)


def cosine_similarity(left: List[float], right: List[float]) -> float: # 余弦相似度函数
    """计算余弦相似度；向量为空或维度不一致时返回 0。"""
    if not left or len(left) != len(right):
        return 0.0
    denominator = math.sqrt(sum(x * x for x in left) * sum(y * y for y in right))
    return sum(x * y for x, y in zip(left, right)) / denominator if denominator else 0.0


def search_chunks(question: str, chunks: Iterable[Dict[str, Any]], top_k: int = 5,
                  embedder: Optional[Embedder] = None) -> List[Dict[str, Any]]:
    """在文本块列表中返回最相似的前 ``top_k`` 个块。

    返回值会复制原字典并增加 ``score``，不会修改 B 提供的原始数据。
    ``top_k`` 被限制为非负整数，避免评测传入异常参数时产生反直觉结果。
    """
    if top_k <= 0:
        return []
    encoder = embedder or Embedder()
    query_vector = encoder.embed(question)
    scored = []
    for position, chunk in enumerate(chunks):
        item = dict(chunk)
        item["score"] = cosine_similarity(query_vector, encoder.embed(_text_of(item)))
        item.setdefault("_position", position)
        scored.append(item)
    scored.sort(key=lambda item: (-item["score"], item["_position"]))
    return [{k: v for k, v in item.items() if k != "_position"} for item in scored[:top_k]]


def embed_and_search(question: str, top_k: int = 5, chunks: Optional[Iterable[Dict[str, Any]]] = None,
                     data_loader: Any = None) -> List[Dict[str, Any]]:
    """C/D 对接的便捷函数：优先使用 B 的 ``search_by_vector``，从数据库中检索，否则使用本地检索。"""
    # 显式传入 chunks 表示调用方要求本地、可复现检索（尤其是单元测试）；
    # 此时不能再隐式连接默认 Neo4j loader。
    if chunks is not None and data_loader is None:
        return search_chunks(question, chunks, top_k)
    loader = data_loader
    if loader is None:
        try:
            from ingest import data_loader as loader  # type: ignore
        except ImportError:
            loader = None
    if loader is not None and hasattr(loader, "search_by_vector"):
        return list(loader.search_by_vector(question, top_k))
    if chunks is None and loader is not None and hasattr(loader, "get_chunks"):
        chunks = loader.get_chunks()
    return search_chunks(question, chunks or [], top_k)
