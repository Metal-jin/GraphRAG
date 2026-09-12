"""阶段二任务 C：图谱分析算法。

本模块只处理已经读入内存的图，不负责连接 Neo4j。图结构约定为：
``{"nodes": [{"name": ...}], "edges": [{"source": ..., "target": ..., "type": ...}]}``。
默认把关系看成无向边，因为人物之间的“关系距离”通常不区分边的方向。
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Dict, List, Optional, Tuple

Graph = Dict[str, List[Dict[str, Any]]]


def _node_info(graph: Graph) -> Dict[str, Dict[str, Any]]:
    """建立“节点名 -> 节点属性”索引，后续函数都通过它快速查节点。"""
    result: Dict[str, Dict[str, Any]] = {}
    for node in graph.get("nodes", []):
        name = str(node.get("name", "")).strip()
        if name and name not in result:
            result[name] = dict(node)
    return result


def build_adjacency(graph: Graph, directed: bool = False) -> Dict[str, List[Tuple[str, Dict[str, Any]]]]:
    """把边列表转成邻接表；邻接表能让 BFS 和中心性计算更高效。"""
    names = set(_node_info(graph))
    adjacency: Dict[str, List[Tuple[str, Dict[str, Any]]]] = defaultdict(list)
    for edge in graph.get("edges", []):
        source = str(edge.get("source", "")).strip()
        target = str(edge.get("target", "")).strip()
        if source not in names or target not in names:
            continue  # 忽略指向不存在节点的脏数据。
        clean_edge = dict(edge)
        adjacency[source].append((target, clean_edge))
        if not directed and source != target:
            adjacency[target].append((source, clean_edge))
    for name in names:
        adjacency.setdefault(name, [])
    return dict(adjacency)


def degree_centrality(graph: Graph, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
    """按直接邻居数量计算度中心性，回答“谁的关系最广”。"""
    nodes = _node_info(graph)
    adjacency = build_adjacency(graph)
    denominator = max(len(nodes) - 1, 1)
    rows = []
    for name, info in nodes.items():
        degree = len({neighbor for neighbor, _ in adjacency.get(name, [])})
        rows.append({"name": name, "type": info.get("type", ""),
                     "era": info.get("era"), "degree": degree,
                     "centrality": round(degree / denominator, 6)})
    rows.sort(key=lambda row: (-row["degree"], row["name"]))
    return rows if top_k is None else rows[:max(top_k, 0)]


def pagerank(graph: Graph, damping: float = 0.85, max_iter: int = 100,
             tol: float = 1e-8, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
    """计算无向图 PageRank，返回按重要性降序排列的节点。"""
    nodes = _node_info(graph)
    names = list(nodes)
    if not names:
        return []
    adjacency = build_adjacency(graph)
    count = len(names)
    scores = {name: 1.0 / count for name in names}
    base = (1.0 - damping) / count
    for _ in range(max(max_iter, 1)):
        next_scores = {name: base for name in names}
        dangling = sum(scores[name] for name in names if not adjacency.get(name))
        for name in names:
            next_scores[name] += damping * dangling / count
        for source in names:
            neighbors = {neighbor for neighbor, _ in adjacency.get(source, [])}
            if neighbors:
                share = damping * scores[source] / len(neighbors)
                for target in neighbors:
                    next_scores[target] += share
        change = sum(abs(next_scores[name] - scores[name]) for name in names)
        scores = next_scores
        if change < tol:
            break
    rows = [{"name": name, "type": nodes[name].get("type", ""),
             "era": nodes[name].get("era"), "score": round(scores[name], 8)}
            for name in names]
    rows.sort(key=lambda row: (-row["score"], row["name"]))
    return rows if top_k is None else rows[:max(top_k, 0)]


page_rank = pagerank  # 兼容常见的 page_rank 拼写。


def shortest_path(graph: Graph, source: str, target: str,
                  max_hops: Optional[int] = None) -> Dict[str, Any]:
    """用 BFS 查找最短路径，并返回跳数、节点路径和关系边。"""
    source, target = str(source).strip(), str(target).strip()
    names = _node_info(graph)
    empty = {"source": source, "target": target, "distance": None,
             "path": [], "edges": []}
    if source not in names or target not in names:
        return empty
    if source == target:
        return {"source": source, "target": target, "distance": 0,
                "path": [source], "edges": []}
    adjacency = build_adjacency(graph)
    queue = deque([source])
    previous: Dict[str, Optional[str]] = {source: None}
    previous_edge: Dict[str, Dict[str, Any]] = {}
    distance = {source: 0}
    while queue:
        current = queue.popleft()
        if max_hops is not None and distance[current] >= max_hops:
            continue
        for neighbor, edge in adjacency.get(current, []):
            if neighbor in previous:
                continue
            previous[neighbor] = current
            previous_edge[neighbor] = edge
            distance[neighbor] = distance[current] + 1
            if neighbor == target:
                queue.clear()
                break
            queue.append(neighbor)
    if target not in previous:
        return empty
    path, edge_path = [], []
    current: Optional[str] = target
    while current is not None:
        path.append(current)
        if current in previous_edge:
            edge_path.append(previous_edge[current])
        current = previous[current]
    path.reverse(); edge_path.reverse()
    return {"source": source, "target": target, "distance": distance[target],
            "path": path, "edges": edge_path}


def relationship_distance(graph: Graph, source: str, target: str,
                          max_hops: Optional[int] = None) -> Optional[int]:
    """只返回两个节点之间的最短跳数。"""
    return shortest_path(graph, source, target, max_hops)["distance"]


def louvain_communities(graph: Graph, max_passes: int = 20) -> Dict[str, int]:
    """执行简化的 Louvain 局部移动，返回“节点名 -> 社区编号”。

    每个节点先单独成组，然后尝试移动到邻居所在社区；只有局部模块度增益
    为正才移动。社区编号只是本次运行的标签，不代表固定门派编号。
    """
    nodes = _node_info(graph)
    adjacency = build_adjacency(graph)
    communities = {name: index for index, name in enumerate(nodes)}
    neighbors = {name: {n for n, _ in adjacency.get(name, [])} for name in nodes}
    degrees = {name: len(neighbors[name]) for name in nodes}
    total_degree = sum(degrees.values())
    if total_degree == 0:
        return communities
    community_degree = {community: degrees[name] for name, community in communities.items()}
    for _ in range(max(max_passes, 1)):
        changed = False
        for node in nodes:
            old = communities[node]
            community_degree[old] -= degrees[node]
            old_internal = sum(communities[n] == old for n in neighbors[node])
            best, best_gain = old, 0.0
            candidates = {communities[n] for n in neighbors[node]}
            for candidate in sorted(candidates):
                internal = sum(communities[n] == candidate for n in neighbors[node])
                gain = ((internal - old_internal) / total_degree
                        - degrees[node] * (community_degree[candidate] - community_degree[old])
                        / (total_degree * total_degree))
                if gain > best_gain + 1e-12:
                    best, best_gain = candidate, gain
            communities[node] = best
            community_degree[best] = community_degree.get(best, 0) + degrees[node]
            changed = changed or best != old
        if not changed:
            break
    compact, result = {}, {}
    for name, community in communities.items():
        compact.setdefault(community, len(compact))
        result[name] = compact[community]
    return result


detect_communities = louvain_communities


def analyze_graph(graph: Graph, top_k: int = 10) -> Dict[str, Any]:
    """一次生成答辩需要的核心节点排名和社区分组结果。"""
    communities = louvain_communities(graph)
    groups: Dict[int, List[str]] = defaultdict(list)
    for name, community in communities.items():
        groups[community].append(name)
    for members in groups.values():
        members.sort()
    return {"degree_centrality": degree_centrality(graph, top_k=top_k),
            "pagerank": pagerank(graph, top_k=top_k),
            "communities": communities,
            "community_groups": dict(sorted(groups.items()))}


__all__ = ["build_adjacency", "degree_centrality", "pagerank", "page_rank",
           "shortest_path", "relationship_distance", "louvain_communities",
           "detect_communities", "analyze_graph"]
