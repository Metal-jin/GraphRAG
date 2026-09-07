"""methods 包：各种检索方法实现。

每个方法一个文件，实现 QAMethod 接口并用 @register 注册。
新增方法后，需要在本文件里 import 对应模块来触发注册。
"""

# 只要导入 src.methods，就会触发装饰器注册；评测和统一入口因此可以
# 通过 get_method("vector") / get_method("library_graphrag") 取得方法。
from .vector import VectorMethod
from .library_graphrag import LibraryGraphRAGMethod

__all__ = ["VectorMethod", "LibraryGraphRAGMethod"]
