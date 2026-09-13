from wsgiref.simple_server import make_server
import json
import sys
import os
from urllib.parse import parse_qs

# 把项目根目录加入路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# 把 src 目录也加入路径，让 service.py 里的 `from core.xxx` 能找到模块
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from src.generate.service import get_available_methods, ask_question, ask_auto
from src.ingest.data_loader import get_graph, run_query


# 前端时代滑块传完整书名，图谱里 era 存的是简写，这里做映射
ERA_MAP = {
    "射雕英雄传": "射雕",
    "神雕侠侣": "神雕",
    "倚天屠龙记": "倚天",
}


def _to_vis_format(nodes, edges):
    """把 data_loader 的节点/边转成 vis-network 格式（用 name 作节点 id）。"""
    vis_nodes = []
    seen = set()
    for n in nodes:
        name = n.get("name")
        if not name or name in seen:
            continue
        seen.add(name)
        vis_nodes.append({"id": name, "label": name, "type": n.get("type", "")})
    vis_edges = []
    seen_e = set()
    for e in edges:
        s, t = e.get("source"), e.get("target")
        if not s or not t:
            continue
        key = (s, t, e.get("type"))
        if key in seen_e:
            continue
        seen_e.add(key)
        vis_edges.append({"from": s, "to": t, "label": e.get("type", "")})
    return {"nodes": vis_nodes, "edges": vis_edges}


def _query_neighbors(name):
    """查某实体（按 name）的 1 跳邻居，返回 vis 格式。"""
    if not name:
        return {"nodes": [], "edges": []}
    try:
        rows = run_query(
            """
            MATCH (n {name: $name})-[r]-(m)
            WHERE type(r) <> 'MENTIONS'
              AND any(l IN labels(n) WHERE l IN ['人物','门派','武功','地点'])
              AND any(l IN labels(m) WHERE l IN ['人物','门派','武功','地点'])
            RETURN n.name AS a, type(r) AS rel, m.name AS b
            """,
            {"name": name},
        )
    except Exception:
        return {"nodes": [], "edges": []}

    node_names = {}
    edges = []
    seen_e = set()
    for row in rows:
        a, b, rel = row["a"], row["b"], row["rel"]
        node_names[a] = a
        node_names[b] = b
        key = (a, b, rel)
        if key not in seen_e:
            seen_e.add(key)
            edges.append({"from": a, "to": b, "label": rel})
    return {
        "nodes": [{"id": v, "label": v} for v in node_names.values()],
        "edges": edges,
    }


def _extract_path(result):
    """从 ask_auto 结果里提取推理路径（节点名列表，供前端高亮）。"""
    method = result.get("method_name", "")
    evidence = result.get("evidence") or []
    names = []
    if method == "master_chain":
        names = [e.get("name") for e in evidence if e.get("name")]
    elif method == "art_lineage":
        for e in evidence:
            if e.get("from"):
                names.append(e["from"])
            if e.get("to"):
                names.append(e["to"])
    elif method == "person_relation":
        for e in evidence:
            if e.get("source"):
                names.append(e["source"])
            if e.get("target"):
                names.append(e["target"])
    else:
        seed = result.get("seed_entity")
        if seed:
            names = [seed]
    # 去重保序
    seen = set()
    path = []
    for n in names:
        if n and n not in seen:
            seen.add(n)
            path.append(n)
    return path


def application(environ, start_response):
    # 允许跨域，方便本地开发
    headers = [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Access-Control-Allow-Origin", "*"),
        ("Access-Control-Allow-Methods", "GET, POST, OPTIONS"),
        ("Access-Control-Allow-Headers", "Content-Type"),
    ]

    # 处理预检请求
    if environ["REQUEST_METHOD"] == "OPTIONS":
        start_response("200 OK", headers)
        return [b""]

    path = environ["PATH_INFO"]
    method = environ["REQUEST_METHOD"]
    query = parse_qs(environ.get("QUERY_STRING", ""))

    # 获取方法列表
    if path == "/api/methods" and method == "GET":
        start_response("200 OK", headers)
        result = get_available_methods()
        return [json.dumps(result, ensure_ascii=False).encode("utf-8")]

    # 问答接口（手动指定方法）
    elif path == "/api/ask" and method == "POST":
        content_length = int(environ.get("CONTENT_LENGTH", 0))
        body = environ["wsgi.input"].read(content_length).decode("utf-8")
        try:
            params = json.loads(body)
        except json.JSONDecodeError:
            start_response("400 Bad Request", headers)
            return [json.dumps({"error": "请求格式错误"}).encode("utf-8")]
        result = ask_question(**params)
        start_response("200 OK", headers)
        return [json.dumps(result, ensure_ascii=False).encode("utf-8")]

    # 自动问答接口（意图识别 + 自动路由）
    elif path == "/api/ask_auto" and method == "POST":
        content_length = int(environ.get("CONTENT_LENGTH", 0))
        body = environ["wsgi.input"].read(content_length).decode("utf-8")
        try:
            params = json.loads(body)
        except json.JSONDecodeError:
            start_response("400 Bad Request", headers)
            return [json.dumps({"error": "请求格式错误"}).encode("utf-8")]
        result = ask_auto(question=params.get("question", ""), top_k=params.get("top_k", 5))
        start_response("200 OK", headers)
        return [json.dumps(result, ensure_ascii=False).encode("utf-8")]

    # 图谱可视化问答接口（E2 前端用）：答案 + 子图 + 推理路径
    elif path == "/api/qa" and method == "POST":
        content_length = int(environ.get("CONTENT_LENGTH", 0))
        body = environ["wsgi.input"].read(content_length).decode("utf-8")
        try:
            params = json.loads(body)
        except json.JSONDecodeError:
            start_response("400 Bad Request", headers)
            return [json.dumps({"error": "请求格式错误"}).encode("utf-8")]
        qa = ask_auto(question=params.get("question", ""), top_k=params.get("top_k", 5))
        seed = qa.get("seed_entity", "")
        subgraph = _query_neighbors(seed) if seed else {"nodes": [], "edges": []}
        result = {
            "answer": qa.get("answer_text", ""),
            "subgraph": subgraph,
            "path": _extract_path(qa),
        }
        start_response("200 OK", headers)
        return [json.dumps(result, ensure_ascii=False).encode("utf-8")]

    # 查询某节点的 1 跳邻居（前端点击节点展开）
    elif path == "/api/node/neighbor" and method == "GET":
        node_id = query.get("nodeId", [""])[0]
        result = _query_neighbors(node_id)
        start_response("200 OK", headers)
        return [json.dumps(result, ensure_ascii=False).encode("utf-8")]

    # 按时代取整张图（前端时代滑块过滤）
    elif path == "/api/graph/byera" and method == "GET":
        era_full = query.get("era", [""])[0]
        era = ERA_MAP.get(era_full, era_full) or None
        try:
            graph = get_graph(era=era)
            result = _to_vis_format(graph.get("nodes", []), graph.get("edges", []))
        except Exception:
            result = {"nodes": [], "edges": []}
        start_response("200 OK", headers)
        return [json.dumps(result, ensure_ascii=False).encode("utf-8")]

    else:
        start_response("404 Not Found", headers)
        return [json.dumps({"error": "接口不存在"}).encode("utf-8")]


if __name__ == "__main__":
    port = 5000
    with make_server("", port, application) as httpd:
        print(f"前端服务已启动，端口: {port}")
        print(f"请打开 frontend/index.html 查看页面")
        httpd.serve_forever()
