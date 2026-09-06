# E1 评测说明

## 1. 问题集

`questions.json` 包含 50 道题，覆盖亲属、师徒、婚姻、门派、结拜、武功等关系；其中 10 道是显式两跳问题。每题包含：

- `answer_entities`：规范实体名，方便人工复核和后续图谱评测；
- `acceptable_answers`：允许的简称、外号或同义答案，自动评分命中其中任意一个即可；
- `relation`：问题期待的关系类型；
- `hop`：理论上的图谱跳数；
- `difficulty`：便于分组统计；
- `source_hint`：出自哪部作品，便于检查语料是否覆盖。

## 2. 指标定义

`run_compare.py` 当前实现三项不依赖外部服务的指标：

1. **准确率（Accuracy）**：成功返回的答案中，包含任意一个 `acceptable_answers` 的题目比例。
2. **关键实体召回率（Entity Recall）**：标准答案实体被召回的题数 / 成功返回题数。当前问题集每题只要求一个实体（个别题允许多个等价答案），因此它与准确率数值相同；未来增加“一题多个必须实体”时再扩展为实体级分母。
3. **可用率（Availability）**：成功返回 `Answer` 的题数 / 总题数。它把“方法没安装/运行失败”和“方法回答错误”区分开。
4. **平均延迟（Average Latency）**：每道成功回答从调用 `ask()` 到返回的毫秒数平均值。

实体命中率不是完整的事实正确率：例如回答里同时提到正确人物和错误人物，当前自动规则仍可能命中。因此答辩时应说明，最终报告还要抽查 `raw_context`、`evidence` 和关系方向；后续可以增加 LLM-as-a-judge 或严格的结构化答案解析。

## 3. 运行方式

在项目根目录执行：

```bash
python -m src.eval.run_compare
```

只测试已经存在的方法：

```bash
python -m src.eval.run_compare --methods vector library_graphrag
```

输出：

- `output/compare_table.md`：适合阅读和答辩展示的表格；
- `output/compare_results.json`：逐题原始结果，便于二次分析。

方法尚未合并时会在逐题结果中显示 `error`，不会中断其他方法的评测。方法全部合并后，不需要修改问题集或脚本即可重新运行。
