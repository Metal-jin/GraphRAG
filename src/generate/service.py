from typing import List, Dict, Any
from core.registry import get_method, list_methods
from core.interfaces import Answer

# 导入 methods 包，触发各方法文件上的 @register 装饰器，否则注册表为空
import methods  # noqa: F401


def get_available_methods() -> List[str]:
    """
    获取所有已注册的检索方法名
    返回值：方法名字符串列表，直接给前端下拉框用
    """
    return list_methods()


def ask_question(question: str, method_name: str = "vector", top_k: int = 5) -> Dict[str, Any]:
    """
    统一问答入口
    :param question: 用户输入的问题字符串
    :param method_name: 检索方法名，默认 vector
    :param top_k: 召回证据数量，默认 5
    :return: 标准结果字典，字段与 Answer 完全对应；出错时包含 error 字段
    """
    try:
        # 从注册表获取方法实例
        method_instance = get_method(method_name)
        # 调用问答接口
        result: Answer = method_instance.ask(question, top_k=top_k)

        # 转为字典返回，保持字段和 Answer 完全一致
        return {
            "answer_text": result.answer_text,
            "method_name": result.method_name,
            "evidence": result.evidence,
            "debug_info": result.debug_info,
            "raw_context": result.raw_context
        }

    except ValueError as e:
        # 方法不存在等异常，返回统一格式的错误信息
        return {
            "error": str(e),
            "answer_text": "",
            "method_name": method_name,
            "evidence": [],
            "debug_info": {},
            "raw_context": ""
        }
