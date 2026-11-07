"""数据迁移脚本（任务 02：切块/图谱/向量索引/checkpoint 版本一致）。

原则：
- **默认只做只读报告**，任何写操作都要显式指定子命令；
- 迁移都是**增量**的（补属性、写元数据），不清空任何数据；
- 破坏性操作（删除旧版本 Chunk）必须再加 --force，并在报告中列出影响行数。

子命令：
    python scripts/migrate_data.py --report                  # 只读：版本/索引/孤儿检查
    python scripts/migrate_data.py --backfill-eras --apply   # 补 eras/books/first_seen_era
    python scripts/migrate_data.py --backfill-art-type --apply
    python scripts/migrate_data.py --index-meta --apply      # 写入 IndexMeta（模型/维度）
    python scripts/migrate_data.py --drop-legacy-chunks --apply --force
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from core.config import get_settings  # noqa: E402
from core.embedding import get_embedder  # noqa: E402
from core.ontology import ENTITY_LABELS  # noqa: E402


def _session():
    from ingest.data_loader import get_driver
    return get_driver().session()


def report() -> Dict[str, Any]:
    """只读报告：实体/关系/Chunk 的版本与元数据现状。"""
    out: Dict[str, Any] = {}
    with _session() as session:
        out["entity_by_label_era"] = session.run(
            "MATCH (n) WHERE any(l IN labels(n) WHERE l IN $labels) "
            "RETURN head([l IN labels(n) WHERE l IN $labels]) AS label, "
            "       coalesce(n.era, '<null>') AS era, count(*) AS count "
            "ORDER BY label, count DESC", {"labels": list(ENTITY_LABELS)}).data()
        out["entities_without_eras"] = session.run(
            "MATCH (n) WHERE any(l IN labels(n) WHERE l IN $labels) "
            "  AND n.eras IS NULL RETURN count(n) AS count",
            {"labels": list(ENTITY_LABELS)}).single()["count"]
        out["entities_without_description"] = session.run(
            "MATCH (n) WHERE any(l IN labels(n) WHERE l IN $labels) "
            "  AND n.description IS NULL RETURN count(n) AS count",
            {"labels": list(ENTITY_LABELS)}).single()["count"]
        out["art_nodes_without_art_type"] = session.run(
            "MATCH (n:武功) WHERE n.art_type IS NULL RETURN count(n) AS count").single()["count"]
        out["chunks"] = session.run(
            "MATCH (c:Chunk) RETURN coalesce(c.dataset_version, '<legacy>') AS version, "
            "       count(*) AS count, min(size(c.embedding)) AS min_dim, "
            "       max(size(c.embedding)) AS max_dim "
            "ORDER BY count DESC").data()
        out["relationships_by_evidence"] = session.run(
            "MATCH ()-[r]->() WHERE type(r) <> 'MENTIONS' "
            "RETURN type(r) AS type, "
            "       count(r) AS total, "
            "       sum(CASE WHEN r.chunk_ids IS NULL OR size(r.chunk_ids) = 0 THEN 1 ELSE 0 END) AS without_evidence "
            "ORDER BY total DESC").data()
        out["self_loops"] = session.run(
            "MATCH (a)-[r]->(a) WHERE type(r) <> 'MENTIONS' "
            "RETURN type(r) AS type, count(*) AS count ORDER BY count DESC").data()
        out["constraints"] = session.run(
            "SHOW CONSTRAINTS YIELD name, type, labelsOrTypes, properties RETURN *").data()
        try:
            from ingest.data_loader import read_index_meta
            out["index_meta"] = read_index_meta()
        except Exception as exc:  # noqa: BLE001
            out["index_meta"] = {"error": str(exc)}
    return out


def backfill_eras(apply: bool) -> Dict[str, int]:
    """补齐 eras / books / first_seen_era（增量、幂等）。"""
    stats = {"entities": 0, "relationships": 0}
    with _session() as session:
        count = session.run(
            "MATCH (n) WHERE any(l IN labels(n) WHERE l IN $labels) AND n.eras IS NULL "
            "RETURN count(n) AS c", {"labels": list(ENTITY_LABELS)}).single()["c"]
        stats["entities"] = count
        if apply and count:
            session.run(
                "MATCH (n) WHERE any(l IN labels(n) WHERE l IN $labels) AND n.eras IS NULL "
                "SET n.eras = [n.era], "
                "    n.books = [CASE n.era "
                "                 WHEN '射雕' THEN '射雕英雄传' "
                "                 WHEN '神雕' THEN '神雕侠侣' "
                "                 WHEN '倚天' THEN '倚天屠龙记' "
                "                 ELSE n.era END], "
                "    n.first_seen_era = coalesce(n.first_seen_era, n.era)",
                {"labels": list(ENTITY_LABELS)})
        rel_count = session.run(
            "MATCH ()-[r]->() WHERE type(r) <> 'MENTIONS' AND r.eras IS NULL "
            "RETURN count(r) AS c").single()["c"]
        stats["relationships"] = rel_count
        if apply and rel_count:
            session.run(
                "MATCH (a)-[r]->(b) WHERE type(r) <> 'MENTIONS' AND r.eras IS NULL "
                "SET r.eras = CASE WHEN a.era IS NULL THEN [] ELSE [a.era] END, "
                "    r.books = CASE WHEN a.era IS NULL THEN [] ELSE [a.era] END")
    return stats


def backfill_art_type(apply: bool) -> Dict[str, int]:
    """武功节点：把旧的 type 属性迁移到 art_type（类型字段分开，任务 07）。"""
    with _session() as session:
        count = session.run(
            "MATCH (n:武功) WHERE n.art_type IS NULL AND n.type IS NOT NULL "
            "RETURN count(n) AS c").single()["c"]
        if apply and count:
            session.run(
                "MATCH (n:武功) WHERE n.art_type IS NULL AND n.type IS NOT NULL "
                "SET n.art_type = n.type")
    return {"art_type_backfilled": count}


def write_index_meta(apply: bool) -> Dict[str, Any]:
    """根据当前数据与嵌入配置写入 IndexMeta（不重建索引）。"""
    embedder = get_embedder()
    probe = embedder.embed_documents(["维度探测"])[0]
    spec = embedder.spec
    with _session() as session:
        existing = session.run(
            "MATCH (c:Chunk) WHERE c.embedding IS NOT NULL "
            "RETURN size(c.embedding) AS dim, count(*) AS c LIMIT 1").single()
    info = {"spec": spec.to_meta(), "probe_dim": len(probe),
            "stored_dim": existing["dim"] if existing else None,
            "stored_chunks": existing["c"] if existing else 0}
    if info["stored_dim"] and info["stored_dim"] != len(probe):
        info["compatible"] = False
        info["message"] = "当前嵌入维度与库内向量不一致，未写入元数据；请先重建索引"
        return info
    info["compatible"] = True
    if apply:
        from ingest.data_loader import write_index_meta as _write
        _write({**spec.to_meta(), "probe_dim": len(probe),
                "stored_dim": info["stored_dim"]})
        info["written"] = True
    return info


def drop_legacy_chunks(apply: bool, force: bool) -> Dict[str, Any]:
    """删除没有 dataset_version 的旧 Chunk（破坏性，需 --force）。"""
    with _session() as session:
        count = session.run(
            "MATCH (c:Chunk) WHERE c.dataset_version IS NULL RETURN count(c) AS c"
        ).single()["c"]
    result = {"legacy_chunks": count, "deleted": 0}
    if not count:
        return result
    if not (apply and force):
        result["message"] = "未执行（需要 --apply 且 --force）"
        return result
    with _session() as session:
        session.run(
            "MATCH (c:Chunk) WHERE c.dataset_version IS NULL DETACH DELETE c")
        result["deleted"] = count
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="GraphRAG 数据迁移（默认只读）")
    parser.add_argument("--report", action="store_true", help="只读报告")
    parser.add_argument("--backfill-eras", action="store_true")
    parser.add_argument("--backfill-art-type", action="store_true")
    parser.add_argument("--index-meta", action="store_true")
    parser.add_argument("--drop-legacy-chunks", action="store_true")
    parser.add_argument("--apply", action="store_true", help="真正写入（默认 dry-run）")
    parser.add_argument("--force", action="store_true", help="允许破坏性操作")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = parser.parse_args()

    settings = get_settings()
    print(f"[migrate] Neo4j = {settings.neo4j_url}，apply={args.apply}")

    outputs: Dict[str, Any] = {}
    if args.report or not any([args.backfill_eras, args.backfill_art_type,
                               args.index_meta, args.drop_legacy_chunks]):
        outputs["report"] = report()
    if args.backfill_eras:
        outputs["eras"] = backfill_eras(args.apply)
    if args.backfill_art_type:
        outputs["art_type"] = backfill_art_type(args.apply)
    if args.index_meta:
        outputs["index_meta"] = write_index_meta(args.apply)
    if args.drop_legacy_chunks:
        outputs["legacy_chunks"] = drop_legacy_chunks(args.apply, args.force)

    if args.json:
        print(json.dumps(outputs, ensure_ascii=False, indent=2, default=str))
    else:
        for key, value in outputs.items():
            print(f"=== {key} ===")
            print(json.dumps(value, ensure_ascii=False, indent=1, default=str)[:4000])
    if not args.apply:
        print("[migrate] dry-run：未改动数据库（加 --apply 才会写入）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
