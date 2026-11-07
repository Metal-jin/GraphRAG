"""数据读取接口（B 维护，C/D 唯一的数据入口）。

提供的函数（返回格式见 INTERFACE.md）：

┌──────────────────────────────┬──────────────────────────────────────────────┐
│ get_chunks(books=None)       │ [{"chunk_id","book","era","chapter","text"}] │
│ get_entity_nodes(...)        │ [{"name","label","era"}]（轻量，给实体链接）  │
│ get_graph(era=, books=)      │ {"nodes": [...], "edges": [...]}             │
│ search_by_vector(q, top_k)   │ [{"chunk_id","text","score"}]                │
│ search_by_text(q, top_k)     │ [{"chunk_id","text","score"}]                │
│ run_query(cypher, params)    │ [dict, ...]（Cypher 原样执行，给领域策略用）  │
└──────────────────────────────┴──────────────────────────────────────────────┘

阶段二优化（任务 03/04/10/29/30）：
- 嵌入统一走 core.embedding 的进程级单例，入库与查询保证同一 spec；
- 向量索引带 IndexMeta 元数据，维度/模型不一致时显式报错，不静默混用；
- get_graph 的时代/书目过滤下推到 Cypher，不再把全图拉到内存再筛；
- 文件兜底读取同一版本的多书 chunks_<书名>.json，返回完整元数据。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

# 自举 sys.path：允许 `python src/ingest/data_loader.py` 直接运行（不依赖 PYTHONPATH）
_SRC_DIR = Path(__file__).resolve().parents[1]
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from neo4j import GraphDatabase  # noqa: E402

from core.config import get_env, get_settings  # noqa: E402
from core.embedding import assert_index_compatible, get_embedder
from core.errors import DataUnavailableError, EmbeddingError
from core.query import QueryScope, normalize_top_k

from ingest.corpus import DEFAULT_OUT_DIR, DEFAULT_OUT_PATH

_DEFAULT_DRIVER = None

ENTITY_LABEL_LIST = ["人物", "门派", "武功", "地点"]

# 兼容旧代码：部分调用方还会 import 这个名字
_last_embedding_error: Optional[str] = None


# ============ 连接 ============

def create_driver():
    """创建 Neo4j driver（统一参数：超时、连接生命周期、关闭属性缺失告警）。"""
    settings = get_settings()
    kwargs = dict(
        auth=(settings.neo4j_user or "neo4j", settings.neo4j_password or ""),
        connection_timeout=15,
        max_connection_lifetime=1800,
    )
    try:
        # 关闭 "property key does not exist" 之类的噪声告警（Neo4j 5.7+）
        return GraphDatabase.driver(settings.neo4j_url or "bolt://localhost:7687",
                                    notifications_min_severity="OFF", **kwargs)
    except TypeError:
        return GraphDatabase.driver(settings.neo4j_url or "bolt://localhost:7687", **kwargs)


def get_driver():
    """惰性单例的 Neo4j driver。"""
    global _DEFAULT_DRIVER
    if _DEFAULT_DRIVER is None:
        _DEFAULT_DRIVER = create_driver()
    return _DEFAULT_DRIVER


def close_driver() -> None:
    """用完关连接（评测脚本/服务退出时调用）。"""
    global _DEFAULT_DRIVER
    if _DEFAULT_DRIVER is not None:
        _DEFAULT_DRIVER.close()
        _DEFAULT_DRIVER = None


def health_check() -> Dict[str, Any]:
    """服务健康检查：数据库与向量索引状态（任务 31）。"""
    result: Dict[str, Any] = {"neo4j": "unknown", "index": None, "error": ""}
    try:
        with get_driver().session() as session:
            session.run("RETURN 1").consume()
        result["neo4j"] = "ok"
        result["index"] = read_index_meta()
    except Exception as exc:  # noqa: BLE001 - 健康检查要吞掉所有异常
        result["neo4j"] = "unavailable"
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


# ============ 1. 文本块 ============

CHUNK_QUERY = """
MATCH (c:Chunk)
WHERE $books IS NULL OR c.book IN $books
RETURN c.chunk_id AS chunk_id, coalesce(c.book, '') AS book,
       coalesce(c.era, '') AS era, coalesce(c.chapter, '') AS chapter,
       c.text AS text
ORDER BY c.book, c.chunk_id
"""


def _chunks_from_files(books: Optional[Sequence[str]] = None) -> List[Dict[str, Any]]:
    """文件兜底：优先读同一版本的多书 chunks_<书名>.json。"""
    out: List[Dict[str, Any]] = []
    files = sorted(Path(DEFAULT_OUT_DIR).glob("chunks_*.json"))
    if books:
        wanted = [b for b in books if b]
        files = [f for f in files if any(w in f.stem for w in wanted)]
    for path in files:
        try:
            rows = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for row in rows:
            if isinstance(row, dict):
                row.setdefault("book", Path(path).stem.replace("chunks_", ""))
                row.setdefault("era", "")
                out.append(row)
    if out:
        return out
    legacy = Path(DEFAULT_OUT_PATH)
    if legacy.exists():
        try:
            return json.loads(legacy.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
    return []


def get_chunks(books: Optional[Sequence[str]] = None) -> List[Dict[str, Any]]:
    """读文本块：优先 Neo4j，连不上时兜底读本地切块文件（多书版本）。"""
    try:
        with get_driver().session() as session:
            rows = session.run(CHUNK_QUERY, books=list(books) if books else None).data()
        if rows:
            return rows
    except Exception:
        pass
    return _chunks_from_files(books)


# ============ 2. 实体 / 关系图 ============

LABEL_FILTER = "any(l IN labels(n) WHERE l IN $labels)"

GET_NODES = f"""
MATCH (n)
WHERE {LABEL_FILTER}
  AND ($eras IS NULL OR n.era IN $eras)
RETURN id(n) AS id, n.name AS name,
       head([l IN labels(n) WHERE l IN $labels]) AS type,
       n.era AS era, n.location AS location,
       coalesce(n.books, [n.era]) AS books
"""

GET_EDGES = f"""
MATCH (a)-[r]->(b)
WHERE {LABEL_FILTER.replace('(n)', '(a)')}
  AND {LABEL_FILTER.replace('(n)', '(b)')}
  AND type(r) <> 'MENTIONS'
  AND ($eras IS NULL OR (coalesce(a.era, '') IN $eras AND coalesce(b.era, '') IN $eras))
RETURN a.name AS source, b.name AS target, type(r) AS type
"""

GET_ENTITY_NODES = f"""
MATCH (n)
WHERE {LABEL_FILTER}
  AND ($eras IS NULL OR n.era IN $eras)
RETURN n.name AS name, head([l IN labels(n) WHERE l IN $labels]) AS label, n.era AS era
"""


def _scope_params(era: Optional[str] = None,
                  books: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    eras = [era] if era else None
    if not eras and books:
        from core.ontology import BOOK_TO_ERA
        eras = [BOOK_TO_ERA[b] for b in books if b in BOOK_TO_ERA] or None
    return {"labels": ENTITY_LABEL_LIST, "eras": eras}


def get_entity_nodes(era: Optional[str] = None,
                     books: Optional[Sequence[str]] = None) -> List[Dict[str, Any]]:
    """只读实体名/类型/时代（实体链接用，避免为找一个种子加载全图）。"""
    with get_driver().session() as session:
        return session.run(GET_ENTITY_NODES, **_scope_params(era, books)).data()


def get_graph(era: Optional[str] = None,
              books: Optional[Sequence[str]] = None) -> Dict[str, List[Dict]]:
    """读实体关系图；era/books 过滤下推到数据库（任务 29）。"""
    params = _scope_params(era, books)
    with get_driver().session() as session:
        nodes = session.run(GET_NODES, **params).data()
        edges = session.run(GET_EDGES, **params).data()
    for node in nodes:
        node.setdefault("era", None)
        node.setdefault("location", None)
    return {"nodes": nodes, "edges": edges}


# ============ 3. 向量检索 ============

VECTOR_SEARCH = """
CALL db.index.vector.queryNodes('text_embeddings', $top_k, $embedding)
YIELD node, score
RETURN node.chunk_id AS chunk_id, node.text AS text, score,
       coalesce(node.book, '') AS book, coalesce(node.era, '') AS era,
       coalesce(node.chapter, '') AS chapter
"""

FULLTEXT_SEARCH = """
CALL db.index.fulltext.queryNodes('text_fulltext', $query)
YIELD node, score
RETURN node.chunk_id AS chunk_id, node.text AS text, score,
       coalesce(node.book, '') AS book, coalesce(node.era, '') AS era,
       coalesce(node.chapter, '') AS chapter
LIMIT $top_k
"""

INDEX_META_QUERY = "MATCH (m:IndexMeta {name: $name}) RETURN properties(m) AS meta"
INDEX_META_WRITE = """
MERGE (m:IndexMeta {name: $name})
SET m += $meta, m.updated_at = timestamp()
"""


def read_index_meta(name: str = "chunk_embeddings") -> Optional[Dict[str, Any]]:
    """读取向量索引元数据（模型/维度/版本）。"""
    try:
        with get_driver().session() as session:
            row = session.run(INDEX_META_QUERY, name=name).single()
        return dict(row["meta"]) if row and row["meta"] else None
    except Exception:
        return None


def write_index_meta(meta: Dict[str, Any], name: str = "chunk_embeddings") -> None:
    with get_driver().session() as session:
        session.run(INDEX_META_WRITE, name=name, meta=meta)


def search_by_vector(question: str, top_k: int = 5,
                     era: Optional[str] = None) -> List[Dict[str, Any]]:
    """按向量找最相似的文本块（走 text_embeddings 向量索引）。"""
    top_k = normalize_top_k(top_k)
    embedder = get_embedder()
    # 必须先算查询向量：远程嵌入的 spec.dimension 在首次调用前是 0，
    # 先校验会把"维度未知"误判成"维度不一致"。
    try:
        embedding = embedder.embed_query(question)
    except EmbeddingError:
        raise
    except Exception as exc:
        raise DataUnavailableError("查询向量生成失败", detail=str(exc)) from exc
    meta = read_index_meta()
    try:
        assert_index_compatible(meta, embedder.spec)
    except Exception as exc:  # 索引不兼容
        raise DataUnavailableError("向量检索不可用", detail=str(exc)) from exc
    if meta and meta.get("dimension") and len(embedding) != int(meta["dimension"]):
        raise DataUnavailableError(
            "查询向量维度与索引不一致",
            detail=f"query={len(embedding)} index={meta.get('dimension')}；"
                   f"请重建索引或修正 EMBED_* 配置")
    try:
        with get_driver().session() as session:
            rows = session.run(VECTOR_SEARCH, top_k=top_k, embedding=embedding).data()
    except Exception as exc:
        raise DataUnavailableError("向量索引查询失败", detail=str(exc)) from exc
    if era:
        rows = [r for r in rows if r.get("era") in (era, "", None)]
    return rows


# ============ 4. 全文检索（辅助） ============

def search_by_text(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """按关键词全文检索文本块；无结果或索引缺失时返回空列表（不抛异常）。"""
    top_k = normalize_top_k(top_k)
    if not (query or "").strip():
        return []
    with get_driver().session() as session:
        try:
            return session.run(FULLTEXT_SEARCH, query=query, top_k=top_k).data()
        except Exception:
            return []


# ============ 5. 通用 Cypher ============

def run_query(cypher: str, params: Optional[Dict[str, Any]] = None) -> List[Dict]:
    """执行任意 Cypher 查询，返回 list[dict]。数据库不可用时抛 DataUnavailableError。"""
    try:
        with get_driver().session() as session:
            return session.run(cypher, params or {}).data()
    except Exception as exc:
        raise DataUnavailableError("图数据库查询失败", detail=str(exc)) from exc


def run_query_with_scope(cypher: str, params: Optional[Dict[str, Any]] = None,
                         scope: Optional[QueryScope] = None) -> List[Dict]:
    """带查询范围的 run_query：把 eras 参数注入到 Cypher 参数里。"""
    merged = dict(params or {})
    merged.setdefault("eras", list(scope.eras) if scope and scope.eras else None)
    return run_query(cypher, merged)


if __name__ == "__main__":
    # 简单自检：python data_loader.py
    chunks = get_chunks()
    print(f"chunks: {len(chunks)}")
    graph = get_graph()
    print(f"nodes: {len(graph['nodes'])}, edges: {len(graph['edges'])}")
    print(f"health: {health_check()}")


__all__ = ["get_driver", "close_driver", "health_check", "get_chunks",
           "get_entity_nodes", "get_graph", "search_by_vector", "search_by_text",
           "run_query", "run_query_with_scope", "read_index_meta", "write_index_meta",
           "ENTITY_LABEL_LIST"]
