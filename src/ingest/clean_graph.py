"""
ingest/clean_graph.py
阶段一（《射雕英雄传》）图谱轻量清洗 —— B 任务收尾步骤（方案 B：规则 + 别名表，零 API 成本）。

两类操作（均幂等，可重复执行；只动本地 Neo4j 库，不影响任何源文件）：
1) 别名归并：把 九指神丐/北丐/洪帮主/洪恩师 等并入 洪七公，
   连带迁移全部关系与 MENTIONS 溯源边（Chunk 溯源自动跟到正名节点），再删除别名节点；
   仅处理指定 label（默认 人物），防止误伤同名的门派/地点节点。
2) 噪声剔除：删除把指称/动物误抽成"人物"的节点（师父/大师父/白雕/汗血宝马/小红马…），
   仅限 label=人物 的节点（小红马作为地点仍有引用，不受影响）。

用法（在仓库根目录、PYTHONPATH=src 下）：
    python src/ingest/clean_graph.py            # 执行清洗（真实改动）
    python src/ingest/clean_graph.py --dry-run  # 只报告计划，不改库
    python src/ingest/clean_graph.py --audit    # 打印候选名单在库中的现状（只读）

阶段二说明：新增一本书后如需清洗，只需扩充 ALIAS_GROUPS / DROP_NAMES 即可复用。
"""
import argparse
import sys
from typing import Dict, Iterable, List, Optional, Set, Tuple

from neo4j import GraphDatabase

from core.config import get_env

# 图内已出现的关系类型白名单（含 MENTIONS 溯源边），动态建边只允许这些类型
ALLOWED_REL_TYPES: Set[str] = {
    "MASTER_OF", "MASTERS", "BELONGS_TO", "LOCATED_IN", "PARENT_OF",
    "SPOUSE_OF", "SWORN_BROTHER_OF", "ENEMY_OF", "FOUNDER_OF",
    "BRANCHED_FROM", "MENTIONS",
}

# 实体标签全集（用于类型判断）
ENTITY_LABELS = {"人物", "门派", "武功", "地点"}


# ---------------- 纯函数：可单测 ----------------

def quote_type(t: str) -> str:  # 该函数输入关系类型字符串，输出安全的 Cypher 动态语句（反引号包裹）
    """把关系类型安全地放进 Cypher 动态语句（反引号包裹）。"""
    return f"`{t}`"


def validate_groups(alias_groups: Dict[str, Dict], drop_names: Iterable[str]) -> None: # 检查：正名不能出现在别名列表里，别名不能重复，一个名字不能属于两个组...
    """校验别名组/剔除名单的合法性，非法直接抛 ValueError，例如别名重复、正名在别名列表里、一个名字被多个组引用。"""
    if not alias_groups:
        raise ValueError("alias_groups 不能为空")
    seen: Set[str] = set()
    for canonical, cfg in alias_groups.items():
        aliases = cfg["aliases"]
        if cfg["label"] not in ENTITY_LABELS:
            raise ValueError(f"非法 label: {cfg['label']}")
        if canonical in aliases:
            raise ValueError(f"canonical 不能同时出现在 aliases: {canonical}")
        if len(set(aliases)) != len(aliases):
            raise ValueError(f"aliases 内有重复: {canonical}")
        for nm in [canonical] + aliases:
            if nm in seen:
                raise ValueError(f"实体名被多个组引用: {nm}")
            seen.add(nm)
    for nm in drop_names:
        if nm in seen:
            raise ValueError(f"实体 {nm} 同时出现在别名组和剔除名单")
        if not nm:
            raise ValueError("剔除名单含空字符串")


def rel_key(t: str, xid: str, direction: str) -> Tuple[str, str, str]: # 把三个信息（关系类型、对方节点ID、方向）打包成一个“三元素组合”，用来作为唯一标识，判断一条关系是否已经被处理过了
    """迁移去重用的边键。"""
    return (t, xid, direction)


# ---------------- 数据库访问 ----------------

def _driver(): 
    return GraphDatabase.driver(
        get_env("NEO4J_URL", "bolt://localhost:7687"),
        auth=(get_env("NEO4J_USER", "neo4j"), get_env("NEO4J_PASSWORD", "")),
    )


def audit(alias_groups: Dict[str, Dict], drop_names: List[str]) -> None: # 打印想要的名单现状（只读，不改库）
    """打印候选名单现状（只读，不改库）。"""
    with _driver().session() as s: # 连接到数据库，创建会话
        for canonical, cfg in alias_groups.items():
            names = [canonical] + cfg["aliases"] # 把正名和别名都放在一起，方便遍历
            for nm in names: # 遍历每个实体名
                rows = s.run(
                    "MATCH (n {name: $n}) RETURN labels(n) AS labels, "
                    "count { (n)--() } AS degree ORDER BY degree DESC",
                    {"n": nm},
                ).data()
                if not rows:
                    print(f"  {nm}: (不存在)")
                else:
                    for r in rows:
                        print(f"  {nm}: labels={r['labels']} degree={r['degree']}")
        print("  --- 剔除名单 ---") # 打印剔除名单，对应之前的剔除
        for nm in drop_names:
            rows = s.run(
                "MATCH (n {name: $n}) RETURN labels(n) AS labels, "
                "count { (n)--() } AS degree ORDER BY degree DESC",
                {"n": nm},
            ).data()
            if not rows:
                print(f"  {nm}: (不存在)")
            else:
                for r in rows:
                    print(f"  {nm}: labels={r['labels']} degree={r['degree']}")


# ---------------- 清洗主逻辑 ----------------

def _find_group_nodes(session, group_names: List[str],
                      label: str) -> List[dict]:
    """找出 group_names 里、带指定 label 的所有节点。"""
    return session.run(
        "MATCH (n) WHERE n.name IN $names AND $label IN labels(n) "
        "RETURN elementId(n) AS eid, n.name AS name",
        {"names": group_names, "label": label},
    ).data()


def _ensure_canonical(session, canonical: str, label: str,
                      existing_eids: Set[str]) -> str:
    """确保“正名”节点存在。如果已经存在，直接返回它的 ID；如果不存在，就新建一个，然后返回新节点的 ID"""
    rows = _find_group_nodes(session, [canonical], label)
    if rows:
        return rows[0]["eid"]
    res = session.run(
        f"CREATE (c:{label} {{name: $name, era: '射雕'}}) RETURN elementId(c) AS eid",
        {"name": canonical},
    ).single()
    return res["eid"]


def _absorb_props(session, canonical_eid: str, alias_eid: str,
                  alias_name: str) -> None:
    """把别名节点的标量属性并入正名节点（era/location/desc/别名记录）。"""
    session.run(
        "MATCH (c) WHERE elementId(c) = $c "
        "MATCH (a) WHERE elementId(a) = $a "
        "SET c.era = coalesce(c.era, a.era), "
        "    c.location = coalesce(c.location, a.location), "
        "    c.description = CASE "
        "        WHEN size(coalesce(c.description, '')) < size(coalesce(a.description, '')) "
        "        THEN a.description ELSE c.description END, "
        "    c.aliases = coalesce(c.aliases, []) + $nm",
        {"c": canonical_eid, "a": alias_eid, "nm": alias_name},
    )


def _migrate_edges(session, alias_eid: str, canonical_eid: str,
                   group_eids: Set[str]) -> Tuple[int, int]:
    """把别名节点的所有关系迁到正名节点。

    返回 (新建条数, 因已存在而跳过的条数)。别名↔别名组内部边直接丢弃（本来就该合并）。
    """
    created = skipped = 0
    for direction, pattern in (("out", "(a)-[r]->(x)"), ("in", "(x)-[r]->(a)")):
        rows = session.run(
            f"MATCH (a) WHERE elementId(a) = $a MATCH {pattern} "
            "WHERE NOT elementId(x) = $a "
            "RETURN type(r) AS t, elementId(x) AS xid, properties(r) AS props",
            {"a": alias_eid},
        ).data()
        for row in rows:
            t, xid = row["t"], row["xid"]
            if t not in ALLOWED_REL_TYPES:
                print(f"    [warn] 跳过未白名单的关系类型: {t}")
                continue
            if xid in group_eids:
                continue  # 组内互相引用的边：等正名合并后自然消失
            key = rel_key(t, xid, direction)
            if key in _migrate_edges._seen:
                continue
            _migrate_edges._seen.add(key)
            if direction == "out":
                exists_q = (f"MATCH (c) WHERE elementId(c) = $c "
                            f"MATCH (x) WHERE elementId(x) = $x "
                            f"MATCH (c)-[r:{quote_type(t)}]->(x) RETURN count(r) AS n")
            else:
                exists_q = (f"MATCH (c) WHERE elementId(c) = $c "
                            f"MATCH (x) WHERE elementId(x) = $x "
                            f"MATCH (x)-[r:{quote_type(t)}]->(c) RETURN count(r) AS n")
            exists = session.run(
                exists_q,
                {"c": canonical_eid, "x": xid},
            ).single()["n"]
            if exists > 0:
                skipped += 1
                continue
            props = row["props"] or {}
            if direction == "out":
                session.run(
                    f"MATCH (c) WHERE elementId(c) = $c "
                    f"MATCH (x) WHERE elementId(x) = $x "
                    f"CREATE (c)-[r:{quote_type(t)}]->(x) SET r += $props",
                    {"c": canonical_eid, "x": xid, "props": props},
                )
            else:
                session.run(
                    f"MATCH (c) WHERE elementId(c) = $c "
                    f"MATCH (x) WHERE elementId(x) = $x "
                    f"CREATE (x)-[r:{quote_type(t)}]->(c) SET r += $props",
                    {"c": canonical_eid, "x": xid, "props": props},
                )
            created += 1
    return created, skipped


_migrate_edges._seen = set()


def merge_alias_group(session, canonical: str, cfg: Dict,
                      dry_run: bool) -> None:
    """归并一个别名组到正名。"""
    label = cfg["label"]
    names = [canonical] + cfg["aliases"]
    nodes = _find_group_nodes(session, names, label)
    if not nodes:
        print(f"[alias] {canonical}: 无可归并节点（跳过）")
        return
    group_eids = {n["eid"] for n in nodes}
    present = {n["name"] for n in nodes}
    to_merge = present - {canonical}
    print(f"[alias] {canonical} ({label}): 组内节点 {sorted(present)}")
    if not to_merge:
        print("         已是正名，无需归并")
        return
    if dry_run:
        print(f"         [dry-run] 将归并别名: {sorted(to_merge)}")
        return
    canonical_eid = _ensure_canonical(session, canonical, label, group_eids)
    group_eids.add(canonical_eid)
    _migrate_edges._seen = set()
    for n in nodes:
        if n["eid"] == canonical_eid:
            continue
        _absorb_props(session, canonical_eid, n["eid"], n["name"])
        created, skipped = _migrate_edges(session, n["eid"], canonical_eid,
                                          group_eids)
        session.run(
            "MATCH (a) WHERE elementId(a) = $a DETACH DELETE a",
            {"a": n["eid"]},
        )
        print(f"         归并 {n['name']}: 新建边 {created}，跳过已存在 {skipped}")


def drop_noise(session, drop_names: List[str], dry_run: bool) -> None:
    """删除误抽为"人物"的指称/动物节点。"""
    nodes = session.run(
        "MATCH (n:人物) WHERE n.name IN $names "
        "RETURN n.name AS name, elementId(n) AS eid, "
        "count { (n)--() } AS degree",
        {"names": drop_names},
    ).data()
    if not nodes:
        print("[drop] 无可剔除节点")
        return
    for n in nodes:
        print(f"[drop] {n['name']}（人物，度 {n['degree']}）")
        if not dry_run:
            session.run(
                "MATCH (a) WHERE elementId(a) = $a DETACH DELETE a",
                {"a": n["eid"]},
            )
            print(f"       已剔除")
        else:
            print("       [dry-run] 将剔除")


def summary(session) -> None:
    """清洗后简单统计。"""
    rows = session.run(
        "MATCH (n) WHERE any(l IN labels(n) WHERE l IN ['人物', '门派', '武功', '地点']) "
        "RETURN head([l IN labels(n) WHERE l IN ['人物', '门派', '武功', '地点']]) AS t, "
        "n.era AS era, count(*) AS c ORDER BY c DESC"
    ).data()
    print("--- 清洗后实体统计 ---")
    for r in rows:
        print(f"  {r['t']:4s} era={r['era']} count={r['c']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="阶段一图谱轻量清洗")
    parser.add_argument("--dry-run", action="store_true", help="只报告，不改库")
    parser.add_argument("--audit", action="store_true", help="打印候选名单现状后退出")
    args = parser.parse_args()

    alias_groups: Dict[str, Dict] = { # 别名组候选名单，保证正确率，提升效率
        "洪七公": {"label": "人物", "aliases": ["九指神丐", "北丐", "洪帮主", "洪恩师"]},
        "黄药师": {"label": "人物", "aliases": ["东邪", "黄岛主"]},
        "欧阳锋": {"label": "人物", "aliases": ["西毒", "欧阳先生"]},
        "周伯通": {"label": "人物", "aliases": ["老顽童"]},
        "王重阳": {"label": "人物", "aliases": ["中神通", "重阳真人"]},
        "一灯大师": {"label": "人物", "aliases": ["南帝", "段智兴"]},
        "丘处机": {"label": "人物", "aliases": ["长春子"]},
        "马钰": {"label": "人物", "aliases": ["丹阳子"]},
        "黄蓉": {"label": "人物", "aliases": ["蓉儿"]},
        "郭靖": {"label": "人物", "aliases": ["靖哥哥"]},
        "江南七怪": {"label": "人物", "aliases": ["江南六怪", "江南七侠", "六怪"]},
    }
    drop_names: List[str] = ["师父", "大师父", "白雕", "汗血宝马", "小红马"]
    validate_groups(alias_groups, drop_names)

    with _driver().session() as session:
        if args.audit:
            print("===== 别名组候选现状 =====")
            audit(alias_groups, drop_names)
            return
        for canonical, cfg in alias_groups.items():
            merge_alias_group(session, canonical, cfg, args.dry_run)
        drop_noise(session, drop_names, args.dry_run)
        summary(session)
    print("done." if not args.dry_run else "dry-run done.（未改动数据库）")


if __name__ == "__main__":
    sys.exit(main())
