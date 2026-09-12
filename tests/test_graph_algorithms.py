"""任务 C 图算法的离线测试，不需要 Neo4j 或 OpenAI。"""

from retrieve.graph_algorithms import (analyze_graph, degree_centrality,
                                       louvain_communities, pagerank,
                                       relationship_distance, shortest_path)


def sample_graph():
    return {
        "nodes": [
            {"name": "郭靖", "type": "人物", "era": "射雕英雄传"},
            {"name": "黄蓉", "type": "人物", "era": "射雕英雄传"},
            {"name": "杨过", "type": "人物", "era": "神雕侠侣"},
            {"name": "小龙女", "type": "人物", "era": "神雕侠侣"},
            {"name": "黄衫女子", "type": "人物", "era": "倚天屠龙记"},
        ],
        "edges": [
            {"source": "郭靖", "target": "黄蓉", "type": "SPOUSE_OF"},
            {"source": "郭靖", "target": "杨过", "type": "KNOWS"},
            {"source": "杨过", "target": "小龙女", "type": "SPOUSE_OF"},
            {"source": "小龙女", "target": "黄衫女子", "type": "INHERITS"},
        ],
    }


def test_shortest_path_and_distance_limit():
    graph = sample_graph()
    result = shortest_path(graph, "郭靖", "小龙女")
    assert result["distance"] == 2
    assert result["path"] == ["郭靖", "杨过", "小龙女"]
    assert relationship_distance(graph, "郭靖", "小龙女", max_hops=1) is None


def test_centrality_and_pagerank_are_ranked():
    graph = sample_graph()
    degree = degree_centrality(graph, top_k=2)
    scores = pagerank(graph)
    assert degree[0]["degree"] == max(row["degree"] for row in degree)
    assert scores[0]["score"] >= scores[-1]["score"]
    assert abs(sum(row["score"] for row in scores) - 1.0) < 1e-6


def test_communities_and_summary():
    graph = sample_graph()
    communities = louvain_communities(graph)
    assert set(communities) == {node["name"] for node in graph["nodes"]}
    summary = analyze_graph(graph, top_k=3)
    assert len(summary["degree_centrality"]) == 3
    assert len(summary["pagerank"]) == 3
    assert sum(len(x) for x in summary["community_groups"].values()) == 5
