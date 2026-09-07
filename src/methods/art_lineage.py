"""武功传承检索（art_lineage）。

领域策略之三：针对"武功传承"问题（如"降龙十八掌从谁传到谁"），
通过师徒（MASTER_OF）+ 精通（MASTERS）组合推导传承链，无需专门的三元关系。
"""

from typing import Any, Dict, List, Optional

from core.interfaces import Answer, QAMethod
from core.registry import register
from ingest.data_loader import get_graph, run_query


def _find_seed_art(question: str) -> Optional[str]:
    """从问题中识别起始武功（简单字符串匹配，长名优先）。"""
    try:
        graph = get_graph()
    except Exception:
        return None
    arts = [
        n.get("name", "")
        for n in graph.get("nodes", [])
        if n.get("type") == "武功"
    ]
    arts = [a for a in arts if a]
    for name in sorted(arts, key=len, reverse=True):
        if name in question:
            return name
    return None


@register("art_lineage")
class ArtLineageMethod(QAMethod):
    name = "art_lineage"

    def __init__(self, data_loader: Any = None, chunks=None):
        self.data_loader = data_loader
        self.chunks = chunks

    def ask(self, question: str, top_k: int = 5) -> Answer:
        if not isinstance(question, str) or not question.strip():
            raise ValueError("question 必须是非空字符串")

        seed = _find_seed_art(question)
        if not seed:
            return Answer(
                answer_text="未能从问题中识别出武功实体。",
                method_name=self.name,
                evidence=[],
                debug_info={"question": question, "seed": None},
                raw_context="",
            )

        try:
            rows: List[Dict[str, Any]] = run_query(
                """
                MATCH (a:武功 {name: $art})<-[:MASTERS]-(m:人物)-[:MASTER_OF]->(d:人物)
                WHERE (d)-[:MASTERS]->(a)
                RETURN m.name AS source, d.name AS target
                """,
                {"art": seed},
            )
        except Exception as e:
            return Answer(
                answer_text=f"查询武功传承失败（请确认 Neo4j 已启动、数据已入库）：{e}",
                method_name=self.name,
                evidence=[],
                debug_info={"seed": seed, "error": str(e)},
                raw_context="",
            )

        if not rows:
            return Answer(
                answer_text=f"图谱中没有找到 {seed} 的传承信息。",
                method_name=self.name,
                evidence=[{"art": seed, "lineage": []}],
                debug_info={"seed": seed, "hit_count": 0},
                raw_context=f"{seed} 无传承链",
            )

        # 整理传承链
        lineage = [{"from": r["source"], "to": r["target"]} for r in rows]

        # 生成答案文本
        parts = [f"{r['source']} 传给 {r['target']}" for r in rows]
        answer_text = f"{seed} 的传承：{'；'.join(parts)}。"

        return Answer(
            answer_text=answer_text,
            method_name=self.name,
            evidence=lineage,
            debug_info={"seed": seed, "lineage_count": len(lineage)},
            raw_context="\n".join(f"{r['source']} -> {r['target']}" for r in rows),
        )
