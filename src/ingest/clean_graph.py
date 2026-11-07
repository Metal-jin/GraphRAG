"""图谱清洗（阶段一方案 B 的延续 + 任务 08 的统一实现）。

两类操作（均幂等，可重复执行；只动本地 Neo4j 库，不影响源文件）：
1. 别名归并：把 九指神丐/北丐/洪帮主 等并入 洪七公，连带迁移全部关系与
   MENTIONS 溯源边（Chunk 溯源自动跟到正名节点），再删除别名节点；
2. 噪声剔除：删除把指称/动物误抽成"人物"的节点。

与 entity_alignment.py 的关系：底层"属性合并 + 边迁移 + 删节点"统一由
ingest.graph_ops 提供，关系白名单统一来自 core.ontology，避免两套逻辑漂移。

用法（仓库根目录、PYTHONPATH=src）：
    python src/ingest/clean_graph.py            # 执行清洗
    python src/ingest/clean_graph.py --dry-run  # 只报告
    python src/ingest/clean_graph.py --audit    # 只读查看候选现状
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple

# 自举 sys.path：允许 `python src/ingest/clean_graph.py` 直接运行（不依赖 PYTHONPATH）
_SRC_DIR = Path(__file__).resolve().parents[1]
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from neo4j import GraphDatabase  # noqa: E402

from core.config import get_settings  # noqa: E402
from core.ontology import ALL_RELATION_TYPES, ENTITY_LABEL_SET  # noqa: E402
from ingest import graph_ops  # noqa: E402
from ingest.graph_ops import (ALLOWED_REL_TYPES, UnknownRelationError,  # noqa: E402
                              quote_type)

ENTITY_LABELS = ENTITY_LABEL_SET


# ---------------- 纯函数：可单测 ----------------

def validate_groups(alias_groups: Dict[str, Dict], drop_names: Iterable[str]) -> None:
    """校验别名组/剔除名单，非法直接抛 ValueError。"""
    if not alias_groups:
        raise ValueError("alias_groups 不能为空")
    seen: Set[str] = set()
    for canonical, cfg in alias_groups.items():
        aliases = cfg.get("aliases", [])
        label = cfg.get("label")
        if label not in ENTITY_LABEL_SET:
            raise ValueError(f"非法 label: {label}")
        if canonical in aliases:
            raise ValueError(f"canonical 不能同时出现在 aliases: {canonical}")
        if len(set(aliases)) != len(aliases):
            raise ValueError(f"aliases 内有重复: {canonical}")
        for name in [canonical] + list(aliases):
            if name in seen:
                raise ValueError(f"实体名被多个组引用: {name}")
            seen.add(name)
    for name in drop_names:
        if not name:
            raise ValueError("剔除名单含空字符串")
        if name in seen:
            raise ValueError(f"实体 {name} 同时出现在别名组和剔除名单")


def rel_key(rel_type: str, other_eid: str, direction: str) -> Tuple[str, str, str]:
    """迁移去重用的边键。"""
    return (rel_type, other_eid, direction)


# ---------------- 数据库访问 ----------------

def _driver():
    from ingest.data_loader import create_driver
    return create_driver()


def audit(alias_groups: Dict[str, Dict], drop_names: List[str]) -> None:
    """打印候选名单现状（只读）。"""
    with _driver().session() as session:
        for canonical, cfg in alias_groups.items():
            for name in [canonical] + list(cfg.get("aliases", [])):
                rows = session.run(
                    "MATCH (n {name: $n}) RETURN labels(n) AS labels, "
                    "count { (n)--() } AS degree ORDER BY degree DESC",
                    {"n": name}).data()
                if not rows:
                    print(f"  {name}: (不存在)")
                for row in rows:
                    print(f"  {name}: labels={row['labels']} degree={row['degree']}")
        print("  --- 剔除名单 ---")
        for name in drop_names:
            rows = session.run(
                "MATCH (n {name: $n}) RETURN labels(n) AS labels, "
                "count { (n)--() } AS degree ORDER BY degree DESC",
                {"n": name}).data()
            if not rows:
                print(f"  {name}: (不存在)")
            for row in rows:
                print(f"  {name}: labels={row['labels']} degree={row['degree']}")


def merge_alias_group(session, canonical: str, cfg: Dict, dry_run: bool) -> Dict[str, int]:
    """归并一个别名组到正名（属性 + 边 + 删除别名节点）。"""
    label = cfg["label"]
    names = [canonical] + list(cfg.get("aliases", []))
    nodes = graph_ops.find_nodes(session, names, label)
    if not nodes:
        print(f"[alias] {canonical}: 无可归并节点（跳过）")
        return {"merged": 0, "created_edges": 0, "skipped_edges": 0,
                "dropped_edges": 0, "errors": 0}
    present = {n["name"] for n in nodes}
    to_merge = present - {canonical}
    print(f"[alias] {canonical} ({label}): 组内节点 {sorted(present)}")
    if not to_merge:
        print("         已是正名，无需归并")
        return {"merged": 0, "created_edges": 0, "skipped_edges": 0,
                "dropped_edges": 0, "errors": 0}
    if dry_run:
        print(f"         [dry-run] 将归并别名: {sorted(to_merge)}")
        return {"merged": len(to_merge), "created_edges": 0, "skipped_edges": 0,
                "dropped_edges": 0, "errors": 0}

    era = nodes[0].get("era")
    alias_nodes = [n for n in nodes if n["name"] != canonical]
    stats = graph_ops.merge_into(session, canonical, label, alias_nodes, era=era,
                                 dry_run=False)
    print(f"         归并 {len(alias_nodes)} 个节点：新建边 {stats['created_edges']}，"
          f"跳过 {stats['skipped_edges']}，组内丢弃 {stats['dropped_edges']}，"
          f"失败 {stats['errors']}")
    return stats


def drop_noise(session, drop_names: List[str], dry_run: bool) -> None:
    """删除误抽为"人物"的指称/动物节点。"""
    nodes = session.run(
        "MATCH (n:人物) WHERE n.name IN $names "
        "RETURN n.name AS name, elementId(n) AS eid, count { (n)--() } AS degree",
        {"names": drop_names}).data()
    if not nodes:
        print("[drop] 无可剔除节点")
        return
    for node in nodes:
        print(f"[drop] {node['name']}（人物，度 {node['degree']}）")
        if dry_run:
            print("       [dry-run] 将剔除")
        else:
            graph_ops.delete_node(session, node["eid"])
            print("       已剔除")


def summary(session) -> None:
    """清洗后简单统计。"""
    rows = session.run(
        "MATCH (n) WHERE any(l IN labels(n) WHERE l IN $labels) "
        "RETURN head([l IN labels(n) WHERE l IN $labels]) AS t, "
        "n.era AS era, count(*) AS c ORDER BY c DESC",
        {"labels": list(ENTITY_LABELS)}).data()
    print("--- 清洗后实体统计 ---")
    for row in rows:
        print(f"  {row['t']:4s} era={row['era']} count={row['c']}")


DEFAULT_ALIAS_GROUPS: Dict[str, Dict] = {
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
DEFAULT_DROP_NAMES: List[str] = ["师父", "大师父", "白雕", "汗血宝马", "小红马"]


def main() -> int:
    from core.console import ensure_utf8_console
    ensure_utf8_console()
    parser = argparse.ArgumentParser(description="图谱轻量清洗（别名归并 + 噪声剔除）")
    parser.add_argument("--dry-run", action="store_true", help="只报告，不改库")
    parser.add_argument("--audit", action="store_true", help="打印候选名单现状后退出")
    args = parser.parse_args()

    validate_groups(DEFAULT_ALIAS_GROUPS, DEFAULT_DROP_NAMES)
    with _driver().session() as session:
        if args.audit:
            print("===== 别名组候选现状 =====")
            audit(DEFAULT_ALIAS_GROUPS, DEFAULT_DROP_NAMES)
            return 0
        for canonical, cfg in DEFAULT_ALIAS_GROUPS.items():
            merge_alias_group(session, canonical, cfg, args.dry_run)
        drop_noise(session, DEFAULT_DROP_NAMES, args.dry_run)
        summary(session)
    print("done." if not args.dry_run else "dry-run done.（未改动数据库）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
