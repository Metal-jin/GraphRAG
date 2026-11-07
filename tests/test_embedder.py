"""向量工具测试（任务 03/04 的回归用例）。

关键点：测试必须**离线可复现**，不能因为 .env 配了远程嵌入就依赖网络，
也不能因为 PYTHONHASHSEED 不同而结果不同。
"""
import subprocess
import sys
from pathlib import Path

import pytest

from core import embedding
from retrieve.vector_utils import Embedder, cosine_similarity, search_chunks


def local_embedder():
    """强制本地哈希模式的嵌入器（不读 .env 的远程配置）。"""
    service = embedding.EmbeddingService(endpoint="", model="", token="")
    return Embedder(service=service)


def test_test_session_is_offline():
    """测试会话必须使用本地嵌入，绝不能因为 .env 配了远程服务就去调用它。"""
    from core.embedding import get_embedder
    service = get_embedder()
    assert service.uses_remote is False
    assert service.spec.kind == "local-hash"


def test_fallback_embedding_is_deterministic_and_normalized():
    encoder = local_embedder()
    first = encoder.embed("郭靖 江南七怪")
    second = encoder.embed("郭靖 江南七怪")
    assert first == second
    assert len(first) == 256
    assert abs(cosine_similarity(first, first) - 1.0) < 1e-9


def test_local_hash_is_stable_across_processes():
    """任务 03 回归：不同 PYTHONHASHSEED 下同一文本必须得到同一向量。"""
    script = (
        "import sys; sys.path.insert(0, 'src');"
        "from core.embedding import local_hash_embed;"
        "print(round(sum(local_hash_embed('郭靖的师父')), 10))"
    )
    values = []
    for seed in ("0", "12345"):
        completed = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True,
            env={"PYTHONHASHSEED": seed, "PYTHONPATH": "src",
                 "SYSTEMROOT": "C:/Windows"},
            cwd=str(Path(__file__).resolve().parents[1]))
        assert completed.returncode == 0, completed.stderr
        values.append(completed.stdout.strip())
    assert values[0] == values[1], f"不同哈希种子得到不同向量：{values}"


def test_search_chunks_returns_sorted_top_k_with_score():
    chunks = [
        {"id": "a", "text": "郭靖的师父是江南七怪。"},
        {"id": "b", "text": "桃花岛是黄药师居住的地方。"},
    ]
    hits = search_chunks("郭靖的师父", chunks, top_k=1, embedder=local_embedder())
    assert len(hits) == 1
    assert hits[0]["id"] == "a"
    assert "score" in hits[0]
    assert "score" not in chunks[0]  # 不污染调用方数据


def test_non_positive_top_k_returns_empty():
    assert search_chunks("问题", [{"text": "证据"}], top_k=0) == []


def test_embedding_spec_carries_identity():
    spec = local_embedder().spec
    assert spec.kind == "local-hash"
    assert spec.dimension == 256
    assert spec.fingerprint.startswith("local-hash")


def test_remote_failure_does_not_silently_mix_vectors(monkeypatch):
    """任务 04 回归：远程失败默认抛错，不回退到不兼容的本地向量。"""
    service = embedding.EmbeddingService(
        endpoint="http://127.0.0.1:9", model="fake-model", token="x",
        allow_local_fallback=False)

    def boom(texts):
        raise RuntimeError("network down")

    monkeypatch.setattr(service, "_remote_embed", boom)
    with pytest.raises(embedding.EmbeddingError):
        service.embed_query("郭靖")


def test_index_compatibility_check():
    spec = embedding.EmbeddingSpec("remote", "m", 1024)
    embedding.assert_index_compatible({"dimension": 1024, "fingerprint": spec.fingerprint}, spec)
    with pytest.raises(embedding.IndexCompatibilityError):
        embedding.assert_index_compatible({"dimension": 256}, spec)
