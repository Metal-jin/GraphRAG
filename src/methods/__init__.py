"""methods 包：各种检索方法实现。

每个方法一个文件，实现 QAMethod 接口并用 @register 注册。
新增方法后，需要在本文件里 import 对应模块来触发注册。
"""

# 只要导入 src.methods，就会触发装饰器注册；评测和统一入口因此可以
# 通过 get_method("vector") / get_method("library_graphrag") / get_method("master_chain")
# / get_method("sect_agg") / get_method("art_lineage") 取得方法。
from .vector import VectorMethod
from .library_graphrag import LibraryGraphRAGMethod
# 图谱方法会间接依赖 OpenAI/Neo4j。缺少这些可选服务时，仍允许本地算法
# 和跨书离线测试导入；依赖安装完整后，下面的导入会照常触发方法注册。
try:
    from .master_chain import MasterChainMethod
except ModuleNotFoundError as exc:
    if exc.name not in {"openai", "neo4j"}:
        raise
    MasterChainMethod = None
try:
    from .sect_agg import SectAggMethod
except ModuleNotFoundError as exc:
    if exc.name not in {"openai", "neo4j"}:
        raise
    SectAggMethod = None
try:
    from .art_lineage import ArtLineageMethod
except ModuleNotFoundError as exc:
    if exc.name not in {"openai", "neo4j"}:
        raise
    ArtLineageMethod = None
try:
    from .person_relation import PersonRelationMethod
except ModuleNotFoundError as exc:
    if exc.name not in {"openai", "neo4j"}:
        raise
    PersonRelationMethod = None
from .cross_novel import CrossNovelMethod  # 阶段二：跨书人物关联检索。

__all__ = [
    "VectorMethod",
    "LibraryGraphRAGMethod",
    "MasterChainMethod",
    "SectAggMethod",
    "ArtLineageMethod",
    "PersonRelationMethod",
    "CrossNovelMethod",
]
