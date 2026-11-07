"""清空图谱数据（可选工具，默认只读预演）。

背景：migrate_data.py 的 --drop-legacy-chunks 只删除"没有 dataset_version 的 Chunk"，
不足以完成"备份后清库重建"。本脚本给出一个**范围明确、可预演、需二次确认**的清库入口。

清理范围（默认）：
    - 所有 :Chunk 节点（含其 embedding 属性）
    - 所有 :人物 / :门派 / :武功 / :地点 实体节点
    - 上述节点相关联的所有关系（DETACH DELETE）
**保留**：
    - :IndexMeta（记录当前向量索引的模型/维度，索引本身也保留）
    - 向量索引 text_embeddings、全文索引 text_fulltext、约束

用法：
    python scripts/wipe_graph.py                       # 只读预演（默认）
    python scripts/wipe_graph.py --apply --force       # 真正删除
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

ENTITY_LABELS = ["人物", "门派", "武功", "地点"]


def _session():
    from ingest.data_loader import get_driver
    return get_driver().session()


def inventory() -> dict:
    with _session() as session:
        return {
            "total_nodes": session.run("MATCH (n) RETURN count(n) AS c").single()["c"],
            "total_relationships": session.run(
                "MATCH ()-[r]->() RETURN count(r) AS c").single()["c"],
            "chunks": session.run("MATCH (c:Chunk) RETURN count(c) AS c").single()["c"],
            "entities": session.run(
                "MATCH (n) WHERE any(l IN labels(n) WHERE l IN $labels) "
                "RETURN count(n) AS c", {"labels": ENTITY_LABELS}).single()["c"],
            "index_meta": session.run(
                "MATCH (n:IndexMeta) RETURN count(n) AS c").single()["c"],
            "other_nodes": session.run(
                "MATCH (n) WHERE NOT n:Chunk AND NOT n:IndexMeta "
                "  AND NOT any(l IN labels(n) WHERE l IN $labels) "
                "RETURN count(n) AS c", {"labels": ENTITY_LABELS}).single()["c"],
            "by_label": {row["label"]: row["count"] for row in session.run(
                "MATCH (n) UNWIND labels(n) AS label RETURN label, count(*) AS count "
                "ORDER BY count DESC").data()},
            "by_rel_type": {row["type"]: row["count"] for row in session.run(
                "MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS count "
                "ORDER BY count DESC").data()},
        }


def _list_indexes() -> list:
    with _session() as session:
        return session.run(
            "SHOW INDEXES YIELD name, type RETURN name, type").data()


def wipe(apply: bool, thorough: bool = False) -> dict:
    inv = inventory()
    indexes = _list_indexes()
    plan = {
        "will_delete_nodes": inv["chunks"] + inv["entities"],
        "will_delete_chunks": inv["chunks"],
        "will_delete_entities": inv["entities"],
        "will_delete_relationships": inv["total_relationships"],
        "will_keep_index_meta": 0 if thorough else inv["index_meta"],
        "will_drop_indexes": [i["name"] for i in indexes
                              if i["type"] in ("VECTOR", "FULLTEXT")] if thorough else [],
        "will_keep_other_nodes": inv["other_nodes"],
    }
    print(json.dumps({"inventory": inv, "indexes": indexes, "plan": plan},
                     ensure_ascii=False, indent=2))
    if not apply:
        print("[wipe] 预演模式：未删除任何数据（加 --apply --force 才会执行）")
        return plan
    with _session() as session:
        session.run(
            "MATCH (n) WHERE n:Chunk OR n:IndexMeta "
            "  OR any(l IN labels(n) WHERE l IN $labels) DETACH DELETE n",
            {"labels": ENTITY_LABELS})
        dropped = []
        if thorough:
            for item in indexes:
                if item["type"] in ("VECTOR", "FULLTEXT"):
                    session.run(f"DROP INDEX {item['name']} IF EXISTS")
                    dropped.append(item["name"])
        remaining = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        remaining_rel = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
        remaining_idx = _list_indexes()
    print(f"[wipe] 删除完成；剩余节点 {remaining}，剩余关系 {remaining_rel}")
    print(f"[wipe] 已删除索引 {dropped}；剩余索引 {[i['name'] for i in remaining_idx]}")
    return {**plan, "remaining_nodes": remaining,
            "remaining_relationships": remaining_rel,
            "dropped_indexes": dropped}


def main() -> int:
    parser = argparse.ArgumentParser(description="清空图谱（默认只读预演）")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--thorough", action="store_true",
                        help="彻底重建：同时删除向量/全文索引与 IndexMeta")
    args = parser.parse_args()
    if args.apply and not args.force:
        raise SystemExit("删除前请确认备份已完成，并加 --force")
    wipe(args.apply, thorough=args.thorough)
    return 0


if __name__ == "__main__":
    sys.exit(main())
