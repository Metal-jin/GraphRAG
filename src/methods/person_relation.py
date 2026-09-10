"""人物关系检索（person_relation）。

领域策略之四：针对非师徒的人物关系（父子/配偶/结拜/仇敌），
根据问题关键词识别关系类型，用 Cypher 查询对应关系并返回三元组证据。

与 master_chain（专做师徒多跳链）互补：本策略针对 PARENT_OF / SPOUSE_OF /
SWORN_BROTHER_OF / ENEMY_OF 等单跳关系，证据以三元组形式返回。
"""

from typing import Any, Dict, List, Optional

from core.interfaces import Answer, QAMethod
from core.registry import register
from ingest.data_loader import get_graph, run_query


# 关系关键词 → 关系类型（从问题里识别问的是哪种关系）
RELATION_KEYWORDS: Dict[str, List[str]] = {
    "PARENT_OF": ["父亲", "母亲", "爸爸", "妈妈", "爹", "娘", "儿子", "女儿",
                  "子女", "孩子", "父母", "父子", "父女", "母子", "母女", "爹娘"],
    "SPOUSE_OF": ["配偶", "妻子", "丈夫", "老婆", "老公", "夫人", "娘子", "夫妻"],
    "SWORN_BROTHER_OF": ["结拜", "义兄", "义弟", "义结金兰", "结义"],
    "ENEMY_OF": ["仇敌", "敌人", "对手", "死对头", "仇人"],
}

# 关系类型的中文名（注入时用，方便 LLM 理解）
REL_NAMES = {
    "PARENT_OF": "父母子女",
    "SPOUSE_OF": "配偶",
    "SWORN_BROTHER_OF": "结拜",
    "ENEMY_OF": "仇敌",
}


def _find_seed_person(question: str) -> Optional[str]:
    """从问题中识别起始人物（长名优先）。"""
    try:
        graph = get_graph()
    except Exception:
        return None
    people = [n.get("name", "") for n in graph.get("nodes", [])
              if n.get("type") == "人物"]
    people = [p for p in people if p]
    for name in sorted(people, key=len, reverse=True):
        if name in question:
            return name
    return None


def _detect_relation_type(question: str) -> Optional[str]:
    """根据关键词识别关系类型（长关键词优先，避免「父亲」误匹配「父母」）。"""
    for rel_type, keywords in RELATION_KEYWORDS.items():
        for kw in sorted(keywords, key=len, reverse=True):
            if kw in question:
                return rel_type
    return None


@register("person_relation")
class PersonRelationMethod(QAMethod):
    name = "person_relation"

    def __init__(self, data_loader: Any = None, chunks=None):
        self.data_loader = data_loader
        self.chunks = chunks

    def ask(self, question: str, top_k: int = 5) -> Answer:
        if not isinstance(question, str) or not question.strip():
            raise ValueError("question 必须是非空字符串")

        seed = _find_seed_person(question)
        if not seed:
            return Answer(
                answer_text="未能从问题中识别出人物实体。",
                method_name=self.name, evidence=[],
                debug_info={"question": question, "seed": None}, raw_context="",
            )

        rel_type = _detect_relation_type(question)
        if not rel_type:
            return Answer(
                answer_text="未能识别问题涉及的关系类型。",
                method_name=self.name, evidence=[],
                debug_info={"seed": seed, "rel_type": None}, raw_context="",
            )

        rel_name = REL_NAMES.get(rel_type, rel_type)

        try:
            # 出边：seed 是关系起点（如「郭靖的儿子」→ 郭靖 -PARENT_OF-> 儿子）
            out_rows = run_query(
                """
                MATCH (p:人物 {name: $name})-[r]->(other:人物)
                WHERE type(r) = $rel_type
                RETURN p.name AS source, type(r) AS rel, other.name AS target
                """,
                {"name": seed, "rel_type": rel_type},
            )
            # 入边：seed 是关系终点（如「黄蓉的父亲」→ 父亲 -PARENT_OF-> 黄蓉）
            in_rows = run_query(
                """
                MATCH (p:人物 {name: $name})<-[r]-(other:人物)
                WHERE type(r) = $rel_type
                RETURN other.name AS source, type(r) AS rel, p.name AS target
                """,
                {"name": seed, "rel_type": rel_type},
            )
        except Exception as e:
            return Answer(
                answer_text=f"查询人物关系失败（请确认 Neo4j 已启动、数据已入库）：{e}",
                method_name=self.name, evidence=[],
                debug_info={"seed": seed, "error": str(e)}, raw_context="",
            )

        # 去重 + 转成中文关系名的三元组
        triples = []
        seen = set()
        for row in out_rows + in_rows:
            key = (row["source"], row["rel"], row["target"])
            if key in seen:
                continue
            seen.add(key)
            triples.append({"source": row["source"], "rel": rel_name, "target": row["target"]})

        if not triples:
            return Answer(
                answer_text=f"图谱中没有找到 {seed} 的{rel_name}关系。",
                method_name=self.name, evidence=[],
                debug_info={"seed": seed, "rel_type": rel_type, "hit_count": 0},
                raw_context=f"{seed} 无{rel_name}关系",
            )

        # 答案文本只做概述，具体回答交给 LLM 根据三元组生成
        answer_text = f"找到 {seed} 的{rel_name}关系 {len(triples)} 条。"

        return Answer(
            answer_text=answer_text,
            method_name=self.name,
            evidence=triples,
            debug_info={"seed": seed, "rel_type": rel_type, "hit_count": len(triples)},
            raw_context="\n".join(
                f"({t['source']}，{t['rel']}，{t['target']})" for t in triples
            ),
        )
