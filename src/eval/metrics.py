"""可解释性评测指标与分类汇总。

指标只依赖 ``Answer`` 的 evidence/debug_info，不调用 LLM 或 Neo4j，因而可在
CI 和离线环境稳定复现。路径完整性衡量多跳证据是否覆盖预期跳数；证据充分性
衡量答案实体和证据实体是否都被召回，并惩罚空证据。
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping

from .run_compare import entity_hit, normalize_text


def _evidence_entities(evidence: Iterable[Mapping[str, Any]]) -> set[str]:
    names: set[str] = set()
    for item in evidence or []:
        for key in ("name", "source", "target", "person", "entity", "seed"):
            value = item.get(key)
            if value:
                names.add(normalize_text(str(value)))
    return {n for n in names if n}


def path_completeness(question: Mapping[str, Any], evidence: Iterable[Mapping[str, Any]]) -> float:
    """返回 ``0..1`` 的路径完整性；单跳题有证据即满分，多跳题按跳数覆盖。"""
    expected_hops = max(1, int(question.get("hop", 1) or 1))
    evidence = list(evidence or [])
    if not evidence:
        return 0.0
    depths = [int(e["depth"]) for e in evidence if str(e.get("depth", "")).isdigit()]
    if depths:
        covered = len({d for d in depths if d > 0})
    else:
        covered = sum(1 for e in evidence if e.get("source") and e.get("target"))
    return round(min(1.0, covered / expected_hops), 4)


def evidence_sufficiency(
    question: Mapping[str, Any], answer_text: str, evidence: Iterable[Mapping[str, Any]]
) -> float:
    """衡量证据是否足以支持答案实体，取答案命中与证据命中的平均值。"""
    expected = question.get("acceptable_answers") or question.get("answer_entities") or []
    answer_ok = 1.0 if entity_hit(answer_text, expected) else 0.0
    evidence_text = " ".join(str(value) for item in (evidence or []) for value in item.values())
    evidence_ok = 1.0 if entity_hit(evidence_text, expected) else 0.0
    return round((answer_ok + evidence_ok) / 2, 4)


def evaluate_result(question: Mapping[str, Any], answer_text: str, evidence: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """计算单题的准确率与两项可解释性指标。"""
    evidence = list(evidence or [])
    return {
        "entity_hit": entity_hit(answer_text, question.get("acceptable_answers", [])),
        "path_completeness": path_completeness(question, evidence),
        "evidence_sufficiency": evidence_sufficiency(question, answer_text, evidence),
        "evidence_count": len(evidence),
    }


def category_name(question: Mapping[str, Any]) -> str:
    """将阶段一的细粒度标签归一为验收要求的四类。"""
    raw = str(question.get("category", "")).lower()
    if any(k in raw for k in ("武功", "传承")):
        return "武功"
    if "门派" in raw or "帮派" in raw:
        return "门派"
    if any(k in raw for k in ("比较", "综合")):
        return "综合"
    return "人物"


def summarize_by_category(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """按方法及人物/武功/门派/综合计算分项指标。"""
    groups: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(str(row.get("method", "all")), str(row.get("category", "人物")))].append(row)
    output = []
    methods = sorted({method for method, _ in groups})
    for method in methods:
        for category in ("人物", "武功", "门派", "综合"):
            items = groups.get((method, category), [])
            if not items:
                continue
            output.append({
                "method": method,
                "category": category,
                "questions": len(items),
                "accuracy": round(sum(bool(x.get("entity_hit")) for x in items) / len(items), 4),
                "path_completeness": round(sum(float(x.get("path_completeness", 0)) for x in items) / len(items), 4),
                "evidence_sufficiency": round(sum(float(x.get("evidence_sufficiency", 0)) for x in items) / len(items), 4),
            })
    return output


def compare_injection_forms(question: Mapping[str, Any], evidence: list[dict[str, Any]], contexts: Mapping[str, str]) -> dict[str, Any]:
    """比较三种注入文本的结构覆盖度，供无 LLM 时的可重复实验使用。"""
    expected = [normalize_text(x) for x in question.get("answer_entities", [])]
    result = {}
    for form, context in contexts.items():
        normalized = normalize_text(context)
        hits = sum(bool(x) and x in normalized for x in expected)
        result[form] = {
            "answer_entity_coverage": round(hits / len(expected), 4) if expected else 0.0,
            "context_chars": len(context or ""),
            "evidence_items": len(evidence),
        }
    return result
