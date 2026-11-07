"""关系证据约束与 PARENT_OF 二次校验（本轮新增）。

背景：LLM 会把"同一段文字里同时出现"当成关系，最典型的是
`郭襄 -> 郭靖`、`黄药师 -> 郭靖` 这类错误的 PARENT_OF。
上一轮重建中只有 66% 的 PARENT_OF 证据句包含亲属词。

本模块做两件事：
1. **证据约束**：每条关系必须在抽取结果里给出 evidence（原文句子），
   校验时要求该句子确实是文本块的逐字子串；
2. **PARENT_OF 二次校验**：亲属关系还必须在证据句里出现
   父/母/爹/娘/儿子/女儿/之子/之女/所生/生下 等明确表述。

不满足的关系会被拒绝（进入 rejected 清单并记录原因），而不是静默写入。
纯函数，不依赖数据库与 LLM。
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

# 亲属表述（PARENT_OF 二次校验用）
KINSHIP_PATTERN = re.compile(
    r"父亲|母亲|爸爸|妈妈|爹|娘|父母|儿子|女儿|子女|孩子|"
    r"之子|之女|之孙|所生|生下|亲生|骨肉|后母|继母|养父|养母|"
    r"诞下|生有|独子|独女|长子|次子|长女|次女")

# 需要二次校验的关系类型（目前只对亲属关系强制）
STRICT_TYPES = frozenset({"PARENT_OF"})

# 其他关系类型的弱提示词（仅在没给 evidence 时用于兜底判断）
TYPE_HINTS: Dict[str, re.Pattern] = {
    "MASTER_OF": re.compile(r"师|徒弟|弟子|传授|学艺|拜|教|授"),
    "SPOUSE_OF": re.compile(r"夫妻|妻|夫|婚|嫁|娶|配偶|夫人"),
    "SWORN_BROTHER_OF": re.compile(r"结拜|义兄|义弟|金兰|兄弟"),
    "ENEMY_OF": re.compile(r"仇|敌|对头|恨"),
    "BELONGS_TO": re.compile(r"门|帮|派|教|会|属|弟"),
    "MASTERS": re.compile(r"掌|法|剑|刀|拳|功|招|武|棍|棒|指"),
    "FOUNDER_OF": re.compile(r"创|立|开派|祖师"),
    "LOCATED_IN": re.compile(r"在|于|位于|处|山|岛|城"),
    "BRANCHED_FROM": re.compile(r"演化|源自|演变|由.{0,6}而来"),
    "DESCENDANT_OF": re.compile(r"之后|后人|之女|之子|血脉|后裔"),
}

_WS = re.compile(r"\s+")


def _norm(text: str) -> str:
    return _WS.sub("", text or "")


def split_sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[。！？!?；;\n])", text or "")
    return [part.strip() for part in parts if part.strip()]


def find_shared_sentences(text: str, source: str, target: str) -> List[str]:
    """返回同时包含两个实体的句子。"""
    if not source or not target:
        return []
    return [s for s in split_sentences(text) if source in s and target in s]


def validate_relationship(rel: Dict, chunk_text: str) -> Tuple[bool, str, str]:
    """校验一条关系是否有原文证据。

    返回 (是否通过, 拒绝原因, 采用的证据句)。
    """
    rel_type = str(rel.get("type", "")).upper()
    source = str(rel.get("source", "")).strip()
    target = str(rel.get("target", "")).strip()
    evidence = str(rel.get("evidence", "") or "").strip()

    # 1) 模型给了证据句：必须是原文子串
    if evidence:
        if _norm(evidence) not in _norm(chunk_text):
            return False, "给定的证据句不是原文子串（疑似改写或编造）", ""
        if rel_type in STRICT_TYPES and not KINSHIP_PATTERN.search(evidence):
            return False, "亲属关系缺少父/母/子/女等明确表述", ""
        return True, "", evidence

    # 2) 没给证据句：退化为"同一句共现"判断
    shared = find_shared_sentences(chunk_text, source, target)
    if not shared:
        return False, "同一文本块中没有同时提到两个实体的句子", ""
    if rel_type in STRICT_TYPES:
        for sentence in shared:
            if KINSHIP_PATTERN.search(sentence):
                return True, "", sentence
        return False, "共现句子中没有亲属表述（疑似由共现推断）", ""
    hint = TYPE_HINTS.get(rel_type)
    if hint is not None:
        for sentence in shared:
            if hint.search(sentence):
                return True, "", sentence
        return True, "", shared[0]
    return True, "", shared[0]


def gate_relationships(relationships: List[Dict], chunk_text: str
                       ) -> Tuple[List[Dict], List[Dict]]:
    """批量校验；通过的补上 evidence 字段，不通过的进入 rejected。"""
    kept: List[Dict] = []
    rejected: List[Dict] = []
    for rel in relationships:
        ok, reason, evidence = validate_relationship(rel, chunk_text)
        if ok:
            kept.append({**rel, "evidence": evidence})
        else:
            rejected.append({"raw": rel, "reason": reason})
    return kept, rejected


__all__ = ["KINSHIP_PATTERN", "STRICT_TYPES", "TYPE_HINTS", "split_sentences",
           "find_shared_sentences", "validate_relationship", "gate_relationships"]
