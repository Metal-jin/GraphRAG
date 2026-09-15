# GraphRAG 方法对比评测结果

> 本表由 `src/eval/run_compare.py` 自动生成。准确率和关键实体召回率是当前阶段的自动指标，最终结论仍需结合证据和人工复核。

- 生成时间：`2026-09-14T18:29:20+08:00`
- 评测问题数：`100`
- 统一 `top_k`：`5`
- 自动判分：回答文本命中该题 `acceptable_answers` 中任一实体或别名即记为命中。

## 汇总

| 方法 | 可用题数 | 可用率 | 实体命中数 | 准确率 | 关键实体召回率 | 平均耗时(ms) |
|---|---:|---:|---:|---:|---:|---:|
| art_lineage | 100/100 | 100.00% | 3 | 3.00% | 3.00% | 573.48 |
| cross_novel | 54/100 | 54.00% | 15 | 27.78% | 27.78% | 996.35 |
| library_graphrag | 100/100 | 100.00% | 87 | 87.00% | 87.00% | 783.33 |
| master_chain | 100/100 | 100.00% | 68 | 68.00% | 68.00% | 1195.62 |
| person_relation | 100/100 | 100.00% | 31 | 31.00% | 31.00% | 779.57 |
| sect_agg | 100/100 | 100.00% | 1 | 1.00% | 1.00% | 577.22 |
| vector | 100/100 | 100.00% | 85 | 85.00% | 85.00% | 815.60 |

## 分类别结果

| 方法 | 类别 | 题数 | 准确率 | 路径完整性 | 证据充分性 |
|---|---|---:|---:|---:|---:|
| art_lineage | 人物 | 72 | 2.78% | 0.00% | 2.78% |
| art_lineage | 武功 | 11 | 9.09% | 0.00% | 9.09% |
| art_lineage | 门派 | 13 | 0.00% | 0.00% | 0.00% |
| art_lineage | 综合 | 4 | 0.00% | 0.00% | 0.00% |
| cross_novel | 人物 | 72 | 20.83% | 36.11% | 11.11% |
| cross_novel | 武功 | 11 | 0.00% | 31.82% | 0.00% |
| cross_novel | 门派 | 13 | 0.00% | 7.69% | 0.00% |
| cross_novel | 综合 | 4 | 0.00% | 0.00% | 0.00% |
| library_graphrag | 人物 | 72 | 87.50% | 0.00% | 86.11% |
| library_graphrag | 武功 | 11 | 90.91% | 0.00% | 90.91% |
| library_graphrag | 门派 | 13 | 76.92% | 0.00% | 84.62% |
| library_graphrag | 综合 | 4 | 100.00% | 0.00% | 100.00% |
| master_chain | 人物 | 72 | 72.22% | 86.11% | 63.19% |
| master_chain | 武功 | 11 | 9.09% | 100.00% | 9.09% |
| master_chain | 门派 | 13 | 84.62% | 100.00% | 53.85% |
| master_chain | 综合 | 4 | 100.00% | 100.00% | 100.00% |
| person_relation | 人物 | 72 | 41.67% | 50.00% | 40.97% |
| person_relation | 武功 | 11 | 0.00% | 0.00% | 0.00% |
| person_relation | 门派 | 13 | 0.00% | 0.00% | 0.00% |
| person_relation | 综合 | 4 | 25.00% | 25.00% | 25.00% |
| sect_agg | 人物 | 72 | 1.39% | 0.00% | 4.86% |
| sect_agg | 武功 | 11 | 0.00% | 0.00% | 4.55% |
| sect_agg | 门派 | 13 | 0.00% | 0.00% | 0.00% |
| sect_agg | 综合 | 4 | 0.00% | 0.00% | 0.00% |
| vector | 人物 | 72 | 86.11% | 0.00% | 85.42% |
| vector | 武功 | 11 | 90.91% | 0.00% | 90.91% |
| vector | 门派 | 13 | 76.92% | 0.00% | 84.62% |
| vector | 综合 | 4 | 75.00% | 0.00% | 87.50% |

## 指标解释

- **可用率**：方法成功返回 `Answer` 的题数 / 总题数。
- **准确率**：自动判分成功题数 / 方法成功返回题数；方法不可用不会被误算成回答错误。
- **路径完整性**：证据覆盖的关系跳数 / 问题预期跳数，范围 0~1。
- **证据充分性**：答案命中标准实体与证据非空两项的平均值，范围 0~1。
- **平均耗时**：从调用 `ask()` 到返回或抛出异常的单题平均耗时。

## 逐题结果

| 题号 | 方法 | 状态 | 实体命中 | 回答/错误 |
|---|---|---|---|---|
| q001 | vector | ok | 是 | 郭啸天 |
| q002 | vector | ok | 是 | 李萍 |
| q003 | vector | ok | 是 | 黄药师 |
| q004 | vector | ok | 是 | 包惜弱 |
| q005 | vector | ok | 是 | 欧阳锋 |
| q006 | vector | ok | 是 | 黄蓉 |
| q007 | vector | ok | 是 | 包惜弱 |
| q008 | vector | ok | 是 | 瑛姑 |
| q009 | vector | ok | 是 | 黄蓉 |
| q010 | vector | ok | 是 | 郭靖 |
| q011 | vector | ok | 是 | 柯镇恶 |
| q012 | vector | ok | 是 | 洪七公 |
| q013 | vector | ok | 是 | 丘处机、梅超风（即“瞎眼婆子”，教他九阴白骨爪等功夫）。 |
| q014 | vector | ok | 是 | 黄药师 |
| q015 | vector | ok | 否 | 根据现有资料无法回答。 |
| q016 | vector | ok | 是 | 洪七公 |
| q017 | vector | ok | 是 | 马钰（丹阳真人马道长）。 |
| q018 | vector | ok | 是 | 丐帮 |
| q019 | vector | ok | 是 | 桃花岛 |
| q020 | vector | ok | 是 | 全真教 |
| q021 | vector | ok | 否 | 西域 |
| q022 | vector | ok | 否 | 段氏 |
| q023 | vector | ok | 是 | 铁掌帮 |
| q024 | vector | ok | 是 | 江南七怪 |
| q025 | vector | ok | 是 | 全真教 |
| q026 | vector | ok | 是 | 降龙十八掌、空明拳。 |
| q027 | vector | ok | 是 | 打狗棒法 |
| q028 | vector | ok | 是 | 蛤蟆功 |
| q029 | vector | ok | 是 | 一阳指、先天功、千里传音。 |
| q030 | vector | ok | 是 | 空明拳、双手互搏（双手两用术）。 |
| q031 | vector | ok | 是 | 弹指神通 |
| q032 | vector | ok | 是 | 九阴白骨爪 |
| q033 | vector | ok | 否 | 根据现有资料无法回答。 |
| q034 | vector | ok | 是 | 欧阳锋 |
| q035 | vector | ok | 是 | 黄药师 |
| q036 | vector | ok | 是 | 梅超风 |
| q037 | vector | ok | 是 | 丐帮 |
| q038 | vector | ok | 是 | 全真教 |
| q039 | vector | ok | 是 | 江南七怪 |
| q040 | vector | ok | 否 | 降龙十八掌 |
| q041 | vector | ok | 是 | 降龙十八掌 |
| q042 | vector | ok | 是 | 老顽童 |
| q043 | vector | ok | 是 | 郭靖 |
| q044 | vector | ok | 是 | 洪七公 |
| q045 | vector | ok | 否 | 根据现有资料无法回答。 |
| q046 | vector | ok | 是 | 黄蓉 |
| q047 | vector | ok | 否 | 根据现有资料无法回答。 |
| q048 | vector | ok | 是 | 黄蓉 |
| q049 | vector | ok | 是 | 王重阳 |
| q050 | vector | ok | 是 | 打狗棒法 |
| q051 | vector | ok | 否 | 根据现有资料无法回答。 |
| q052 | vector | ok | 是 | 是，黄药师。 |
| q053 | vector | ok | 是 | 王重阳 |
| q054 | vector | ok | 是 | 黄药师、洪七公 |
| q055 | vector | ok | 是 | 杨过 |
| q056 | vector | ok | 是 | 杨康 |
| q057 | vector | ok | 否 | 根据现有资料无法回答。 |
| q058 | vector | ok | 是 | 小龙女 |
| q059 | vector | ok | 是 | 欧阳锋 |
| q060 | vector | ok | 是 | 小龙女 |
| q061 | vector | ok | 是 | 杨过 |
| q062 | vector | ok | 是 | 灭绝师太 |
| q063 | vector | ok | 是 | 峨嵋派 |
| q064 | vector | ok | 是 | 张翠山 |
| q065 | vector | ok | 是 | 殷素素 |
| q066 | vector | ok | 是 | 谢逊 |
| q067 | vector | ok | 否 | 根据现有资料无法回答。 |
| q068 | vector | ok | 是 | 汝阳王 |
| q069 | vector | ok | 否 | 根据现有资料无法回答。 |
| q070 | vector | ok | 是 | 武当派 |
| q071 | vector | ok | 是 | 杨过 |
| q072 | vector | ok | 否 | 殷天正 |
| q073 | vector | ok | 否 | 峨嵋派 |
| q074 | vector | ok | 是 | 金毛狮王 |
| q075 | vector | ok | 否 | 郭芙 |
| q076 | vector | ok | 是 | 郭芙 |
| q077 | vector | ok | 是 | 郭靖 |
| q078 | vector | ok | 是 | 黄蓉 |
| q079 | vector | ok | 是 | 黄蓉 |
| q080 | vector | ok | 是 | 小龙女 |
| q081 | vector | ok | 是 | 古墓派 |
| q082 | vector | ok | 否 | 臭蛤蟆 |
| q083 | vector | ok | 是 | 黄药师 |
| q084 | vector | ok | 是 | 古墓派 |
| q085 | vector | ok | 是 | 明教 |
| q086 | vector | ok | 是 | 成昆（混元霹雳手成昆） |
| q087 | vector | ok | 是 | 明教 |
| q088 | vector | ok | 是 | 峨嵋派 |
| q089 | vector | ok | 是 | 武当派 |
| q090 | vector | ok | 是 | 张翠山 |
| q091 | vector | ok | 是 | 谢逊 |
| q092 | vector | ok | 是 | 张三丰 |
| q093 | vector | ok | 是 | 成昆 |
| q094 | vector | ok | 是 | 峨嵋派 |
| q095 | vector | ok | 是 | 张无忌 |
| q096 | vector | ok | 是 | 混元霹雳手 |
| q097 | vector | ok | 是 | 杨过 |
| q098 | vector | ok | 是 | 黄蓉 |
| q099 | vector | ok | 是 | 武当派 |
| q100 | vector | ok | 是 | 混元霹雳手 |
| q001 | library_graphrag | ok | 是 | 郭啸天 |
| q002 | library_graphrag | ok | 是 | 李萍 |
| q003 | library_graphrag | ok | 是 | 黄药师 |
| q004 | library_graphrag | ok | 是 | 包惜弱 |
| q005 | library_graphrag | ok | 是 | 欧阳锋 |
| q006 | library_graphrag | ok | 是 | 黄蓉 |
| q007 | library_graphrag | ok | 是 | 包惜弱 |
| q008 | library_graphrag | ok | 是 | 瑛姑 |
| q009 | library_graphrag | ok | 是 | 黄蓉 |
| q010 | library_graphrag | ok | 是 | 郭靖 |
| q011 | library_graphrag | ok | 是 | 柯镇恶 |
| q012 | library_graphrag | ok | 是 | 洪七公 |
| q013 | library_graphrag | ok | 是 | 丘处机、梅超风（“小王爷”的师父，教他九阴白骨爪等功夫）。 |
| q014 | library_graphrag | ok | 是 | 黄药师 |
| q015 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q016 | library_graphrag | ok | 是 | 洪七公 |
| q017 | library_graphrag | ok | 是 | 马钰（丹阳真人马道长）。 |
| q018 | library_graphrag | ok | 是 | 丐帮 |
| q019 | library_graphrag | ok | 是 | 桃花岛 |
| q020 | library_graphrag | ok | 是 | 全真教 |
| q021 | library_graphrag | ok | 否 | 西域 |
| q022 | library_graphrag | ok | 否 | 段氏 |
| q023 | library_graphrag | ok | 是 | 铁掌帮 |
| q024 | library_graphrag | ok | 是 | 江南七怪 |
| q025 | library_graphrag | ok | 是 | 全真教 |
| q026 | library_graphrag | ok | 是 | 降龙十八掌、空明拳。 |
| q027 | library_graphrag | ok | 是 | 打狗棒法 |
| q028 | library_graphrag | ok | 是 | 蛤蟆功 |
| q029 | library_graphrag | ok | 是 | 一阳指、先天功、千里传音。 |
| q030 | library_graphrag | ok | 是 | 空明拳、双手互搏（双手两用术）。 |
| q031 | library_graphrag | ok | 是 | 弹指神通 |
| q032 | library_graphrag | ok | 是 | 九阴白骨爪 |
| q033 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q034 | library_graphrag | ok | 是 | 欧阳锋 |
| q035 | library_graphrag | ok | 是 | 黄药师 |
| q036 | library_graphrag | ok | 是 | 梅超风 |
| q037 | library_graphrag | ok | 是 | 丐帮 |
| q038 | library_graphrag | ok | 是 | 全真教 |
| q039 | library_graphrag | ok | 是 | 江南七怪 |
| q040 | library_graphrag | ok | 否 | 降龙十八掌 |
| q041 | library_graphrag | ok | 是 | 降龙十八掌 |
| q042 | library_graphrag | ok | 是 | 老顽童 |
| q043 | library_graphrag | ok | 是 | 郭靖 |
| q044 | library_graphrag | ok | 是 | 洪七公 |
| q045 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q046 | library_graphrag | ok | 是 | 黄蓉 |
| q047 | library_graphrag | ok | 是 | 成吉思汗 |
| q048 | library_graphrag | ok | 是 | 黄蓉 |
| q049 | library_graphrag | ok | 是 | 王重阳 |
| q050 | library_graphrag | ok | 是 | 打狗棒法 |
| q051 | library_graphrag | ok | 是 | 洪七公 |
| q052 | library_graphrag | ok | 是 | 是，黄药师。 |
| q053 | library_graphrag | ok | 是 | 王重阳 |
| q054 | library_graphrag | ok | 是 | 黄药师、洪七公 |
| q055 | library_graphrag | ok | 是 | 杨过 |
| q056 | library_graphrag | ok | 是 | 杨康 |
| q057 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q058 | library_graphrag | ok | 是 | 小龙女 |
| q059 | library_graphrag | ok | 是 | 欧阳锋 |
| q060 | library_graphrag | ok | 是 | 小龙女 |
| q061 | library_graphrag | ok | 是 | 杨过 |
| q062 | library_graphrag | ok | 是 | 灭绝师太 |
| q063 | library_graphrag | ok | 是 | 峨嵋派 |
| q064 | library_graphrag | ok | 是 | 张翠山 |
| q065 | library_graphrag | ok | 是 | 殷素素 |
| q066 | library_graphrag | ok | 是 | 谢逊 |
| q067 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q068 | library_graphrag | ok | 是 | 汝阳王 |
| q069 | library_graphrag | ok | 否 | 根据现有资料无法回答。 |
| q070 | library_graphrag | ok | 是 | 武当派 |
| q071 | library_graphrag | ok | 是 | 杨过 |
| q072 | library_graphrag | ok | 否 | 殷天正 |
| q073 | library_graphrag | ok | 否 | 峨嵋派 |
| q074 | library_graphrag | ok | 是 | 金毛狮王 |
| q075 | library_graphrag | ok | 否 | 郭芙 |
| q076 | library_graphrag | ok | 是 | 郭芙 |
| q077 | library_graphrag | ok | 是 | 郭靖 |
| q078 | library_graphrag | ok | 是 | 黄蓉 |
| q079 | library_graphrag | ok | 是 | 黄蓉 |
| q080 | library_graphrag | ok | 是 | 小龙女 |
| q081 | library_graphrag | ok | 是 | 古墓派 |
| q082 | library_graphrag | ok | 否 | 臭蛤蟆 |
| q083 | library_graphrag | ok | 是 | 黄药师 |
| q084 | library_graphrag | ok | 是 | 古墓派 |
| q085 | library_graphrag | ok | 是 | 明教 |
| q086 | library_graphrag | ok | 是 | 成昆（混元霹雳手成昆） |
| q087 | library_graphrag | ok | 是 | 明教 |
| q088 | library_graphrag | ok | 是 | 峨嵋派 |
| q089 | library_graphrag | ok | 是 | 武当派 |
| q090 | library_graphrag | ok | 是 | 张翠山 |
| q091 | library_graphrag | ok | 是 | 谢逊 |
| q092 | library_graphrag | ok | 是 | 张三丰 |
| q093 | library_graphrag | ok | 是 | 成昆 |
| q094 | library_graphrag | ok | 是 | 峨嵋派 |
| q095 | library_graphrag | ok | 是 | 张无忌 |
| q096 | library_graphrag | ok | 是 | 混元霹雳手 |
| q097 | library_graphrag | ok | 是 | 杨过 |
| q098 | library_graphrag | ok | 是 | 黄蓉 |
| q099 | library_graphrag | ok | 是 | 武当派 |
| q100 | library_graphrag | ok | 是 | 混元霹雳手 |
| q001 | master_chain | ok | 否 | 根据现有资料无法回答。 |
| q002 | master_chain | ok | 否 | 根据现有资料无法回答。 |
| q003 | master_chain | ok | 是 | 黄药师 |
| q004 | master_chain | ok | 否 | 穆念慈 |
| q005 | master_chain | ok | 是 | 欧阳锋 |
| q006 | master_chain | ok | 是 | 黄蓉 |
| q007 | master_chain | ok | 否 | 根据现有资料无法回答 |
| q008 | master_chain | ok | 否 | 根据现有资料无法回答。 |
| q009 | master_chain | ok | 是 | 黄蓉 |
| q010 | master_chain | ok | 是 | 郭靖 |
| q011 | master_chain | ok | 是 | 柯镇恶 |
| q012 | master_chain | ok | 是 | 洪七公 |
| q013 | master_chain | ok | 是 | 丘处机、梅超风 |
| q014 | master_chain | ok | 是 | 黄药师 |
| q015 | master_chain | ok | 是 | 周伯通 |
| q016 | master_chain | ok | 是 | 黄药师、洪七公 |
| q017 | master_chain | ok | 是 | 马钰 |
| q018 | master_chain | ok | 是 | 丐帮 |
| q019 | master_chain | ok | 是 | 桃花岛 |
| q020 | master_chain | ok | 是 | 全真教 |
| q021 | master_chain | ok | 否 | 根据现有资料无法回答。 |
| q022 | master_chain | ok | 是 | 大理段氏 |
| q023 | master_chain | ok | 否 | 根据现有资料无法回答。 |
| q024 | master_chain | ok | 是 | 江南七怪 |
| q025 | master_chain | ok | 是 | 全真教 |
| q026 | master_chain | ok | 否 | 根据现有资料无法回答。 |
| q027 | master_chain | ok | 否 | 根据现有资料无法回答。 |
| q028 | master_chain | ok | 否 | 根据现有资料无法回答。 |
| q029 | master_chain | ok | 否 | 根据现有资料无法回答。 |
| q030 | master_chain | ok | 否 | 根据现有资料无法回答。 |
| q031 | master_chain | ok | 否 | 根据现有资料无法回答。 |
| q032 | master_chain | ok | 否 | 根据现有资料无法回答。 |
| q033 | master_chain | ok | 否 | 博尔忽、哲别 |
| q034 | master_chain | ok | 是 | 欧阳锋 |
| q035 | master_chain | ok | 是 | 黄药师 |
| q036 | master_chain | ok | 是 | 梅超风 |
| q037 | master_chain | ok | 是 | 丐帮 |
| q038 | master_chain | ok | 是 | 全真教 |
| q039 | master_chain | ok | 是 | 江南七怪 |
| q040 | master_chain | ok | 否 | 根据现有资料无法回答。 |
| q041 | master_chain | ok | 否 | 根据现有资料无法回答。 |
| q042 | master_chain | ok | 否 | 根据现有资料无法回答。 |
| q043 | master_chain | ok | 是 | 郭靖 |
| q044 | master_chain | ok | 否 | 黄药师 |
| q045 | master_chain | ok | 是 | 黄蓉的师父有洪七公、黄药师，洪七公属于丐帮，黄药师属于桃花岛。 |
| q046 | master_chain | ok | 是 | 黄蓉 |
| q047 | master_chain | ok | 是 | 成吉思汗 |
| q048 | master_chain | ok | 是 | 黄蓉 |
| q049 | master_chain | ok | 是 | 王重阳 |
| q050 | master_chain | ok | 否 | 根据现有资料无法回答。 |
| q051 | master_chain | ok | 是 | 洪七公 |
| q052 | master_chain | ok | 是 | 是，黄药师。 |
| q053 | master_chain | ok | 是 | 王重阳 |
| q054 | master_chain | ok | 是 | 黄药师、洪七公 |
| q055 | master_chain | ok | 是 | 杨过 |
| q056 | master_chain | ok | 是 | 杨康 |
| q057 | master_chain | ok | 是 | 穆念慈 |
| q058 | master_chain | ok | 是 | 小龙女 |
| q059 | master_chain | ok | 是 | 欧阳锋 |
| q060 | master_chain | ok | 是 | 小龙女 |
| q061 | master_chain | ok | 是 | 杨过 |
| q062 | master_chain | ok | 是 | 灭绝师太 |
| q063 | master_chain | ok | 是 | 峨眉派 |
| q064 | master_chain | ok | 否 | 根据现有资料无法回答 |
| q065 | master_chain | ok | 否 | 根据现有资料无法回答 |
| q066 | master_chain | ok | 是 | 谢逊 |
| q067 | master_chain | ok | 否 | 根据现有资料无法回答。 |
| q068 | master_chain | ok | 否 | 根据现有资料无法回答 |
| q069 | master_chain | ok | 是 | 张三丰 |
| q070 | master_chain | ok | 是 | 武当派 |
| q071 | master_chain | ok | 是 | 杨过 |
| q072 | master_chain | ok | 否 | 根据现有资料无法回答。 |
| q073 | master_chain | ok | 是 | 峨眉派 |
| q074 | master_chain | ok | 是 | 金毛狮王 |
| q075 | master_chain | ok | 是 | 郭襄 |
| q076 | master_chain | ok | 是 | 郭芙 |
| q077 | master_chain | ok | 是 | 郭靖 |
| q078 | master_chain | ok | 否 | 根据现有资料无法回答 |
| q079 | master_chain | ok | 是 | 黄蓉 |
| q080 | master_chain | ok | 否 | 根据现有资料无法回答 |
| q081 | master_chain | ok | 是 | 古墓派 |
| q082 | master_chain | ok | 是 | 西毒 |
| q083 | master_chain | ok | 是 | 黄药师 |
| q084 | master_chain | ok | 是 | 古墓派 |
| q085 | master_chain | ok | 是 | 明教 |
| q086 | master_chain | ok | 是 | 成昆 |
| q087 | master_chain | ok | 是 | 明教 |
| q088 | master_chain | ok | 是 | 峨眉派 |
| q089 | master_chain | ok | 是 | 武当派 |
| q090 | master_chain | ok | 否 | 根据现有资料无法回答 |
| q091 | master_chain | ok | 否 | 根据现有资料无法回答 |
| q092 | master_chain | ok | 否 | 根据现有资料无法回答 |
| q093 | master_chain | ok | 是 | 成昆 |
| q094 | master_chain | ok | 是 | 峨眉派 |
| q095 | master_chain | ok | 是 | 张无忌 |
| q096 | master_chain | ok | 是 | 混元霹雳手 |
| q097 | master_chain | ok | 否 | 根据现有资料无法回答 |
| q098 | master_chain | ok | 是 | 黄蓉 |
| q099 | master_chain | ok | 否 | 根据现有资料无法回答 |
| q100 | master_chain | ok | 是 | 混元霹雳手 |
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
| q011 | sect_agg | ok | 是 | 柯镇恶 |
| q012 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q013 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q014 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q015 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q016 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q017 | sect_agg | ok | 否 | 根据现有资料无法回答 |
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
| q033 | sect_agg | ok | 否 | 根据现有资料无法回答 |
| q034 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q035 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q036 | sect_agg | ok | 否 | 根据现有资料无法回答 |
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
| q049 | sect_agg | ok | 否 | 根据现有资料无法回答 |
| q050 | sect_agg | ok | 否 | 根据现有资料无法回答 |
| q051 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q052 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q053 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q054 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q055 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q056 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q057 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q058 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q059 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q060 | sect_agg | ok | 否 | 根据现有资料无法回答 |
| q061 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q062 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q063 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q064 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q065 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q066 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q067 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q068 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q069 | sect_agg | ok | 否 | 根据现有资料无法回答 |
| q070 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q071 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q072 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q073 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q074 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q075 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q076 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q077 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q078 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q079 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q080 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q081 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q082 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q083 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q084 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q085 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q086 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q087 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q088 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q089 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q090 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q091 | sect_agg | ok | 否 | 根据现有资料无法回答 |
| q092 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q093 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q094 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q095 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q096 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q097 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q098 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q099 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
| q100 | sect_agg | ok | 否 | 未能从问题中识别出门派实体。 |
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
| q017 | art_lineage | ok | 否 | 根据现有资料无法回答 |
| q018 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q019 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q020 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q021 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q022 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q023 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q024 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q025 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q026 | art_lineage | ok | 否 | 根据现有资料无法回答 |
| q027 | art_lineage | ok | 否 | 根据现有资料无法回答 |
| q028 | art_lineage | ok | 否 | 根据现有资料无法回答 |
| q029 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q030 | art_lineage | ok | 否 | 根据现有资料无法回答 |
| q031 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q032 | art_lineage | ok | 否 | 根据现有资料无法回答 |
| q033 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q034 | art_lineage | ok | 是 | 西毒 |
| q035 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q036 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q037 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q038 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q039 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q040 | art_lineage | ok | 否 | 根据现有资料无法回答 |
| q041 | art_lineage | ok | 否 | 根据现有资料无法回答 |
| q042 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q043 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q044 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q045 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q046 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q047 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q048 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q049 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q050 | art_lineage | ok | 否 | 根据现有资料无法回答 |
| q051 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q052 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q053 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q054 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q055 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q056 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q057 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q058 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q059 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q060 | art_lineage | ok | 是 | 小龙女 |
| q061 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q062 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q063 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q064 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q065 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q066 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q067 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q068 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q069 | art_lineage | ok | 否 | 根据现有资料无法回答 |
| q070 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q071 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q072 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q073 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q074 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q075 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q076 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q077 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q078 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q079 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q080 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q081 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q082 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q083 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q084 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q085 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q086 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q087 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q088 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q089 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q090 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q091 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q092 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q093 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q094 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q095 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q096 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q097 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q098 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q099 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q100 | art_lineage | ok | 否 | 未能从问题中识别出武功实体。 |
| q001 | person_relation | ok | 是 | 郭啸天 |
| q002 | person_relation | ok | 是 | 李萍 |
| q003 | person_relation | ok | 是 | 黄药师 |
| q004 | person_relation | ok | 是 | 包惜弱 |
| q005 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q006 | person_relation | ok | 是 | 黄蓉 |
| q007 | person_relation | ok | 是 | 包惜弱 |
| q008 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q009 | person_relation | ok | 是 | 黄蓉 |
| q010 | person_relation | ok | 是 | 郭靖 |
| q011 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q012 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q013 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q014 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q015 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q016 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q017 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q018 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q019 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q020 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q021 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q022 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q023 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q024 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q025 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q026 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q027 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q028 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q029 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q030 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q031 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q032 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q033 | person_relation | ok | 是 | 拖雷 |
| q034 | person_relation | ok | 是 | 欧阳锋 |
| q035 | person_relation | ok | 是 | 黄药师 |
| q036 | person_relation | ok | 否 | 根据现有资料无法回答 |
| q037 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q038 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q039 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q040 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q041 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q042 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q043 | person_relation | ok | 是 | 郭靖 |
| q044 | person_relation | ok | 否 | 根据现有资料无法回答。 |
| q045 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q046 | person_relation | ok | 否 | 根据现有资料无法回答 |
| q047 | person_relation | ok | 是 | 成吉思汗 |
| q048 | person_relation | ok | 否 | 根据现有资料无法回答 |
| q049 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q050 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q051 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q052 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q053 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q054 | person_relation | ok | 是 | 黄药师、洪七公 |
| q055 | person_relation | ok | 是 | 杨过 |
| q056 | person_relation | ok | 是 | 杨康 |
| q057 | person_relation | ok | 是 | 穆念慈 |
| q058 | person_relation | ok | 是 | 小龙女 |
| q059 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q060 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q061 | person_relation | ok | 是 | 杨过、公孙止、谷主、公孙先生 |
| q062 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q063 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q064 | person_relation | ok | 是 | 张翠山 |
| q065 | person_relation | ok | 是 | 殷素素 |
| q066 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q067 | person_relation | ok | 是 | 周芷若、赵敏、殷离、小昭 |
| q068 | person_relation | ok | 是 | 察罕特穆尔（汝阳王） |
| q069 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q070 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q071 | person_relation | ok | 是 | 杨过 |
| q072 | person_relation | ok | 否 | 根据现有资料无法回答。 |
| q073 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q074 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q075 | person_relation | ok | 是 | 郭襄 |
| q076 | person_relation | ok | 是 | 郭芙 |
| q077 | person_relation | ok | 是 | 郭靖 |
| q078 | person_relation | ok | 是 | 黄蓉 |
| q079 | person_relation | ok | 是 | 黄蓉 |
| q080 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q081 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q082 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q083 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q084 | person_relation | ok | 否 | 根据现有资料无法回答。 |
| q085 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q086 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q087 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q088 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q089 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q090 | person_relation | ok | 否 | 根据现有资料无法回答。 |
| q091 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q092 | person_relation | ok | 否 | 根据现有资料无法回答 |
| q093 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q094 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q095 | person_relation | ok | 否 | 根据现有资料无法回答 |
| q096 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q097 | person_relation | ok | 是 | 杨过、公孙止、谷主、公孙先生 |
| q098 | person_relation | ok | 是 | 黄蓉 |
| q099 | person_relation | ok | 否 | 根据现有资料无法回答 |
| q100 | person_relation | ok | 否 | 未能识别问题涉及的关系类型。 |
| q001 | cross_novel | ok | 否 | 没有找到满足时代差异条件的跨书人物关联。 |
| q002 | cross_novel | ok | 否 | 根据现有资料无法回答。 |
| q003 | cross_novel | ok | 否 | 没有找到满足时代差异条件的跨书人物关联。 |
| q004 | cross_novel | ok | 是 | 包惜弱 |
| q005 | cross_novel | error | 否 | KeyError: '丐帮' |
| q006 | cross_novel | ok | 否 | 没有找到满足时代差异条件的跨书人物关联。 |
| q007 | cross_novel | error | 否 | KeyError: '全真教' |
| q008 | cross_novel | ok | 否 | 没有找到满足时代差异条件的跨书人物关联。 |
| q009 | cross_novel | ok | 否 | 没有找到满足时代差异条件的跨书人物关联。 |
| q010 | cross_novel | ok | 否 | 没有找到满足时代差异条件的跨书人物关联。 |
| q011 | cross_novel | error | 否 | KeyError: '桃花岛' |
| q012 | cross_novel | ok | 否 | 没有找到满足时代差异条件的跨书人物关联。 |
| q013 | cross_novel | error | 否 | KeyError: '桃花岛' |
| q014 | cross_novel | ok | 是 | 黄药师 |
| q015 | cross_novel | error | 否 | KeyError: '轻功' |
| q016 | cross_novel | error | 否 | KeyError: '桃花岛' |
| q017 | cross_novel | ok | 否 | 没有找到满足时代差异条件的跨书人物关联。 |
| q018 | cross_novel | ok | 否 | 根据现有资料无法回答 |
| q019 | cross_novel | ok | 否 | 没有找到满足时代差异条件的跨书人物关联。 |
| q020 | cross_novel | error | 否 | KeyError: '轻功' |
| q021 | cross_novel | error | 否 | KeyError: '桃花岛' |
| q022 | cross_novel | error | 否 | KeyError: '大理' |
| q023 | cross_novel | error | 否 | KeyError: '全真教' |
| q024 | cross_novel | error | 否 | KeyError: '天罡北斗阵' |
| q025 | cross_novel | ok | 否 | 没有找到满足时代差异条件的跨书人物关联。 |
| q026 | cross_novel | ok | 否 | 没有找到满足时代差异条件的跨书人物关联。 |
| q027 | cross_novel | ok | 否 | 根据现有资料无法回答 |
| q028 | cross_novel | error | 否 | KeyError: '桃花岛' |
| q029 | cross_novel | error | 否 | KeyError: '大理' |
| q030 | cross_novel | ok | 否 | 没有找到满足时代差异条件的跨书人物关联。 |
| q031 | cross_novel | ok | 否 | 没有找到满足时代差异条件的跨书人物关联。 |
| q032 | cross_novel | ok | 否 | 根据现有资料无法回答。 |
| q033 | cross_novel | ok | 否 | 没有找到满足时代差异条件的跨书人物关联。 |
| q034 | cross_novel | ok | 否 | 没有找到满足时代差异条件的跨书人物关联。 |
| q035 | cross_novel | ok | 否 | 没有找到满足时代差异条件的跨书人物关联。 |
| q036 | cross_novel | ok | 是 | 陈玄风、梅超风 |
| q037 | cross_novel | error | 否 | KeyError: '桃花岛' |
| q038 | cross_novel | error | 否 | KeyError: '桃花岛' |
| q039 | cross_novel | error | 否 | KeyError: '桃花岛' |
| q040 | cross_novel | error | 否 | KeyError: '桃花岛' |
| q041 | cross_novel | ok | 否 | 根据现有资料无法回答。 |
| q042 | cross_novel | error | 否 | KeyError: '桃花岛' |
| q043 | cross_novel | ok | 否 | 根据现有资料无法回答。 |
| q044 | cross_novel | error | 否 | KeyError: '桃花岛' |
| q045 | cross_novel | error | 否 | KeyError: '桃花岛' |
| q046 | cross_novel | ok | 否 | 根据现有资料无法回答 |
| q047 | cross_novel | ok | 否 | 根据现有资料无法回答 |
| q048 | cross_novel | ok | 是 | 黄蓉 |
| q049 | cross_novel | error | 否 | KeyError: '天罡北斗阵' |
| q050 | cross_novel | ok | 否 | 根据现有资料无法回答。 |
| q051 | cross_novel | error | 否 | KeyError: '桃花岛' |
| q052 | cross_novel | error | 否 | KeyError: '桃花岛' |
| q053 | cross_novel | error | 否 | KeyError: '天罡北斗阵' |
| q054 | cross_novel | error | 否 | KeyError: '桃花岛' |
| q055 | cross_novel | ok | 否 | 没有找到满足时代差异条件的跨书人物关联。 |
| q056 | cross_novel | error | 否 | KeyError: '丐帮' |
| q057 | cross_novel | ok | 是 | 穆念慈 |
| q058 | cross_novel | error | 否 | KeyError: '丐帮' |
| q059 | cross_novel | ok | 否 | 杨过 |
| q060 | cross_novel | error | 否 | KeyError: '丐帮' |
| q061 | cross_novel | error | 否 | KeyError: '剑法' |
| q062 | cross_novel | ok | 是 | 灭绝师太 |
| q063 | cross_novel | ok | 否 | 根据现有资料无法回答 |
| q064 | cross_novel | ok | 是 | 张翠山 |
| q065 | cross_novel | error | 否 | KeyError: '丐帮' |
| q066 | cross_novel | ok | 是 | 谢逊 |
| q067 | cross_novel | ok | 否 | 根据现有资料无法回答 |
| q068 | cross_novel | error | 否 | KeyError: '丐帮' |
| q069 | cross_novel | ok | 否 | 根据现有资料无法回答 |
| q070 | cross_novel | ok | 否 | 没有找到满足时代差异条件的跨书人物关联。 |
| q071 | cross_novel | error | 否 | KeyError: '丐帮' |
| q072 | cross_novel | ok | 否 | 根据现有资料无法回答 |
| q073 | cross_novel | ok | 否 | 根据现有资料无法回答 |
| q074 | cross_novel | ok | 否 | 谢逊 |
| q075 | cross_novel | ok | 否 | 没有找到满足时代差异条件的跨书人物关联。 |
| q076 | cross_novel | ok | 否 | 没有找到满足时代差异条件的跨书人物关联。 |
| q077 | cross_novel | error | 否 | KeyError: '剑法' |
| q078 | cross_novel | ok | 是 | 黄蓉 |
| q079 | cross_novel | ok | 是 | 黄蓉 |
| q080 | cross_novel | error | 否 | KeyError: '桃花岛' |
| q081 | cross_novel | error | 否 | KeyError: '剑法' |
| q082 | cross_novel | ok | 是 | 西毒 |
| q083 | cross_novel | ok | 是 | 黄药师 |
| q084 | cross_novel | ok | 否 | 根据现有资料无法回答。 |
| q085 | cross_novel | ok | 是 | 明教 |
| q086 | cross_novel | error | 否 | KeyError: '峨嵋派' |
| q087 | cross_novel | error | 否 | KeyError: '明教' |
| q088 | cross_novel | ok | 否 | 根据现有资料无法回答。 |
| q089 | cross_novel | ok | 是 | 武当派 |
| q090 | cross_novel | error | 否 | KeyError: '丐帮' |
| q091 | cross_novel | error | 否 | KeyError: '轻功' |
| q092 | cross_novel | error | 否 | KeyError: '九阴真经' |
| q093 | cross_novel | error | 否 | KeyError: '峨嵋派' |
| q094 | cross_novel | error | 否 | KeyError: '峨嵋派' |
| q095 | cross_novel | ok | 否 | 根据现有资料无法回答。 |
| q096 | cross_novel | error | 否 | KeyError: '桃花岛' |
| q097 | cross_novel | error | 否 | KeyError: '桃花岛' |
| q098 | cross_novel | ok | 是 | 黄蓉 |
| q099 | cross_novel | error | 否 | KeyError: '九阴真经' |
| q100 | cross_novel | error | 否 | KeyError: '桃花岛' |
