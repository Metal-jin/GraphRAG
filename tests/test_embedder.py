"""向量工具测试。

这些测试不依赖网络、OpenAI 密钥或 Neo4j，因此任何组员 clone 项目后都能运行。
"""

from retrieve.vector_utils import Embedder, cosine_similarity, search_chunks


def test_fallback_embedding_is_deterministic_and_normalized():
    embedder = Embedder()
    first = embedder.embed("郭靖 江南七怪")
    second = embedder.embed("郭靖 江南七怪")
    assert first == second
    assert len(first) == 256
    assert abs(cosine_similarity(first, first) - 1.0) < 1e-9


def test_search_chunks_returns_sorted_top_k_with_score():
    chunks = [
        {"id": "a", "text": "郭靖的师父是江南七怪。"},
        {"id": "b", "text": "桃花岛是黄药师居住的地方。"},
    ]
    hits = search_chunks("郭靖的师父", chunks, top_k=1)
    assert len(hits) == 1
    assert hits[0]["id"] == "a"
    assert "score" in hits[0]
    # 工具不应把分数写回调用方的原始字典。
    assert "score" not in chunks[0]


def test_non_positive_top_k_returns_empty():
    assert search_chunks("问题", [{"text": "证据"}], top_k=0) == []
