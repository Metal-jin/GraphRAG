"""
tests/test_smoke.py
冒烟测试：验证框架核心（接口 + 注册表）能正常工作。

这是 A 负责的"一键自检"，只要这个测试通过，
说明地基没散架，其他组员可以在上面放心写代码。
"""
from core.interfaces import QAMethod, Answer
from core.registry import register, get_method, list_methods


@register("test_method")
class TestMethod(QAMethod):
    """用于自检的临时方法，验证接口约定是否成立。"""
    name = "test_method"

    def ask(self, question: str, top_k: int = 5) -> Answer:
        return Answer(
            answer_text=f"回答: {question}",
            method_name=self.name,
            evidence=[{"chunk": "测试证据"}],
            debug_info={"top_k": top_k},
            raw_context="测试上下文",
        )


def test_register_and_list():
    """验证方法能注册、能列出。"""
    assert "test_method" in list_methods(), "注册失败：方法没出现在列表里"


def test_get_and_call():
    """验证能按名字取方法、能调用、返回结构正确。"""
    m = get_method("test_method")
    a = m.ask("测试问题")

    assert isinstance(a, Answer), "返回值必须是 Answer 类型"
    assert a.answer_text == "回答: 测试问题", "answer_text 字段错误"
    assert a.method_name == "test_method", "method_name 字段错误"
    assert a.evidence == [{"chunk": "测试证据"}], "evidence 字段错误"
    assert a.debug_info["top_k"] == 5, "debug_info 字段错误"
    assert a.raw_context == "测试上下文", "raw_context 字段错误"


def test_duplicate_register_fails():
    """验证重复注册会报错（防止方法名冲突）。"""
    try:
        @register("test_method")
        class Dup(QAMethod):
            pass
        assert False, "重复注册应该抛异常"
    except ValueError:
        pass


def test_unknown_method_fails():
    """验证取不存在的名字会报错。"""
    try:
        get_method("不存在的名字")
        assert False, "取未知方法应该抛异常"
    except ValueError:
        pass


if __name__ == "__main__":
    test_register_and_list()
    test_get_and_call()
    test_duplicate_register_fails()
    test_unknown_method_fails()
    print("全部自检通过 ✓")
