# 接口约定文档（INTERFACE.md）

> 本文件是全组的"对接依据"。任何人在写代码前，先读这里。
> 内容由 A 负责定义，E2 负责整理成文档。**改接口必须同步改这里。**

---

## 1. 检索方法统一接口：QAMethod

所有检索方法（vector / library_graphrag / tcpr）**必须**：
1. 继承 `QAMethod`（定义在 `src/core/interfaces.py`）
2. 设置 `name`（方法唯一名字）
3. 实现 `ask(question, top_k)` 方法
4. 用 `@register(name)` 注册（见 `src/core/registry.py`）

```python
from core.registry import register
from core.interfaces import QAMethod, Answer

@register("my_method")
class MyMethod(QAMethod):
    name = "my_method"

    def ask(self, question: str, top_k: int = 5) -> Answer:
        # ... 检索 + 生成 ...
        return Answer(answer_text="...", method_name=self.name)
```

## 2. 统一返回结构：Answer

所有方法的 `ask()` 都必须返回 `Answer`，字段如下：

| 字段 | 类型 | 含义 |
|---|---|---|
| `answer_text` | str | 最终答案文本 |
| `method_name` | str | 方法名（前端显示、评测记录用） |
| `evidence` | list | 用到的证据（文本块/子图/路径，前端高亮用） |
| `debug_info` | dict | 调试信息（命中了哪些实体等） |
| `raw_context` | str | 喂给 LLM 的原始上下文（评测复现用） |

## 3. 数据读取接口：data_loader

B 负责实现 `src/ingest/data_loader.py`，提供以下函数，C、D 都通过它读数据：

| 函数 | 返回 | 用途 |
|---|---|---|
| `get_chunks()` | list[dict] | 读所有文本块 |
| `get_graph()` | dict（含 nodes、edges） | 读实体关系图 |
| `search_by_vector(question, top_k)` | list[dict] | 按向量找相似文本块 |

> **返回格式由 B 和 C、D 提前约定，B 不要自己埋头写。**

## 4. 方法调用方式

任何地方（评测、前端、命令行）都统一这样调用：

```python
from core.registry import get_method

method = get_method("vector")       # 换成任意已注册的方法名
answer = method.ask("郭靖的师父是谁？")
print(answer.answer_text)
```

## 5. 新增方法的步骤

1. 在 `src/methods/` 下新建文件，实现 `QAMethod`
2. 用 `@register(name)` 注册
3. 在 `src/methods/__init__.py` 里 `import` 该模块，触发注册
4. 更新本文件
