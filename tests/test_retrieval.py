"""两个基线方法的接口和数据对接测试。"""

import pytest

from core.interfaces import Answer
from methods.library_graphrag import LibraryGraphRAGMethod
from methods.vector import VectorMethod


class FakeLoader:
    """模拟 B 的 data_loader，验证 C 不会自己猜数据库查询。"""

    def __init__(self):
        self.called_with = None

    def search_by_vector(self, question, top_k):
        self.called_with = (question, top_k)
        return [{"id": "from-loader", "text": "这是 B 返回的证据。", "score": 0.99}]


@pytest.mark.parametrize("method_class,method_name", [
    (VectorMethod, "vector"),
    (LibraryGraphRAGMethod, "library_graphrag"),
])
def test_baseline_returns_common_answer(method_class, method_name):
    answer = method_class(chunks=[{"text": "本地测试证据"}]).ask("测试问题", top_k=2)
    assert isinstance(answer, Answer)
    assert answer.method_name == method_name
    assert answer.evidence
    assert answer.raw_context == answer.answer_text


def test_library_baseline_delegates_to_loader_vector_search():
    loader = FakeLoader()
    answer = LibraryGraphRAGMethod(data_loader=loader).ask("问题", top_k=3)
    assert loader.called_with == ("问题", 3)
    assert answer.evidence[0]["id"] == "from-loader"


@pytest.mark.parametrize("method_class", [VectorMethod, LibraryGraphRAGMethod])
def test_empty_question_is_rejected(method_class):
    with pytest.raises(ValueError):
        method_class(chunks=[]).ask("   ")
