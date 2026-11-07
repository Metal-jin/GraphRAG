"""两个基线方法的接口与数据对接测试（任务 17 重写后的契约）。"""
import pytest

from core.interfaces import Answer
from methods.library_graphrag import LibraryGraphRAGMethod
from methods.vector import VectorMethod


class FakeLoader:
    """模拟数据加载器：验证方法通过统一接口取数据，而不是自己猜 SQL。"""

    def __init__(self):
        self.called_with = None

    def search_by_vector(self, question, top_k):
        self.called_with = (question, top_k)
        return [{"chunk_id": "c1", "text": "这是数据层返回的证据。", "score": 0.99}]


@pytest.mark.parametrize("method_class,method_name", [
    (VectorMethod, "vector"),
    (LibraryGraphRAGMethod, "library_graphrag"),
])
def test_baseline_returns_common_answer(method_class, method_name):
    answer = method_class(chunks=[{"text": "本地测试证据"}]).ask("测试问题", top_k=2)
    assert isinstance(answer, Answer)
    assert answer.method_name == method_name
    assert answer.evidence
    assert answer.debug_info.get("status") == "ok"


def test_vector_baseline_delegates_to_loader_vector_search():
    loader = FakeLoader()
    answer = VectorMethod(data_loader=loader).ask("问题", top_k=3)
    assert loader.called_with == ("问题", 3)
    assert answer.evidence[0]["legacy"]["chunk_id"] == "c1"


def test_library_baseline_uses_graph_expansion_when_db_available():
    """任务 17 回归：library_graphrag 必须真的做图扩展，而不是复制 vector。"""

    def fake_run(cypher, params):
        assert "MENTIONS" in cypher
        return [{"source": "洪七公", "type": "MASTER_OF", "target": "郭靖",
                 "chunk_ids": ["c1"]}]

    loader = FakeLoader()
    answer = LibraryGraphRAGMethod(data_loader=loader, run_query=fake_run)        .ask("郭靖的师父是谁", top_k=3)
    assert answer.debug_info["uses_graph"] is True
    assert answer.debug_info["expanded_relations"] == 1
    assert "洪七公" in answer.raw_context


def test_library_baseline_degrades_explicitly():
    def boom(cypher, params):
        raise RuntimeError("neo4j down")

    loader = FakeLoader()
    answer = LibraryGraphRAGMethod(data_loader=loader, run_query=boom)        .ask("郭靖的师父是谁", top_k=3)
    assert answer.debug_info["status"] == "degraded"
    assert "neo4j down" in answer.debug_info["degraded"]


@pytest.mark.parametrize("method_class", [VectorMethod, LibraryGraphRAGMethod])
def test_empty_question_is_rejected(method_class):
    with pytest.raises(ValueError):
        method_class(chunks=[]).ask("   ")
