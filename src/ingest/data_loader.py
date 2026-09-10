"""
ingest/data_loader.py
数据读取接口：C（两个基线）和 D（PPR / 领域策略）都通过这里读数据，
不要在检索代码里自己连 Neo4j。

提供的函数（返回格式已和 C、D 约定，见 INTERFACE.md）：

┌──────────────────────────────┬──────────────────────────────────────────┐
│ 函数                          │ 返回                                     │
├──────────────────────────────┼──────────────────────────────────────────┤
│ get_chunks()                 │ [{"chunk_id", "chapter", "text"}, ...]   │
│ get_graph(era=None)          │ {"nodes": [...], "edges": [...]}         │
│ search_by_vector(q, top_k)   │ [{"chunk_id", "text", "score"}, ...]     │
│ search_by_text(q, top_k)     │ [{"chunk_id", "text", "score"}, ...]     │
│ run_query(cypher, params)    │ [dict, ...]（Cypher 原样执行，给 D 用）   │
└──────────────────────────────┴──────────────────────────────────────────┘

节点结构：{"id": 内部id, "name", "type": 人物/门派/武功/地点, "era", ...}
边结构：  {"source": 名字, "target": 名字, "type": MASTER_OF/...}

era 过滤：阶段二多本书后，get_graph(era="射雕") 可以只取一个时代的子图，
用于跨书噪声过滤；阶段一单书时不用传。
"""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from neo4j import GraphDatabase

from core.config import get_env
from ingest.build_kg import make_embedder
from ingest.corpus import DEFAULT_OUT_PATH

# 复用 build_kg 的嵌入方案，保证入库和检索用同一套向量（对比才公平）
_embedder = make_embedder()

_driver = None


def get_driver(): # 获取 Neo4j 连接驱动
    """惰性单例的 Neo4j driver。"""
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            get_env("NEO4J_URL", "bolt://localhost:7687"),
            auth=(get_env("NEO4J_USER", "neo4j"),
                  get_env("NEO4J_PASSWORD", "")),
        )
    return _driver


def close_driver(): # 关闭 Neo4j 连接驱动
    """用完关连接（评测脚本/服务退出时调用）。"""
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None


# ============ 1. 文本块 ============

def get_chunks() -> List[Dict[str, Any]]:
    """读所有文本块（从 Neo4j 的 Chunk 节点读，没有库时兜底读 chunks.json）。"""
    try:
        with get_driver().session() as session:
            rows = session.run(
                "MATCH (c:Chunk) RETURN c.chunk_id AS chunk_id, "
                "c.chapter AS chapter, c.text AS text ORDER BY c.chunk_id"
            ).data()
        if rows:
            return rows
    except Exception:
        pass
    # 兜底：还没入库时，直接读切块的中间文件
    if Path(DEFAULT_OUT_PATH).exists():
        return json.loads(Path(DEFAULT_OUT_PATH).read_text(encoding="utf-8"))
    return []


# ============ 2. 实体关系图 ============

GET_NODES = """
MATCH (n)
WHERE any(l IN labels(n) WHERE l IN ['人物', '门派', '武功', '地点'])
RETURN id(n) AS id, n.name AS name,
       head([l IN labels(n) WHERE l IN ['人物', '门派', '武功', '地点']]) AS type,
       n.era AS era, n.location AS location
"""

GET_EDGES = """
MATCH (a)-[r]->(b)
WHERE any(l IN labels(a) WHERE l IN ['人物', '门派', '武功', '地点'])
  AND any(l IN labels(b) WHERE l IN ['人物', '门派', '武功', '地点'])
  AND type(r) <> 'MENTIONS'
RETURN a.name AS source, b.name AS target, type(r) AS type
"""


def get_graph(era: Optional[str] = None) -> Dict[str, List[Dict]]:
    """读实体关系图。

    era 传 "射雕"/"神雕"/"倚天" 时只返回该时代的实体及其之间的边
    （跨书噪声过滤）。不传返回全图。
    """
    with get_driver().session() as session:
        nodes = session.run(GET_NODES).data()
        if era:
            nodes = [n for n in nodes if n.get("era") == era]
        names = {n["name"] for n in nodes}
        edges = session.run(GET_EDGES).data()
        edges = [e for e in edges
                 if e["source"] in names and e["target"] in names]

    # 统一节点字段（前端画图直接用）
    for n in nodes:
        n.setdefault("era", None)
        n.setdefault("location", None)
    return {"nodes": nodes, "edges": edges}


# ============ 3. 向量检索 ============

VECTOR_SEARCH = """
CALL db.index.vector.queryNodes('text_embeddings', $top_k, $embedding)
YIELD node, score
RETURN node.chunk_id AS chunk_id, node.text AS text, score
"""


def search_by_vector(question: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """按向量找最相似的文本块（走 text_embeddings 向量索引）。"""
    embedding = _embedder([question])[0]
    with get_driver().session() as session:
        return session.run(VECTOR_SEARCH, top_k=top_k,
                           embedding=embedding).data()


# ============ 4. 全文检索（辅助） ============

FULLTEXT_SEARCH = """
CALL db.index.fulltext.queryNodes('text_fulltext', $query)
YIELD node, score
RETURN node.chunk_id AS chunk_id, node.text AS text, score
LIMIT $top_k
"""


def search_by_text(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """按关键词全文检索文本块（走 text_fulltext 全文索引）。

    向量检索找"语义相似"，全文检索找"字面命中"（比如人名、招式名），
    C 的基线和 D 的"定位起始实体"都可以用。
    """
    with get_driver().session() as session:
        return session.run(FULLTEXT_SEARCH, query=query, top_k=top_k).data()


# ============ 5. 通用 Cypher（给 D 用） ============

def run_query(cypher: str, params: Optional[Dict[str, Any]] = None) -> List[Dict]:
    """执行任意 Cypher 查询，返回 list[dict]。

    这是给 D 的领域策略（master_chain / sect_agg / art_lineage）用的
    通用图查询入口，D 自己写 Cypher，例如：

        # 师徒链：郭靖的师父的师父
        run_query(\"\"\"
            MATCH (p:人物 {name: $name})<-[:MASTER_OF*1..3]-(master:人物)
            RETURN master.name AS name
        \"\"\", {"name": "郭靖"})

        # 门派聚合：丐帮下的人物和武功
        run_query(\"\"\"
            MATCH (s:门派 {name: $sect})<-[:BELONGS_TO]-(p:人物)
            OPTIONAL MATCH (p)-[:MASTERS]->(a:武功)
            RETURN p.name AS person, collect(a.name) AS arts
        \"\"\", {"sect": "丐帮"})

        # 武功传承：降龙十八掌从谁传给谁
        run_query(\"\"\"
            MATCH (a:武功 {name: $art})<-[:MASTERS]-(m:人物)-[:MASTER_OF]->(d:人物)
            WHERE (d)-[:MASTERS]->(a)
            RETURN m.name AS from, d.name AS to
        \"\"\", {"art": "降龙十八掌"})
    """
    with get_driver().session() as session:
        return session.run(cypher, params or {}).data()


if __name__ == "__main__":
    # 简单自检：python data_loader.py
    chunks = get_chunks()
    print(f"chunks: {len(chunks)}")
    graph = get_graph()
    print(f"nodes: {len(graph['nodes'])}, edges: {len(graph['edges'])}")
