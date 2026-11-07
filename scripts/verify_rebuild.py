"""重建后的数据校验（每本书样本导入后、全量构建后都可复跑）。

检查项：
1. 规模：块数 / 实体数 / 关系数 / 按书目与类型分布
2. 首次写入的实体属性：description / location / art_type 覆盖率与样例
3. 关系证据：chunk_ids 覆盖率；抽样验证 snippet 确实出现在对应原文块里
4. 向量检索：查询能召回新块（chunker-v2 id），维度与索引一致
5. 索引/约束/IndexMeta 状态
6. 断点：完成数 / 失败数（失败块可用 --reingest-failed 重试）

用法：
    python scripts/verify_rebuild.py
    python scripts/verify_rebuild.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

ENTITY_LABELS = ["人物", "门派", "武功", "地点"]
BOOKS = ["射雕英雄传", "神雕侠侣", "倚天屠龙记"]


def _session():
    from ingest.data_loader import get_driver
    return get_driver().session()


def collect() -> dict:
    report: dict = {}
    with _session() as session:
        report["chunks_by_book"] = {
            row["book"]: {"count": row["c"], "version": row["v"], "with_embedding": row["e"]}
            for row in session.run(
                "MATCH (c:Chunk) RETURN coalesce(c.book,'?') AS book, "
                "  coalesce(c.dataset_version,'legacy') AS v, count(c) AS c, "
                "  sum(CASE WHEN c.embedding IS NULL THEN 0 ELSE 1 END) AS e "
                "ORDER BY c DESC").data()}
        report["entities_by_label_era"] = [
            dict(row) for row in session.run(
                "MATCH (n) WHERE any(l IN labels(n) WHERE l IN $labels) "
                "RETURN head([l IN labels(n) WHERE l IN $labels]) AS label, "
                "       coalesce(n.era,'<null>') AS era, count(*) AS c "
                "ORDER BY label, c DESC", {"labels": ENTITY_LABELS}).data()]
        report["entity_attributes"] = session.run(
            "MATCH (n) WHERE any(l IN labels(n) WHERE l IN $labels) "
            "RETURN count(n) AS total, "
            "  sum(CASE WHEN n.description IS NOT NULL THEN 1 ELSE 0 END) AS with_description, "
            "  sum(CASE WHEN n.location IS NOT NULL THEN 1 ELSE 0 END) AS with_location, "
            "  sum(CASE WHEN n.art_type IS NOT NULL THEN 1 ELSE 0 END) AS with_art_type, "
            "  sum(CASE WHEN n.description IS NOT NULL AND n.description <> '' "
            "           THEN 1 ELSE 0 END) AS with_description_text",
            {"labels": ENTITY_LABELS}).single().data()
        report["attribute_samples"] = {
            "人物": session.run(
                "MATCH (n:人物) WHERE n.description IS NOT NULL "
                "RETURN n.name AS name, n.description AS description LIMIT 3").data(),
            "门派": session.run(
                "MATCH (n:门派) WHERE n.location IS NOT NULL "
                "RETURN n.name AS name, n.location AS location LIMIT 3").data(),
            "武功": session.run(
                "MATCH (n:武功) WHERE n.art_type IS NOT NULL "
                "RETURN n.name AS name, n.art_type AS art_type LIMIT 3").data(),
        }
        rel = session.run(
            "MATCH ()-[r]->() WHERE type(r) <> 'MENTIONS' "
            "RETURN count(r) AS total, "
            "  sum(CASE WHEN r.chunk_ids IS NOT NULL AND size(r.chunk_ids) > 0 "
            "           THEN 1 ELSE 0 END) AS with_evidence, "
            "  sum(CASE WHEN r.snippets IS NOT NULL AND size(r.snippets) > 0 "
            "           THEN 1 ELSE 0 END) AS with_snippet").single()
        report["relationship_evidence"] = rel.data()
        # 抽样 5 条关系，验证 snippet 确实出现在对应 chunk 原文里
        samples = session.run(
            "MATCH (a)-[r]->(b) WHERE type(r) <> 'MENTIONS' "
            "  AND r.chunk_ids IS NOT NULL AND size(r.chunk_ids) > 0 "
            "  AND r.snippets IS NOT NULL AND size(r.snippets) > 0 "
            "RETURN a.name AS source, b.name AS target, type(r) AS type, "
            "       r.chunk_ids[0] AS chunk_id, r.snippets[0] AS snippet LIMIT 5").data()
        verified = []
        for item in samples:
            row = session.run("MATCH (c:Chunk {chunk_id: $cid}) RETURN c.text AS text",
                              {"cid": item["chunk_id"]}).single()
            text = (row["text"] if row else "") or ""
            verified.append({**item,
                             "chunk_exists": bool(row),
                             "snippet_in_chunk": bool(item["snippet"]) and item["snippet"] in text})
        report["evidence_samples"] = verified
        report["indexes"] = session.run(
            "SHOW INDEXES YIELD name, type, state, labelsOrTypes, properties "
            "RETURN name, type, state, labelsOrTypes, properties").data()
        report["constraints"] = session.run(
            "SHOW CONSTRAINTS YIELD name, type RETURN name, type").data()

    from ingest.data_loader import read_index_meta
    report["index_meta"] = read_index_meta()

    # 向量检索召回
    try:
        from ingest.data_loader import search_by_vector
        hits = search_by_vector("郭靖的师父是谁", 5)
        report["vector_search"] = [
            {"chunk_id": h.get("chunk_id"), "book": h.get("book"),
             "score": round(float(h.get("score") or 0), 4)} for h in hits]
        report["vector_search_ok"] = any(
            "chunker-v2" in str(h.get("chunk_id")) for h in hits)
    except Exception as exc:  # noqa: BLE001
        report["vector_search"] = {"error": f"{type(exc).__name__}: {exc}"}
        report["vector_search_ok"] = False

    # 断点
    checkpoints = {}
    for book in BOOKS:
        path = ROOT / "data" / "interim" / f"kg_checkpoint_{book}.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):  # 旧格式（裸 chunk_id 列表）
            checkpoints[book] = {"dataset_version": "legacy-list",
                                 "completed": len(data), "failed": 0,
                                 "failed_ids": []}
            continue
        checkpoints[book] = {
            "dataset_version": data.get("dataset_version"),
            "completed": len(data.get("completed") or {}),
            "failed": len(data.get("failed") or {}),
            "failed_ids": list((data.get("failed") or {}).keys())[:5],
        }
    report["checkpoints"] = checkpoints
    return report


def summarize(report: dict) -> None:
    print("=== 1. 规模 ===")
    total = 0
    for book, info in report["chunks_by_book"].items():
        total += info["count"]
        print(f"  {book:8s} 块={info['count']:5d} 版本={info['version']:12s} "
              f"有向量={info['with_embedding']}")
    print(f"  合计块数：{total}")
    print("  实体分布：")
    for row in report["entities_by_label_era"]:
        print(f"    {row['label']:4s} era={row['era']:8s} {row['c']}")

    print("=== 2. 实体属性（首次创建即写入） ===")
    attrs = report["entity_attributes"]
    print(f"  实体 {attrs['total']}：description {attrs['with_description']}，"
          f"location {attrs['with_location']}，art_type {attrs['with_art_type']}")
    for label, samples in report["attribute_samples"].items():
        for sample in samples:
            print(f"    样例[{label}]: {json.dumps(sample, ensure_ascii=False)[:120]}")

    print("=== 3. 关系证据 ===")
    rel = report["relationship_evidence"]
    print(f"  关系 {rel['total']}：有 chunk_ids {rel['with_evidence']}，"
          f"有 snippets {rel['with_snippet']}")
    for item in report["evidence_samples"]:
        print(f"    {item['source']} -[{item['type']}]-> {item['target']} "
              f"| chunk={item['chunk_id']} 存在={item['chunk_exists']} "
              f"片段命中={item['snippet_in_chunk']}")

    print("=== 4. 向量检索 ===")
    hits = report.get("vector_search") or []
    if isinstance(hits, dict):
        print(f"    检索失败：{hits.get('error')}")
    else:
        for hit in hits:
            print(f"    {hit.get('chunk_id')} book={hit.get('book')} score={hit.get('score')}")
    print(f"  召回新块(chunker-v2)：{report.get('vector_search_ok')}")
    print(f"  IndexMeta：{report.get('index_meta')}")

    print("=== 5. 索引与约束 ===")
    for index in report["indexes"]:
        print(f"    {index['name']:26s} {index['type']:9s} {index['state']}")
    for constraint in report["constraints"]:
        print(f"    constraint {constraint['name']} ({constraint['type']})")

    print("=== 6. 断点 ===")
    for book, info in report["checkpoints"].items():
        print(f"    {book}: 完成 {info['completed']}，失败 {info['failed']} "
              f"版本={info['dataset_version']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="重建后数据校验")
    parser.add_argument("--json", action="store_true", help="输出原始 JSON")
    args = parser.parse_args()
    report = collect()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        summarize(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
