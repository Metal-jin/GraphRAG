"""武功传承检索（art_lineage）——任务 15 重写。

修复内容：
- 区分"创立者"与"传承"两类问法；
- 传承分两种可信度：
  * 关系上带 chunk_ids/snippets 证据 → confidence=extracted
  * 仅由"师徒 + 共同精通"推出 → confidence=inferred，并在答案里显式标注
- 上下文包含武功名称与方向，证据数量受 top_k 限制；
- 找不到有证据的传授时，明确说明是推断而不是事实。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.entity_link import EntityIndex
from core.evidence import make_edge, make_node
from core.interfaces import Answer, QAMethod
from core.registry import register
from methods._common import (current_index, ensure_question, link_seed,
                             no_entity_answer, resolve_scope, resolve_top_k,
                             unavailable_answer)

ORIGIN_KEYWORDS = ("创始人", "谁创", "谁创造", "源自", "出自", "由谁创", "何人所创")
PRACTITIONER_KEYWORDS = ("谁会", "哪些人会", "精通")

ORIGIN_QUERY = """
MATCH (p:人物)-[r:FOUNDER_OF]->(a:武功 {name: $name})
RETURN p.name AS person, coalesce(r.chunk_ids, []) AS chunk_ids,
       coalesce(r.snippets, []) AS snippets
LIMIT $limit
"""

BRANCH_QUERY = """
MATCH (a:武功 {name: $name})-[r:BRANCHED_FROM]->(src:武功)
RETURN src.name AS source, coalesce(r.chunk_ids, []) AS chunk_ids
LIMIT $limit
"""

LINEAGE_QUERY = """
MATCH (a:武功 {name: $name})<-[:MASTERS]-(master:人物)-[r:MASTER_OF]->(disciple:人物)
WHERE (disciple)-[:MASTERS]->(a) AND master <> disciple
RETURN master.name AS source, disciple.name AS target,
       coalesce(r.chunk_ids, []) AS chunk_ids, coalesce(r.snippets, []) AS snippets
LIMIT $limit
"""

PRACTITIONER_QUERY = """
MATCH (p:人物)-[r:MASTERS]->(a:武功 {name: $name})
RETURN p.name AS person, coalesce(r.chunk_ids, []) AS chunk_ids,
       coalesce(r.snippets, []) AS snippets
LIMIT $limit
"""


def _kind(question: str) -> str:
    if any(word in question for word in ORIGIN_KEYWORDS):
        return "origin"
    if any(word in question for word in PRACTITIONER_KEYWORDS):
        return "practitioners"
    return "lineage"


@register("art_lineage")
class ArtLineageMethod(QAMethod):
    name = "art_lineage"

    def __init__(self, data_loader: Any = None, chunks=None,
                 entity_index: Optional[EntityIndex] = None,
                 run_query: Any = None):
        self.data_loader = data_loader
        self.chunks = chunks
        self.entity_index = entity_index
        self._run_query = run_query

    def _query(self):
        if self._run_query is not None:
            return self._run_query
        from ingest.data_loader import run_query
        return run_query

    def ask(self, question: str, top_k: int = 5) -> Answer:
        question = ensure_question(question, self.name)
        top_k = resolve_top_k(top_k)
        scope = resolve_scope(question)

        index = current_index(self.data_loader, self.entity_index)
        seed = link_seed(question, index, ("武功",))
        if seed is None:
            return no_entity_answer(self.name, question, "武功", scope)

        kind = _kind(question)
        if kind == "origin":
            return self._origin(question, seed.canonical, top_k, scope)
        if kind == "practitioners":
            return self._practitioners(question, seed.canonical, top_k, scope)
        return self._lineage(question, seed.canonical, top_k, scope)

    # ---------- 传承 ----------

    def _lineage(self, question: str, art: str, top_k: int, scope) -> Answer:
        try:
            rows = self._query()(LINEAGE_QUERY, {"name": art, "limit": top_k * 3})
        except Exception as exc:
            return unavailable_answer(self.name, question, exc)

        if not rows:
            # 没有"师徒 + 共同精通"的组合，退回到"谁会这门武功"
            return self._practitioners(question, art, top_k, scope,
                                       note="没有找到师徒传承组合，以下为精通该武功的人物：")

        nodes = [make_node(art, "武功")]
        edges: List[Dict] = []
        evidenced: List[str] = []
        inferred: List[str] = []
        for row in rows[:top_k]:
            chunk_ids = row.get("chunk_ids") or []
            confidence = "extracted" if chunk_ids else "inferred"
            nodes.append(make_node(row["source"], "人物"))
            nodes.append(make_node(row["target"], "人物"))
            edges.append(make_edge(row["source"], row["target"], "MASTER_OF",
                                   chunk_ids=chunk_ids,
                                   snippets=row.get("snippets") or [],
                                   confidence=confidence))
            text = f"{row['source']} 传给 {row['target']}"
            (evidenced if confidence == "extracted" else inferred).append(text)

        parts = []
        if evidenced:
            parts.append("有原文证据：" + "、".join(evidenced))
        if inferred:
            parts.append("推断（师徒关系 + 可能共同精通该武功，未找到直接传授证据）："
                         + "、".join(inferred))
        answer_text = f"{art} 的传承 —— " + "；".join(parts) + "。"

        return Answer(
            answer_text=answer_text, method_name=self.name,
            evidence=[{"kind": "art", "source_method": self.name,
                       "confidence": "extracted" if evidenced and not inferred
                                     else "inferred",
                       "seed": art, "complete": bool(evidenced),
                       "nodes": nodes, "edges": edges,
                       "chunk_ids": sorted({c for e in edges for c in e["chunk_ids"]}),
                       "text": answer_text,
                       "legacy": {"art": art, "evidenced": evidenced,
                                  "inferred": inferred}}],
            debug_info={"question": question, "seed": art, "kind": "lineage",
                        "evidenced_count": len(evidenced),
                        "inferred_count": len(inferred),
                        "scope": scope.to_dict(), "status": "ok"},
            raw_context="\n".join(f"{row['source']} -> {row['target']}（{art}）"
                                   for row in rows[:top_k * 2]))

    # ---------- 创立者 ----------

    def _origin(self, question: str, art: str, top_k: int, scope) -> Answer:
        try:
            rows = self._query()(ORIGIN_QUERY, {"name": art, "limit": top_k})
            branches = self._query()(BRANCH_QUERY, {"name": art, "limit": top_k})
        except Exception as exc:
            return unavailable_answer(self.name, question, exc)

        if not rows and not branches:
            return Answer(
                answer_text=f"图谱中没有 {art} 的创立者或演化来源信息。",
                method_name=self.name, evidence=[],
                debug_info={"question": question, "seed": art, "kind": "origin",
                            "hit_count": 0, "scope": scope.to_dict(),
                            "status": "no_result"},
                raw_context="")

        nodes = [make_node(art, "武功")]
        edges: List[Dict] = []
        for row in rows:
            nodes.append(make_node(row["person"], "人物"))
            edges.append(make_edge(row["person"], art, "FOUNDER_OF",
                                   chunk_ids=row.get("chunk_ids") or [],
                                   snippets=row.get("snippets") or []))
        for row in branches:
            nodes.append(make_node(row["source"], "武功"))
            edges.append(make_edge(art, row["source"], "BRANCHED_FROM",
                                   chunk_ids=row.get("chunk_ids") or [],
                                   confidence="extracted" if row.get("chunk_ids") else "inferred"))

        parts = []
        if rows:
            parts.append("创立者：" + "、".join(row["person"] for row in rows))
        if branches:
            parts.append("演化自：" + "、".join(row["source"] for row in branches))
        answer_text = f"{art} —— " + "；".join(parts) + "。"

        return Answer(
            answer_text=answer_text, method_name=self.name,
            evidence=[{"kind": "art", "source_method": self.name,
                       "confidence": "extracted", "seed": art, "complete": True,
                       "nodes": nodes, "edges": edges,
                       "chunk_ids": sorted({c for e in edges for c in e["chunk_ids"]}),
                       "text": answer_text, "legacy": {}}],
            debug_info={"question": question, "seed": art, "kind": "origin",
                        "hit_count": len(rows) + len(branches),
                        "scope": scope.to_dict(), "status": "ok"},
            raw_context="\n".join(parts))

    # ---------- 精通者 ----------

    def _practitioners(self, question: str, art: str, top_k: int, scope,
                       note: str = "") -> Answer:
        try:
            rows = self._query()(PRACTITIONER_QUERY, {"name": art, "limit": top_k * 3})
        except Exception as exc:
            return unavailable_answer(self.name, question, exc)
        if not rows:
            return Answer(
                answer_text=f"图谱中没有找到精通 {art} 的人物。",
                method_name=self.name, evidence=[],
                debug_info={"question": question, "seed": art,
                            "kind": "practitioners", "hit_count": 0,
                            "scope": scope.to_dict(), "status": "no_result"},
                raw_context="")
        nodes = [make_node(art, "武功")]
        edges = []
        for row in rows[:top_k * 3]:
            nodes.append(make_node(row["person"], "人物"))
            edges.append(make_edge(row["person"], art, "MASTERS",
                                   chunk_ids=row.get("chunk_ids") or [],
                                   snippets=row.get("snippets") or []))
        people = list(dict.fromkeys(row["person"] for row in rows))
        answer_text = (note or f"精通 {art} 的人物：") + "、".join(people) + "。"
        return Answer(
            answer_text=answer_text, method_name=self.name,
            evidence=[{"kind": "art", "source_method": self.name,
                       "confidence": "extracted", "seed": art, "complete": True,
                       "nodes": nodes, "edges": edges,
                       "chunk_ids": sorted({c for e in edges for c in e["chunk_ids"]}),
                       "text": answer_text, "legacy": {"people": people}}],
            debug_info={"question": question, "seed": art,
                        "kind": "practitioners", "hit_count": len(people),
                        "scope": scope.to_dict(), "status": "ok"},
            raw_context="\n".join(f"{row['person']} 精通 {art}" for row in rows))
