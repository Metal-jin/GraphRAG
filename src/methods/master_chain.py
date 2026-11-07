"""师徒链检索（master_chain）——任务 12 重写。

修复内容：
- 不再固定"向上 1~3 跳"：按问题判断方向（师父 / 徒弟）与跳数；
- 返回**真实有向路径**（节点 + 关系 + 方向 + 来源块），可还原整条推理链；
- 保留分支；同一 depth 只表示"第几代"，不再推断师兄弟关系；
- 遵守 top_k，证据规模有界。

Cypher 示例：
    MATCH path = (p:人物 {name: $name})<-[:MASTER_OF*N..N]-(m:人物)
    RETURN [n IN nodes(path) | n.name] AS names, length(path) AS depth
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from core.entity_link import EntityIndex
from core.evidence import entity_id, make_edge, make_node
from core.interfaces import Answer, QAMethod
from core.ontology import BIDIRECTIONAL_RELS, RELATIONS
from core.question_plan import focus_person_question, is_person_reference
from core.registry import register
from methods._common import (current_index, ensure_question,
                             no_entity_answer, resolve_scope, resolve_top_k,
                             unavailable_answer)

DISCIPLE_KEYWORDS = ("徒弟", "弟子", "徒儿", "门徒", "传人")
MASTER_KEYWORDS = ("师父", "师傅", "师祖", "太师父", "恩师", "师承", "师从", "师门")


def _direction(question: str) -> str:
    """up = 找师父（沿 MASTER_OF 反向）；down = 找徒弟。"""
    if any(word in question for word in DISCIPLE_KEYWORDS):
        return "down"
    return "up"


def _max_hops(question: str) -> int:
    """从问法推断跳数：师祖/太师父 = 2~3 跳，连续"师父"按次数计算。"""
    hops = max(1, question.count("师父") + question.count("师傅"))
    if "太师父" in question:
        hops = max(hops, 3)
    elif "师祖" in question:
        hops = max(hops, 2)
    return max(1, min(hops, 4))


@register("master_chain")
class MasterChainMethod(QAMethod):
    name = "master_chain"

    def __init__(self, data_loader: Any = None, chunks=None,
                 entity_index: Optional[EntityIndex] = None,
                 run_query: Any = None):
        self.data_loader = data_loader
        self.chunks = chunks
        self.entity_index = entity_index
        self._run_query = run_query

    # ---------- 依赖 ----------

    def _query(self):
        if self._run_query is not None:
            return self._run_query
        from ingest.data_loader import run_query
        return run_query

    # ---------- 主流程 ----------

    def ask(self, question: str, top_k: int = 5) -> Answer:
        question = ensure_question(question, self.name)
        top_k = resolve_top_k(top_k)
        scope = resolve_scope(question)

        index = current_index(self.data_loader, self.entity_index)
        aliases = index.alias_mapping("人物")
        focused, people = focus_person_question(question, index.link(question, labels=["人物"]), aliases)
        if not people:
            return no_entity_answer(self.name, question, "人物", scope)
        seed = people[0]

        direction = _direction(focused)
        hops = _max_hops(focused)
        rel_pattern = (f"<-[:MASTER_OF*{hops}..{hops}]-" if direction == "up"
                       else f"-[:MASTER_OF*{hops}..{hops}]->")
        cypher = (
            "MATCH path = (p:人物 {name: $name})" + rel_pattern + "(m:人物) "
            "WHERE m <> p "
            "RETURN [n IN nodes(path) | n.name] AS names, "
            "       [r IN relationships(path) | {chunk_ids: coalesce(r.chunk_ids, []), "
            "                                      snippets: coalesce(r.snippets, [])}] AS rels, "
            "       length(path) AS depth "
            "ORDER BY depth, names LIMIT $limit")

        try:
            rows = self._query()(cypher, {"name": seed.canonical,
                                          "limit": max(top_k * 4, top_k)})
        except Exception as exc:
            return unavailable_answer(self.name, question, exc)

        if not rows:
            subject = "师父" if direction == "up" else "徒弟"
            return Answer(
                answer_text=f"图谱中没有找到 {seed.canonical} 的{subject}信息。",
                method_name=self.name,
                evidence=[],
                debug_info={"question": question, "seed": seed.canonical,
                            "direction": direction, "hops": hops,
                            "hit_count": 0, "status": "no_result"},
                raw_context="")

        # 构造真实路径证据（去重、限制规模）
        seen_paths = set()
        evidence: List[Dict] = []
        first_generation: List[str] = []
        deeper: List[str] = []
        for row in rows:
            names = [aliases.get(n, n) for n in row.get("names") or [] if n]
            if (len(names) != hops + 1 or len(set(names)) != len(names)
                    or any(is_person_reference(n) for n in names)):
                continue
            key = tuple(names)
            if key in seen_paths:
                continue
            seen_paths.add(key)
            if len(evidence) >= top_k:
                break
            nodes = [make_node(name, "人物") for name in names]
            edges = []
            for position in range(len(names) - 1):
                relations = row.get("rels") or []
                rel = relations[position] if position < len(relations) else {}
                if direction == "up":
                    source, target, edge_dir = names[position], names[position + 1], "backward"
                else:
                    source, target, edge_dir = names[position], names[position + 1], "forward"
                edges.append(make_edge(source, target, "MASTER_OF", direction=edge_dir,
                                       chunk_ids=rel.get("chunk_ids") or [],
                                       snippets=rel.get("snippets") or []))
            evidence.append({"kind": "path", "source_method": self.name,
                             "confidence": "extracted", "seed": seed.canonical,
                             "complete": True,
                             "nodes": nodes, "edges": edges,
                             "chunk_ids": sorted({c for e in edges for c in e["chunk_ids"]}),
                             "text": " -> ".join(names),
                             "legacy": {"names": names, "depth": row.get("depth")}})
            target_name = names[-1]
            if row.get("depth") == 1:
                if target_name not in first_generation:
                    first_generation.append(target_name)
            else:
                label = f"{target_name}（第{row.get('depth')}代）"
                if label not in deeper:
                    deeper.append(label)

        if not evidence:
            return Answer(
                answer_text=f"图谱中没有找到 {seed.canonical} 的有效师徒路径。",
                method_name=self.name, evidence=[],
                debug_info={"seed": seed.canonical, "status": "no_result"},
                raw_context="")

        parts = []
        if first_generation:
            parts.append(f"第1代：{'、'.join(first_generation)}")
        if deeper:
            parts.append("更上层：" + "、".join(deeper[:10]))
        if direction == "up":
            answer_text = f"{seed.canonical} 的师父链：" + "；".join(parts) + "。"
        else:
            answer_text = f"{seed.canonical} 的徒弟：" + "、".join(
                sorted({e["nodes"][-1]["name"] for e in evidence})) + "。"

        raw_context = "\n".join(e["text"] for e in evidence)
        return Answer(
            answer_text=answer_text, method_name=self.name, evidence=evidence,
            debug_info={"question": question, "seed": seed.canonical,
                        "direction": direction, "hops": hops,
                        "path_count": len(evidence),
                        "scope": scope.to_dict(), "status": "ok"},
            raw_context=raw_context)
