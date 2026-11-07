# GraphRAG 方法对比评测结果

> 由 src/eval/run_compare.py 自动生成。entity_string_hit 只是**辅助指标**，不等于事实准确率；结论需结合证据与人工复核。

- 生成时间：2026-11-07T16:41:31+08:00
- 题集：src\eval\questions.json（54 题）
- 统一 top_k：5
- 判分：答案文本命中 acceptable_answers 且非否定表述记为命中；exact_match 要求 answer_entities 全部命中。

## 汇总（端到端 vs 条件）

| 方法 | 题数 | 成功 | 降级 | 异常 | 可用率 | 命中 | 端到端准确率 | 条件准确率 | 平均耗时(ms) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| art_lineage | 54 | 54 | 0 | 0 | 100.00% | 1 | 1.85% | 1.85% | 103.98 |
| library_graphrag | 54 | 54 | 0 | 0 | 100.00% | 41 | 75.93% | 75.93% | 721.91 |
| master_chain | 54 | 54 | 0 | 0 | 100.00% | 9 | 16.67% | 16.67% | 535.05 |
| person_relation | 54 | 54 | 0 | 0 | 100.00% | 22 | 40.74% | 40.74% | 426.31 |
| sect_agg | 54 | 54 | 0 | 0 | 100.00% | 2 | 3.70% | 3.70% | 66.52 |
| vector | 54 | 54 | 0 | 0 | 100.00% | 40 | 74.07% | 74.07% | 900.78 |

## 分类别结果

| 方法 | category | 题数 | 准确率 | 完全匹配 | 路径完整性 | 证据充分性 |
|---|---|---:|---:|---:|---:|---:|
| art_lineage | 人物 | 26 | 0.00% | 0.00% | 3.85% | 0.96% |
| art_lineage | 武功 | 11 | 9.09% | 9.09% | 36.36% | 25.00% |
| art_lineage | 综合 | 4 | 0.00% | 0.00% | 0.00% | 0.00% |
| art_lineage | 门派 | 13 | 0.00% | 0.00% | 0.00% | 0.00% |
| library_graphrag | 人物 | 26 | 73.08% | 69.23% | 84.62% | 73.08% |
| library_graphrag | 武功 | 11 | 90.91% | 90.91% | 86.36% | 79.55% |
| library_graphrag | 综合 | 4 | 50.00% | 50.00% | 50.00% | 50.00% |
| library_graphrag | 门派 | 13 | 76.92% | 76.92% | 80.77% | 76.92% |
| master_chain | 人物 | 26 | 11.54% | 11.54% | 73.08% | 34.62% |
| master_chain | 武功 | 11 | 0.00% | 0.00% | 63.64% | 22.73% |
| master_chain | 综合 | 4 | 50.00% | 50.00% | 50.00% | 56.25% |
| master_chain | 门派 | 13 | 30.77% | 30.77% | 50.00% | 40.38% |
| person_relation | 人物 | 26 | 76.92% | 73.08% | 67.31% | 76.92% |
| person_relation | 武功 | 11 | 0.00% | 0.00% | 4.55% | 4.55% |
| person_relation | 综合 | 4 | 25.00% | 25.00% | 37.50% | 37.50% |
| person_relation | 门派 | 13 | 7.69% | 7.69% | 15.38% | 19.23% |
| sect_agg | 人物 | 26 | 3.85% | 3.85% | 7.69% | 3.85% |
| sect_agg | 武功 | 11 | 0.00% | 0.00% | 4.55% | 4.55% |
| sect_agg | 综合 | 4 | 0.00% | 0.00% | 0.00% | 0.00% |
| sect_agg | 门派 | 13 | 7.69% | 7.69% | 11.54% | 11.54% |
| vector | 人物 | 26 | 69.23% | 65.38% | 0.00% | 34.62% |
| vector | 武功 | 11 | 90.91% | 90.91% | 0.00% | 45.45% |
| vector | 综合 | 4 | 50.00% | 50.00% | 0.00% | 25.00% |
| vector | 门派 | 13 | 76.92% | 76.92% | 0.00% | 38.46% |

## 分书目结果

| 方法 | book | 题数 | 准确率 | 完全匹配 | 路径完整性 | 证据充分性 |
|---|---|---:|---:|---:|---:|---:|
| art_lineage | 射雕英雄传 | 54 | 1.85% | 1.85% | 9.26% | 5.56% |
| library_graphrag | 射雕英雄传 | 54 | 75.93% | 74.07% | 81.48% | 73.61% |
| master_chain | 射雕英雄传 | 54 | 16.67% | 16.67% | 63.89% | 35.19% |
| person_relation | 射雕英雄传 | 54 | 40.74% | 38.89% | 39.81% | 45.37% |
| sect_agg | 射雕英雄传 | 54 | 3.70% | 3.70% | 7.41% | 5.56% |
| vector | 射雕英雄传 | 54 | 74.07% | 72.22% | 0.00% | 37.04% |

## 分跳数结果

| 方法 | hop | 题数 | 准确率 | 完全匹配 | 路径完整性 | 证据充分性 |
|---|---|---:|---:|---:|---:|---:|
| art_lineage | 1 | 34 | 2.94% | 2.94% | 11.76% | 5.88% |
| art_lineage | 2 | 20 | 0.00% | 0.00% | 5.00% | 5.00% |
| library_graphrag | 1 | 34 | 82.35% | 82.35% | 100.00% | 77.21% |
| library_graphrag | 2 | 20 | 65.00% | 60.00% | 50.00% | 67.50% |
| master_chain | 1 | 34 | 14.71% | 14.71% | 76.47% | 30.15% |
| master_chain | 2 | 20 | 20.00% | 20.00% | 42.50% | 43.75% |
| person_relation | 1 | 34 | 41.18% | 41.18% | 41.18% | 41.18% |
| person_relation | 2 | 20 | 40.00% | 35.00% | 37.50% | 52.50% |
| sect_agg | 1 | 34 | 5.88% | 5.88% | 8.82% | 5.88% |
| sect_agg | 2 | 20 | 0.00% | 0.00% | 5.00% | 5.00% |
| vector | 1 | 34 | 79.41% | 79.41% | 0.00% | 39.71% |
| vector | 2 | 20 | 65.00% | 60.00% | 0.00% | 32.50% |

## 指标解释

- **端到端准确率**：命中题数 / 全部题数（异常与降级也算未答对）。
- **条件准确率**：命中题数 / 成功返回题数。
- **完全匹配（exact_match）**：answer_entities 全部命中才算 1。
- **路径完整性**：证据路径必须**连通**且覆盖预期跳数，不连通的边不得分。
- **证据充分性**：答案命中 × 证据覆盖预期关系类型。
- **否定表述**（如「不是洪七公」）不计为命中。

## 逐题结果

| 题号 | 方法 | 状态 | 命中 | 注入 | 生成状态 | 回答/错误 |
|---|---|---|---|---|---|---|
| q001 | vector | ok | 否 | text | ok | 根据现有资料无法回答。 |
| q002 | vector | ok | 是 | text | ok | 李萍 |
| q003 | vector | ok | 是 | text | ok | 黄药师 |
| q004 | vector | ok | 是 | text | ok | 包惜弱 |
| q005 | vector | ok | 是 | text | ok | 欧阳锋 |
| q006 | vector | ok | 是 | text | ok | 黄蓉 |
| q007 | vector | ok | 是 | text | ok | 包惜弱 |
| q008 | vector | ok | 否 | text | ok | 根据现有资料无法回答。 |
| q009 | vector | ok | 是 | text | ok | 黄蓉 |
| q010 | vector | ok | 是 | text | ok | 郭靖 |
| q011 | vector | ok | 否 | text | ok | 根据现有资料无法回答。 |
| q012 | vector | ok | 是 | text | ok | 洪七公。 |
| q013 | vector | ok | 是 | text | ok | 丘处机 |
| q014 | vector | ok | 是 | text | ok | 黄药师 |
| q015 | vector | ok | 否 | text | ok | 根据现有资料无法回答。 |
| q016 | vector | ok | 否 | text | ok | 黄药师 |
| q017 | vector | ok | 是 | text | ok | 马钰 |
| q018 | vector | ok | 是 | text | ok | 丐帮 |
| q019 | vector | ok | 是 | text | ok | 桃花岛。 |
| q020 | vector | ok | 是 | text | ok | 全真教 |
| q021 | vector | ok | 否 | text | ok | 西域 |
| q022 | vector | ok | 否 | text | ok | 段氏 |
| q023 | vector | ok | 是 | text | ok | 铁掌帮。 |
| q024 | vector | ok | 是 | text | ok | 江南七怪 |
| q025 | vector | ok | 是 | text | ok | 全真教 |
| q026 | vector | ok | 是 | text | ok | 降龙十八掌 |
| q027 | vector | ok | 是 | text | ok | 打狗棒法 |
| q028 | vector | ok | 是 | text | ok | 蛤蟆功 |
| q029 | vector | ok | 是 | text | ok | 一阳指 |
| q030 | vector | ok | 是 | text | ok | 空明拳、双手互搏。 |
| q031 | vector | ok | 是 | text | ok | 弹指神通 |
| q032 | vector | ok | 是 | text | ok | 九阴白骨爪 |
| q033 | vector | ok | 是 | text | ok | 拖雷 |
| q034 | vector | ok | 是 | text | ok | 欧阳锋 |
| q035 | vector | ok | 否 | text | ok | 根据现有资料无法回答。 |
| q036 | vector | ok | 否 | text | ok | 根据现有资料无法回答。 |
| q037 | vector | ok | 是 | text | ok | 丐帮 |
| q038 | vector | ok | 是 | text | ok | 全真教 |
| q039 | vector | ok | 是 | text | ok | 江南七怪 |
| q040 | vector | ok | 否 | text | ok | 降龙十八掌 |
| q041 | vector | ok | 是 | text | ok | 降龙十八掌 |
| q042 | vector | ok | 是 | text | ok | 老顽童 |
| q043 | vector | ok | 是 | text | ok | 郭靖 |
| q044 | vector | ok | 否 | text | ok | 根据现有资料无法回答。 |
| q045 | vector | ok | 否 | text | ok | 根据现有资料无法回答。 |
| q046 | vector | ok | 是 | text | ok | 黄蓉。 |
| q047 | vector | ok | 是 | text | ok | 铁木真 |
| q048 | vector | ok | 是 | text | ok | 黄蓉 |
| q049 | vector | ok | 是 | text | ok | 王重阳 |
| q050 | vector | ok | 是 | text | ok | 打狗棒法 |
| q051 | vector | ok | 否 | text | ok | 根据现有资料无法回答。 |
| q052 | vector | ok | 否 | text | ok | 根据现有资料无法回答。 |
| q053 | vector | ok | 是 | text | ok | 王重阳 |
| q054 | vector | ok | 是 | text | ok | 黄药师、洪七公 |
| q001 | library_graphrag | ok | 否 | text | ok | 根据现有资料无法回答。 |
| q002 | library_graphrag | ok | 是 | text | ok | 李萍 |
| q003 | library_graphrag | ok | 是 | text | ok | 黄药师 |
| q004 | library_graphrag | ok | 是 | text | ok | 包惜弱 |
| q005 | library_graphrag | ok | 是 | text | ok | 欧阳锋。 |
| q006 | library_graphrag | ok | 是 | text | ok | 黄蓉 |
| q007 | library_graphrag | ok | 是 | text | ok | 包惜弱 |
| q008 | library_graphrag | ok | 否 | text | ok | 根据现有资料无法回答。 |
| q009 | library_graphrag | ok | 是 | text | ok | 黄蓉 |
| q010 | library_graphrag | ok | 是 | text | ok | 郭靖 |
| q011 | library_graphrag | ok | 是 | text | ok | 柯镇恶 |
| q012 | library_graphrag | ok | 是 | text | ok | 洪七公 |
| q013 | library_graphrag | ok | 是 | text | ok | 丘处机 |
| q014 | library_graphrag | ok | 是 | text | ok | 黄药师 |
| q015 | library_graphrag | ok | 否 | text | ok | 根据现有资料无法回答。 |
| q016 | library_graphrag | ok | 否 | text | ok | 黄药师 |
| q017 | library_graphrag | ok | 是 | text | ok | 马钰 |
| q018 | library_graphrag | ok | 是 | text | ok | 丐帮 |
| q019 | library_graphrag | ok | 是 | text | ok | 桃花岛。 |
| q020 | library_graphrag | ok | 是 | text | ok | 全真教 |
| q021 | library_graphrag | ok | 否 | text | ok | 西域 |
| q022 | library_graphrag | ok | 否 | text | ok | 段氏 |
| q023 | library_graphrag | ok | 是 | text | ok | 铁掌帮。 |
| q024 | library_graphrag | ok | 是 | text | ok | 江南七怪 |
| q025 | library_graphrag | ok | 是 | text | ok | 全真教 |
| q026 | library_graphrag | ok | 是 | text | ok | 降龙十八掌 |
| q027 | library_graphrag | ok | 是 | text | ok | 打狗棒法 |
| q028 | library_graphrag | ok | 是 | text | ok | 蛤蟆功 |
| q029 | library_graphrag | ok | 是 | text | ok | 一阳指 |
| q030 | library_graphrag | ok | 是 | text | ok | 空明拳、双手互搏。 |
| q031 | library_graphrag | ok | 是 | text | ok | 弹指神通 |
| q032 | library_graphrag | ok | 是 | text | ok | 九阴白骨爪 |
| q033 | library_graphrag | ok | 是 | text | ok | 拖雷 |
| q034 | library_graphrag | ok | 是 | text | ok | 欧阳锋 |
| q035 | library_graphrag | ok | 否 | text | ok | 根据现有资料无法回答。 |
| q036 | library_graphrag | ok | 否 | text | ok | 根据现有资料无法回答。 |
| q037 | library_graphrag | ok | 是 | text | ok | 丐帮 |
| q038 | library_graphrag | ok | 是 | text | ok | 全真教 |
| q039 | library_graphrag | ok | 是 | text | ok | 江南七怪 |
| q040 | library_graphrag | ok | 否 | text | ok | 降龙十八掌 |
| q041 | library_graphrag | ok | 是 | text | ok | 降龙十八掌 |
| q042 | library_graphrag | ok | 是 | text | ok | 老顽童 |
| q043 | library_graphrag | ok | 是 | text | ok | 郭靖 |
| q044 | library_graphrag | ok | 否 | text | ok | 根据现有资料无法回答。 |
| q045 | library_graphrag | ok | 否 | text | ok | 根据现有资料无法回答。 |
| q046 | library_graphrag | ok | 是 | text | ok | 黄蓉 |
| q047 | library_graphrag | ok | 是 | text | ok | 铁木真 |
| q048 | library_graphrag | ok | 是 | text | ok | 黄蓉 |
| q049 | library_graphrag | ok | 是 | text | ok | 王重阳 |
| q050 | library_graphrag | ok | 是 | text | ok | 打狗棒法 |
| q051 | library_graphrag | ok | 否 | text | ok | 根据现有资料无法回答。 |
| q052 | library_graphrag | ok | 否 | text | ok | 根据现有资料无法回答。 |
| q053 | library_graphrag | ok | 是 | text | ok | 王重阳 |
| q054 | library_graphrag | ok | 是 | text | ok | 黄药师、洪七公 |
| q001 | master_chain | ok | 否 | path | ok | 根据现有资料无法回答。 |
| q002 | master_chain | ok | 否 | path | ok | 根据现有资料无法回答。 |
| q003 | master_chain | ok | 否 | path | ok | 根据现有资料无法回答。 |
| q004 | master_chain | ok | 否 | path | ok | 根据现有资料无法回答。 |
| q005 | master_chain | ok | 否 | path | ok | 根据现有资料无法回答。 |
| q006 | master_chain | ok | 否 | path | ok | 根据现有资料无法回答。 |
| q007 | master_chain | no_context | 否 | path | no_context | 图谱中没有找到 杨铁心 的师父信息。 |
| q008 | master_chain | ok | 否 | path | ok | 根据现有资料无法回答。 |
| q009 | master_chain | ok | 否 | path | ok | 根据现有资料无法回答。 |
| q010 | master_chain | ok | 否 | path | ok | 根据现有资料无法回答。 |
| q011 | master_chain | ok | 否 | path | ok | 根据现有资料无法回答。 |
| q012 | master_chain | ok | 否 | path | ok | 七公 |
| q013 | master_chain | ok | 是 | path | ok | 丘处机、梅超风、欧阳锋、汤祖德、洪七公 |
| q014 | master_chain | ok | 是 | path | ok | 黄药师 |
| q015 | master_chain | no_context | 否 | path | no_context | 图谱中没有找到 王重阳 的师父信息。 |
| q016 | master_chain | ok | 是 | path | ok | 洪七公、朱聪、柯镇恶 |
| q017 | master_chain | ok | 否 | path | ok | 根据现有资料无法回答。 |
| q018 | master_chain | no_context | 否 | path | no_context | 图谱中没有找到 洪七公 的有效师徒路径。 |
| q019 | master_chain | ok | 否 | path | ok | 根据现有资料无法回答。 |
| q020 | master_chain | no_context | 否 | path | no_context | 图谱中没有找到 王重阳 的师父信息。 |
| q021 | master_chain | no_context | 否 | path | no_context | 图谱中没有找到 欧阳锋 的师父信息。 |
| q022 | master_chain | ok | 否 | path | ok | 根据现有资料无法回答。 |
| q023 | master_chain | ok | 是 | path | ok | 铁掌帮 |
| q024 | master_chain | no_context | 否 | path | no_context | 图谱中没有找到 柯镇恶 的师父信息。 |
| q025 | master_chain | ok | 是 | path | ok | 全真教 |
| q026 | master_chain | ok | 否 | path | ok | 根据现有资料无法回答。 |
| q027 | master_chain | no_context | 否 | path | no_context | 图谱中没有找到 洪七公 的有效师徒路径。 |
| q028 | master_chain | no_context | 否 | path | no_context | 图谱中没有找到 欧阳锋 的师父信息。 |
| q029 | master_chain | ok | 否 | path | ok | 根据现有资料无法回答 |
| q030 | master_chain | ok | 否 | path | ok | 根据现有资料无法回答。 |
| q031 | master_chain | ok | 否 | path | ok | 根据现有资料无法回答。 |
| q032 | master_chain | ok | 否 | path | ok | 根据现有资料无法回答 |
| q033 | master_chain | ok | 否 | path | ok | 根据现有资料无法回答。 |
| q034 | master_chain | ok | 否 | path | ok | 根据现有资料无法回答。 |
| q035 | master_chain | ok | 否 | path | ok | 根据现有资料无法回答。 |
| q036 | master_chain | ok | 否 | path | ok | 根据现有资料无法回答。 |
| q037 | master_chain | ok | 否 | path | ok | 根据现有资料无法回答。 |
| q038 | master_chain | ok | 否 | path | ok | 根据现有资料无法回答。 |
| q039 | master_chain | ok | 否 | path | ok | 根据现有资料无法回答。 |
| q040 | master_chain | ok | 否 | path | ok | 根据现有资料无法回答。 |
| q041 | master_chain | ok | 否 | path | ok | 根据现有资料无法回答。 |
| q042 | master_chain | no_context | 否 | path | no_context | 图谱中没有找到 王重阳 的师父信息。 |
| q043 | master_chain | ok | 否 | path | ok | 根据现有资料无法回答。 |
| q044 | master_chain | ok | 否 | path | ok | 根据现有资料无法回答。 |
| q045 | master_chain | ok | 是 | path | ok | 丐帮 |
| q046 | master_chain | no_context | 否 | path | no_context | 图谱中没有找到 欧阳锋 的师父信息。 |
| q047 | master_chain | ok | 否 | path | ok | 根据现有资料无法回答。 |
| q048 | master_chain | ok | 否 | path | ok | 根据现有资料无法回答。 |
| q049 | master_chain | ok | 是 | path | ok | 王重阳 |
| q050 | master_chain | no_context | 否 | path | no_context | 图谱中没有找到 洪七公 的有效师徒路径。 |
| q051 | master_chain | ok | 否 | path | ok | 根据现有资料无法回答。 |
| q052 | master_chain | ok | 否 | path | ok | 根据现有资料无法回答。 |
| q053 | master_chain | ok | 是 | path | ok | 王重阳 |
| q054 | master_chain | ok | 是 | path | ok | 黄药师、洪七公 |
| q001 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q002 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q003 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q004 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q005 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q006 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q007 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q008 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q009 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q010 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q011 | sect_agg | ok | 否 | subgraph | ok | 根据现有资料无法回答。 |
| q012 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q013 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q014 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q015 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q016 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q017 | sect_agg | ok | 是 | subgraph | ok | 马钰 |
| q018 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q019 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q020 | sect_agg | ok | 是 | subgraph | ok | 全真教 |
| q021 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q022 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q023 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q024 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q025 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q026 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q027 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q028 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q029 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q030 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q031 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q032 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q033 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q034 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q035 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q036 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q037 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q038 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q039 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q040 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q041 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q042 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q043 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q044 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q045 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q046 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q047 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q048 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q049 | sect_agg | ok | 否 | subgraph | ok | 根据现有资料无法回答。 |
| q050 | sect_agg | ok | 否 | subgraph | ok | 根据现有资料无法回答 |
| q051 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q052 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q053 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q054 | sect_agg | no_context | 否 | subgraph | no_context | 未能从问题中识别出门派实体。 |
| q001 | art_lineage | no_context | 否 | path | no_context | 未能从问题中识别出武功实体。 |
| q002 | art_lineage | no_context | 否 | path | no_context | 未能从问题中识别出武功实体。 |
| q003 | art_lineage | no_context | 否 | path | no_context | 未能从问题中识别出武功实体。 |
| q004 | art_lineage | no_context | 否 | path | no_context | 未能从问题中识别出武功实体。 |
| q005 | art_lineage | no_context | 否 | path | no_context | 未能从问题中识别出武功实体。 |
| q006 | art_lineage | no_context | 否 | path | no_context | 未能从问题中识别出武功实体。 |
| q007 | art_lineage | no_context | 否 | path | no_context | 未能从问题中识别出武功实体。 |
| q008 | art_lineage | no_context | 否 | path | no_context | 未能从问题中识别出武功实体。 |
| q009 | art_lineage | no_context | 否 | path | no_context | 未能从问题中识别出武功实体。 |
| q010 | art_lineage | no_context | 否 | path | no_context | 未能从问题中识别出武功实体。 |
| q011 | art_lineage | no_context | 否 | path | no_context | 未能从问题中识别出武功实体。 |
| q012 | art_lineage | ok | 是 | path | ok | 洪七公 |
| q013 | art_lineage | no_context | 否 | path | no_context | 未能从问题中识别出武功实体。 |
| q014 | art_lineage | no_context | 否 | path | no_context | 未能从问题中识别出武功实体。 |
| q015 | art_lineage | no_context | 否 | path | no_context | 未能从问题中识别出武功实体。 |
| q016 | art_lineage | no_context | 否 | path | no_context | 未能从问题中识别出武功实体。 |
| q017 | art_lineage | ok | 否 | path | ok | 根据现有资料无法回答。 |
| q018 | art_lineage | no_context | 否 | path | no_context | 未能从问题中识别出武功实体。 |
| q019 | art_lineage | no_context | 否 | path | no_context | 未能从问题中识别出武功实体。 |
| q020 | art_lineage | no_context | 否 | path | no_context | 未能从问题中识别出武功实体。 |
| q021 | art_lineage | no_context | 否 | path | no_context | 未能从问题中识别出武功实体。 |
| q022 | art_lineage | no_context | 否 | path | no_context | 未能从问题中识别出武功实体。 |
| q023 | art_lineage | no_context | 否 | path | no_context | 未能从问题中识别出武功实体。 |
| q024 | art_lineage | no_context | 否 | path | no_context | 未能从问题中识别出武功实体。 |
| q025 | art_lineage | no_context | 否 | path | no_context | 未能从问题中识别出武功实体。 |
| q026 | art_lineage | ok | 否 | path | ok | 根据现有资料无法回答 |
| q027 | art_lineage | ok | 否 | path | ok | 根据现有资料无法回答。 |
| q028 | art_lineage | no_context | 否 | path | no_context | 未能从问题中识别出武功实体。 |
| q029 | art_lineage | no_context | 否 | path | no_context | 未能从问题中识别出武功实体。 |
| q030 | art_lineage | no_context | 否 | path | no_context | 未能从问题中识别出武功实体。 |
| q031 | art_lineage | no_context | 否 | path | no_context | 未能从问题中识别出武功实体。 |
| q032 | art_lineage | no_context | 否 | path | no_context | 未能从问题中识别出武功实体。 |
| q033 | art_lineage | no_context | 否 | path | no_context | 未能从问题中识别出武功实体。 |
| q034 | art_lineage | no_context | 否 | path | no_context | 未能从问题中识别出武功实体。 |
| q035 | art_lineage | no_context | 否 | path | no_context | 未能从问题中识别出武功实体。 |
| q036 | art_lineage | no_context | 否 | path | no_context | 未能从问题中识别出武功实体。 |
| q037 | art_lineage | no_context | 否 | path | no_context | 未能从问题中识别出武功实体。 |
| q038 | art_lineage | no_context | 否 | path | no_context | 未能从问题中识别出武功实体。 |
| q039 | art_lineage | no_context | 否 | path | no_context | 未能从问题中识别出武功实体。 |
| q040 | art_lineage | no_context | 否 | path | no_context | 未能从问题中识别出武功实体。 |
| q041 | art_lineage | ok | 否 | path | ok | 根据现有资料无法回答。 |
| q042 | art_lineage | no_context | 否 | path | no_context | 未能从问题中识别出武功实体。 |
| q043 | art_lineage | no_context | 否 | path | no_context | 未能从问题中识别出武功实体。 |
| q044 | art_lineage | no_context | 否 | path | no_context | 未能从问题中识别出武功实体。 |
| q045 | art_lineage | no_context | 否 | path | no_context | 未能从问题中识别出武功实体。 |
| q046 | art_lineage | no_context | 否 | path | no_context | 未能从问题中识别出武功实体。 |
| q047 | art_lineage | no_context | 否 | path | no_context | 未能从问题中识别出武功实体。 |
| q048 | art_lineage | no_context | 否 | path | no_context | 未能从问题中识别出武功实体。 |
| q049 | art_lineage | no_context | 否 | path | no_context | 未能从问题中识别出武功实体。 |
| q050 | art_lineage | ok | 否 | path | ok | 根据现有资料无法回答。 |
| q051 | art_lineage | no_context | 否 | path | no_context | 未能从问题中识别出武功实体。 |
| q052 | art_lineage | no_context | 否 | path | no_context | 未能从问题中识别出武功实体。 |
| q053 | art_lineage | no_context | 否 | path | no_context | 未能从问题中识别出武功实体。 |
| q054 | art_lineage | no_context | 否 | path | no_context | 未能从问题中识别出武功实体。 |
| q001 | person_relation | ok | 是 | triples | ok | 郭啸天 |
| q002 | person_relation | ok | 是 | triples | ok | 李萍 |
| q003 | person_relation | ok | 是 | triples | ok | 黄药师 |
| q004 | person_relation | ok | 是 | triples | ok | 包惜弱 |
| q005 | person_relation | no_context | 否 | triples | no_context | 无法回答：侄子属于旁系亲属，当前本体没有对应关系类型。 |
| q006 | person_relation | ok | 是 | triples | ok | 黄蓉 |
| q007 | person_relation | ok | 是 | triples | ok | 包惜弱 |
| q008 | person_relation | no_context | 否 | triples | no_context | 未能识别问题涉及的关系类型。 |
| q009 | person_relation | ok | 是 | triples | ok | 黄蓉 |
| q010 | person_relation | ok | 是 | triples | ok | 郭靖 |
| q011 | person_relation | ok | 是 | triples | ok | 柯镇恶 |
| q012 | person_relation | no_context | 否 | triples | no_context | 未能识别问题涉及的关系类型。 |
| q013 | person_relation | ok | 是 | triples | ok | 丘处机、梅超风、欧阳锋、汤祖德、洪七公 |
| q014 | person_relation | ok | 是 | triples | ok | 黄药师 |
| q015 | person_relation | no_context | 否 | triples | no_context | 未能识别问题涉及的关系类型。 |
| q016 | person_relation | ok | 是 | triples | ok | 洪七公、柯镇恶、黄药师、朱聪 |
| q017 | person_relation | no_context | 否 | triples | no_context | 未能识别问题涉及的关系类型。 |
| q018 | person_relation | no_context | 否 | triples | no_context | 未能识别问题涉及的关系类型。 |
| q019 | person_relation | no_context | 否 | triples | no_context | 未能识别问题涉及的关系类型。 |
| q020 | person_relation | no_context | 否 | triples | no_context | 未能识别问题涉及的关系类型。 |
| q021 | person_relation | no_context | 否 | triples | no_context | 未能识别问题涉及的关系类型。 |
| q022 | person_relation | no_context | 否 | triples | no_context | 未能识别问题涉及的关系类型。 |
| q023 | person_relation | no_context | 否 | triples | no_context | 未能识别问题涉及的关系类型。 |
| q024 | person_relation | no_context | 否 | triples | no_context | 未能识别问题涉及的关系类型。 |
| q025 | person_relation | no_context | 否 | triples | no_context | 未能识别问题涉及的关系类型。 |
| q026 | person_relation | no_context | 否 | triples | no_context | 未能识别问题涉及的关系类型。 |
| q027 | person_relation | no_context | 否 | triples | no_context | 未能识别问题涉及的关系类型。 |
| q028 | person_relation | no_context | 否 | triples | no_context | 未能识别问题涉及的关系类型。 |
| q029 | person_relation | no_context | 否 | triples | no_context | 未能识别问题涉及的关系类型。 |
| q030 | person_relation | no_context | 否 | triples | no_context | 未能识别问题涉及的关系类型。 |
| q031 | person_relation | no_context | 否 | triples | no_context | 未能识别问题涉及的关系类型。 |
| q032 | person_relation | no_context | 否 | triples | no_context | 未能识别问题涉及的关系类型。 |
| q033 | person_relation | ok | 是 | triples | ok | 拖雷 |
| q034 | person_relation | ok | 是 | triples | ok | 欧阳锋 |
| q035 | person_relation | ok | 是 | triples | ok | 黄药师 |
| q036 | person_relation | ok | 是 | triples | ok | 陈玄风 |
| q037 | person_relation | ok | 否 | triples | ok | 根据现有资料无法回答 |
| q038 | person_relation | ok | 否 | triples | ok | 根据现有资料无法回答。 |
| q039 | person_relation | ok | 是 | triples | ok | 江南七怪 |
| q040 | person_relation | ok | 否 | triples | ok | 根据现有资料无法回答。 |
| q041 | person_relation | no_context | 否 | triples | no_context | 未能识别问题涉及的关系类型。 |
| q042 | person_relation | no_context | 否 | triples | no_context | 未能识别问题涉及的关系类型。 |
| q043 | person_relation | ok | 是 | triples | ok | 郭靖 |
| q044 | person_relation | ok | 是 | triples | ok | 洪七公、柯镇恶、黄药师、朱聪 |
| q045 | person_relation | ok | 否 | triples | ok | 根据现有资料无法回答。 |
| q046 | person_relation | no_context | 否 | triples | no_context | 无法回答：侄子属于旁系亲属，当前本体没有对应关系类型。 |
| q047 | person_relation | ok | 是 | triples | ok | 铁木真（成吉思汗） |
| q048 | person_relation | ok | 是 | triples | ok | 黄蓉 |
| q049 | person_relation | no_context | 否 | triples | no_context | 未能识别问题涉及的关系类型。 |
| q050 | person_relation | no_context | 否 | triples | no_context | 未能识别问题涉及的关系类型。 |
| q051 | person_relation | ok | 否 | triples | ok | 根据现有资料无法回答。 |
| q052 | person_relation | ok | 否 | triples | ok | 根据现有资料无法回答。 |
| q053 | person_relation | no_context | 否 | triples | no_context | 未能识别问题涉及的关系类型。 |
| q054 | person_relation | ok | 是 | triples | ok | 黄药师、洪七公 |
