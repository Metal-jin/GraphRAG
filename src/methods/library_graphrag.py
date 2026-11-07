"""调库 GraphRAG 基线（library_graphrag）——任务 17 重写。

旧实现与 vector 基线完全同一条代码路径（只是 debug 里写 uses_graph=True），
无法证明"图检索"和"纯向量"的差异。现在实现真正的通用图检索：

1. 向量检索拿到 seed 文本块；
2. 通过 Chunk-[MENTIONS]->实体 找到种子实体；
3. 沿任意关系做 1 跳扩展，收集三元组；
4. 生成上下文 = seed 原文 + 扩展三元组。

这仍是"通用"策略（不区分师徒/门派等语义），正好作为领域策略的对照组。
数据库不可用时显式降级（debug 里标注 degraded），不伪装成功。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.interfaces import Answer, QAMethod
from core.registry import register
from retrieve.vector_utils import embed_and_search, _text_of

RELATION_NAMES = {
    "MASTER_OF": "师徒", "SPOUSE_OF": "夫妻", "PARENT_OF": "父母",
    "SWORN_BROTHER_OF": "结拜", "ENEMY_OF": "仇敌", "BELONGS_TO": "属于",
    "MASTERS": "精通", "FOUNDER_OF": "创立", "LOCATED_IN": "位于",
    "BRANCHED_FROM": "演化", "DESCENDANT_OF": "血缘",
}

EXPAND_QUERY = """
MATCH (c:Chunk {chunk_id: $chunk_id})-[:MENTIONS]->(e)
MATCH (e)-[r]-(f)
WHERE type(r) <> 'MENTIONS'
RETURN DISTINCT e.name AS source, type(r) AS type, f.name AS target,
                coalesce(r.chunk_ids, []) AS chunk_ids
LIMIT $limit
"""


@register("library_graphrag")
class LibraryGraphRAGMethod(QAMethod):
    name = "library_graphrag"

    def __init__(self, data_loader: Any = None, chunks=None, hops: int = 1,
                 expansion_limit: int = 12, run_query: Any = None):
        self.data_loader = data_loader
        self.chunks = chunks
        self.hops = max(1, hops)
        self.expansion_limit = max(1, expansion_limit)
        self._run_query = run_query

    def _query(self):
        if self._run_query is not None:
            return self._run_query
        from ingest.data_loader import run_query
        return run_query

    def _expand(self, hits: List[Dict], top_k: int):
        """对 seed 块的实体做 1 跳扩展，返回 (三元组, 涉及实体)。"""
        triples: List[Dict[str, Any]] = []
        seen = set()
        chunk_ids = [hit.get("chunk_id") for hit in hits if hit.get("chunk_id")]
        for chunk_id in chunk_ids:
            rows = self._query()(EXPAND_QUERY,
                                 {"chunk_id": chunk_id,
                                  "limit": self.expansion_limit})
            for row in rows:
                key = (row["source"], row["type"], row["target"])
                if key in seen:
                    continue
                seen.add(key)
                triples.append({"source": row["source"], "type": row["type"],
                                "target": row["target"],
                                "chunk_ids": row.get("chunk_ids") or []})
                if len(triples) >= top_k * self.expansion_limit:
                    return triples
        return triples

    def ask(self, question: str, top_k: int = 5) -> Answer:
        if not isinstance(question, str) or not question.strip():
            raise ValueError("question 必须是非空字符串")
        hits = embed_and_search(question, top_k, self.chunks, self.data_loader)

        triples: List[Dict[str, Any]] = []
        degraded = ""
        try:
            if self.chunks is None:
                triples = self._expand(hits, top_k)
        except Exception as exc:  # 数据库不可用 → 显式降级为纯向量
            degraded = f"{type(exc).__name__}: {exc}"

        chunk_text = "\n\n".join(_text_of(item) for item in hits)
        triple_text = "\n".join(
            f"{t['source']} --[{RELATION_NAMES.get(t['type'], t['type'])}]--> {t['target']}"
            for t in triples)
        context_parts = []
        if chunk_text:
            context_parts.append("【相关原文】\n" + chunk_text)
        if triple_text:
            context_parts.append("【图谱扩展关系（1 跳）】\n" + triple_text)
        context = "\n\n".join(context_parts) if context_parts else ""

        evidence: List[Dict[str, Any]] = []
        for item in hits:
            evidence.append({"kind": "chunk", "source_method": self.name,
                             "confidence": "extracted", "seed": None, "complete": True,
                             "nodes": [], "edges": [],
                             "chunk_ids": [item.get("chunk_id")] if item.get("chunk_id") is not None else [],
                             "text": _text_of(item)[:400], "score": item.get("score"),
                             "book": item.get("book"), "era": item.get("era"),
                             "legacy": item})
        for triple in triples[:top_k * 2]:
            evidence.append({
                "kind": "triple", "source_method": self.name,
                "confidence": "extracted", "seed": None, "complete": True,
                "nodes": [], "edges": [{"source": triple["source"],
                                        "target": triple["target"],
                                        "type": triple["type"],
                                        "direction": "forward",
                                        "chunk_ids": triple["chunk_ids"],
                                        "snippets": [],
                                        "confidence": "extracted"}],
                "chunk_ids": triple["chunk_ids"],
                "text": f"{triple['source']} --[{triple['type']}]--> {triple['target']}",
                "legacy": triple})

        return Answer(
            answer_text=context or "未检索到相关内容。",
            method_name=self.name,
            evidence=evidence,
            debug_info={"top_k": top_k, "hit_count": len(hits),
                        "uses_graph": bool(triples),
                        "retriever": "neo4j-vector + 1hop graph expansion",
                        "seed_chunks": [item.get("chunk_id") for item in hits],
                        "expanded_relations": len(triples),
                        "hops": self.hops,
                        "degraded": degraded,
                        "status": "degraded" if degraded else "ok"},
            raw_context=context)
