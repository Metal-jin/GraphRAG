"""
core/interfaces.py
统一接口定义：所有检索方法必须实现 QAMethod，返回统一的 Answer。

这是整个项目的"地基"。任何一个检索方法（vector / library_graphrag / master_chain）
都要遵守这里的约定，评测（E1）和前端（E2）都依赖这个统一结构。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass # 自动生成 __init__ 方法，方便创建实例
class Answer:
    """统一的问答结果结构。

    所有检索方法最终都必须返回这个结构，字段含义：

    - answer_text: 最终答案文本（给用户看的）
    - method_name: 用了哪个方法（前端显示用、评测记录用）
    - evidence:    用到的证据列表（文本块 / 子图 / 路径等，前端用来高亮）
    - debug_info:  调试信息（评测和可视化用，比如命中了哪些实体）
    - raw_context: 喂给 LLM 的原始上下文（评测复现用）
    """
    answer_text: str
    method_name: str
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    debug_info: Dict[str, Any] = field(default_factory=dict)
    raw_context: str = ""


class QAMethod(ABC): # 这个类是一个抽象类，不能直接实例化（不能 QAMethod()），只能被继承。
    """检索方法统一接口。

    任何新的检索方法都要这样做：
    1. 继承 QAMethod
    2. 设置 name（方法唯一名字）
    3. 实现 ask() 方法
    4. 用 @register(name) 注册（见 registry.py）

    例子：
        from core.registry import register

        @register("my_method")
        class MyMethod(QAMethod):
            name = "my_method"

            def ask(self, question: str, top_k: int = 5) -> Answer:
                ...
                return Answer(answer_text="...", method_name=self.name)
    """
    name: str = "base"

    @abstractmethod # 想要继承 QAMethod，必须实现这个方法，否则会报错
    def ask(self, question: str, top_k: int = 5) -> Answer:
        """输入问题，返回统一的 Answer。"""
        raise NotImplementedError
