"""统一实体链接（任务 11 / 19 / 29）。

历史问题：
- 意图分类器和 5 个检索方法各写一套 _find_seed_*，长名字符串匹配互相矛盾；
- 分类器识别的 seed 根本没有传给检索器；
- 只取“第一个”命中，多人物/混合关系问题选错起点；
- 分类器首次连库失败就永久缓存空图，数据库恢复后仍全部走 vector。

本模块提供：
- EntityIndex：一次构建“名字 -> 类型/时代/正名”索引（只缓存实体名，不缓存整张边图）；
- link_entities()：返回**全部**命中（含位置、置信度、是否别名），按位置排序且不重叠；
- EntityIndexCache：带 TTL、图谱版本、失败负缓存与显式失效。
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from core.ontology import ENTITY_LABEL_SET, PRONOUN_MARKERS, is_noise_name

DEFAULT_ALIAS_PATH = Path(__file__).resolve().parents[2] / "data" / "processed" / "alias_dict.json"


@dataclass(frozen=True)
class EntityMatch:
    """一次实体命中。"""

    name: str            # 命中文本（可能是别名）
    canonical: str       # 正名
    label: Optional[str]
    era: Optional[str]
    start: int
    end: int
    source: str = "graph"   # graph / alias
    confidence: float = 1.0

    @property
    def is_alias(self) -> bool:
        return self.name != self.canonical

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "canonical": self.canonical,
                "label": self.label, "era": self.era,
                "start": self.start, "end": self.end,
                "source": self.source, "confidence": round(self.confidence, 3)}


class EntityIndex:
    """实体名索引：支持正名、别名与多命中链接。"""

    def __init__(self, entities: Iterable[Dict[str, Any]] = (),
                 aliases: Iterable[Dict[str, Any]] = ()):
        # (匹配串, 正名, label, era, source)
        self._entries: List[Tuple[str, str, Optional[str], Optional[str], str]] = []
        self._by_name: Dict[str, List[Tuple[str, Optional[str], Optional[str]]]] = {}
        self._add_entities(entities)
        self._add_aliases(aliases)
        self._entries.sort(key=lambda item: (-len(item[0]), item[0]))

    # ---------- 构建 ----------

    @staticmethod
    def _is_relation_designation(name: str) -> bool:
        """判断是不是"X的父亲"这类关系指称（被误抽成实体的噪声）。

        金庸人物本名几乎不含"的"；"之/与/和/跟"只对长名字生效，避免误伤。
        """
        if "的" in name:
            return True
        if len(name) > 5 and any(marker in name for marker in PRONOUN_MARKERS):
            return True
        return False

    def _add_entities(self, entities: Iterable[Dict[str, Any]]) -> None:
        for node in entities:
            name = str(node.get("name") or "").strip()
            if not name or is_noise_name(name):
                continue
            if self._is_relation_designation(name):
                continue
            label = node.get("label") or node.get("type")
            if label is not None and label not in ENTITY_LABEL_SET:
                continue
            era = node.get("era")
            self._entries.append((name, name, label, era, "graph"))
            self._by_name.setdefault(name, []).append((name, label, era))

    def _add_aliases(self, aliases: Iterable[Dict[str, Any]]) -> None:
        for entry in aliases:
            alias = str(entry.get("alias") or "").strip()
            canonical = str(entry.get("canonical") or "").strip()
            if not alias or not canonical or alias == canonical or is_noise_name(alias):
                continue
            label = entry.get("label")
            eras = entry.get("applicable_eras") or []
            era = eras[0] if len(eras) == 1 else None
            self._entries.append((alias, canonical, label, era, "alias"))

    @classmethod
    def from_nodes(cls, nodes: Sequence[Dict[str, Any]],
                   alias_path: Optional[Path] = None) -> "EntityIndex":
        return cls(entities=nodes, aliases=load_alias_entries(alias_path))

    @classmethod
    def from_graph(cls, graph: Dict[str, Any],
                   alias_path: Optional[Path] = None) -> "EntityIndex":
        return cls(entities=graph.get("nodes") or [], aliases=load_alias_entries(alias_path))

    # ---------- 查询 ----------

    def entities(self, label: Optional[str] = None,
                 era: Optional[str] = None) -> List[Dict[str, Any]]:
        out = []
        for name, entries in self._by_name.items():
            for canonical, lbl, ent_era in entries:
                if label and lbl != label:
                    continue
                if era and ent_era and ent_era != era:
                    continue
                out.append({"name": canonical, "label": lbl, "era": ent_era})
        return out

    def names(self, label: Optional[str] = None) -> List[str]:
        return sorted({e["name"] for e in self.entities(label)}, key=len, reverse=True)

    def find_canonical(self, name: str) -> Optional[str]:
        for entry_name, canonical, _, _, _ in self._entries:
            if entry_name == name:
                return canonical
        return None

    def alias_mapping(self, label: str) -> Dict[str, str]:
        """仅归一词典中指向唯一、确实存在的同类型实体的别名。"""
        candidates: Dict[str, set[str]] = {}
        for name, canonical, entry_label, _, source in self._entries:
            if source == "alias" and entry_label in (None, label):
                candidates.setdefault(name, set()).add(canonical)
        known = {name for name, entries in self._by_name.items()
                 if any(entry[1] == label for entry in entries)}
        return {name: next(iter(targets)) for name, targets in candidates.items()
                if len(targets) == 1 and targets <= known}

    def link(self, text: str, *, labels: Optional[Sequence[str]] = None,
             limit: int = 8) -> List[EntityMatch]:
        """返回文本中全部实体命中，长名优先、互不重叠、按出现位置排序。"""
        text = text or ""
        if not text:
            return []
        allowed = set(labels) if labels else None
        candidates: List[EntityMatch] = []
        for match_name, canonical, label, era, source in self._entries:
            if allowed and label is not None and label not in allowed:
                continue
            start = text.find(match_name)
            while start != -1:
                candidates.append(EntityMatch(
                    name=match_name, canonical=canonical, label=label, era=era,
                    start=start, end=start + len(match_name), source=source,
                    confidence=1.0 if source == "graph" else 0.9))
                start = text.find(match_name, start + 1)
        if not candidates:
            return []
        # 非指称名优先，其次长名优先，避免“黄”抢走“黄药师”、
        # 也避免“张无忌的父亲”抢走“张无忌”
        candidates.sort(key=lambda m: (EntityIndex._is_relation_designation(m.name),
                                       -(m.end - m.start), m.start))
        taken: List[EntityMatch] = []
        for cand in candidates:
            if any(not (cand.end <= other.start or cand.start >= other.end) for other in taken):
                continue
            taken.append(cand)
            if len(taken) >= limit:
                break
        taken.sort(key=lambda m: m.start)
        # 同名多时代：无法消歧时降低置信度
        result = []
        for m in taken:
            eras = {e[2] for e in self._by_name.get(m.canonical, []) if e[2]}
            confidence = m.confidence * (0.85 if len(eras) > 1 else 1.0)
            result.append(EntityMatch(m.name, m.canonical, m.label, m.era,
                                      m.start, m.end, m.source, confidence))
        return result

    def seed(self, text: str, labels: Optional[Sequence[str]] = None) -> Optional[str]:
        """取第一个（最靠前、最长）命中的正名。"""
        matches = self.link(text, labels=labels, limit=1)
        return matches[0].canonical if matches else None


def load_alias_entries(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    path = Path(path) if path else DEFAULT_ALIAS_PATH
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


@dataclass
class _CacheState:
    index: Optional[EntityIndex] = None
    loaded_at: float = 0.0
    version: str = ""
    degraded_reason: str = ""
    failures: int = 0
    negative_until: float = 0.0


class EntityIndexCache:
    """实体索引缓存：TTL + 版本 + 失败负缓存 + 主动失效（任务 19）。"""

    def __init__(self, loader: Optional[Callable[[], Sequence[Dict[str, Any]]]] = None,
                 *, ttl: float = 300.0, negative_ttl: float = 15.0,
                 alias_path: Optional[Path] = None):
        self.loader = loader or self._default_loader
        self.ttl = max(1.0, float(ttl))
        self.negative_ttl = max(0.0, float(negative_ttl))
        self.alias_path = alias_path
        self._state = _CacheState()

    # ---------- 默认数据源 ----------

    @staticmethod
    def _default_loader() -> Sequence[Dict[str, Any]]:
        from ingest.data_loader import get_entity_nodes
        return get_entity_nodes()

    # ---------- 公共 API ----------

    @property
    def degraded_reason(self) -> str:
        return self._state.degraded_reason

    def invalidate(self) -> None:
        self._state = _CacheState()

    def get(self, *, force: bool = False) -> EntityIndex:
        now = time.time()
        state = self._state
        if not force and state.index is not None and now - state.loaded_at < self.ttl:
            return state.index
        if not force and state.index is None and now < state.negative_until:
            return EntityIndex(aliases=load_alias_entries(self.alias_path))
        try:
            nodes = list(self.loader() or [])
        except Exception as exc:  # 数据库临时不可用
            state.failures += 1
            state.degraded_reason = f"{type(exc).__name__}: {exc}"
            state.negative_until = now + self.negative_ttl
            if state.index is not None:      # 有旧索引就先用旧的
                return state.index
            return EntityIndex(aliases=load_alias_entries(self.alias_path))
        version = f"{len(nodes)}:{hash(tuple(sorted((str(n.get('name')), str(n.get('era'))) for n in nodes))) & 0xFFFFFFFF}"
        state.index = EntityIndex(entities=nodes,
                                  aliases=load_alias_entries(self.alias_path))
        state.loaded_at = now
        state.version = version
        state.degraded_reason = ""
        state.failures = 0
        state.negative_until = 0.0
        return state.index


_DEFAULT_CACHE: Optional[EntityIndexCache] = None


def get_entity_index(force: bool = False) -> EntityIndex:
    global _DEFAULT_CACHE
    if _DEFAULT_CACHE is None:
        _DEFAULT_CACHE = EntityIndexCache()
    return _DEFAULT_CACHE.get(force=force)


def link_entities(text: str, *, labels: Optional[Sequence[str]] = None,
                  index: Optional[EntityIndex] = None,
                  force: bool = False) -> List[EntityMatch]:
    """便捷入口：链接问题中的所有实体。"""
    idx = index or get_entity_index(force=force)
    return idx.link(text, labels=labels)


def primary_entity(text: str, labels: Optional[Sequence[str]] = None,
                   index: Optional[EntityIndex] = None) -> Optional[EntityMatch]:
    matches = link_entities(text, labels=labels, index=index)
    return matches[0] if matches else None


__all__ = ["EntityMatch", "EntityIndex", "EntityIndexCache", "get_entity_index",
           "link_entities", "primary_entity", "load_alias_entries"]
