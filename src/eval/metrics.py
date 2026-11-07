"""评测指标（任务 23 重做）。

旧指标的问题：
- "答案不是洪七公"仍算命中；
- 多答案题只命中一个实体也算全对；
- 两条不连通的边也能让 path_completeness = 1.0；
- 证据里出现答案名字 ≠ 证据支持所问关系。

新指标分三层：
1. 字符串命中（entity_string_hit）：保留作**辅助**指标，不叫"事实准确率"；
2. 实体级 P/R/F1 与集合完全匹配：区分"多个都必须答对"与"同一实体多个别名"；
3. 结构与证据指标：路径连续性/方向/起终点、证据与预期关系的匹配。

全部是纯函数，不依赖数据库与 LLM。
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

# ============ 文本归一化 ============

_PUNCT_CHARS = chr(96) + """*_#~。，、；：！？（）()【】[]{}“”‘’"'：:,.!?;"""
_PUNCT_RE = re.compile("[" + re.escape(_PUNCT_CHARS) + r"\s]+")
NEGATION_MARKERS = ("不是", "并非", "没有", "不属于", "非是", "而不是", "不认识", "未")


def normalize_text(text: Any) -> str:
    if text is None:
        return ""
    text = str(text).strip().lower()
    return _PUNCT_RE.sub("", text)


def _occurrences(text: str, needle: str) -> List[int]:
    positions, start = [], text.find(needle)
    while start != -1:
        positions.append(start)
        start = text.find(needle, start + 1)
    return positions


def is_negated(answer: str, alias: str, window: int = 4) -> bool:
    """判断答案中该实体的每次出现是否都被否定词修饰。"""
    if not alias:
        return False
    normalized_answer = normalize_text(answer)
    normalized_alias = normalize_text(alias)
    if not normalized_alias or normalized_alias not in normalized_answer:
        return False
    for position in _occurrences(normalized_answer, normalized_alias):
        prefix = normalized_answer[max(0, position - window):position]
        if not any(marker in prefix for marker in NEGATION_MARKERS):
            return False  # 至少有一处是肯定提及
    return True


def entity_string_hit(answer_text: str, acceptable_answers: Iterable[str]) -> bool:
    """字符串命中（辅助指标）：命中任一别名且不是否定表述。"""
    if not normalize_text(answer_text):
        return False
    for alias in acceptable_answers or []:
        alias_norm = normalize_text(alias)
        if not alias_norm:
            continue
        if alias_norm in normalize_text(answer_text) and not is_negated(answer_text, alias):
            return True
    return False


# 兼容旧名
entity_hit = entity_string_hit


# ============ 实体级指标 ============

def entity_matches(answer_text: str, expected: Iterable[str]) -> Set[str]:
    """返回答案中**肯定提及**的预期实体集合。"""
    found: Set[str] = set()
    answer_norm = normalize_text(answer_text)
    for entity in expected or []:
        entity_norm = normalize_text(entity)
        if entity_norm and entity_norm in answer_norm and not is_negated(answer_text, entity):
            found.add(entity)
    return found


def entity_prf(answer_text: str, expected: Iterable[str]) -> Dict[str, float]:
    """实体级 precision / recall / F1 / 完全匹配。

    expected 是"必须回答的实体集合"（同一实体的多个别名请用 acceptable_answers）。
    答案里的其它实体无法可靠枚举，因此 precision 采用保守近似：
    命中即为 1.0，未命中为 0.0；recall 为命中数 / 必须实体数。
    """
    expected_set = {e for e in (expected or []) if normalize_text(e)}
    if not expected_set:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0,
                "exact_match": 0.0, "matched": 0, "expected": 0}
    matched = len(entity_matches(answer_text, expected_set))
    recall = matched / len(expected_set)
    precision = 1.0 if matched else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {"precision": round(precision, 4), "recall": round(recall, 4),
            "f1": round(f1, 4), "exact_match": 1.0 if matched == len(expected_set) else 0.0,
            "matched": matched, "expected": len(expected_set)}


# ============ 路径与证据 ============

def _bundle_edges(evidence: Iterable[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    edges: List[Mapping[str, Any]] = []
    for item in evidence or []:
        for edge in item.get("edges") or []:
            edges.append(edge)
        legacy = item.get("legacy") or {}
        if not item.get("edges") and legacy.get("source") and legacy.get("target"):
            edges.append({"source": legacy.get("source"), "target": legacy.get("target"),
                          "type": legacy.get("type") or legacy.get("rel"),
                          "direction": legacy.get("direction", "forward")})
    return edges


def path_is_continuous(evidence: Iterable[Mapping[str, Any]]) -> Tuple[bool, int]:
    """检查证据里的路径是否连通：边首尾相接。返回 (是否连通, 最长连通边数)。"""
    edges = _bundle_edges(evidence)
    if not edges:
        return False, 0
    best = 0
    for item in evidence or []:
        item_edges = item.get("edges") or []
        if len(item_edges) < 2:
            continue
        node = item_edges[0].get("source")
        count = 0
        for edge in item_edges:
            if edge.get("source") != node:
                break
            node = edge.get("target")
            count += 1
        best = max(best, count)
    if best == 0:
        best = 1 if edges else 0
    return best >= 1, best


def path_completeness(question: Mapping[str, Any],
                      evidence: Iterable[Mapping[str, Any]]) -> float:
    """路径完整性：要求路径**连通**且覆盖预期跳数。"""
    evidence = list(evidence or [])
    expected_hops = max(1, int(question.get("hop", 1) or 1))
    if not evidence:
        return 0.0
    continuous, covered = path_is_continuous(evidence)
    if not continuous:
        return 0.0
    return round(min(1.0, covered / expected_hops), 4)


# 关系类型 -> 问题里可能出现的说法（同一关系的多个中文同义词）
_REL_SYNONYMS = {
    "MASTER_OF": ("师徒", "师父", "师傅", "恩师", "徒弟", "弟子", "师承", "师门"),
    "SPOUSE_OF": ("夫妻", "妻子", "丈夫", "配偶", "夫人", "老婆", "老公"),
    "PARENT_OF": ("父母", "父亲", "母亲", "父子", "父女", "母子", "母女",
                  "子女", "儿子", "女儿", "孩子"),
    "SWORN_BROTHER_OF": ("结拜", "义兄", "义弟", "结义"),
    "ENEMY_OF": ("仇敌", "敌人", "对手", "仇人"),
    "BELONGS_TO": ("门派", "帮派", "所属", "归属"),
    "MASTERS": ("精通", "武功", "绝学", "绝技"),
    "FOUNDER_OF": ("创立", "创始人", "开派"),
    "LOCATED_IN": ("地点", "位于", "所在"),
    "BRANCHED_FROM": ("演化", "源自", "衍生"),
    "DESCENDANT_OF": ("血缘", "后人", "之后", "后代"),
}


def _rel_translation(rel_type: Any) -> str:
    synonyms = _REL_SYNONYMS.get(str(rel_type or "").upper(), ())
    return synonyms[0] if synonyms else ""


def _relation_matches(rel_type: Any, expected: str) -> bool:
    """关系类型是否与问题里期待的关系说法一致（支持同义词）。"""
    if not expected:
        return True
    synonyms = _REL_SYNONYMS.get(str(rel_type or "").upper(), ())
    return any(word and word in expected for word in synonyms)


def path_validity(question: Mapping[str, Any],
                  evidence: Iterable[Mapping[str, Any]]) -> float:
    """方向/关系类型校验（近似）：边类型属于本体且方向字段合法。"""
    from core.ontology import RELATION_TYPES

    edges = _bundle_edges(evidence)
    if not edges:
        return 0.0
    valid = 0
    for edge in edges:
        rel = str(edge.get("type") or "").upper()
        direction = edge.get("direction", "forward")
        if rel in RELATION_TYPES and direction in ("forward", "backward", "symmetric"):
            valid += 1
    return round(valid / len(edges), 4)


def evidence_sufficiency(question: Mapping[str, Any], answer_text: str,
                         evidence: Iterable[Mapping[str, Any]]) -> float:
    """证据是否真的支持所问关系：答案命中 × 证据覆盖预期关系。"""
    evidence = list(evidence or [])
    expected = (question.get("acceptable_answers")
                or question.get("answer_entities") or [])
    answer_ok = 1.0 if entity_string_hit(answer_text, expected) else 0.0
    if not evidence:
        return 0.0
    edges = _bundle_edges(evidence)
    if not edges:
        return round(answer_ok * 0.5, 4)
    expected_rel = str(question.get("relation") or "").strip()
    rel_hit = 1.0
    if expected_rel and expected_rel not in ("", "关系"):
        rel_hit = 1.0 if any(_relation_matches(edge.get("type"), expected_rel)
                             for edge in edges) else 0.5
    return round((answer_ok + rel_hit) / 2, 4)


def evaluate_result(question: Mapping[str, Any], answer_text: str,
                    evidence: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    """单题全部指标。"""
    evidence = list(evidence or [])
    expected = question.get("answer_entities") or []
    acceptable = question.get("acceptable_answers") or []
    prf = entity_prf(answer_text, expected)
    return {
        "entity_hit": entity_string_hit(answer_text, acceptable),
        "path_completeness": path_completeness(question, evidence),
        "evidence_sufficiency": evidence_sufficiency(question, answer_text, evidence),
        "evidence_count": len(evidence),
        "entity_string_hit": entity_string_hit(answer_text, acceptable),
        "entity_precision": prf["precision"],
        "entity_recall": prf["recall"],
        "entity_f1": prf["f1"],
        "exact_match": prf["exact_match"],
        "path_validity": path_validity(question, evidence),
    }


# ============ 分类汇总 ============

def category_name(question: Mapping[str, Any]) -> str:
    raw = str(question.get("category", "")).lower()
    if any(k in raw for k in ("武功", "传承")):
        return "武功"
    if "门派" in raw or "帮派" in raw:
        return "门派"
    if any(k in raw for k in ("比较", "综合")):
        return "综合"
    return "人物"


def _mean(values: Sequence[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def summarize_by(rows: Iterable[Mapping[str, Any]],
                 keys: Sequence[str]) -> List[Dict[str, Any]]:
    """按任意维度（method/category/book/hop/difficulty）汇总。"""
    groups: Dict[Tuple, List[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[tuple(str(row.get(key, "")) for key in keys)].append(row)
    output = []
    for group_key, items in sorted(groups.items()):
        record: Dict[str, Any] = {key: value for key, value in zip(keys, group_key)}
        record.update({
            "questions": len(items),
            "ok": sum(1 for x in items if x.get("status") == "ok"),
            "accuracy": _mean([1.0 if (x.get("entity_string_hit") or x.get("entity_hit"))
                               else 0.0 for x in items]),
            "exact_match": _mean([float(x.get("exact_match", 0) or 0) for x in items]),
            "entity_f1": _mean([float(x.get("entity_f1", 0) or 0) for x in items]),
            "path_completeness": _mean([float(x.get("path_completeness", 0) or 0)
                                        for x in items]),
            "path_validity": _mean([float(x.get("path_validity", 0) or 0) for x in items]),
            "evidence_sufficiency": _mean([float(x.get("evidence_sufficiency", 0) or 0)
                                           for x in items]),
            "error_rate": _mean([1.0 if x.get("status") == "error" else 0.0 for x in items]),
            "degraded_rate": _mean([1.0 if x.get("status") == "degraded" else 0.0
                                    for x in items]),
        })
        output.append(record)
    return output


def summarize_by_category(rows: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """兼容旧接口：按方法 + 四类汇总。"""
    return summarize_by(rows, ("method", "category"))


# ============ 注入形式对比（结构演示，不泄漏标准答案） ============

def compare_injection_forms(facts: Sequence[Mapping[str, Any]],
                            contexts: Mapping[str, str]) -> Dict[str, Any]:
    """比较三种注入形式的**结构指标**（不是效果实验，也不参与准确率结论）。"""
    result = {}
    for form, context in contexts.items():
        text = context or ""
        result[form] = {
            "context_chars": len(text),
            "fact_count": len(facts),
            "has_direction": ("->" in text) or ("<-" in text),
            "has_relation_label": any(
                marker in text for marker in
                ("师徒", "夫妻", "父母", "结拜", "仇敌", "属于", "精通")),
            "empty": not text.strip(),
        }
    return result


__all__ = ["normalize_text", "entity_hit", "entity_string_hit", "is_negated",
           "entity_matches", "entity_prf", "path_is_continuous", "path_completeness",
           "path_validity", "evidence_sufficiency", "evaluate_result",
           "category_name", "summarize_by", "summarize_by_category",
           "compare_injection_forms"]
