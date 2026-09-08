# GraphRAG 方法对比评测结果

> 本表由 `src/eval/run_compare.py` 自动生成。准确率和关键实体召回率是当前阶段的自动指标，最终结论仍需结合证据和人工复核。

- 生成时间：`2026-09-08T18:59:52+08:00`
- 评测问题数：`50`
- 统一 `top_k`：`5`
- 自动判分：回答文本命中该题 `acceptable_answers` 中任一实体或别名即记为命中。

## 汇总

| 方法 | 可用题数 | 可用率 | 实体命中数 | 准确率 | 关键实体召回率 | 平均耗时(ms) |
|---|---:|---:|---:|---:|---:|---:|
| art_lineage | 50/50 | 100.00% | 1 | 2.00% | 2.00% | 191.63 |
| library_graphrag | 50/50 | 100.00% | 6 | 12.00% | 12.00% | 762.95 |
| master_chain | 50/50 | 100.00% | 32 | 64.00% | 64.00% | 1131.92 |
| sect_agg | 50/50 | 100.00% | 3 | 6.00% | 6.00% | 221.43 |
| vector | 50/50 | 100.00% | 6 | 12.00% | 12.00% | 761.51 |

## 指标解释

- **可用率**：方法成功返回 `Answer` 的题数 / 总题数。
- **准确率**：自动判分成功题数 / 方法成功返回题数；方法不可用不会被误算成回答错误。
- **关键实体召回率**：标准实体被召回的题数 / 方法成功返回题数；当前每题只要求一个实体，因此数值与准确率相同。
- **平均耗时**：从调用 `ask()` 到返回或抛出异常的单题平均耗时。
- 本阶段未自动判“关系方向、证据完整性、答案幻觉”；这些应在有真实图谱和 LLM 输出后人工复核或继续扩展指标。

## 逐题结果

| 题号 | 方法 | 状态 | 实体命中 | 回答/错误 |
|---|---|---|---|---|
| q001 | vector | ok | 否 | 根据现有资料无法回答。 |
| q002 | vector | ok | 否 | 根据现有资料无法回答。 |
| q003 | vector | ok | 是 | 黄药师 |
| q004 | vector | ok | 否 | 根据现有资料无法回答。 |
| q005 | vector | ok | 否 | 根据现有资料无法回答。 |
| q006 | vector | ok | 是 | 黄药师是黄蓉的父亲，但资料中未提及黄药师有女儿。根据现有资料无法回答。 |
| q007 | vector | ok | 否 | 根据现有资料无法回答。 |
| q008 | vector | ok | 否 | 根据现有资料无法回答。 |
| q009 | vector | ok | 否 | 根据现有资料无法回答。 |
| q010 | vector | ok | 否 | 根据现有资料无法回答。 |
| q011 | vector | ok | 否 | 根据现有资料无法回答。 |
| q012 | vector | ok | 是 | 郭靖向洪七公学习降龙十八掌。 |
| q013 | vector | ok | 否 | 根据现有资料无法回答。 |
| q014 | vector | ok | 否 | 根据现有资料无法回答。 |
| q015 | vector | ok | 否 | 根据现有资料无法回答。 |
| q016 | vector | ok | 否 | 根据现有资料无法回答。 |
| q017 | vector | ok | 否 | 根据现有资料无法回答。 |
| q018 | vector | ok | 否 | 根据现有资料无法回答。 |
| q019 | vector | ok | 否 | 根据现有资料无法回答。 |
| q020 | vector | ok | 否 | 根据现有资料无法回答。 |
| q021 | vector | ok | 否 | 根据现有资料无法回答。 |
| q022 | vector | ok | 否 | 根据现有资料无法回答。 |
| q023 | vector | ok | 否 | 根据现有资料无法回答。 |
| q024 | vector | ok | 是 | 柯镇恶是“江南七怪”的成员。 |
| q025 | vector | ok | 否 | 根据现有资料无法回答。 |
| q026 | vector | ok | 否 | 根据现有资料无法回答。 |
| q027 | vector | ok | 否 | 根据现有资料无法回答。 |
| q028 | vector | ok | 是 | 蛤蟆功 |
| q029 | vector | ok | 否 | 根据现有资料无法回答。 |
| q030 | vector | ok | 否 | 根据现有资料无法回答。 |
| q031 | vector | ok | 否 | 根据现有资料无法回答。 |
| q032 | vector | ok | 否 | 根据现有资料无法回答。 |
| q033 | vector | ok | 否 | 根据现有资料无法回答。 |
| q034 | vector | ok | 否 | 根据现有资料无法回答。 |
| q035 | vector | ok | 否 | 根据现有资料无法回答。 |
| q036 | vector | ok | 否 | 根据现有资料无法回答。 |
| q037 | vector | ok | 否 | 根据现有资料无法回答。 |
| q038 | vector | ok | 否 | 根据现有资料无法回答。 |
| q039 | vector | ok | 是 | 柯镇恶是“江南七怪”的成员。 |
| q040 | vector | ok | 否 | 根据现有资料无法回答。 |
| q041 | vector | ok | 否 | 根据现有资料无法回答。 |
| q042 | vector | ok | 否 | 根据现有资料无法回答。 |
| q043 | vector | ok | 否 | 根据现有资料无法回答。 |
| q044 | vector | ok | 否 | 根据现有资料无法回答。 |
| q045 | vector | ok | 否 | 根据现有资料无法回答。 |
| q046 | vector | ok | 否 | 根据现有资料无法回答。 |
| q047 | vector | ok | 否 | 根据现有资料无法回答。 |
| q048 | vector | ok | 否 | 根据现有资料无法回答。 |
| q049 | vector | ok | 否 | 根据现有资料无法回答。 |
| q050 | vector | ok | 否 | 根据现有资料无法回答。 |
| q001 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q002 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q003 | library_graphrag | ok | 是 | 黄药师 |
| q004 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q005 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q006 | library_graphrag | ok | 是 | 黄药师是黄蓉的父亲，但资料中未提及黄药师有女儿。根据现有资料无法回答。 |
| q007 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q008 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q009 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q010 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q011 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q012 | library_graphrag | ok | 是 | 郭靖向洪七公学习降龙十八掌。 |
| q013 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q014 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q015 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q016 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q017 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q018 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q019 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q020 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q021 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q022 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q023 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q024 | library_graphrag | ok | 是 | 柯镇恶是“江南七怪”的成员。 |
| q025 | library_graphrag | ok | 是 | 马钰属于全真教。 |
| q026 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q027 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q028 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q029 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q030 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q031 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q032 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q033 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q034 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q035 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q036 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q037 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q038 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q039 | library_graphrag | ok | 是 | 柯镇恶是“江南七怪”的成员。 |
| q040 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q041 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q042 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q043 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q044 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q045 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q046 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q047 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q048 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q049 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q050 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q001 | master_chain | ok | 否 | 根据现有资料无法回答。 |
| q002 | master_chain | ok | 否 | 根据现有资料无法回答。 |
| q003 | master_chain | ok | 是 | 黄药师 |
| q004 | master_chain | ok | 是 | 包惜弱 |
| q005 | master_chain | ok | 是 | 欧阳锋 |
| q006 | master_chain | ok | 是 | 黄蓉 |
| q007 | master_chain | ok | 是 | 包惜弱 |
| q008 | master_chain | ok | 否 | 根据现有资料无法回答。 |
| q009 | master_chain | ok | 是 | 黄蓉 |
| q010 | master_chain | ok | 是 | 郭靖 |
| q011 | master_chain | ok | 否 | 根据现有资料无法回答。 |
| q012 | master_chain | ok | 是 | 洪七公 |
| q013 | master_chain | ok | 是 | 丘处机 |
| q014 | master_chain | ok | 是 | 黄药师 |
| q015 | master_chain | ok | 是 | 周伯通 |
| q016 | master_chain | ok | 是 | 黄药师、洪七公 |
| q017 | master_chain | ok | 是 | 马钰 |
| q018 | master_chain | ok | 是 | 丐帮。 |
| q019 | master_chain | ok | 是 | 桃花岛。 |
| q020 | master_chain | ok | 否 | 根据现有资料无法回答。 |
| q021 | master_chain | ok | 否 | 根据现有资料无法回答。 |
| q022 | master_chain | ok | 否 | 根据现有资料无法回答。 |
| q023 | master_chain | ok | 是 | 铁掌帮帮主。 |
| q024 | master_chain | ok | 是 | 柯镇恶是江南七怪的成员。 |
| q025 | master_chain | ok | 否 | 根据现有资料无法回答。 |
| q026 | master_chain | ok | 否 | 根据现有资料无法回答。 |
| q027 | master_chain | ok | 否 | 根据现有资料无法回答。 |
| q028 | master_chain | ok | 否 | 根据现有资料无法回答。 |
| q029 | master_chain | ok | 是 | 一阳指 |
| q030 | master_chain | ok | 否 | 根据现有资料无法回答。 |
| q031 | master_chain | ok | 否 | 根据现有资料无法回答。 |
| q032 | master_chain | ok | 否 | 根据现有资料无法回答。 |
| q033 | master_chain | ok | 是 | 拖雷 |
| q034 | master_chain | ok | 是 | 欧阳锋 |
| q035 | master_chain | ok | 是 | 黄药师 |
| q036 | master_chain | ok | 是 | 陈玄风、梅超风 |
| q037 | master_chain | ok | 是 | 丐帮。 |
| q038 | master_chain | ok | 是 | 全真教 |
| q039 | master_chain | ok | 是 | 江南七怪 |
| q040 | master_chain | ok | 否 | 根据现有资料无法回答。 |
| q041 | master_chain | ok | 否 | 根据现有资料无法回答。 |
| q042 | master_chain | ok | 是 | 老顽童 |
| q043 | master_chain | ok | 是 | 郭靖 |
| q044 | master_chain | ok | 否 | 黄药师 |
| q045 | master_chain | ok | 否 | 根据现有资料无法回答。 |
| q046 | master_chain | ok | 是 | 黄蓉 |
| q047 | master_chain | ok | 是 | 成吉思汗 |
| q048 | master_chain | ok | 是 | 黄蓉 |
| q049 | master_chain | ok | 是 | 王重阳 |
| q050 | master_chain | ok | 是 | 打狗棒法 |
| q001 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q002 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q003 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q004 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q005 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q006 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q007 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q008 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q009 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q010 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q011 | sect_agg | ok | 否 | 根据现有资料无法回答。 |
| q012 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q013 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q014 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q015 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q016 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q017 | sect_agg | ok | 否 | 根据现有资料无法回答。 |
| q018 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q019 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q020 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q021 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q022 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q023 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q024 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q025 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q026 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q027 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q028 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q029 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q030 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q031 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q032 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q033 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q034 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q035 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q036 | sect_agg | ok | 是 | 陈玄风 |
| q037 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q038 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q039 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q040 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q041 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q042 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q043 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q044 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q045 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q046 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q047 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q048 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q049 | sect_agg | ok | 是 | 王重阳 |
| q050 | sect_agg | ok | 是 | 打狗棒法 |
| q001 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q002 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q003 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q004 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q005 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q006 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q007 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q008 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q009 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q010 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q011 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q012 | art_lineage | ok | 是 | 洪七公 |
| q013 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q014 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q015 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q016 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q017 | art_lineage | ok | 否 | 根据现有资料无法回答。 |
| q018 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q019 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q020 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q021 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q022 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q023 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q024 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q025 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q026 | art_lineage | ok | 否 | 根据现有资料无法回答。 |
| q027 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q028 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q029 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q030 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q031 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q032 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q033 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q034 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q035 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q036 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q037 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q038 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q039 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q040 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q041 | art_lineage | ok | 否 | 根据现有资料无法回答。 |
| q042 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q043 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q044 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q045 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q046 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q047 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q048 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q049 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q050 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
