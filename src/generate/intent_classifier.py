"""意图分类器（任务 11 / 19 重写）。

变化：
- 实体识别统一走 core.entity_link（正名 + 别名 + 全量命中 + 置信度），
  不再自己写一套长名字符串匹配；
- 分类结果带 seed 的实体 ID / 类型 / 置信度，并传给检索器；
- 新增 cross_novel（跨书关联/血缘）与 compare（综合比较）意图；
- 索引缓存可刷新、可失效，数据库恢复后能自动恢复（不再是"一次失败永久空图"）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from core.entity_link import EntityIndex, EntityIndexCache, EntityMatch
from core.query import QueryScope, detect_scope
from core.question_plan import FOUNDING_VERBS

ART_KEYWORDS = ("传承", "谁传", "传给谁", "传给了", "传给", "谁传授",
                "创始人", "谁创", "源自", "流自", "从谁", "演化")
SECT_KEYWORDS = ("绝学", "成员", "门下", "有哪些", "掌门", "帮主", "什么武功", "会什么",
                 "创始人", "谁创", *FOUNDING_VERBS)
MASTER_KEYWORDS = ("师父", "师傅", "师祖", "太师父", "徒弟", "弟子", "师承", "师从",
                   "师门", "门徒", "恩师")
PERSON_REL_KEYWORDS = (
    "父亲", "母亲", "爸爸", "妈妈", "爹", "娘", "儿子", "女儿", "子女", "孩子",
    "父母", "父子", "父女", "母子", "母女", "爹娘",
    "配偶", "妻子", "丈夫", "老婆", "老公", "夫人", "娘子", "夫妻",
    "结拜", "义兄", "义弟", "结义", "义结金兰",
    "仇敌", "敌人", "对手", "死对头", "仇人",
    "岳父", "岳母", "外公", "外婆", "孙子", "孙女",
)
COMPARE_KEYWORDS = ("谁厉害", "谁强", "谁更", "比较", "区别", "对比", "哪个厉害",
                    "谁武功高", "谁高")
CROSS_NOVEL_KEYWORDS = ("跨书", "血缘", "后人", "之后人", "关联", "什么关系", "有何关系",
                        "几代", "时代差异")
ART_SKILL_KEYWORDS = ("精通", "掌法", "棒法", "剑法", "拳法", "刀法", "棍法", "指法",
                      "爪法", "绝技", "绝学", "成名武功", "独门武功", "所学武功")
SECT_LOCATION_KEYWORDS = ("属于哪个门派", "哪个帮派", "哪个门派", "来自哪里", "来自何处",
                          "创立的门派", "创立了什么门派", "哪里的岛主", "哪里的")


@dataclass
class Intent:
    """分类结果（字段只增不减，保持向后兼容）。"""

    intent: str
    method_name: str
    seed_entity: str = ""
    entity_type: str = ""
    injection: str = "text"
    reason: str = ""
    seed_entity_id: str = ""
    confidence: float = 0.0
    scope: QueryScope = field(default_factory=QueryScope)
    matches: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"intent": self.intent, "method_name": self.method_name,
                "seed_entity": self.seed_entity, "entity_type": self.entity_type,
                "injection": self.injection, "reason": self.reason,
                "seed_entity_id": self.seed_entity_id,
                "confidence": round(self.confidence, 3),
                "scope": self.scope.to_dict(), "matches": self.matches}


class IntentClassifier:
    """规则 + 实体链接的分类器（离线可用，无需训练模型）。"""

    def __init__(self, index_cache: Optional[EntityIndexCache] = None):
        self.cache = index_cache or EntityIndexCache()

    # ---------- 缓存 ----------

    def _index(self) -> EntityIndex:
        return self.cache.get()

    def invalidate(self) -> None:
        self.cache.invalidate()

    @property
    def degraded_reason(self) -> str:
        return self.cache.degraded_reason

    # ---------- 分类 ----------

    @staticmethod
    def _first_match(matches: Sequence[EntityMatch], label: Optional[str]) -> Optional[EntityMatch]:
        for match in matches:
            if label is None or match.label == label:
                return match
        return None

    def classify(self, question: str) -> Intent:
        text = (question or "").strip()
        scope = detect_scope(text)
        index = self._index()
        matches = index.link(text, limit=6)
        match_dicts = [m.to_dict() for m in matches]

        art = self._first_match(matches, "武功")
        sect = self._first_match(matches, "门派")
        people = [m for m in matches if m.label == "人物"]
        person = people[0] if people else None

        # 多个跨时代人物 + 关联词 → 跨书检索
        if len(people) >= 2 and any(word in text for word in CROSS_NOVEL_KEYWORDS):
            return self._build("cross_novel", "cross_novel", people[0], "人物",
                               "triples", "命中多个人物且含跨书/关联关键词", match_dicts, scope)
        if len(people) >= 2 and scope.is_filtered and any(w in text for w in ("关联", "关系")):
            return self._build("cross_novel", "cross_novel", people[0], "人物",
                               "triples", "命中多个人物且指定了时代范围", match_dicts, scope)

        # 武功 + 传承/创立 → 武功传承
        if art and any(word in text for word in ART_KEYWORDS):
            return self._build("art", "art_lineage", art, "武功", "path",
                               f"命中武功实体「{art.canonical}」且含传承关键词",
                               match_dicts, scope)

        # 门派 + 聚合关键词 → 门派聚合
        if sect and any(word in text for word in SECT_KEYWORDS):
            return self._build("sect", "sect_agg", sect, "门派", "subgraph",
                               f"命中门派实体「{sect.canonical}」且含聚合关键词",
                               match_dicts, scope)

        # 人物 + 创立问法 → 门派检索（反向查 FOUNDER_OF）
        if person and any(word in text for word in FOUNDING_VERBS):
            return self._build("sect", "sect_agg", person, "人物", "subgraph",
                               "命中人物 + 创立问法，反向查其创立的门派",
                               match_dicts, scope)

        # 人物 + 武功精通问法 → 通用检索（MASTERS 关系覆盖不全时更稳）
        if person and any(word in text for word in ART_SKILL_KEYWORDS):
            return self._build("general", "vector", person, "人物", "text",
                               "人物 + 武功精通问法，走通用检索", match_dicts, scope)

        # 人物 + 门派/地点问法 → 通用检索
        if person and any(word in text for word in SECT_LOCATION_KEYWORDS):
            return self._build("general", "vector", person, "人物", "text",
                               "人物 + 门派/地点问法，走通用检索", match_dicts, scope)

        # 人物 + 亲属/配偶/结拜/仇敌 → 人物关系
        if person and any(word in text for word in PERSON_REL_KEYWORDS):
            return self._build("person_relation", "person_relation", person, "人物",
                               "triples", "人物关系关键词（父子/配偶/结拜/仇敌）",
                               match_dicts, scope)

        # 人物 + 综合比较 → 通用检索
        if person and any(word in text for word in COMPARE_KEYWORDS):
            return self._build("general", "vector", person, "人物", "text",
                               "人物 + 综合比较类，走通用检索", match_dicts, scope)

        # 人物 + 师徒关键词 → 师徒链
        if person and any(word in text for word in MASTER_KEYWORDS):
            return self._build("person", "master_chain", person, "人物", "path",
                               "人物 + 师徒关系关键词", match_dicts, scope)

        # 只有人物、没有明确关系问法：走通用检索（不再默认当成师徒问题）
        if person:
            intent = self._build("general", "vector", person, "人物", "text",
                                 "命中人物但没有明确关系问法，走通用检索",
                                 match_dicts, scope)
            intent.confidence = min(intent.confidence, 0.4)
            return intent

        # 兜底
        return self._build("general", "vector", None, "", "text",
                           "未命中领域实体，走通用检索", match_dicts, scope)

    @staticmethod
    def _build(intent: str, method: str, match: Optional[EntityMatch],
               entity_type: str, injection: str, reason: str,
               matches: List[Dict[str, Any]], scope: QueryScope) -> Intent:
        return Intent(
            intent=intent, method_name=method,
            seed_entity=match.canonical if match else "",
            entity_type=entity_type if match else "",
            injection=injection, reason=reason,
            seed_entity_id=(f"{entity_type}::{match.canonical}" if match else ""),
            confidence=match.confidence if match else 0.2,
            scope=scope, matches=matches)


_classifier: Optional[IntentClassifier] = None


def get_classifier(refresh: bool = False) -> IntentClassifier:
    global _classifier
    if refresh or _classifier is None:
        _classifier = IntentClassifier()
    return _classifier


def classify(question: str) -> Intent:
    """便捷入口：分类一个问题。"""
    return get_classifier().classify(question)


def invalidate_cache() -> None:
    get_classifier().invalidate()


__all__ = ["Intent", "IntentClassifier", "classify", "get_classifier", "invalidate_cache"]
