"""意图分类器：识别问题类型，自动路由到领域检索策略。

阶段二核心：用户不再需要手动选方法，系统根据问题自动判断意图并路由。

意图（语义）→ 路由（方法）+ 注入形式：
    - person（人物关系）  → master_chain + path（路径）
    - sect（门派聚合）    → sect_agg     + subgraph（子图摘要）
    - art（武功传承）     → art_lineage  + path（路径）
    - general（通用兜底） → vector       + text（原文）

分类方法（规则 + 实体识别，阶段二够用，无需训练模型）：
    1. 从图谱拿到全部实体名，按类型分组（人物 / 门派 / 武功）
    2. 在问题里做「长名优先」的字符串匹配，命中起始实体
    3. 结合关键词（师徒 / 传承 / 绝学等）判断最终意图
"""
from dataclasses import dataclass
from typing import Dict, Optional

from ingest.data_loader import get_graph


@dataclass
class Intent:
    """分类结果。"""
    intent: str        # 语义意图（person / sect / art / general）
    method_name: str   # 路由到的检索方法名
    seed_entity: str   # 识别出的起始实体（可能为空字符串）
    entity_type: str   # 实体类型（人物 / 门派 / 武功 / 空）
    injection: str     # 注入形式（path / subgraph / text）
    reason: str        # 分类依据，方便调试和答辩解释


# 关键词表（辅助判断意图）
ART_KEYWORDS = ("传承", "谁传", "传给谁", "创始人", "谁创", "源自", "流自", "从谁")
SECT_KEYWORDS = ("绝学", "成员", "门下", "有哪些", "掌门", "帮主", "什么武功", "会什么")
MASTER_KEYWORDS = ("师父", "师傅", "师祖", "太师父", "徒弟", "弟子", "师承", "师从", "师门", "门徒")


class IntentClassifier:
    """规则 + 实体识别的意图分类器。"""

    def __init__(self):
        self._graph_cache: Optional[Dict] = None

    def _graph(self) -> Dict:
        """惰性加载图谱（缓存，避免每次分类都连 Neo4j）。"""
        if self._graph_cache is None:
            try:
                self._graph_cache = get_graph()
            except Exception:
                # Neo4j 未启动时降级为空图，分类会落到 general
                self._graph_cache = {"nodes": [], "edges": []}
        return self._graph_cache

    def _match_entity(self, question: str, entity_type: str) -> str:
        """在问题里匹配指定类型的实体，长名优先。

        长名优先是为了避免「黄」误匹配到「黄蓉」而非「黄药师」。
        """
        nodes = self._graph().get("nodes", [])
        names = [n.get("name", "") for n in nodes if n.get("type") == entity_type]
        names = [n for n in names if n]
        for name in sorted(names, key=len, reverse=True):
            if name in question:
                return name
        return ""

    def classify(self, question: str) -> Intent:
        q = (question or "").strip()

        # 1. 武功实体 + 传承关键词 → 武功传承
        art = self._match_entity(q, "武功")
        if art and any(k in q for k in ART_KEYWORDS):
            return Intent("art", "art_lineage", art, "武功", "path",
                          f"命中武功实体「{art}」且含传承关键词")

        # 2. 门派实体 + 聚合关键词 → 门派聚合
        sect = self._match_entity(q, "门派")
        if sect and any(k in q for k in SECT_KEYWORDS):
            return Intent("sect", "sect_agg", sect, "门派", "subgraph",
                          f"命中门派实体「{sect}」且含聚合关键词")

        # 3. 人物实体 + 师徒/关系关键词 → 师徒链
        person = self._match_entity(q, "人物")
        if person and any(k in q for k in MASTER_KEYWORDS):
            return Intent("person", "master_chain", person, "人物", "path",
                          f"命中人物实体「{person}」且含师徒关系关键词")

        # 4. 人物实体（无明确关键词）→ 默认按人物关系处理
        if person:
            return Intent("person", "master_chain", person, "人物", "path",
                          f"命中人物实体「{person}」，默认按人物关系处理")

        # 5. 兜底 → 通用基线
        return Intent("general", "vector", "", "", "text", "未命中领域实体，走通用检索")


# 模块级单例，供 service 直接使用
_classifier = IntentClassifier()


def classify(question: str) -> Intent:
    """便捷入口：分类一个问题。"""
    return _classifier.classify(question)
