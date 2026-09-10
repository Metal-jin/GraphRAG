"""门派聚合检索（sect_agg）。
万变不离其宗
领域策略之二：针对"门派归属与聚合"问题（如"丐帮有哪些绝学"），
定位门派节点，聚合其下所有人物和武功，返回门派子图作为证据。
"""

from typing import Any, Dict, List, Optional

from core.interfaces import Answer, QAMethod
from core.registry import register
from ingest.data_loader import get_graph, run_query


def _find_seed_sect(question: str) -> Optional[str]:
    """从问题中识别起始门派（简单字符串匹配，长名优先）。"""
    try:
        graph = get_graph()
    except Exception:
        return None
    sects = [
        n.get("name", "")
        for n in graph.get("nodes", [])
        if n.get("type") == "门派"
    ]
    sects = [s for s in sects if s]
    for name in sorted(sects, key=len, reverse=True):
        if name in question:
            return name
    return None


@register("sect_agg")
class SectAggMethod(QAMethod):
    name = "sect_agg"

    def __init__(self, data_loader: Any = None, chunks=None):
        self.data_loader = data_loader
        self.chunks = chunks

    def ask(self, question: str, top_k: int = 5) -> Answer:
        if not isinstance(question, str) or not question.strip():
            raise ValueError("question 必须是非空字符串")

        seed = _find_seed_sect(question)
        if not seed:
            return Answer(
                answer_text="未能从问题中识别出门派实体。",
                method_name=self.name,
                evidence=[],
                debug_info={"question": question, "seed": None},
                raw_context="",
            )

        try:
            rows: List[Dict[str, Any]] = run_query(
                """
                MATCH (s:门派 {name: $sect})<-[:BELONGS_TO]-(p:人物)
                OPTIONAL MATCH (p)-[:MASTERS]->(a:武功)
                RETURN p.name AS person, collect(a.name) AS arts
                ORDER BY p.name
                """,
                {"sect": seed},
            )
        except Exception as e:
            return Answer(
                answer_text=f"查询门派聚合失败（请确认 Neo4j 已启动、数据已入库）：{e}",
                method_name=self.name,
                evidence=[],
                debug_info={"seed": seed, "error": str(e)},
                raw_context="",
            )

        if not rows:
            return Answer(
                answer_text=f"图谱中没有找到门派 {seed} 的成员信息。",
                method_name=self.name,
                evidence=[{"seed": seed, "members": []}],
                debug_info={"seed": seed, "hit_count": 0},
                raw_context=f"{seed} 无成员",
            )

        # 整理成员清单
        members = []
        for r in rows:
            arts = [a for a in (r.get("arts") or []) if a]
            members.append({"person": r["person"], "arts": arts})

        # 生成答案文本
        parts = []
        for m in members:
            if m["arts"]:
                parts.append(f"{m['person']}（会 {'、'.join(m['arts'])}）")
            else:
                parts.append(f"{m['person']}")
        answer_text = f"{seed} 门下成员：{'；'.join(parts)}。"

        return Answer(
            answer_text=answer_text,
            method_name=self.name,
            evidence=members,
            debug_info={"seed": seed, "member_count": len(members)},
            raw_context=f"{seed} 成员 {len(members)} 人",
        )
