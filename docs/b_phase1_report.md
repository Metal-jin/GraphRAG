# B 任务阶段一交付说明 —《射雕英雄传》知识图谱构建

- **提交分支**：`feature/b-ingest`
- **日期**：2026-09-07
- **执行环境**：conda env `hu`（Python 3.10.21）；Neo4j 5-community（Docker 容器 `neo4j-graphrag`）；抽取模型 DeepSeek
- **负责人**：B（数据 + 图谱构建）

## 一、交付内容

| 模块 | 文件 | 说明 |
|---|---|---|
| 语料切块 | `src/ingest/corpus.py` | 章节 + 滑窗切块（600 字/块，重叠 80），输出 1,789 块 |
| LLM 抽取入库 | `src/ingest/build_kg.py` | 调用 LLM 抽取实体/关系，MERGE 幂等入库 Neo4j；checkpoint 断点续跑；支持 `--era`（阶段二扩书零改码） |
| 数据接口 | `src/ingest/data_loader.py` | `get_chunks` / `get_graph(era=)` / `search_by_vector` / `search_by_text` / `run_query(cypher, params)`（给 D 的通用 Cypher 入口，含三种策略示例） |
| 图谱清洗 | `src/ingest/clean_graph.py` | 幂等；别名归并 + 噪声剔除；`--dry-run` / `--audit` |
| 单元测试 | `tests/test_kg_builder.py` + `tests/test_clean_graph.py` | **41 用例全绿**（mock，不依赖真实 Neo4j/LLM） |
| 一键流水线 | `scripts/build_kg.ps1` | `-Limit 20` 小批量试跑 / 全量 / `-Resume` 断点续跑 / `-DryRun` |

## 二、图数据规模（清洗后，已入库）

| 指标 | 数值 |
|---|---|
| 语料 | 《射雕英雄传》精校全文，1,060,073 字，1,789 文本块 |
| 实体（节点） | **1,621** = 人物 739 / 地点 492 / 武功 331 / 门派 59 |
| 关系（边） | **2,964**（去 MENTIONS） |
| era 属性 | **100% = 射雕**（跨书提及已归一） |
| 溯源边 MENTIONS | 14,037（块 → 实体，可回查原文） |

关系 10 种全覆盖：ENEMY_OF 984、MASTERS 524、MASTER_OF 464、BELONGS_TO 369、LOCATED_IN 285、PARENT_OF 188、SPOUSE_OF 148、SWORN_BROTHER_OF 140、FOUNDER_OF 25、**BRANCHED_FROM 12**（净衣派→丐帮、摩尼教→明教、降龙十八掌→降龙二十八掌 等，语义已验证）。

- 本体：人物/门派/武功/地点（中文 label）；层次结构 **门派→人物→武功**；武功传承由 MASTER_OF+MASTERS 组合推导，不单独抽关系。
- 双向关系（ENEMY_OF/SPOUSE_OF/SWORN_BROTHER_OF/PARENT_OF）已展开双向边，PPR 可直接游走。
- 索引就绪：向量 `text_embeddings` + 全文 `text_fulltext`，检索接口全部可用。

## 三、已执行的清洗（2026-09-07，方案 B）

1. **别名归并 21 → 11 组**：九指神丐/北丐/洪帮主/洪恩师→洪七公；东邪/黄岛主→黄药师；西毒/欧阳先生→欧阳锋；老顽童→周伯通；中神通/重阳真人→王重阳；南帝/段智兴→一灯大师；长春子→丘处机；丹阳子→马钰；蓉儿→黄蓉；靖哥哥→郭靖；江南六怪/江南七侠/六怪→江南七怪。边与 MENTIONS 溯源全部迁移。
2. **噪声剔除 5 项**：师父(66 度)/大师父/白雕/汗血宝马/小红马（仅剔除"人物"标签，动物地点节点保留）。
3. 效果：实体 1,646→1,621、关系 3,139→2,964；脚本幂等，复跑无事可做。

## 四、已知问题（诚实清单）

1. **MASTERS(武功) 少量武功名与归属错配**（如桃花岛下出现罗汉拳）——LLM 抽取噪声，未处理。
2. **MASTER_OF 少量方向反置**（弟子/师父颠倒）——未处理。
3. 残余别名/噪声：个别指称实体（"渔樵耕读"集体名词）、门派标签异类节点（江南六怪/江南七侠/东邪 as 门派）——影响小。
4. Neo4j 驱动告警 `id()` deprecated（仅告警，不影响）。

以上属 LLM 抽取固有噪声，检索侧（PPR + 图谱过滤）可部分容忍；如需更干净可跑方案 C（LLM 二次校验，另计 token）。

## 五、复现步骤（给队友/评测）

```powershell
# 1. 启动 Neo4j（Docker）
docker start neo4j-graphrag        # 容器映射：浏览器 17474，Bolt 7687

# 2. 配置 .env（gitignore，本地自建）
#    NEO4J_URI=bolt://localhost:7687
#    NEO4J_USER=neo4j
#    NEO4J_PASSWORD=***
#    LLM_TOKEN=***   # DeepSeek，仅重跑抽取时需要

# 3. 依赖
pip install -r requirements.txt    # neo4j / openai / python-dotenv

# 4. 测试
$env:PYTHONUTF8='1'; $env:PYTHONPATH='src'
python -m pytest tests/ -q          # 41 passed（mock，不需 Neo4j/LLM）

# 5. 重跑抽取（可选，全量 1,789 块约 1,789 次 LLM 调用）
powershell -File scripts/build_kg.ps1 -Limit 20    # 先小批量
powershell -File scripts/build_kg.ps1 -Resume      # 断点续跑全量
```

## 六、数据接口速查（供 D 使用）

见 `src/ingest/data_loader.py` docstring：`run_query` 内置三种领域策略 Cypher 示例（师徒链 / 门派聚合 / 武功传承）。`get_graph(era='射雕')` 支持按时代过滤，阶段二扩书后即按 era 分流。

## 七、阶段二展望

代码从第一版即支持 `era` 字段；阶段二换《神雕》《倚天》语料后以 `--era 神雕/倚天` 参数运行即可，无需改代码。新增语料建议按人物跨书同一性补充别名表后再清洗。
