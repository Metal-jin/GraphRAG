"""单一本体定义（Single Source of Truth）。

任务清单 08 要求：实体类型、关系允许的起终点、方向、是否对称只能维护一处，
所有模块（build_kg / clean_graph / entity_alignment / 检索 / 文档）都从这里取。

本模块是**纯函数 + 常量**，不依赖 neo4j / openai，可在任何环境导入。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, Iterable, Optional, Tuple

# ============ 实体类型 ============

ENTITY_LABELS: Tuple[str, ...] = ("人物", "门派", "武功", "地点")
ENTITY_LABEL_SET: FrozenSet[str] = frozenset(ENTITY_LABELS)

# 武功类别（写进 @type 属性，和实体类型分开，见任务 07）
ART_TYPES: Tuple[str, ...] = ("内功", "外功", "轻功", "暗器")

# ============ 时代维度 ============

VALID_ERAS: Tuple[str, ...] = ("射雕", "神雕", "倚天")
ERA_SET: FrozenSet[str] = frozenset(VALID_ERAS)

BOOK_TO_ERA: Dict[str, str] = {
    "射雕英雄传": "射雕",
    "神雕侠侣": "神雕",
    "倚天屠龙记": "倚天",
}
ERA_TO_BOOK: Dict[str, str] = {v: k for k, v in BOOK_TO_ERA.items()}


def infer_era(book: str) -> Optional[str]:
    """从书名推断 era；识别不了返回 None（调用方必须显式处理，不要瞎填）。"""
    if book in BOOK_TO_ERA:
        return BOOK_TO_ERA[book]
    for key, era in BOOK_TO_ERA.items():
        if key in book:
            return era
    return None


# ============ 关系 ============

@dataclass(frozen=True)
class RelationSpec:
    """一条关系的完整定义。

    属性：
        name:       Cypher 关系类型
        domains:    允许的起点实体类型集合；None 表示不限制（不建议使用）
        ranges:     允许的终点实体类型集合；None 表示不限制
        symmetric:  是否对称关系（写入时展开双向）
        description: 中文含义（给 prompt / 前端 / 文档用）
        evidence_required: 是否要求绑定原文证据（任务 09）
    """

    name: str
    domains: Optional[FrozenSet[str]]
    ranges: Optional[FrozenSet[str]]
    symmetric: bool = False
    description: str = ""
    evidence_required: bool = True

    def allows(self, source_type: Optional[str], target_type: Optional[str]) -> Tuple[bool, str]:
        """校验一条关系两端的实体类型是否合法。返回 (是否合法, 原因)。"""
        if self.domains is not None and source_type not in self.domains:
            return False, f"{self.name} 起点类型不合法：{source_type!r}（允许 {sorted(self.domains)}）"
        if self.ranges is not None and target_type not in self.ranges:
            return False, f"{self.name} 终点类型不合法：{target_type!r}（允许 {sorted(self.ranges)}）"
        return True, ""


_S = frozenset

RELATIONS: Dict[str, RelationSpec] = {
    # ---- 人际关系 ----
    "MASTER_OF": RelationSpec(
        "MASTER_OF", _S({"人物"}), _S({"人物"}),
        description="师徒：A 是 B 的师父（有向）"),
    "SPOUSE_OF": RelationSpec(
        "SPOUSE_OF", _S({"人物"}), _S({"人物"}), symmetric=True,
        description="夫妻（双向）"),
    "PARENT_OF": RelationSpec(
        "PARENT_OF", _S({"人物"}), _S({"人物"}),
        description="父母子女：A 是 B 的父母（有向）"),
    "SWORN_BROTHER_OF": RelationSpec(
        "SWORN_BROTHER_OF", _S({"人物"}), _S({"人物"}), symmetric=True,
        description="结拜（双向）"),
    "ENEMY_OF": RelationSpec(
        "ENEMY_OF", _S({"人物"}), _S({"人物"}), symmetric=True,
        description="仇敌（双向）"),
    # ---- 层次关系 ----
    "BELONGS_TO": RelationSpec(
        "BELONGS_TO", _S({"人物"}), _S({"门派"}),
        description="所属门派：A 属于门派 B（有向）"),
    "MASTERS": RelationSpec(
        "MASTERS", _S({"人物"}), _S({"武功"}),
        description="精通武功：A 精通武功 B（有向）"),
    "FOUNDER_OF": RelationSpec(
        "FOUNDER_OF", _S({"人物"}), _S({"门派"}),
        description="创立门派：A 创立门派 B（有向）"),
    "LOCATED_IN": RelationSpec(
        "LOCATED_IN", _S({"人物", "门派", "地点"}), _S({"地点"}),
        description="位于地点：A 位于地点 B（有向）"),
    # ---- 演化关系 ----
    "BRANCHED_FROM": RelationSpec(
        "BRANCHED_FROM", _S({"门派", "武功"}), _S({"门派", "武功"}),
        description="演化：B 由 A 衍生（门派/武功均可，有向）"),
    # ---- 血缘关系（阶段二新增）----
    "DESCENDANT_OF": RelationSpec(
        "DESCENDANT_OF", _S({"人物"}), _S({"人物"}),
        description="血缘：A 是祖先，B 是后代，写作 (祖先)-[:DESCENDANT_OF]->(后代)"),
}

RELATION_TYPES: FrozenSet[str] = frozenset(RELATIONS)
BIDIRECTIONAL_RELS: FrozenSet[str] = frozenset(
    name for name, spec in RELATIONS.items() if spec.symmetric)

# 系统内部关系（不作为知识事实参与检索/评测）
MENTIONS = "MENTIONS"
SYSTEM_RELATIONS: FrozenSet[str] = frozenset({MENTIONS})

ALL_RELATION_TYPES: FrozenSet[str] = RELATION_TYPES | SYSTEM_RELATIONS


def relation_spec(name: str) -> Optional[RelationSpec]:
    return RELATIONS.get((name or "").strip().upper())


def is_valid_relation_type(name: str) -> bool:
    return (name or "").strip().upper() in RELATIONS


def validate_relation(rel_type: str, source_type: Optional[str],
                      target_type: Optional[str]) -> Tuple[bool, str]:
    """校验关系的类型与两端实体类型。未知关系类型一律不合法。"""
    spec = relation_spec(rel_type)
    if spec is None:
        return False, f"未知关系类型：{rel_type!r}"
    return spec.allows(source_type, target_type)


def relation_prompt_block() -> str:
    """生成抽取 prompt 用的关系清单（避免 prompt 与本体漂移）。"""
    return "\n".join(
        f"- {name}（{spec.description}）" for name, spec in RELATIONS.items()
    )


def entity_prompt_block() -> str:
    return (
        "1. 人物：era（射雕/神雕/倚天）、description（原文对该人物的描述，有则填）\n"
        "2. 门派：era、location（门派所在地点）、description\n"
        "3. 武功：type 固定填「武功」，另用 art_type 标注类别"
        f"（{'/'.join(ART_TYPES)}，判断不了留空）、era\n"
        "4. 地点：era"
    )


# 噪声节点（指称 / 动物被误抽成人物）—— 全项目共用一份
NOISE_NAMES: FrozenSet[str] = frozenset({
    "师父", "大师父", "白雕", "汗血宝马", "小红马",
    "神雕", "大雕", "雕儿",
    "某", "某人", "那汉", "那女子", "之", "其", "此人", "那人",
})

# 常见指称连接词：含这些字的“名字”多半是关系指称而不是本名
PRONOUN_MARKERS: Tuple[str, ...] = ("的", "之", "与", "和", "跟")


def is_noise_name(name: str) -> bool:
    name = (name or "").strip()
    if not name or len(name) <= 1:
        return True
    if name in NOISE_NAMES:
        return True
    return False


__all__ = [
    "ENTITY_LABELS", "ENTITY_LABEL_SET", "ART_TYPES", "VALID_ERAS", "ERA_SET",
    "BOOK_TO_ERA", "ERA_TO_BOOK", "infer_era", "RelationSpec", "RELATIONS",
    "RELATION_TYPES", "BIDIRECTIONAL_RELS", "MENTIONS", "SYSTEM_RELATIONS",
    "ALL_RELATION_TYPES", "relation_spec", "is_valid_relation_type",
    "validate_relation", "relation_prompt_block", "entity_prompt_block",
    "NOISE_NAMES", "PRONOUN_MARKERS", "is_noise_name",
]
