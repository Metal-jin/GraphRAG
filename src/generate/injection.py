"""知识注入层：把检索到的证据按问题类型转成最适合 LLM 的注入形式。

三种注入形式：
    1. 关系路径（path）    ：多跳追溯类，如「郭靖 --师父--> 马钰 --师父--> 王重阳」
    2. 子图摘要（subgraph） ：聚合类，如「丐帮门下：郭靖（会降龙十八掌）…」
    3. 原文（text）        ：通用兜底，直接给检索到的文本块

设计目标（对应整改方案「子问题 3」）：不是比较哪种注入更好，
而是根据问题类型动态选择最合适的证据呈现形式，提升 LLM 的推理效果。
"""
from typing import Dict, List


def _chain_to_path(evidence: List[Dict], relation: str) -> str:
    """师徒链（带 depth 的扁平列表）→ 分代关系文本。

    master_chain 的 evidence 形如：
        [{"name": "郭靖", "depth": 0}, {"name": "洪七公", "depth": 1}, ...]
    同一 depth 是「同一代师父」，彼此是兄弟而不是父子关系，
    因此按代分组展示，避免把兄弟节点误串成「X 的师父是 Y」的错误链。
    """
    by_depth: Dict[int, List[str]] = {}
    for e in evidence:
        name = str(e.get("name", "") or "").strip()
        if not name:
            continue
        depth = e.get("depth", 0)
        by_depth.setdefault(depth, []).append(name)

    lines = []
    for depth in sorted(by_depth.keys()):
        names = by_depth[depth]
        if depth == 0:
            lines.append(f"{names[0]}（第0代）")
        else:
            lines.append(f"第{depth}代{relation}：{'、'.join(names)}")
    return "\n".join(lines)


def _lineage_to_path(evidence: List[Dict], relation: str) -> str:
    """传承对列表 → 关系路径文本。

    evidence: [{"from": "洪七公", "to": "郭靖"}, ...]
    输出: 洪七公 --传承--> 郭靖
    """
    steps = [f"{e.get('from', '')} --{relation}--> {e.get('to', '')}" for e in evidence]
    return "，".join(steps)


def _members_to_subgraph(evidence: List[Dict]) -> str:
    """门派成员列表 → 子图摘要文本。

    evidence: [{"person": "郭靖", "arts": ["降龙十八掌"]}, ...]
    输出: 郭靖（会：降龙十八掌）
         黄蓉（会：打狗棒法）
    """
    lines = []
    for m in evidence:
        person = m.get("person", "")
        arts = m.get("arts") or []
        if not person:
            continue
        if arts:
            lines.append(f"{person}（会：{'、'.join(str(a) for a in arts)}）")
        else:
            lines.append(person)
    return "\n".join(lines)


def _triples_injection(evidence: List[Dict]) -> str:
    """三元组列表 → 文本。

    evidence: [{"source": "黄药师", "rel": "父母子女", "target": "黄蓉"}, ...]
    输出: （黄药师，父母子女，黄蓉）
    """
    lines = [f"（{e.get('source', '')}，{e.get('rel', '关系')}，{e.get('target', '')}）" for e in evidence]
    return "\n".join(lines)


def build_context(method_name: str, evidence: List[Dict], raw_context: str = "") -> str:
    """根据路由到的方法，把证据转成对应的注入形式。

    返回的字符串将作为 LLM 的「检索到的资料」。
    """
    if method_name == "master_chain":
        return _chain_to_path(evidence, "师父")
    if method_name == "art_lineage":
        return _lineage_to_path(evidence, "传承")
    if method_name == "sect_agg":
        return _members_to_subgraph(evidence)
    if method_name == "person_relation":
        return _triples_injection(evidence)
    # general / vector / library_graphrag：直接用原始检索文本
    return raw_context or ""
