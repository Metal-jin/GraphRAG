# 接口约定文档（INTERFACE.md）

> 本文件是全组的"对接依据"。任何人在写代码前，先读这里。
> 内容由 A 负责定义。**改接口必须同步改这里。**

---

## 1. 检索方法统一接口：QAMethod

所有检索方法 **必须**：
1. 继承 `QAMethod`（定义在 `src/core/interfaces.py`）
2. 设置 `name`（方法唯一名字）
3. 实现 `ask(question, top_k)` 方法
4. 用 `@register(name)` 注册（见 `src/core/registry.py`）

**当前已注册的 5 个方法**：

| 方法名 | 类型 | 说明 |
|---|---|---|
| `vector` | 基线 | 纯向量检索 |
| `library_graphrag` | 基线 | 调库图检索 |
| `master_chain` | 领域策略 | 师徒链检索 |
| `sect_agg` | 领域策略 | 门派聚合检索 |
| `art_lineage` | 领域策略 | 武功传承检索 |

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
| `get_graph(era=None)` | dict（含 nodes、edges） | 读实体关系图（可传 era 过滤时代） |
| `search_by_vector(question, top_k)` | list[dict] | 按向量找相似文本块 |
| `search_by_text(query, top_k)` | list[dict] | 按关键词全文检索文本块 |
| `run_query(cypher, params)` | list[dict] | 执行任意 Cypher（D 的领域策略用） |

> **节点结构**：`{"id", "name", "type"（人物/门派/武功/地点）, "era", "location"}`
> **边结构**：`{"source", "target", "type"（MASTER_OF/...）}`
> **返回格式由 B 和 C、D 约定，B 不要自己埋头写。**

---

## 4. 阶段二新增：意图分类器（intent_classifier）

文件：`src/generate/intent_classifier.py`

**作用**：识别问题类型，自动路由到领域策略，用户无需手动选方法。

```python
from generate.intent_classifier import classify

intent = classify("郭靖的师父的师父是谁")
# intent.intent       -> "person"（语义意图）
# intent.method_name  -> "master_chain"（路由到的方法）
# intent.seed_entity  -> "郭靖"（识别的起始实体）
# intent.injection    -> "path"（注入形式）
# intent.reason       -> "命中人物实体「郭靖」且含师徒关系关键词"（解释）
```

**意图 → 路由 → 注入 映射关系**：

| 意图（intent） | 路由（method_name） | 注入形式（injection） |
|---|---|---|
| `person`（人物关系） | `master_chain` | `path`（关系路径） |
| `sect`（门派聚合） | `sect_agg` | `subgraph`（子图摘要） |
| `art`（武功传承） | `art_lineage` | `path`（关系路径） |
| `general`（通用兜底） | `vector` | `text`（原文） |

---

## 5. 阶段二新增：知识注入层（injection）

文件：`src/generate/injection.py`

**作用**：把检索到的证据按意图转成最适合 LLM 的注入形式。

```python
from generate.injection import build_context

context = build_context(method_name, evidence, raw_context)
# master_chain  -> 关系路径："郭靖（第0代）\n第1代师父：洪七公、马钰…"
# sect_agg      -> 子图摘要："郭靖（会：降龙十八掌）\n黄蓉（会：打狗棒法）"
# art_lineage   -> 关系路径："洪七公 --传承--> 郭靖"
# vector/其他   -> 原文（直接用 raw_context）
```

---

## 6. 阶段二新增：全自动问答入口 ask_auto

文件：`src/generate/service.py`

**作用**：`意图识别 → 路由 → 注入 → 生成` 全自动链路，是阶段二的核心入口。

```python
from src.generate.service import ask_auto

result = ask_auto("丐帮有哪些绝学")
```

**返回字段**（在原 Answer 基础上扩展）：

| 字段 | 类型 | 含义 |
|---|---|---|
| `answer_text` | str | LLM 生成的最终答案 |
| `method_name` | str | 实际路由到的检索方法名 |
| `intent` | str | 识别出的语义意图（person/sect/art/general） |
| `seed_entity` | str | 识别的起始实体（可能为空） |
| `injection` | str | 使用的注入形式（path/subgraph/text） |
| `reason` | str | 分类依据（可解释性、调试用） |
| `evidence` | list | 检索到的证据 |
| `debug_info` | dict | 调试信息 |
| `raw_context` | str | **注入后**喂给 LLM 的上下文（注意：不是原始 raw_context） |

> 旧的 `ask_question(question, method_name, top_k)` 保留，向后兼容（手动指定方法）。

---

## 7. 方法调用方式

```python
from core.registry import get_method

# 方式一：手动指定方法（阶段一用法，保留）
method = get_method("master_chain")
answer = method.ask("郭靖的师父是谁？")

# 方式二：全自动（阶段二推荐，用户无需选方法）
from src.generate.service import ask_auto
result = ask_auto("郭靖的师父是谁？")
```

## 8. 新增方法的步骤

1. 在 `src/methods/` 下新建文件，实现 `QAMethod`
2. 用 `@register(name)` 注册
3. 在 `src/methods/__init__.py` 里 `import` 该模块，触发注册
4. 更新本文件
