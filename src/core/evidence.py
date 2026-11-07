"""统一证据结构与适配层（任务 18 / 09 / 23）。

历史问题：不同方法的 evidence 各用一套键（name/depth、from/to、person/arts、
source/rel/target），评测和前端不得不为每个方法写分支；以 name 当身份还会
混淆同名不同类型实体。

本模块定义唯一的证据契约，并提供 legacy 形状的升级适配：

    {
      "kind": "path" | "triple" | "chain" | "member" | "chunk" | "art",
      "source_method": "master_chain",
      "confidence": "extracted" | "inferred",
      "seed": "郭靖",
      "complete": true,
      "nodes": [{"id","name","type","era"}],
      "edges": [{"source","target","type","direction","chunk_ids","snippets"}],
      "chunk_ids": [...],
      "text": "给人看的渲染文本",
      "legacy": {...原始结构，保持向后兼容...}
    }

纯函数，不依赖数据库/LLM。
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence

ID_SEPARATOR = "::"


def entity_id(name: str, label: Optional[str] = None) -> str:
    """稳定实体 ID：类型::名字（比 Neo4j 内部 id 稳定，便于跨库对比）。"""
    name = (name or "").strip()
    return f"{label or '实体'}{ID_SEPARATOR}{name}" if name else ""


def make_node(name: str, label: Optional[str] = None,
              era: Optional[str] = None) -> Dict[str, Any]:
    return {"id": entity_id(name, label), "name": (name or "").strip(),
            "type": label, "era": era}


def make_edge(source: str, target: str, rel_type: str, *,
              direction: str = "forward",
              chunk_ids: Optional[Sequence[str]] = None,
              snippets: Optional[Sequence[str]] = None,
              confidence: str = "extracted") -> Dict[str, Any]:
    """direction: forward(源->目标) / backward(目标->源) / symmetric。"""
    return {
        "source": (source or "").strip(),
        "target": (target or "").strip(),
        "type": (rel_type or "").strip().upper(),
        "direction": direction,
        "chunk_ids": list(chunk_ids or []),
        "snippets": list(snippets or []),
        "confidence": confidence,
    }


def make_chunk_evidence(item: Dict[str, Any], method_name: str = "") -> Dict[str, Any]:
    return {
        "kind": "chunk",
        "source_method": method_name,
        "confidence": "extracted",
        "seed": None,
        "complete": True,
        "nodes": [],
        "edges": [],
        "chunk_ids": [item.get("chunk_id")] if item.get("chunk_id") is not None else [],
        "text": str(item.get("text") or item.get("content") or "")[:400],
        "score": item.get("score"),
        "book": item.get("book"),
        "era": item.get("era"),
        "chapter": item.get("chapter"),
        "legacy": item,
    }


def make_bundle(kind: str, *, source_method: str, nodes: Optional[Iterable[Dict]] = None,
                edges: Optional[Iterable[Dict]] = None, seed: Optional[str] = None,
                complete: bool = True, confidence: str = "extracted",
                text: str = "", legacy: Optional[Dict] = None) -> Dict[str, Any]:
    return {
        "kind": kind,
        "source_method": source_method,
        "confidence": confidence,
        "seed": seed,
        "complete": complete,
        "nodes": list(nodes or []),
        "edges": list(edges or []),
        "chunk_ids": sorted({cid for e in (edges or []) for cid in e.get("chunk_ids", [])}),
        "text": text,
        "legacy": legacy or {},
    }


# ---------------- legacy 适配 ----------------

def _looks_like_chunk(item: Dict[str, Any]) -> bool:
    return "chunk_id" in item or ("text" in item and "score" in item)


def _looks_like_chain(item: Dict[str, Any]) -> bool:
    return "name" in item and "depth" in item


def _looks_like_lineage(item: Dict[str, Any]) -> bool:
    return "from" in item and "to" in item


def _looks_like_member(item: Dict[str, Any]) -> bool:
    return "person" in item or ("arts" in item and "person" not in item)


def _looks_like_triple(item: Dict[str, Any]) -> bool:
    return "source" in item and "target" in item


def normalize_evidence(method_name: str,
                       evidence: Optional[Sequence[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """把任意方法返回的 evidence 升级成统一契约（保留 legacy 原始结构）。"""
    if not evidence:
        return []
    out: List[Dict[str, Any]] = []
    for item in evidence:
        if not isinstance(item, dict):
            out.append(make_bundle("chunk", source_method=method_name,
                                   text=str(item)[:400], legacy={"raw": str(item)}))
            continue
        if item.get("kind") and "source_method" in item:  # 已是新契约
            out.append(item)
            continue
        if _looks_like_chain(item):
            node = make_node(item.get("name", ""), "人物", item.get("era"))
            out.append(make_bundle("chain", source_method=method_name, nodes=[node],
                                   text=f"{item.get('name')}（第{item.get('depth', 0)}代）",
                                   legacy=item))
        elif _looks_like_lineage(item):
            edge = make_edge(item.get("from", ""), item.get("to", ""), "MASTER_OF",
                             confidence=item.get("confidence", "inferred"))
            out.append(make_bundle("art", source_method=method_name, edges=[edge],
                                   text=f"{item.get('from')} -> {item.get('to')}",
                                   legacy=item))
        elif _looks_like_member(item):
            person = item.get("person", "")
            nodes = [make_node(person, "人物")]
            edges = [make_edge(person, art, "MASTERS") for art in (item.get("arts") or [])]
            out.append(make_bundle("member", source_method=method_name, nodes=nodes,
                                   edges=edges, text=str(item), legacy=item))
        elif _looks_like_triple(item):
            edge = make_edge(item.get("source", ""), item.get("target", ""),
                             item.get("type") or item.get("rel") or "", 
                             direction=item.get("direction", "forward"),
                             confidence=item.get("confidence", "extracted"))
            out.append(make_bundle("triple", source_method=method_name, edges=[edge],
                                   text=str(item), legacy=item))
        elif _looks_like_chunk(item):
            out.append(make_chunk_evidence(item, method_name))
        else:
            out.append(make_bundle("chunk", source_method=method_name,
                                   text=str(item)[:400], legacy=item))
    return out


def evidence_entity_names(evidence: Sequence[Dict[str, Any]]) -> List[str]:
    """收集证据里出现过的实体名（评测/注入用）。"""
    names: List[str] = []
    for item in evidence or []:
        for node in item.get("nodes") or []:
            if node.get("name"):
                names.append(node["name"])
        for edge in item.get("edges") or []:
            for key in ("source", "target"):
                if edge.get(key):
                    names.append(edge[key])
        legacy = item.get("legacy") or {}
        for key in ("name", "person", "from", "to", "source", "target"):
            if legacy.get(key):
                names.append(str(legacy[key]))
    seen, result = set(), []
    for n in names:
        if n not in seen:
            seen.add(n)
            result.append(n)
    return result


RELATION_CN = {
    "MASTER_OF": "师徒", "SPOUSE_OF": "夫妻", "PARENT_OF": "父母",
    "SWORN_BROTHER_OF": "结拜", "ENEMY_OF": "仇敌", "BELONGS_TO": "属于",
    "MASTERS": "精通", "FOUNDER_OF": "创立", "LOCATED_IN": "位于",
    "BRANCHED_FROM": "演化", "DESCENDANT_OF": "血缘",
}


def render_evidence(evidence: Sequence[Dict[str, Any]]) -> str:
    """把证据渲染成可直接注入 LLM 的中文文本（保序、去重）。"""
    lines: List[str] = []
    for item in evidence or []:
        if item.get("kind") == "chunk":
            lines.append(str(item.get("text") or ""))
            continue
        for edge in item.get("edges") or []:
            direction = edge.get("direction", "forward")
            arrow = {"symmetric": "--", "backward": "<-"}.get(direction, "->")
            rel = RELATION_CN.get(str(edge.get("type") or "").upper(),
                                  str(edge.get("type") or ""))
            lines.append(f"{edge.get('source')} {arrow}[{rel}] {edge.get('target')}")
        if not item.get("edges"):
            for node in item.get("nodes") or []:
                lines.append(str(node.get("name")))
    seen, unique = set(), []
    for line in lines:
        if line and line not in seen:
            seen.add(line)
            unique.append(line)
    return "\n".join(unique)


__all__ = ["entity_id", "make_node", "make_edge", "make_chunk_evidence",
           "make_bundle", "normalize_evidence", "evidence_entity_names",
           "render_evidence", "RELATION_CN", "ID_SEPARATOR"]
