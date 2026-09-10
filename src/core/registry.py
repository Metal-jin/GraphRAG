"""
core/registry.py
方法注册表：用装饰器把方法注册进来，统一管理和调用。

这样评测脚本、前端都只需要"按名字取方法"，不用关心具体是哪个类。
"""
from typing import Dict, Type

from .interfaces import QAMethod


_REGISTRY: Dict[str, Type[QAMethod]] = {} # 注册表，键是方法名，值是方法类


def register(name: str): # 注册方法装饰器
    """装饰器：把一个方法类注册到注册表。

    用法：
        @register("vector")
        class VectorMethod(QAMethod):
            ...
    """
    def decorator(cls: Type[QAMethod]) -> Type[QAMethod]: # 装饰器函数，返回一个方法类
        if name in _REGISTRY:
            raise ValueError(f"方法名 '{name}' 已存在，请换一个名字")
        _REGISTRY[name] = cls
        return cls
    return decorator


def get_method(name: str, **kwargs) -> QAMethod: # 获取方法实例函数
    """根据名字创建方法实例。

    例子：
        method = get_method("vector")
        answer = method.ask("郭靖的师父是谁？")
    """
    if name not in _REGISTRY:
        raise ValueError(
            f"未知方法: '{name}'，已注册的方法有: {list(_REGISTRY.keys())}"
        )
    return _REGISTRY[name](**kwargs) #从注册表拿到类（_REGISTRY[name]），然后用 (**kwargs) 实例化一个对象


def list_methods() -> list:
    """列出所有已注册的方法名。"""
    return list(_REGISTRY.keys())
