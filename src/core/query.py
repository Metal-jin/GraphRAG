"""问题范围与预算（任务 10 / 22 / 29）。

把“问题里提到的时代/书目”和“证据预算”集中解析，避免每个方法各写一套。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from core.ontology import BOOK_TO_ERA, ERA_TO_BOOK, ERA_SET, VALID_ERAS

DEFAULT_TOP_K = 5
MAX_TOP_K = 50

# 时代关键词：同时支持简称、书名和朝代说法（朝代映射到可能的多本）
ERA_KEYWORDS = {
    "射雕": ("射雕",),
    "射雕英雄传": ("射雕",),
    "南宋": ("射雕", "神雕"),
    "神雕": ("神雕",),
    "神雕侠侣": ("神雕",),
    "倚天": ("倚天",),
    "倚天屠龙记": ("倚天",),
    "元末": ("倚天",),
    "明初": ("倚天",),
}


@dataclass(frozen=True)
class QueryScope:
    """一次查询允许的数据范围。eras 为空表示不限制。"""

    eras: Tuple[str, ...] = ()
    books: Tuple[str, ...] = ()
    explicit: bool = False

    @property
    def is_filtered(self) -> bool:
        return bool(self.eras)

    def to_dict(self) -> dict:
        return {"eras": list(self.eras), "books": list(self.books),
                "explicit": self.explicit}


def detect_scope(question: str) -> QueryScope:
    """从问题文本识别时代/书目范围（长关键词优先）。"""
    text = question or ""
    eras: list[str] = []
    for keyword in sorted(ERA_KEYWORDS, key=len, reverse=True):
        if keyword in text:
            for era in ERA_KEYWORDS[keyword]:
                if era not in eras:
                    eras.append(era)
            break  # 命中最长的一个即可，避免“射雕英雄传”再命中“射雕”
    books = tuple(ERA_TO_BOOK[e] for e in eras if e in ERA_TO_BOOK)
    return QueryScope(eras=tuple(eras), books=books, explicit=bool(eras))


def normalize_top_k(value: Optional[int], default: int = DEFAULT_TOP_K,
                    maximum: int = MAX_TOP_K) -> int:
    """把 top_k 规整到 [1, maximum]；非法值用默认值。"""
    try:
        number = int(value) if value is not None else default
    except (TypeError, ValueError):
        number = default
    if number <= 0:
        number = default
    return max(1, min(number, maximum))


def normalize_era(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    value = str(value).strip()
    if value in ERA_SET:
        return value
    return BOOK_TO_ERA.get(value)


def valid_eras(values) -> Tuple[str, ...]:
    return tuple(v for v in (values or []) if v in ERA_SET)


__all__ = ["QueryScope", "detect_scope", "normalize_top_k", "normalize_era",
           "valid_eras", "DEFAULT_TOP_K", "MAX_TOP_K", "ERA_KEYWORDS"]
