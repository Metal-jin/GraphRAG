# 项目交接文档（HANDOFF）

> 本文档是给接手本项目的新成员/新 agent 的完整上下文总结。
> 读完本文档，应能了解：项目是什么、做到哪了、还差什么、关键技术约定。

---

## 一、项目一句话概述

**金庸武侠知识图谱问答系统**：把金庸小说构建成**带时代维度的层次化知识图谱**，用"两个通用基线 + 三个领域检索策略"做问答，对比层次化知识与领域策略对武侠多跳推理的帮助。

- 课程：天津大学 2026 知识工程综合实践
- 仓库：https://github.com/Metal-jin/GraphRAG
- 技术栈：Python + Neo4j + LLM（DeepSeek）+ Flask/D3

---

## 二、项目定位（重要：整改后）

本项目**不是**"通用方法对比平台"（那是要避开的雷同方向），而是**垂直领域知识推理系统**。

**研究问题（三个）**：
1. **层次化 KG 的有效性**：引入"门派 → 人物 → 武功 → 时代"层次结构后，相比扁平三元组，能否提升跨代际多跳推理（如"郭靖的师父的师父是谁"）的准确率？
2. **领域检索策略的鲁棒性**：师徒链、门派聚合等领域专用策略，相比通用图检索，能否过滤跨书噪声？
3. **知识注入形式的适配性**：三元组 / 路径 / 子图摘要，哪种注入形式更利于 LLM 武侠推理？

**差异化核心**：卖点是"武侠领域知识推理"，不是"检索算法对比"。

---

## 三、技术架构

### 1. 本体（层次化 + 时代维度）

见 `docs/ontology.md`。

- **实体**（4 类，都带 `era` 属性）：人物 / 门派 / 武功 / 地点
- **时代 era**：射雕（南宋）/ 神雕（南宋末-元初）/ 倚天（元末明初）
- **层次结构**：门派 → 人物 → 武功
- **关系**（10 种）：
  - 人际：MASTER_OF（师徒）、SPOUSE_OF、PARENT_OF、SWORN_BROTHER_OF、ENEMY_OF
  - 层次：BELONGS_TO（所属门派）、MASTERS（精通武功）、FOUNDER_OF、LOCATED_IN
  - 演化：BRANCHED_FROM（门派演化）
- **武功传承**：不单独抽三元关系，靠"师徒 MASTER_OF + 精通 MASTERS"组合推导

### 2. 检索方法（5 个，统一 QAMethod 接口）

| 方法名 | 类型 | 负责人 | 状态 |
|---|---|---|---|
| `vector` | 基线（纯向量） | C | ✅ 完成 |
| `library_graphrag` | 基线（调库图检索） | C | ✅ 完成 |
| `master_chain` | 领域策略（师徒链） | D | ❌ 未写 |
| `sect_agg` | 领域策略（门派聚合） | D | ❌ 未写 |
| `art_lineage` | 领域策略（武功传承） | D | ❌ 未写 |

领域策略设计见 `docs/retrieval_strategies.md`（含每条策略的 Cypher 示意）。

### 3. 知识注入

三种形式，按问题类型选择：三元组列表 / 关系路径 / 子图摘要。

---

## 四、目录结构

```
src/
  core/      接口、方法注册表、配置（interfaces.py / registry.py / config.py）
  methods/   检索方法实现（vector / library_graphrag 已完成，master_chain 等待写）
  retrieve/  检索算法细节（vector_utils.py 已完成）
  ingest/    数据构建（corpus / build_kg / clean_graph / data_loader）
  generate/  统一问答入口（service.py）
  eval/      评测（questions.json / run_compare.py）
docs/        文档（ontology / retrieval_strategies / b_guide / b_phase1_report / evaluation_report）
frontend/    前端（index.html）
tests/       测试
scripts/     一键脚本（build_kg.ps1 / run_tests.ps1）
data/        语料（不进 git）
output/      评测输出
```

---

## 五、团队分工与当前进展

| 成员 | 职责 | 状态 |
|---|---|---|
| A+D（组长） | 架构 + 三个领域策略 | 架构✅ / 领域策略❌ |
| B | 数据 + 图谱构建 | ✅ 完成 |
| C | 两个基线 | ✅ 完成 |
| E1 | 评测 | ✅ 完成 |
| E2 | 前端 + 生成 | ✅ 完成 |

---

## 六、组员已完成成果（详细）

### B（数据构建）— 优秀
- `corpus.py`：章节+滑窗切块（600字/块，重叠80），1789 块
- `build_kg.py`：LLM 抽取（带 era）+ MERGE 入库 + 断点续跑
- `clean_graph.py`：图谱清洗（别名归并 + 噪声剔除）
- `data_loader.py`：`get_chunks` / `get_graph(era=)` / `search_by_vector` / `run_query(cypher)`（给 D 的通用 Cypher 入口）
- 数据规模：**1621 实体 / 2964 关系**，era 100% 射雕，10 种关系全覆盖
- 测试：test_kg_builder + test_clean_graph（41 用例，需 neo4j/openai 依赖）

### C（两个基线）— 良好
- `vector.py` + `library_graphrag.py`：正确实现 QAMethod 接口 + @register
- `vector_utils.py`：向量检索工具

### E1（评测）— 良好
- `questions.json`：50+ 问题，带 category/hop/difficulty/acceptable_answers
- `run_compare.py`：评测脚本，方法名已统一为 5 个方法

### E2（前端+生成）— 良好
- `service.py`：统一问答入口（get_method / list_methods）
- `index.html`：前端页面

---

## 七、待办事项（D 的核心任务）

**三个领域策略还没写**（这是当前最关键的缺口）：

1. `src/methods/master_chain.py` — 师徒链（沿 MASTER_OF 反向走多跳）
2. `src/methods/sect_agg.py` — 门派聚合（聚合门派下人物+武功）
3. `src/methods/art_lineage.py` — 武功传承（师徒+精通推导传承链）

设计依据：`docs/retrieval_strategies.md`（含 Cypher 示意）
数据接口：`src/ingest/data_loader.py` 的 `run_query(cypher)`

---

## 八、关键技术约定（必须遵守）

### 1. 统一接口
- 所有方法继承 `QAMethod`（`src/core/interfaces.py`）
- 用 `@register("名字")` 注册（`src/core/registry.py`）
- `ask()` 返回统一 `Answer`（字段：answer_text / method_name / evidence / debug_info / raw_context）

### 2. 导入约定
- 用 `from core.xxx import ...`（**不带 src 前缀**）
- `pytest.ini` 已配置 `pythonpath = src`
- 跑测试用 `python -m pytest`（不要直接 python xxx.py）

### 3. 方法名（已统一）
`vector` / `library_graphrag` / `master_chain` / `sect_agg` / `art_lineage`

### 4. 数据字段
- 实体带 `era` 属性（射雕/神雕/倚天）
- 关系方向：师徒/父母/所属/精通/创立/位于有方向；夫妻/结拜/仇敌双向

---

## 九、已知问题

1. **环境缺依赖**：当前 anaconda base 环境缺 `neo4j`、`openai`，需 `pip install -r requirements.txt`（B 的测试才能跑）。
2. **D 的领域策略未实现**：评测时这 3 个方法会显示 unavailable（脚本已兼容，不会崩）。
3. **E1 问题集覆盖多部小说**（射雕/神雕/笑傲/倚天），但 B 阶段一只做了射雕，部分问题暂无数据可答（阶段二扩充解决）。
4. **LLM 抽取固有噪声**：MASTERS 少量错配、MASTER_OF 少量方向反置（B 已诚实记录）。

---

## 十、下一步行动（按优先级）

1. **组长亲自验收**（跑测试、查数据、查接口）— 验收清单已给组长。
2. **D 写三个领域策略**（先 master_chain，最简单）。
3. **装依赖**，让全部测试通过。
4. **阶段二**：扩充多部小说（神雕/倚天），era 真正用于跨书过滤；跑五方法对比评测，出对比表。
