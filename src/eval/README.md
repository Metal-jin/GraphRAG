# E1 评测说明（改造后）

## 1. 题集

| 文件 | 题数 | 说明 |
|---|---|---|
| `questions.json` | 54 | 阶段二分类评测集（重点：四类分项） |
| `questions_full.json` | 50 | 早期完整集（历史数据，供对照） |
| `questions_stage2.json` | 100 | 三本书综合集（射雕 + 神雕 + 倚天） |

每题包含 `id`、`question`、`answer_entities`、`acceptable_answers`、
`category`、`relation`、`hop`、`difficulty`、`source_hint`。

**重要**：`acceptable_answers` 是同一实体的多个别名；`answer_entities` 是必须答对的实体集合。
这两者语义不同，评测时不要混用。

## 2. 指标

| 指标 | 含义 | 说明 |
|---|---|---|
| `entity_string_hit` | 答案命中任一别名且**未被否定** | 辅助指标，不叫"事实准确率" |
| `exact_match` | `answer_entities` 全部命中 | 多实体题必须全对 |
| `entity_precision/recall/f1` | 实体级指标 | precision 为保守近似 |
| `path_completeness` | 证据路径是否**连通**并覆盖预期跳数 | 两条不相连的边不算完整路径 |
| `path_validity` | 边的关系类型与方向是否合法 | 基于本体校验 |
| `evidence_sufficiency` | 答案命中 × 证据覆盖预期关系 | "证据里有名字"不算充分 |

**否定识别**："答案不是洪七公"不计为命中（`is_negated`）。

**状态区分**：`ok` / `no_context` / `degraded` / `error`。
`degraded` 表示生成模型不可用、已退回检索原文。

## 3. 运行方式

```bash
# 方法对比（会调用 LLM 生成）
python -m src.eval.run_compare --methods vector master_chain person_relation

# 只用前 5 题快速验证（子集写到 output/）
python -m src.eval.run_compare --limit 5

# 自动路由整链路评测
python run_auto_eval.py --limit 20 --resume

# 注入形式结构对比（不调用 LLM）
python -m src.eval.injection_experiment
```

输出：

- `output/compare_table.md`：人读的对比表（汇总/分类别/分书目/分跳数/逐题）；
- `output/compare_results.json`：完整逐题结果（含证据、生成状态、指标）。

## 4. 注入形式对比实验

`injection_experiment.py` 现在**只用检索到的事实**构造三种编码（三元组/路径/子图摘要），
标准答案不参与构造，只报告结构指标（上下文长度、方向是否可见、关系标签是否可见、空事实率）。
`--demo` 模式会用标准答案构造，输出里明确标注 `mode=demo`，**不作为实验结论**。

## 5. 历史报告

`docs/evaluation_report.md` 保留早期模板与历史结论，已标注数据版本；
新实验请用上面的命令重新生成，不要直接引用旧数字。
