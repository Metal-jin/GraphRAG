"""检索方法共用工具（任务 11 / 18）。

把"问题校验 / 实体链接 / 错误 Answer / 证据构造"集中一处，避免 6 个方法
各写一套 _find_seed_* 与错误处理。
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence

from core.entity_link import EntityIndex, EntityMatch, get_entity_index
from core.evidence import make_bundle, make_edge, make_node
from core.interfaces import Answer
from core.query import QueryScope, detect_scope, normalize_top_k


def ensure_question(question: str, method_name: str) -> str:
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question 必须是非空字符串")
    return question.strip()


def resolve_top_k(top_k: Optional[int]) -> int:
    return normalize_top_k(top_k)


def resolve_scope(question: str) -> QueryScope:
    return detect_scope(question)


def current_index(data_loader: Any = None, entity_index: Optional[EntityIndex] = None,
                  force: bool = False) -> EntityIndex:
    """优先用注入的索引/数据加载器，最后才用进程级缓存索引。"""
    if entity_index is not None:
        return entity_index
    if data_loader is not None and hasattr(data_loader, "get_entity_nodes"):
        try:
            return EntityIndex(entities=data_loader.get_entity_nodes())
        except Exception:
            pass
    return get_entity_index(force=force)


def link_seed(question: str, index: EntityIndex,
              labels: Sequence[str]) -> Optional[EntityMatch]:
    matches = index.link(question, labels=list(labels))
    return matches[0] if matches else None


def unavailable_answer(method_name: str, question: str, exc: Exception) -> Answer:
    return Answer(
        answer_text=f"检索失败（数据源不可用）：{type(exc).__name__}: {exc}",
        method_name=method_name,
        evidence=[],
        debug_info={"question": question, "error": str(exc),
                    "degraded": "data_unavailable", "status": "error"},
        raw_context="")


def no_entity_answer(method_name: str, question: str, entity_type: str,
                     scope: Optional[QueryScope] = None) -> Answer:
    return Answer(
        answer_text=f"未能从问题中识别出{entity_type}实体。",
        method_name=method_name,
        evidence=[],
        debug_info={"question": question, "seed": None,
                    "scope": scope.to_dict() if scope else {},
                    "status": "no_entity"},
        raw_context="")


def path_answer(method_name: str, question: str, seed: str, nodes: List[Dict],
                edges: List[Dict], text: str, *, confidence: str = "extracted",
                debug: Optional[Dict] = None) -> Answer:
    bundle = make_bundle("path", source_method=method_name, nodes=nodes,
                         edges=edges, seed=seed, complete=bool(edges), text=text,
                         confidence=confidence)
    return Answer(answer_text=text, method_name=method_name, evidence=[bundle],
                  debug_info={"question": question, "seed": seed,
                              "node_count": len(nodes), "edge_count": len(edges),
                              "status": "ok", **(debug or {})},
                  raw_context=text)


def triple_bundles(method_name: str, edges: Iterable[Dict],
                   nodes: Optional[Sequence[Dict]] = None,
                   *, confidence: str = "extracted") -> List[Dict]:
    node_list = list(nodes or [])
    return [make_bundle("triple", source_method=method_name, nodes=node_list,
                        edges=[edge], confidence=confidence) for edge in edges]


__all__ = ["ensure_question", "resolve_top_k", "resolve_scope", "current_index",
           "link_seed", "unavailable_answer", "no_entity_answer", "path_answer",
           "triple_bundles", "EntityIndex", "EntityMatch", "make_node", "make_edge"]
