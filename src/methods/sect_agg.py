"""门派聚合检索（sect_agg）——任务 14 重写。

修复内容：
- 区分问法：成员 / 创立者 / 武功（绝学）；
- 返回"门派 -> 人物 -> 武功"的真实连接与来源，而不是只给一句"成员 N 人"；
- "绝学"只在有 MASTERS 事实时陈述，不把普通成员关系推成绝学；
- 遵守 top_k，证据规模有界。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.entity_link import EntityIndex
from core.evidence import make_edge, make_node
from core.interfaces import Answer, QAMethod
from core.question_plan import FOUNDING_VERBS
from core.registry import register
from methods._common import (current_index, ensure_question, link_seed,
                             no_entity_answer, resolve_scope, resolve_top_k,
                             unavailable_answer)

FOUNDER_KEYWORDS = (*FOUNDING_VERBS, "谁创", "创始人")
ARTS_KEYWORDS = ("绝学", "武功", "会什么", "精通", "成名绝技", "招数")
LEADER_KEYWORDS = ("掌门", "帮主", "教主", "盟主")

MEMBER_QUERY = """
MATCH (p:人物)-[r:BELONGS_TO]->(s:门派 {name: $name})
RETURN p.name AS person, p.era AS era,
       coalesce(r.chunk_ids, []) AS chunk_ids, coalesce(r.snippets, []) AS snippets
LIMIT $limit
"""

FOUNDER_QUERY = """
MATCH (p:人物)-[r:FOUNDER_OF]->(s:门派 {name: $name})
RETURN p.name AS person, coalesce(r.chunk_ids, []) AS chunk_ids,
       coalesce(r.snippets, []) AS snippets
LIMIT $limit
"""

ARTS_QUERY = """
MATCH (p:人物)-[:BELONGS_TO]->(s:门派 {name: $name})
MATCH (p)-[r:MASTERS]->(a:武功)
RETURN p.name AS person, a.name AS art,
       coalesce(r.chunk_ids, []) AS chunk_ids, coalesce(r.snippets, []) AS snippets
LIMIT $limit
"""

SECT_ARTS_QUERY = """
MATCH (s:门派 {name: $name})-[r:MASTERS]->(a:武功)
RETURN a.name AS art, coalesce(r.chunk_ids, []) AS chunk_ids,
       coalesce(r.snippets, []) AS snippets
LIMIT $limit
"""

FOUNDED_QUERY = """
MATCH (p:人物 {name: $name})-[r:FOUNDER_OF]->(s:门派)
RETURN s.name AS sect, coalesce(r.chunk_ids, []) AS chunk_ids,
       coalesce(r.snippets, []) AS snippets
LIMIT $limit
"""


def _kind(question: str) -> str:
    if any(word in question for word in FOUNDER_KEYWORDS):
        return "founder"
    if any(word in question for word in ARTS_KEYWORDS):
        return "arts"
    return "members"


@register("sect_agg")
class SectAggMethod(QAMethod):
    name = "sect_agg"

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
        seed = link_seed(question, index, ("门派",))
        if seed is None:
            if any(word in question for word in FOUNDER_KEYWORDS):
                people = index.link(question, labels=["人物"])
                if people:
                    # 优先取紧接创立动词的人，避开前面介绍身份的其他人物。
                    person = next((m for m in reversed(people)
                                   if question[m.end:].lstrip().startswith(FOUNDING_VERBS)),
                                  people[0])
                    return self._sects_founded(question, person.canonical, top_k, scope)
            return no_entity_answer(self.name, question, "门派", scope)

        kind = _kind(question)
        if kind == "founder":
            return self._founder(question, seed.canonical, top_k, scope)
        if kind == "arts":
            return self._arts(question, seed.canonical, top_k, scope)
        if any(word in question for word in LEADER_KEYWORDS):
            # 掌门/帮主：本体没有"任职"关系，明确说明并给出成员作为参考
            answer = self._members(question, seed.canonical, top_k, scope)
            answer.answer_text = ("本体中没有「任职/掌门」关系，无法确定谁是掌门；"
                                  + answer.answer_text)
            answer.debug_info["leader_unsupported"] = True
            return answer
        return self._members(question, seed.canonical, top_k, scope)

    # ---------- 三类问法 ----------

    def _members(self, question: str, sect: str, top_k: int, scope) -> Answer:
        try:
            rows = self._query()(MEMBER_QUERY, {"name": sect, "limit": top_k * 4})
        except Exception as exc:
            return unavailable_answer(self.name, question, exc)
        if not rows:
            return self._empty(question, sect, "成员", scope)

        nodes = [make_node(sect, "门派")]
        edges = []
        for row in rows[:top_k * 2]:
            nodes.append(make_node(row["person"], "人物"))
            edges.append(make_edge(row["person"], sect, "BELONGS_TO",
                                   chunk_ids=row.get("chunk_ids") or [],
                                   snippets=row.get("snippets") or []))
        members = [row["person"] for row in rows[:top_k * 2]]
        answer_text = f"{sect} 门下成员：" + "、".join(members) + f"（共 {len(members)} 人）"
        return Answer(
            answer_text=answer_text, method_name=self.name,
            evidence=[{"kind": "member", "source_method": self.name,
                       "confidence": "extracted", "seed": sect, "complete": True,
                       "nodes": nodes, "edges": edges,
                       "chunk_ids": sorted({c for e in edges for c in e["chunk_ids"]}),
                       "text": answer_text, "legacy": {"members": members}}],
            debug_info={"question": question, "seed": sect, "kind": "members",
                        "member_count": len(members), "scope": scope.to_dict(),
                        "status": "ok"},
            raw_context="\n".join(f"{row['person']} 属于 {sect}" for row in rows[:top_k * 2]))

    def _founder(self, question: str, sect: str, top_k: int, scope) -> Answer:
        try:
            rows = self._query()(FOUNDER_QUERY, {"name": sect, "limit": top_k})
        except Exception as exc:
            return unavailable_answer(self.name, question, exc)
        if not rows:
            return self._empty(question, sect, "创立者", scope)
        nodes = [make_node(sect, "门派")]
        edges = []
        for row in rows:
            nodes.append(make_node(row["person"], "人物"))
            edges.append(make_edge(row["person"], sect, "FOUNDER_OF",
                                   chunk_ids=row.get("chunk_ids") or [],
                                   snippets=row.get("snippets") or []))
        founders = [row["person"] for row in rows]
        answer_text = f"{sect} 的创立者：" + "、".join(founders) + "。"
        return Answer(
            answer_text=answer_text, method_name=self.name,
            evidence=[{"kind": "member", "source_method": self.name,
                       "confidence": "extracted", "seed": sect, "complete": True,
                       "nodes": nodes, "edges": edges,
                       "chunk_ids": sorted({c for e in edges for c in e["chunk_ids"]}),
                       "text": answer_text, "legacy": {"founders": founders}}],
            debug_info={"question": question, "seed": sect, "kind": "founder",
                        "hit_count": len(founders), "scope": scope.to_dict(),
                        "status": "ok"},
            raw_context="\n".join(f"{row['person']} 创立 {sect}" for row in rows))

    def _arts(self, question: str, sect: str, top_k: int, scope) -> Answer:
        try:
            rows = self._query()(ARTS_QUERY, {"name": sect, "limit": top_k * 4})
            sect_rows = self._query()(SECT_ARTS_QUERY, {"name": sect, "limit": top_k})
        except Exception as exc:
            return unavailable_answer(self.name, question, exc)

        if not rows and not sect_rows:
            return self._empty(question, sect, "武功", scope)

        nodes = [make_node(sect, "门派")]
        edges = []
        by_art: Dict[str, List[str]] = {}
        for row in rows[:top_k * 4]:
            nodes.append(make_node(row["person"], "人物"))
            nodes.append(make_node(row["art"], "武功"))
            edges.append(make_edge(row["person"], sect, "BELONGS_TO"))
            edges.append(make_edge(row["person"], row["art"], "MASTERS",
                                   chunk_ids=row.get("chunk_ids") or [],
                                   snippets=row.get("snippets") or []))
            by_art.setdefault(row["art"], []).append(row["person"])
        sect_arts = []
        for row in sect_rows:
            sect_arts.append(row["art"])
            nodes.append(make_node(row["art"], "武功"))
            edges.append(make_edge(sect, row["art"], "MASTERS",
                                   chunk_ids=row.get("chunk_ids") or [],
                                   snippets=row.get("snippets") or []))

        arts = list(dict.fromkeys(list(by_art) + sect_arts))
        answer_text = (f"{sect} 相关武功（来自成员 MASTERS 事实）：" + "、".join(arts[:top_k])
                       + "。注意：成员会某武功不等于该武功是本门绝学。")
        return Answer(
            answer_text=answer_text, method_name=self.name,
            evidence=[{"kind": "member", "source_method": self.name,
                       "confidence": "extracted", "seed": sect, "complete": True,
                       "nodes": nodes, "edges": edges,
                       "chunk_ids": sorted({c for e in edges for c in e["chunk_ids"]}),
                       "text": answer_text,
                       "legacy": {"arts": arts, "by_art": by_art}}],
            debug_info={"question": question, "seed": sect, "kind": "arts",
                        "art_count": len(arts), "scope": scope.to_dict(),
                        "status": "ok"},
            raw_context="\n".join(f"{person} 精通 {art}" for art, persons in by_art.items()
                                   for person in persons))

    def _sects_founded(self, question: str, person: str, top_k: int, scope) -> Answer:
        try:
            rows = self._query()(FOUNDED_QUERY, {"name": person, "limit": top_k})
        except Exception as exc:
            return unavailable_answer(self.name, question, exc)
        if not rows:
            return self._empty(question, person, "创立门派", scope)
        nodes = [make_node(person, "人物")]
        edges = []
        for row in rows:
            nodes.append(make_node(row["sect"], "门派"))
            edges.append(make_edge(person, row["sect"], "FOUNDER_OF",
                                   chunk_ids=row.get("chunk_ids") or [],
                                   snippets=row.get("snippets") or []))
        sects = [row["sect"] for row in rows]
        answer_text = f"{person} 创立的门派：" + "、".join(sects) + "。"
        return Answer(
            answer_text=answer_text, method_name=self.name,
            evidence=[{"kind": "member", "source_method": self.name,
                       "confidence": "extracted", "seed": person, "complete": True,
                       "nodes": nodes, "edges": edges,
                       "chunk_ids": sorted({c for e in edges for c in e["chunk_ids"]}),
                       "text": answer_text, "legacy": {"founder": person, "sects": sects}}],
            debug_info={"question": question, "seed": person, "kind": "sects_founded",
                        "hit_count": len(sects), "scope": scope.to_dict(),
                        "status": "ok"},
            raw_context="\n".join(f"{person} 创立 {row['sect']}" for row in rows))

    def _empty(self, question: str, sect: str, what: str, scope) -> Answer:
        return Answer(
            answer_text=f"图谱中没有找到 {sect} 的{what}信息。",
            method_name=self.name, evidence=[],
            debug_info={"question": question, "seed": sect, "hit_count": 0,
                        "scope": scope.to_dict(), "status": "no_result"},
            raw_context="")
