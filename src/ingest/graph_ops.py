"""图谱通用写入/归并操作（任务 06 / 08 / 20）。

clean_graph.py 与 entity_alignment.py 原来各有一套"属性合并 + 边迁移 + 删节点"
逻辑，关系白名单也各维护一份，导致差异。这里给出唯一实现：

- 关系白名单直接来自 core.ontology（含 MENTIONS / DESCENDANT_OF）；
- 遇到未知关系类型直接中止该次归并（不迁移、也不删除来源节点）；
- 边迁移按 (关系类型, 对端, 方向) 去重，幂等；
- 属性合并保留 aliases 数组。
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from core.ontology import ALL_RELATION_TYPES, ENTITY_LABEL_SET

ALLOWED_REL_TYPES: Set[str] = set(ALL_RELATION_TYPES)


class UnknownRelationError(RuntimeError):
    """迁移过程中发现不在白名单里的关系类型。"""


def quote_type(rel_type: str) -> str:
    """把关系类型安全放进 Cypher（反引号包裹）。"""
    return chr(96) + rel_type + chr(96)


def find_nodes(session, names: Sequence[str], label: str) -> List[Dict]:
    return session.run(
        "MATCH (n) WHERE n.name IN $names AND $label IN labels(n) "
        "RETURN elementId(n) AS eid, n.name AS name, n.era AS era",
        {"names": list(names), "label": label}).data()


def ensure_node(session, name: str, label: str, era: Optional[str] = None) -> str:
    """确保实体节点存在且带合法 label/era；返回 elementId。"""
    if label not in ENTITY_LABEL_SET:
        raise ValueError(f"非法实体类型：{label}")
    rows = find_nodes(session, [name], label)
    if rows:
        return rows[0]["eid"]
    record = session.run(
        f"CREATE (c:{label} {{name: $name}}) "
        "SET c.era = coalesce($era, '未知'), c.eras = [coalesce($era, '未知')] "
        "RETURN elementId(c) AS eid",
        {"name": name, "era": era}).single()
    return record["eid"]


def absorb_props(session, canonical_eid: str, alias_eid: str, alias_name: str) -> None:
    """把别名节点的标量属性并入正名节点。"""
    session.run(
        "MATCH (c) WHERE elementId(c) = $c "
        "MATCH (a) WHERE elementId(a) = $a "
        "SET c.era = coalesce(c.era, a.era), "
        "    c.first_seen_era = coalesce(c.first_seen_era, a.first_seen_era, a.era), "
        "    c.eras = CASE WHEN a.era IS NULL OR a.era IN coalesce(c.eras, []) "
        "             THEN coalesce(c.eras, []) ELSE coalesce(c.eras, []) + a.era END, "
        "    c.books = CASE WHEN a.book IS NULL OR a.book IN coalesce(c.books, []) "
        "             THEN coalesce(c.books, []) ELSE coalesce(c.books, []) + a.book END, "
        "    c.location = coalesce(c.location, a.location), "
        "    c.art_type = coalesce(c.art_type, a.art_type), "
        "    c.description = CASE "
        "        WHEN size(coalesce(c.description, '')) < size(coalesce(a.description, '')) "
        "        THEN a.description ELSE c.description END, "
        "    c.aliases = CASE WHEN $nm IN coalesce(c.aliases, []) "
        "        THEN coalesce(c.aliases, []) ELSE coalesce(c.aliases, []) + $nm END",
        {"c": canonical_eid, "a": alias_eid, "nm": alias_name})


def collect_edges(session, alias_eid: str) -> List[Dict]:
    rows: List[Dict] = []
    for direction, pattern in (("out", "(a)-[r]->(x)"), ("in", "(x)-[r]->(a)")):
        rows.extend(session.run(
            f"MATCH (a) WHERE elementId(a) = $a MATCH {pattern} "
            "WHERE NOT elementId(x) = $a "
            "RETURN type(r) AS t, elementId(x) AS xid, properties(r) AS props, $dir AS dir",
            {"a": alias_eid, "dir": direction}).data())
    return rows


def migrate_edges(session, alias_eid: str, canonical_eid: str,
                  group_eids: Iterable[str], *, dry_run: bool = False
                  ) -> Tuple[int, int, int]:
    """把别名节点的关系迁到正名节点。

    返回 (新建, 因已存在跳过, 组内丢弃)。
    未知关系类型抛 UnknownRelationError（调用方应放弃整次归并）。
    """
    group = set(group_eids)
    edges = collect_edges(session, alias_eid)
    unknown = sorted({e["t"] for e in edges if e["t"] not in ALLOWED_REL_TYPES})
    if unknown:
        raise UnknownRelationError(f"存在未登记的关系类型，拒绝迁移：{unknown}")

    created = skipped = dropped = 0
    seen: Set[Tuple[str, str, str]] = set()
    for edge in edges:
        rel_type, other, direction = edge["t"], edge["xid"], edge["dir"]
        if other in group:
            dropped += 1
            continue
        key = (rel_type, other, direction)
        if key in seen:
            continue
        seen.add(key)
        if dry_run:
            created += 1
            continue
        if direction == "out":
            exists_query = (
                "MATCH (c) WHERE elementId(c) = $c MATCH (x) WHERE elementId(x) = $x "
                f"MATCH (c)-[r:{quote_type(rel_type)}]->(x) RETURN count(r) AS n")
        else:
            exists_query = (
                "MATCH (c) WHERE elementId(c) = $c MATCH (x) WHERE elementId(x) = $x "
                f"MATCH (x)-[r:{quote_type(rel_type)}]->(c) RETURN count(r) AS n")
        exists = session.run(exists_query, {"c": canonical_eid, "x": other}).single()["n"]
        if exists:
            skipped += 1
            continue
        props = edge.get("props") or {}
        if direction == "out":
            session.run(
                "MATCH (c) WHERE elementId(c) = $c MATCH (x) WHERE elementId(x) = $x "
                f"CREATE (c)-[r:{quote_type(rel_type)}]->(x) SET r += $props",
                {"c": canonical_eid, "x": other, "props": props})
        else:
            session.run(
                "MATCH (c) WHERE elementId(c) = $c MATCH (x) WHERE elementId(x) = $x "
                f"CREATE (x)-[r:{quote_type(rel_type)}]->(c) SET r += $props",
                {"c": canonical_eid, "x": other, "props": props})
        created += 1
    return created, skipped, dropped


def delete_node(session, eid: str) -> None:
    session.run("MATCH (a) WHERE elementId(a) = $a DETACH DELETE a", {"a": eid})


def merge_into(session, canonical_name: str, canonical_label: str,
               alias_nodes: Sequence[Dict], *, era: Optional[str] = None,
               dry_run: bool = False) -> Dict[str, int]:
    """把一组别名节点归并到正名节点（正名不存在则新建）。

    alias_nodes: [{"eid","name"}]；返回统计。
    """
    stats = {"merged": 0, "created_edges": 0, "skipped_edges": 0,
             "dropped_edges": 0, "errors": 0}
    if not alias_nodes:
        return stats
    group_eids = {n["eid"] for n in alias_nodes}
    canonical_eid = ensure_node(session, canonical_name, canonical_label, era)
    group_eids.add(canonical_eid)
    for node in alias_nodes:
        if node["eid"] == canonical_eid:
            continue
        if dry_run:
            stats["merged"] += 1
            continue
        try:
            absorb_props(session, canonical_eid, node["eid"], node["name"])
            created, skipped, dropped = migrate_edges(
                session, node["eid"], canonical_eid, group_eids, dry_run=False)
        except UnknownRelationError:
            stats["errors"] += 1
            continue  # 不迁移也不删除，保留原节点，交由人工处理
        stats["created_edges"] += created
        stats["skipped_edges"] += skipped
        stats["dropped_edges"] += dropped
        delete_node(session, node["eid"])
        stats["merged"] += 1
    return stats


__all__ = ["ALLOWED_REL_TYPES", "UnknownRelationError", "quote_type", "find_nodes",
           "ensure_node", "absorb_props", "collect_edges", "migrate_edges",
           "delete_node", "merge_into"]
