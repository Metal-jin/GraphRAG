"""问题解析与关系计划（任务 11 / 13）。

把"郭靖的妻子的师父是谁"这类问题解析成：起点实体 + 有序关系步骤。
检索方法据此逐步执行，而不是各自用关键词猜一次关系。

纯函数，不依赖数据库；执行器通过注入的查询函数工作，便于离线测试。
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, replace
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from core.entity_link import EntityMatch
from core.evidence import make_edge, make_node
from core.ontology import RELATION_TYPES, is_noise_name


FOUNDING_VERBS = ("创立", "创建", "创办", "开创", "所创", "创下", "开派", "建立")


@dataclass(frozen=True)
class RelationStep:
    """一步关系。direction 为 in 表示"目标指向当前实体"。"""

    relation: str
    direction: str      # "out" | "in" | "both"
    keyword: str
    position: int
    target: str = ""     # 题面明确给出的这一跳终点

    def to_dict(self) -> Dict:
        result = {"relation": self.relation, "direction": self.direction,
                  "keyword": self.keyword, "position": self.position}
        if self.target:
            result["target"] = self.target
        return result


# (关键词, 关系类型, 方向)；关键词长的放前面，避免"父亲"被"父"抢
RELATION_KEYWORDS: Tuple[Tuple[str, str, str], ...] = (
    # 师徒
    ("太师父", "MASTER_OF", "in"),
    ("师祖", "MASTER_OF", "in"),
    ("师父", "MASTER_OF", "in"),
    ("师傅", "MASTER_OF", "in"),
    ("恩师", "MASTER_OF", "in"),
    ("师承", "MASTER_OF", "in"),
    ("师从", "MASTER_OF", "in"),
    ("徒弟", "MASTER_OF", "out"),
    ("弟子", "MASTER_OF", "out"),
    ("徒儿", "MASTER_OF", "out"),
    ("门徒", "MASTER_OF", "out"),
    ("传人", "MASTER_OF", "out"),
    # 亲属
    ("父亲", "PARENT_OF", "in"),
    ("母亲", "PARENT_OF", "in"),
    ("爸爸", "PARENT_OF", "in"),
    ("妈妈", "PARENT_OF", "in"),
    ("爹", "PARENT_OF", "in"),
    ("娘", "PARENT_OF", "in"),
    ("父母", "PARENT_OF", "in"),
    ("儿子", "PARENT_OF", "out"),
    ("女儿", "PARENT_OF", "out"),
    ("子女", "PARENT_OF", "out"),
    ("孩子", "PARENT_OF", "out"),
    # 婚姻
    ("妻子", "SPOUSE_OF", "both"),
    ("丈夫", "SPOUSE_OF", "both"),
    ("老婆", "SPOUSE_OF", "both"),
    ("老公", "SPOUSE_OF", "both"),
    ("夫人", "SPOUSE_OF", "both"),
    ("配偶", "SPOUSE_OF", "both"),
    ("夫妻", "SPOUSE_OF", "both"),
    # 结拜 / 仇敌
    ("结拜", "SWORN_BROTHER_OF", "both"),
    ("义兄", "SWORN_BROTHER_OF", "both"),
    ("义弟", "SWORN_BROTHER_OF", "both"),
    ("义结金兰", "SWORN_BROTHER_OF", "both"),
    ("仇敌", "ENEMY_OF", "both"),
    ("敌人", "ENEMY_OF", "both"),
    ("死对头", "ENEMY_OF", "both"),
    ("仇人", "ENEMY_OF", "both"),
)

# 复合称谓：拆成两步
COMPOSITE_KEYWORDS: Dict[str, Tuple[Tuple[str, str], ...]] = {
    "岳父": (("SPOUSE_OF", "both"), ("PARENT_OF", "in")),
    "岳母": (("SPOUSE_OF", "both"), ("PARENT_OF", "in")),
    "公公": (("SPOUSE_OF", "both"), ("PARENT_OF", "in")),
    "婆婆": (("SPOUSE_OF", "both"), ("PARENT_OF", "in")),
    "外公": (("PARENT_OF", "in"), ("PARENT_OF", "in")),
    "外婆": (("PARENT_OF", "in"), ("PARENT_OF", "in")),
    "孙子": (("PARENT_OF", "out"), ("PARENT_OF", "out")),
    "孙女": (("PARENT_OF", "out"), ("PARENT_OF", "out")),
    "师父的师父": (("MASTER_OF", "in"), ("MASTER_OF", "in")),
}


_REFERENCE_SUFFIXES = (
    "父亲", "母亲", "师父", "师傅", "爹爹", "娘亲", "爸爸", "妈妈",
    "妻子", "丈夫", "老婆", "儿子", "女儿", "义父", "义母",
    "之父", "之母", "之妻", "之子", "之女",
)
_UNMODELED_TITLES = ("义父", "义母", "干爹", "干娘", "侄子", "外甥")
_NAMED_UNMODELED = re.compile(r"[的之]?(?:" + "|".join(_UNMODELED_TITLES) + r")\s*[（(]?")
_REFERENCE_NAMES = ({keyword for keyword, _, _ in RELATION_KEYWORDS}
                    | set(COMPOSITE_KEYWORDS) | set(_UNMODELED_TITLES)
                    | {"婴儿", "初生婴儿", "女孩儿", "男孩儿", "父亲", "母亲"})


def is_person_reference(name: str) -> bool:
    """过滤亲属指称和抽取出的通用称呼。已确认的别名应先归一。"""
    return (is_noise_name(name) or "的" in name or name in _REFERENCE_NAMES
            or name.endswith(_REFERENCE_SUFFIXES))


def focus_person_question(
    question: str, matches: Sequence[EntityMatch], aliases: Mapping[str, str]
) -> Tuple[str, List[EntityMatch]]:
    """只在题面用称谓直接点名时，从该人物开始查后续关系。"""
    people = [
        replace(m, canonical=aliases.get(m.name, aliases.get(m.canonical, m.canonical)))
        for m in matches
    ]
    people = [m for m in people if not is_person_reference(m.canonical)]
    if len(people) >= 2:
        subject, named = people[:2]
        prefix = question[subject.end:named.start].strip()
        suffix = question[named.end:]
        if (_NAMED_UNMODELED.fullmatch(prefix)
                and re.match(r"\s*[）)]?\s*[的之]", suffix)
                and plan_relations(suffix)):
            # 这个人的身份由题面给出。查询只验证后面的关系。
            return question[named.start:], [
                replace(m, start=m.start - named.start, end=m.end - named.start)
                for m in people[1:]
            ]
    return question, people


def plan_relations(question: str, people: Sequence[EntityMatch] = ()) -> List[RelationStep]:
    """从问题文本解析有序关系步骤（按出现位置排序、互不重叠）。

    复合称谓（岳父/外公/师父的师父…）先占位，再展开成多步；
    普通关键词若与复合称谓区间重叠则丢弃，避免同一段文本被解析两次。
    """
    text = question or ""

    # 1) 复合称谓占位（同一关键词只取首次出现）
    composites: List[Tuple[int, int, str, Tuple[Tuple[str, str], ...]]] = []
    for keyword, steps in COMPOSITE_KEYWORDS.items():
        start = text.find(keyword)
        if start != -1 and not any(m.start <= start < m.end for m in people):
            composites.append((start, start + len(keyword), keyword, steps))
    composites.sort(key=lambda c: c[0])

    # 2) 普通关键词（排除落在复合区间内的）
    normal: List[Tuple[int, int, str, str, str]] = []
    for keyword, relation, direction in RELATION_KEYWORDS:
        start = text.find(keyword)
        while start != -1:
            end = start + len(keyword)
            inside = any(not (end <= c[0] or start >= c[1]) for c in composites)
            inside_name = any(start < m.end and m.start < end for m in people)
            is_address = keyword == "娘" and start > 0 and text[start - 1] == "姑"
            if not inside and not inside_name and not is_address:
                normal.append((start, end, keyword, relation, direction))
            start = text.find(keyword, start + 1)

    # 3) 长关键词优先、互不重叠
    normal.sort(key=lambda m: (-(m[1] - m[0]), m[0]))
    taken: List[Tuple[int, int, str, str, str]] = []
    for match in normal:
        if any(not (match[1] <= t[0] or match[0] >= t[1]) for t in taken):
            continue
        taken.append(match)

    # 4) 合并成有序步骤
    events: List[Tuple[int, int, RelationStep]] = []
    for start, _end, keyword, steps in composites:
        for offset, (relation, direction) in enumerate(steps):
            events.append((start, offset, RelationStep(relation, direction, keyword, start)))
    for start, _end, keyword, relation, direction in taken:
        if re.search(r"(?:是|为)(?:谁|哪[个位])的\s*$", text[:start]):
            direction = {"in": "out", "out": "in"}.get(direction, direction)
        events.append((start, 0, RelationStep(relation, direction, keyword, start)))
    events.sort(key=lambda item: (item[0], item[1]))
    steps = [event[2] for event in events]
    for i, (step, following) in enumerate(zip(steps, steps[1:])):
        end = step.position + len(step.keyword)
        for match in people:
            if (end <= match.start < following.position
                    and re.fullmatch(r"\s*[（(]?\s*", text[end:match.start])):
                steps[i] = replace(step, target=match.canonical)
                break
    return steps


def plan_text(steps: Sequence[RelationStep]) -> str:
    return " -> ".join(f"{s.relation}({s.direction})" for s in steps) or "无关系步骤"


# ============ 执行器 ============

def _neighbors(run_query: Callable, names: Sequence[str], step: RelationStep,
               targets: Sequence[str], limit: int) -> List[Dict]:
    """先按题面指定的终点约束查询，再限制候选数量。"""
    if step.relation not in RELATION_TYPES:
        raise ValueError(f"未知关系类型：{step.relation}")
    rows: List[Dict] = []
    directions = ("out", "in") if step.direction == "both" else (step.direction,)
    for direction in directions:
        current, other = ("b", "a") if direction == "in" else ("a", "b")
        rows.extend(run_query(
            f"MATCH (a:人物)-[r:{step.relation}]->(b:人物) "
            f"WHERE {current}.name IN $names AND a <> b "
            f"AND (size($targets) = 0 OR {other}.name IN $targets) "
            "RETURN a.name AS source, b.name AS target, type(r) AS type, "
            "coalesce(r.chunk_ids, []) AS chunk_ids, "
            "coalesce(r.snippets, []) AS snippets "
            f"ORDER BY CASE WHEN {other}.name CONTAINS '的' THEN 1 ELSE 0 END, "
            f"size(coalesce(r.chunk_ids, [])) DESC, {other}.name, a.name, b.name "
            "LIMIT $limit", {"names": list(names), "targets": list(targets), "limit": limit}))
    return rows


def traverse_plan(run_query: Callable, seed: str, steps: Sequence[RelationStep],
                  limit: int = 5, *, aliases: Optional[Mapping[str, str]] = None) -> Dict:
    """保留实际走通的分支，按来源证据排序后返回完整路径。"""
    aliases = aliases or {}
    names_for: Dict[str, List[str]] = defaultdict(list)
    for alias, canonical in aliases.items():
        names_for[canonical].append(alias)
    seed = aliases.get(seed, seed)
    frontier = [((seed,), ())]
    # 每步先保留较宽的候选池，最终输出仍受 top_k 约束。
    width = max(10, limit * 2)

    for step_index, step in enumerate(steps):
        candidates = []
        cache: Dict[str, List[Dict]] = {}
        target = aliases.get(step.target, step.target)
        target_names = [target, *names_for[target]] if target else []
        for names, edges in frontier:
            current = names[-1]
            try:
                if current not in cache:
                    cache[current] = _neighbors(run_query, [current, *names_for[current]],
                                                step, target_names, width * 2)
            except Exception as exc:
                return {"paths": [], "nodes": [], "edges": [], "final": [],
                        "stopped_at": f"查询失败：{exc}", "error": str(exc)}
            for row in cache[current]:
                source = aliases.get(row["source"], row["source"])
                destination = aliases.get(row["target"], row["target"])
                if source == current and step.direction in ("out", "both"):
                    other, direction = destination, "forward"
                elif destination == current and step.direction in ("in", "both"):
                    other, direction = source, "backward"
                else:
                    continue
                if other in names or is_person_reference(other) or (target and other != target):
                    continue
                edge = make_edge(
                    source, destination, row["type"],
                    direction=direction,
                    chunk_ids=row.get("chunk_ids") or [],
                    snippets=row.get("snippets") or [])
                candidates.append(((*names, other), (*edges, edge)))
        if not candidates:
            return {"paths": [], "nodes": [], "edges": [], "final": [],
                    "stopped_at": f"第 {step_index + 1} 步（{step.keyword}）没有检索到结果"}
        candidates.sort(key=_path_priority)
        unique = {}
        for names, edges in candidates:
            unique.setdefault(names, edges)
            if len(unique) >= width:
                break
        frontier = list(unique.items())

    selected = frontier[:limit] if steps else []
    paths = [{"names": list(names), "edges": list(edges)} for names, edges in selected]
    return {
        "paths": paths,
        "nodes": _dedupe_nodes(make_node(name, "人物") for names, _ in selected for name in names),
        "edges": _dedupe_edges(edge for _, edges in selected for edge in edges),
        "stopped_at": "",
        "final": list(dict.fromkeys(names[-1] for names, _ in selected)),
    }


def _path_priority(path) -> Tuple:
    names, edges = path
    return (-sum(bool(edge["chunk_ids"]) for edge in edges),
            -sum(bool(edge["snippets"]) for edge in edges),
            -sum(len(edge["chunk_ids"]) for edge in edges), names)


def _dedupe_edges(edges: Iterable[Dict]) -> List[Dict]:
    seen, out = set(), []
    for edge in edges:
        key = (edge["source"], edge["target"], edge["type"])
        if key not in seen:
            seen.add(key)
            out.append(edge)
    return out


def _dedupe_nodes(nodes: Iterable[Dict]) -> List[Dict]:
    seen, out = set(), []
    for node in nodes:
        if node["name"] not in seen:
            seen.add(node["name"])
            out.append(node)
    return out


__all__ = ["RelationStep", "plan_relations", "traverse_plan", "plan_text",
           "focus_person_question", "is_person_reference",
           "RELATION_KEYWORDS", "COMPOSITE_KEYWORDS"]
