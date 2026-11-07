"""前端服务（任务 25 / 27 / 28 / 31 重写）。

改动：
- 并发：ThreadingMixIn + WSGIServer，慢 LLM 请求不会阻塞其他接口；
- 默认只监听回环地址，远程监听需显式 --host；
- 统一请求校验（JSON 对象、question 类型/长度、top_k 范围、方法名、body 大小）；
- 稳定的错误码与 HTTP 状态，数据库不可用不再伪装成"空结果"；
- /api/qa 返回完整信息：答案、状态、方法、意图、证据、子图、推理路径；
- 邻居扩展返回真实起终点与稳定边 ID；时代过滤在数据库侧完成。

启动：
    python run_frontend_server.py                 # 127.0.0.1:5000
    python run_frontend_server.py --port 8000
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
from socketserver import ThreadingMixIn
from urllib.parse import parse_qs
from wsgiref.simple_server import WSGIServer, make_server

# 把项目根目录与 src 加入路径（允许直接 python run_frontend_server.py）
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))

from core.query import MAX_TOP_K, normalize_top_k  # noqa: E402
from generate.service import (ask_auto, ask_question, health,  # noqa: E402
                              get_available_methods)
from ingest.data_loader import get_graph, run_query  # noqa: E402

logger = logging.getLogger("frontend")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")

MAX_BODY_BYTES = 64 * 1024
MAX_QUESTION_CHARS = 500

ERA_MAP = {"射雕英雄传": "射雕", "神雕侠侣": "神雕", "倚天屠龙记": "倚天"}
REL_CN = {"MASTER_OF": "师徒", "SPOUSE_OF": "夫妻", "PARENT_OF": "父母",
          "SWORN_BROTHER_OF": "结拜", "ENEMY_OF": "仇敌", "BELONGS_TO": "门派",
          "MASTERS": "精通", "FOUNDER_OF": "创立", "LOCATED_IN": "位置",
          "BRANCHED_FROM": "演化", "DESCENDANT_OF": "后裔"}

ENTITY_LABELS = ["人物", "门派", "武功", "地点"]


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


# ============ 工具 ============

def _rel_label(rel: str) -> str:
    return REL_CN.get(rel, rel)


def _edge_id(source: str, rel: str, target: str) -> str:
    return f"{source}|{rel}|{target}"


def _to_vis_format(nodes, edges):
    """转成 vis-network 格式；节点用稳定 id，边用稳定 id（避免重复添加）。"""
    vis_nodes, seen = [], set()
    for node in nodes:
        name = node.get("name")
        if not name or name in seen:
            continue
        seen.add(name)
        vis_nodes.append({"id": name, "label": name, "type": node.get("type") or "",
                          "era": node.get("era") or ""})
    vis_edges, seen_edges = [], set()
    for edge in edges:
        source, target = edge.get("source"), edge.get("target")
        rel = edge.get("type", "")
        if not source or not target:
            continue
        eid = _edge_id(source, rel, target)
        if eid in seen_edges:
            continue
        seen_edges.add(eid)
        vis_edges.append({"id": eid, "from": source, "to": target,
                          "label": _rel_label(rel), "rel": rel})
    return {"nodes": vis_nodes, "edges": vis_edges}


def _limit_nodes(graph, max_nodes: int = 40, max_edges: int = 80):
    nodes = graph.get("nodes", []) if isinstance(graph, dict) else []
    edges = graph.get("edges", []) if isinstance(graph, dict) else []
    if len(nodes) <= max_nodes and len(edges) <= max_edges:
        return {"nodes": nodes, "edges": edges}
    degree = {}
    for edge in edges:
        degree[edge.get("source")] = degree.get(edge.get("source"), 0) + 1
        degree[edge.get("target")] = degree.get(edge.get("target"), 0) + 1
    top = set(sorted(degree, key=lambda name: -degree[name])[:max_nodes])
    kept_nodes = [n for n in nodes if n.get("name") in top]
    kept_edges = [e for e in edges
                  if e.get("source") in top and e.get("target") in top]
    kept_edges.sort(key=lambda e: -(degree.get(e.get("source"), 0)
                                    + degree.get(e.get("target"), 0)))
    return {"nodes": kept_nodes, "edges": kept_edges[:max_edges]}


def _query_neighbors(name: str, limit: int = 30, era: str = ""):
    """1 跳邻居：保留真实方向（source -> target），可选按时代过滤。"""
    if not name:
        return {"nodes": [], "edges": []}
    try:
        rows = run_query(
            "MATCH (n {name: $name})-[r]-(m) "
            "WHERE type(r) <> 'MENTIONS' "
            "  AND any(l IN labels(n) WHERE l IN $labels) "
            "  AND any(l IN labels(m) WHERE l IN $labels) "
            "  AND ($era IS NULL OR $era IN coalesce(n.eras, [n.era]) "
            "                        OR $era IN coalesce(m.eras, [m.era])) "
            "RETURN startNode(r).name AS source, endNode(r).name AS target, "
            "       type(r) AS rel, "
            "       head([l IN labels(startNode(r)) WHERE l IN $labels]) AS source_type, "
            "       head([l IN labels(endNode(r)) WHERE l IN $labels]) AS target_type, "
            "       coalesce(r.chunk_ids, []) AS chunk_ids "
            "LIMIT $limit",
            {"name": name, "labels": ENTITY_LABELS, "limit": limit,
             "era": ERA_MAP.get(era, era) or None})
    except Exception as exc:
        raise ApiError(503, "data_unavailable", f"图数据库不可用：{exc}") from exc

    nodes, edges, seen_edges = {}, [], set()
    for row in rows:
        source, target = row["source"], row["target"]
        nodes.setdefault(source, {"id": source, "label": source,
                                  "type": row.get("source_type") or ""})
        nodes.setdefault(target, {"id": target, "label": target,
                                  "type": row.get("target_type") or ""})
        eid = _edge_id(source, row["rel"], target)
        if eid in seen_edges:
            continue
        seen_edges.add(eid)
        edges.append({"id": eid, "from": source, "to": target,
                      "label": _rel_label(row["rel"]), "rel": row["rel"],
                      "chunk_ids": row.get("chunk_ids") or []})
    return {"nodes": list(nodes.values()), "edges": edges}


def _extract_path(result):
    """从统一证据里提取推理路径（节点 + 有向边），支持多跳与分支。"""
    nodes, edges = [], []
    seen_nodes, seen_edges = set(), set()

    def add_node(name):
        if name and name not in seen_nodes:
            seen_nodes.add(name)
            nodes.append(name)

    for item in result.get("evidence") or []:
        for node in item.get("nodes") or []:
            add_node(node.get("name"))
        for edge in item.get("edges") or []:
            source, target = edge.get("source"), edge.get("target")
            add_node(source)
            add_node(target)
            key = (source, target, edge.get("type"))
            if key not in seen_edges:
                seen_edges.add(key)
                edges.append([source, target])
    if not nodes and result.get("seed_entity"):
        add_node(result["seed_entity"])
    return {"nodes": nodes, "edges": edges}


def _json_response(start_response, status: int, payload, extra_headers=None):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = [("Content-Type", "application/json; charset=utf-8"),
               ("Access-Control-Allow-Origin", "*"),
               ("Access-Control-Allow-Methods", "GET, POST, OPTIONS"),
               ("Access-Control-Allow-Headers", "Content-Type"),
               ("Content-Length", str(len(body)))]
    if extra_headers:
        headers.extend(extra_headers)
    start_response(f"{status} {'OK' if status < 400 else 'ERROR'}", headers)
    return [body]


def _read_json(environ) -> dict:
    try:
        length = int(environ.get("CONTENT_LENGTH") or 0)
    except ValueError:
        raise ApiError(400, "invalid_request", "Content-Length 非法")
    if length > MAX_BODY_BYTES:
        raise ApiError(413, "payload_too_large", f"请求体超过 {MAX_BODY_BYTES} 字节")
    raw = environ["wsgi.input"].read(length) if length else b""
    if not raw:
        return {}
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ApiError(400, "invalid_json", f"请求体不是合法 JSON：{exc}")
    if not isinstance(data, dict):
        raise ApiError(400, "invalid_request", "请求体必须是 JSON 对象")
    return data


def _validate_question(data: dict) -> str:
    question = data.get("question")
    if not isinstance(question, str):
        raise ApiError(400, "invalid_request", "question 必须是字符串")
    question = question.strip()
    if not question:
        raise ApiError(400, "invalid_request", "question 不能为空")
    if len(question) > MAX_QUESTION_CHARS:
        raise ApiError(400, "invalid_request",
                       f"question 过长（>{MAX_QUESTION_CHARS} 字符）")
    return question


def _validate_top_k(data: dict) -> int:
    if "top_k" not in data:
        return 5
    try:
        value = int(data["top_k"])
    except (TypeError, ValueError):
        raise ApiError(400, "invalid_request", "top_k 必须是整数")
    if value < 1 or value > MAX_TOP_K:
        raise ApiError(400, "invalid_request", f"top_k 必须在 1..{MAX_TOP_K}")
    return normalize_top_k(value)


# ============ 路由 ============

def application(environ, start_response):
    method = environ.get("REQUEST_METHOD", "GET")
    path = environ.get("PATH_INFO", "/")
    query = parse_qs(environ.get("QUERY_STRING", ""))

    if method == "OPTIONS":
        return _json_response(start_response, 200, {})

    try:
        # ---- 静态页面 ----
        if path in ("/", "/index.html") and method == "GET":
            html_path = os.path.join(ROOT, "frontend", "index.html")
            if not os.path.exists(html_path):
                raise ApiError(404, "not_found", "前端页面不存在")
            with open(html_path, encoding="utf-8") as handle:
                html = handle.read()
            start_response("200 OK", [("Content-Type", "text/html; charset=utf-8"),
                                      ("Access-Control-Allow-Origin", "*")])
            return [html.encode("utf-8")]

        # ---- 元信息 ----
        if path == "/api/methods" and method == "GET":
            return _json_response(start_response, 200,
                                  {"methods": get_available_methods()})

        if path == "/api/health" and method == "GET":
            return _json_response(start_response, 200, health())

        # ---- 手动问答 ----
        if path == "/api/ask" and method == "POST":
            data = _read_json(environ)
            question = _validate_question(data)
            top_k = _validate_top_k(data)
            method_name = data.get("method_name", "vector")
            if not isinstance(method_name, str) or method_name not in get_available_methods():
                raise ApiError(400, "invalid_method", f"未知方法：{method_name}")
            result = ask_question(question, method_name, top_k)
            status = 200 if result.get("status") not in ("invalid_request", "error") else 400
            return _json_response(start_response, status, result)

        # ---- 自动问答 ----
        if path == "/api/ask_auto" and method == "POST":
            data = _read_json(environ)
            question = _validate_question(data)
            top_k = _validate_top_k(data)
            result = ask_auto(question, top_k)
            status = 200 if result.get("status") not in ("invalid_request", "error") else 400
            return _json_response(start_response, status, result)

        # ---- 图谱问答（答案 + 子图 + 路径 + 来源）----
        if path == "/api/qa" and method == "POST":
            data = _read_json(environ)
            question = _validate_question(data)
            top_k = _validate_top_k(data)
            result = ask_auto(question, top_k)
            if result.get("status") == "invalid_request":
                raise ApiError(400, "invalid_request", result.get("error", "参数非法"))
            seed = result.get("seed_entity", "")
            era = data.get("era") if isinstance(data.get("era"), str) else ""
            path_payload = _extract_path(result)
            try:
                subgraph = (_query_neighbors(seed, era=era) if seed
                            else {"nodes": [], "edges": []})
            except ApiError as exc:
                subgraph = {"nodes": [], "edges": []}
                result["subgraph_error"] = exc.message
            existing = {node["id"] for node in subgraph["nodes"]}
            for name in path_payload["nodes"]:
                if name not in existing:
                    subgraph["nodes"].append({"id": name, "label": name, "type": "人物"})
                    existing.add(name)
            payload = {
                "answer": result.get("answer_text", ""),
                "status": result.get("status", ""),
                "method": result.get("method_name", ""),
                "intent": result.get("intent", ""),
                "injection": result.get("injection", ""),
                "reason": result.get("reason", ""),
                "generation": result.get("generation", {}),
                "subgraph": subgraph,
                "path": path_payload,
                "evidence": result.get("evidence") or [],
                "error": result.get("error", ""),
            }
            return _json_response(start_response, 200, payload)

        # ---- 邻居展开 ----
        if path == "/api/node/neighbor" and method == "GET":
            name = (query.get("nodeId") or [""])[0]
            if not name:
                raise ApiError(400, "invalid_request", "缺少 nodeId")
            era = (query.get("era") or [""])[0]
            return _json_response(start_response, 200, _query_neighbors(name, era=era))

        # ---- 按时代取图 ----
        if path == "/api/graph/byera" and method == "GET":
            era_full = (query.get("era") or [""])[0]
            era = ERA_MAP.get(era_full, era_full) or None
            try:
                graph = get_graph(era=era)
                graph = _limit_nodes(graph)
                payload = _to_vis_format(graph.get("nodes", []), graph.get("edges", []))
            except Exception as exc:
                raise ApiError(503, "data_unavailable", f"读取图谱失败：{exc}") from exc
            return _json_response(start_response, 200, payload)

        raise ApiError(404, "not_found", "接口不存在")

    except ApiError as exc:
        logger.warning("api error %s %s -> %s %s", method, path, exc.status, exc.message)
        return _json_response(start_response, exc.status,
                              {"error": {"code": exc.code, "message": exc.message}})
    except Exception as exc:  # noqa: BLE001 - 兜底，避免 500 页面泄露栈
        logger.exception("unhandled error %s %s", method, path)
        return _json_response(start_response, 500,
                              {"error": {"code": "internal_error",
                                         "message": f"{type(exc).__name__}: {exc}"}})


class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="金庸武侠知识图谱问答服务")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认仅回环）")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()

    problems = []
    try:
        from core.config import validate_config
        problems = validate_config(require_neo4j=True)
    except Exception as exc:  # noqa: BLE001
        problems = [f"配置读取失败：{exc}"]
    for problem in problems:
        logger.warning("配置问题：%s", problem)
    if problems:
        logger.warning("服务仍会启动，但相关功能可能不可用（见 /api/health）")

    with make_server(args.host, args.port, application,
                     server_class=ThreadingWSGIServer) as httpd:
        print(f"前端服务已启动：http://{args.host}:{args.port}/")
        print("健康检查：/api/health")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("已停止")
    return 0


if __name__ == "__main__":
    sys.exit(main())
