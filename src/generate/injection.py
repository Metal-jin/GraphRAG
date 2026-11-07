"""知识注入层（任务 18 重写）。

统一证据契约（core.evidence）之后，注入只需按 kind 渲染，不再为每个方法
写一套字段解析；同时按字符预算裁剪，保留方向与来源。

四种展示形式：
    1. 关系路径（path）   ：师徒 / 传承 / 跨书关联
    2. 子图摘要（subgraph）：门派聚合
    3. 三元组（triples）  ：单跳人物关系
    4. 原文（text）       ：向量基线 / 通用兜底
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from core.config import get_settings
from core.evidence import normalize_evidence
from core.ontology import RELATIONS

RELATION_CN = {
    "MASTER_OF": "师徒", "SPOUSE_OF": "夫妻", "PARENT_OF": "父母",
    "SWORN_BROTHER_OF": "结拜", "ENEMY_OF": "仇敌", "BELONGS_TO": "属于",
    "MASTERS": "精通", "FOUNDER_OF": "创立", "LOCATED_IN": "位于",
    "BRANCHED_FROM": "演化", "DESCENDANT_OF": "血缘（祖先→后代）",
}

_DIRECTION_ARROW = {"forward": "->", "backward": "<-", "symmetric": "--"}


def _rel_cn(rel_type: str) -> str:
    return RELATION_CN.get(rel_type, rel_type)


def _render_edge(edge: Dict) -> str:
    arrow = _DIRECTION_ARROW.get(edge.get("direction", "forward"), "->")
    confidence = "（推断）" if edge.get("confidence") == "inferred" else ""
    line = (f"{edge.get('source')} {arrow}[{_rel_cn(edge.get('type', ''))}] "
            f"{edge.get('target')}{confidence}")
    snippets = [s for s in (edge.get("snippets") or []) if s]
    if snippets:
        line += f"｜原文：{snippets[0][:60]}"
    return line


def _render_paths(evidence: Sequence[Dict]) -> List[str]:
    lines: List[str] = []
    for item in evidence:
        if item.get("kind") == "chunk":
            lines.append(str(item.get("text") or ""))
            continue
        if not item.get("edges"):
            continue
        for edge in item["edges"]:
            lines.append(_render_edge(edge))
    return lines


def _render_subgraph(evidence: Sequence[Dict]) -> List[str]:
    """门派子图：<门派> 下的人物 + 人物精通的武功。"""
    lines: List[str] = []
    for item in evidence:
        sect = item.get("seed") or ""
        members: Dict[str, List[str]] = {}
        for edge in item.get("edges") or []:
            if edge.get("type") == "BELONGS_TO":
                members.setdefault(edge.get("source", ""), [])
            elif edge.get("type") == "MASTERS":
                members.setdefault(edge.get("source", ""), []).append(edge.get("target", ""))
            elif edge.get("type") == "FOUNDER_OF":
                lines.append(f"{edge.get('source')} 创立 {edge.get('target')}")
        for person, arts in members.items():
            if not person:
                continue
            if arts:
                lines.append(f"{person}（会：{'、'.join(arts)}）")
            else:
                lines.append(person)
        if lines and sect:
            lines.insert(0, f"门派：{sect}")
    return lines


def _render_triples(evidence: Sequence[Dict]) -> List[str]:
    lines: List[str] = []
    for item in evidence:
        if item.get("kind") == "chunk":
            lines.append(str(item.get("text") or ""))
            continue
        for edge in item.get("edges") or []:
            lines.append(f"（{edge.get('source')}，{_rel_cn(edge.get('type',''))}，"
                         f"{edge.get('target')}）")
        if not item.get("edges"):
            for node in item.get("nodes") or []:
                if node.get("name"):
                    lines.append(str(node["name"]))
    return lines


def _render_person_paths(evidence: Sequence[Dict]) -> List[str]:
    """同一条人物关系路径作为一个上下文单元，边保持图谱中的方向。"""
    return [
        "；".join(_render_edge({**edge, "direction": "forward"})
                  for edge in item["edges"])
        for item in evidence
        if item.get("kind") == "path" and item.get("complete") and item.get("edges")
    ]


def _render_text(evidence: Sequence[Dict], raw_context: str) -> List[str]:
    if raw_context and raw_context.strip():
        return [raw_context.strip()]
    return [str(item.get("text") or "") for item in evidence if item.get("text")]


def _truncate(lines: Sequence[str], budget: int) -> str:
    """按字符预算裁剪（先保留前面的高相关证据）。"""
    out: List[str] = []
    used = 0
    seen = set()
    for line in lines:
        line = (line or "").strip()
        if not line or line in seen:
            continue
        seen.add(line)
        if used + len(line) > budget and out:
            break
        out.append(line)
        used += len(line) + 1
    return "\n".join(out)


def build_context(method_name: str, evidence: Optional[Sequence[Dict]],
                  raw_context: str = "", *,
                  budget: Optional[int] = None) -> str:
    """按方法选择注入形式，返回给 LLM 的"检索到的资料"。"""
    bundles = normalize_evidence(method_name or "", list(evidence or []))
    limit = budget or get_settings().max_context_chars

    if bundles and all(isinstance(b, dict) and b.get("kind") for b in bundles):
        pass  # 已是统一契约

    if method_name in ("vector", "library_graphrag", "general"):
        lines = _render_text(bundles, raw_context)
    elif method_name == "sect_agg":
        lines = _render_subgraph(bundles) or _render_text(bundles, raw_context)
    elif method_name == "person_relation":
        lines = _render_person_paths(bundles) or _render_triples(bundles)
    elif method_name == "cross_novel":
        lines = _render_paths(bundles) or _render_triples(bundles)
    elif method_name in ("master_chain", "art_lineage"):
        lines = _render_paths(bundles) or _render_triples(bundles)
    else:
        lines = _render_text(bundles, raw_context)

    if not lines and raw_context:
        lines = [raw_context]
    return _truncate(lines, limit)


def injection_name(method_name: str) -> str:
    """方法 -> 注入形式名（写进 debug/评测，便于统计）。"""
    return {"master_chain": "path", "art_lineage": "path", "sect_agg": "subgraph",
            "person_relation": "triples", "cross_novel": "path",
            "vector": "text", "library_graphrag": "text"}.get(method_name, "text")


__all__ = ["build_context", "injection_name", "RELATION_CN"]
