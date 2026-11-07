"""Neo4j 逻辑备份 / 恢复 / 校验（不依赖 docker，可在任意环境运行）。

背景：目标 Neo4j 是 Community 版且跑在容器里，本机受限环境下无法访问 Docker
命名管道，因此不用 neo4j-admin dump，而是用 Cypher 做**逻辑备份**：

    backup/<时间戳>/neo4j/nodes.jsonl            节点（不含向量）
    backup/<时间戳>/neo4j/chunk_embeddings.jsonl 文本块向量（单独存放，体积可控）
    backup/<时间戳>/neo4j/rels.jsonl             关系
    backup/<时间戳>/neo4j/meta.json              版本/计数/索引/IndexMeta

恢复用临时标签 _BackupNode + _bk_id 建立映射，恢复完成后移除临时标签与属性，
因此与节点内部 id 无关，可恢复到任意空库。

用法：
    python scripts/neo4j_backup.py export  --out backup/20261107_1200
    python scripts/neo4j_backup.py verify  --backup backup/20261107_1200
    python scripts/neo4j_backup.py restore --backup backup/20261107_1200 --yes
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

BATCH = 500
TEMP_LABEL = "_BackupNode"
TEMP_PROP = "_bk_id"


def _driver():
    from ingest.data_loader import create_driver
    return create_driver()


def _session():
    return _driver().session()


def _jsonl_write(path: Path, rows: Iterable[Dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + chr(10))
            count += 1
    return count


def _jsonl_read(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


# ============ 导出 ============

def export(out_dir: Path, *, include_embeddings: bool = True,
           verbose: bool = True) -> Dict[str, Any]:
    out_dir = Path(out_dir)
    neo4j_dir = out_dir / "neo4j"
    neo4j_dir.mkdir(parents=True, exist_ok=True)
    meta: Dict[str, Any] = {
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "format": "graphrag-logical-backup-v1",
    }

    with _session() as session:
        meta["database"] = session.run(
            "CALL db.info() YIELD name RETURN name").single()["name"]
        try:
            meta["kernel_version"] = session.run(
                "CALL dbms.components() YIELD name, versions "
                "RETURN name, versions LIMIT 1").single()["versions"]
        except Exception:
            meta["kernel_version"] = "unknown"

        # 1) 节点（向量单独导出）
        def node_rows():
            result = session.run(
                "MATCH (n) RETURN elementId(n) AS id, labels(n) AS labels, "
                "       properties(n) AS props")
            for record in result:
                props = dict(record["props"] or {})
                has_embedding = "embedding" in props
                if has_embedding:
                    props.pop("embedding", None)
                yield {"id": record["id"], "labels": record["labels"],
                       "props": props, "has_embedding": has_embedding}

        meta["nodes"] = _jsonl_write(neo4j_dir / "nodes.jsonl", node_rows())

        # 2) 向量
        meta["embeddings"] = 0
        if include_embeddings:
            def embedding_rows():
                result = session.run(
                    "MATCH (c:Chunk) WHERE c.embedding IS NOT NULL "
                    "RETURN c.chunk_id AS chunk_id, c.embedding AS embedding")
                for record in result:
                    yield {"chunk_id": record["chunk_id"],
                           "embedding": record["embedding"]}
            meta["embeddings"] = _jsonl_write(
                neo4j_dir / "chunk_embeddings.jsonl", embedding_rows())

        # 3) 关系
        def rel_rows():
            result = session.run(
                "MATCH (a)-[r]->(b) "
                "RETURN elementId(r) AS id, type(r) AS type, "
                "       elementId(a) AS start, elementId(b) AS end, "
                "       properties(r) AS props")
            for record in result:
                yield {"id": record["id"], "type": record["type"],
                       "start": record["start"], "end": record["end"],
                       "props": dict(record["props"] or {})}

        meta["relationships"] = _jsonl_write(neo4j_dir / "rels.jsonl", rel_rows())

        # 4) 结构与元数据
        meta["labels"] = {
            row["label"]: row["count"] for row in session.run(
                "MATCH (n) UNWIND labels(n) AS label "
                "RETURN label, count(*) AS count ORDER BY count DESC").data()}
        meta["rel_types"] = {
            row["type"]: row["count"] for row in session.run(
                "MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS count "
                "ORDER BY count DESC").data()}
        try:
            meta["indexes"] = session.run(
                "SHOW INDEXES YIELD name, type, labelsOrTypes, properties, state "
                "RETURN name, type, labelsOrTypes, properties, state").data()
        except Exception as exc:  # noqa: BLE001
            meta["indexes"] = {"error": str(exc)}
        try:
            meta["constraints"] = session.run(
                "SHOW CONSTRAINTS YIELD name, type, labelsOrTypes, properties "
                "RETURN *").data()
        except Exception as exc:  # noqa: BLE001
            meta["constraints"] = {"error": str(exc)}
        try:
            from ingest.data_loader import read_index_meta
            meta["index_meta"] = read_index_meta()
        except Exception as exc:  # noqa: BLE001
            meta["index_meta"] = {"error": str(exc)}

    (neo4j_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    if verbose:
        print(f"[backup] 导出完成：{neo4j_dir}")
        print(f"  节点 {meta['nodes']}，关系 {meta['relationships']}，"
              f"向量 {meta['embeddings']}")
    return meta


# ============ 恢复 ============

def _batched(items: Iterable[Dict], size: int = BATCH) -> Iterable[List[Dict]]:
    batch: List[Dict] = []
    for item in items:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def restore(backup_dir: Path, *, include_embeddings: bool = True,
            verbose: bool = True) -> Dict[str, int]:
    backup_dir = Path(backup_dir)
    neo4j_dir = backup_dir / "neo4j"
    nodes_path = neo4j_dir / "nodes.jsonl"
    rels_path = neo4j_dir / "rels.jsonl"
    emb_path = neo4j_dir / "chunk_embeddings.jsonl"
    if not nodes_path.exists() or not rels_path.exists():
        raise SystemExit(f"备份不完整：{neo4j_dir}")

    stats = {"nodes": 0, "relationships": 0, "embeddings": 0}
    with _session() as session:
        # 1) 节点：先按临时标签建，再补真实标签
        for batch in _batched(_jsonl_read(nodes_path)):
            grouped: Dict[tuple, List[Dict]] = {}
            for row in batch:
                grouped.setdefault(tuple(sorted(row["labels"])), []).append(row)
            for labels, rows in grouped.items():
                label_clause = "".join(f":{label}" for label in labels)
                session.run(
                    f"UNWIND $rows AS row "
                    f"MERGE (n:{TEMP_LABEL} {{{TEMP_PROP}: row.id}}) "
                    f"SET n += row.props{label_clause}",
                    rows=[{"id": r["id"], "props": r["props"]} for r in rows])
                stats["nodes"] += len(rows)

        # 2) 关系
        for batch in _batched(_jsonl_read(rels_path)):
            grouped: Dict[str, List[Dict]] = {}
            for row in batch:
                grouped.setdefault(row["type"], []).append(row)
            for rel_type, rows in grouped.items():
                session.run(
                    "UNWIND $rows AS row "
                    f"MATCH (a:{TEMP_LABEL} {{{TEMP_PROP}: row.start}}) "
                    f"MATCH (b:{TEMP_LABEL} {{{TEMP_PROP}: row.end}}) "
                    f"MERGE (a)-[r:{rel_type}]->(b) SET r += row.props",
                    rows=[{"start": r["start"], "end": r["end"], "props": r["props"]}
                          for r in rows])
                stats["relationships"] += len(rows)

        # 3) 向量
        if include_embeddings and emb_path.exists():
            for batch in _batched(_jsonl_read(emb_path)):
                session.run(
                    "UNWIND $rows AS row "
                    "MATCH (c:Chunk {chunk_id: row.chunk_id}) "
                    "SET c.embedding = row.embedding",
                    rows=[{"chunk_id": r["chunk_id"], "embedding": r["embedding"]}
                          for r in batch])
                stats["embeddings"] += len(batch)

        # 4) 移除临时标签与属性
        session.run(
            f"MATCH (n:{TEMP_LABEL}) REMOVE n:{TEMP_LABEL} REMOVE n.{TEMP_PROP}")
    if verbose:
        print(f"[restore] 完成：{stats}")
    return stats


# ============ 校验 ============

def verify(backup_dir: Path) -> Dict[str, Any]:
    backup_dir = Path(backup_dir)
    meta_path = backup_dir / "neo4j" / "meta.json"
    if not meta_path.exists():
        raise SystemExit(f"缺少 meta.json：{meta_path}")
    expected = json.loads(meta_path.read_text(encoding="utf-8"))
    actual: Dict[str, Any] = {}
    with _session() as session:
        actual["nodes"] = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        actual["relationships"] = session.run(
            "MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
        actual["chunks"] = session.run(
            "MATCH (c:Chunk) RETURN count(c) AS c").single()["c"]
        actual["embeddings"] = session.run(
            "MATCH (c:Chunk) WHERE c.embedding IS NOT NULL RETURN count(c) AS c"
        ).single()["c"]
        actual["labels"] = {
            row["label"]: row["count"] for row in session.run(
                "MATCH (n) UNWIND labels(n) AS label RETURN label, count(*) AS count"
            ).data()}
    report = {
        "backup": str(backup_dir),
        "expected": {key: expected.get(key) for key in
                     ("nodes", "relationships", "embeddings", "labels")},
        "actual": actual,
        "matches": (expected.get("nodes") == actual["nodes"]
                    and expected.get("relationships") == actual["relationships"]),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Neo4j 逻辑备份 / 恢复 / 校验")
    sub = parser.add_subparsers(dest="command", required=True)

    p_export = sub.add_parser("export", help="导出当前库")
    p_export.add_argument("--out", required=True)
    p_export.add_argument("--skip-embeddings", action="store_true")

    p_restore = sub.add_parser("restore", help="恢复备份到当前库")
    p_restore.add_argument("--backup", required=True)
    p_restore.add_argument("--skip-embeddings", action="store_true")
    p_restore.add_argument("--yes", action="store_true", help="确认执行写入")

    p_verify = sub.add_parser("verify", help="对比备份与当前库")
    p_verify.add_argument("--backup", required=True)

    args = parser.parse_args()
    if args.command == "export":
        export(Path(args.out), include_embeddings=not args.skip_embeddings)
    elif args.command == "verify":
        verify(Path(args.backup))
    else:
        if not args.yes:
            raise SystemExit("恢复会写入数据库，请加 --yes 确认")
        restore(Path(args.backup), include_embeddings=not args.skip_embeddings)
    return 0


if __name__ == "__main__":
    sys.exit(main())
