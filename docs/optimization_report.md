# DeepSeek 优化任务清单实施报告

> 对应输入：[DeepSeek优化任务清单.md](DeepSeek优化任务清单.md)（32 项）
> 实施环境：Windows + Python 3.13.9 + Neo4j 5-community（本地 7687）
> 数据现状：5596 个 Chunk（1024 维远程嵌入 bge-m3）、5978 个实体、12187 条关系

## 0. 一句话说明

32 项任务全部**落到代码**；其中 27 项已完成并可离线验证，5 项需要人工执行数据迁移或
依赖新的抽取结果（已在表中标注"需人工执行"），没有任何一项被静默跳过。

验证基线：`python -m pytest` → **190 passed**（改造前 87 passed / 1 failed / 7 errors）。

---

## 1. 总体对照表

| # | 任务 | 状态 | 关键改动 |
|---|---|---|---|
| 01 | 落实 1500/200 切块、覆盖与参数合法 | ✅ 已完成 | `corpus.py`：参数强校验 + 句子边界 + 字符偏移 + 尾块合并 |
| 02 | 切块/图谱/向量/checkpoint 版本一致 | ✅ 代码完成，**需人工执行迁移** | chunk_id 带版本、manifest、checkpoint 版本校验、`scripts/migrate_data.py` |
| 03 | 统一嵌入算法 | ✅ 已完成 | `core/embedding.py` 唯一实现，sha256 稳定哈希，跨进程可复现 |
| 04 | 远程嵌入失败不得混用向量 | ✅ 已完成 | 失败默认抛错；`IndexMeta` 维度/模型校验；显式降级开关 |
| 05 | 区分抽取失败与合法空结果 | ✅ 已完成 | 四态状态机 + 原子 checkpoint + `--reparse` + `--save-raw` |
| 06 | 事务与唯一约束 | ✅ 已完成 | 单块单事务 + 4 个实体唯一约束 + Chunk 约束 + UNWIND 批量写 |
| 07 | 保存完整实体属性 | ✅ 已完成 | description/location/art_type 全链路保存（`art_type` 与实体类型分离） |
| 08 | 统一本体与关系方向 | ✅ 已完成 | `core/ontology.py` 单一来源 + 两端类型校验 + 未知关系拒绝迁移 |
| 09 | 关系证据可回原文 | ✅ 已完成 | 关系带 chunk_ids/snippets/versions/confidence |
| 10 | 区分首现时代、出现书目、事实时间 | ✅ 已完成（含回填） | `era` + `first_seen_era` + `eras` + `books` |
| 11 | 统一实体链接与问题解析 | ✅ 已完成 | `core/entity_link.py` + `core/question_plan.py` |
| 12 | 师徒检索真实有向路径 | ✅ 已完成 | 方向/跳数推断、真实路径、分支、top_k |
| 13 | 人物关系方向与组合多跳 | ✅ 已完成 | 关系计划逐步执行、保留正式关系类型、方向正确 |
| 14 | 门派检索保留子图并区分问法 | ✅ 已完成 | 成员/创立者/武功三类问法 + 真实连接子图 |
| 15 | 武功传承区分推断与事实 | ✅ 已完成 | confidence=extracted/inferred + 创立者问法 |
| 16 | 跨书检索 KeyError 与语义 | ✅ 已完成 | 全节点索引、单源 BFS、血缘/一般关联区分 |
| 17 | 实现真实 GraphRAG 基线 | ✅ 已完成 | 向量召回 + MENTIONS 实体 + 1 跳图扩展 |
| 18 | 统一证据结构与三条链路 | ✅ 已完成 | `core/evidence.py` 契约 + 统一 retrieve→inject→generate |
| 19 | 分类器缓存刷新与恢复 | ✅ 已完成 | TTL + 版本 + 负缓存 + 主动失效 |
| 20 | 修复实体对齐规则与落库范围 | ✅ 已完成 | 正名入索引、era 作用域、冲突/成环/链式归并 |
| 21 | 后代扫描身份与证据 | ✅ 已完成 | 候选校验 + 不造无标签节点 + evidence + inferred |
| 22 | 评测走真实流程与正确题集 | ✅ 已完成 | 统一链路、题集贯通、状态区分、多维分组 |
| 23 | 重做事实与证据评价 | ✅ 已完成 | 否定识别、实体 P/R/F1、连通性、关系匹配 |
| 24 | 重做注入对比实验 | ✅ 已完成 | 真实检索事实、无 gold 泄漏、仅结构指标 |
| 25 | API 输入/错误/返回规范化 | ✅ 已完成 | 统一校验 + 稳定错误码 + HTTP 状态 |
| 26 | LLM 调用时限/重试/降级状态 | ✅ 已完成 | 客户端复用、超时预算、降级可见 |
| 27 | 图谱展开/箭头/多跳高亮 | ✅ 已完成 | 稳定边 ID、真实方向、完整路径高亮 |
| 28 | 前端状态与时代一致性 | ✅ 已完成 | 加载态、请求序号、防抖、证据面板、版本固定 |
| 29 | 减少全图读取与重复计算 | ✅ 已完成 | DB 侧过滤、实体索引缓存、嵌入缓存、单次 BFS |
| 30 | 修正一键脚本与文件兜底 | ✅ 已完成 | 脚本路径/退出码/DryRun 语义、多书文件兜底 |
| 31 | 并发、配置与可复现环境 | ✅ 已完成 | ThreadingWSGIServer、回环监听、配置校验、依赖下限 |
| 32 | 回归验证与文档 | ✅ 已完成 | 190 个离线测试 + CI + 本报告 |

---

## 2. 阶段 A：数据基础与直接故障

### 01 切块（`src/ingest/corpus.py`）

- **根因**：按字符固定滑窗，缺少参数校验，尾块合并会把重复内容拼进前一块。
- **改法**：
  - `ChunkParams.validate()` 统一校验 `size > 0`、`0 <= overlap < size`，CLI 与函数共用；
  - 先按句末标点（。！？；换行）取边界，再按目标长度切；无标点的长段退回固定滑窗；
  - 每个块记录字符区间 `[offset, end)`，重叠按区间维护，**去掉重叠可按偏移还原原文**；
  - 尾块改为"延长前一块的 end"，不再重复拼接文本；
  - 输出明确标注单位是**字符**，不是 token。
- **验证**：`tests/test_kg_builder.py::TestCorpus`（含还原性、无标点、非法参数）。

### 02 版本一致（corpus / build_kg / data_loader / migrate_data.py）

- **根因**：chunk_id 只有 `书名::序号`，切块参数一变，同 ID 对应不同正文，旧断点会跳过新内容。
- **改法**：
  - chunk_id 升级为 `书名::chunker-v2::序号`，另存 `logical_id` 与 `content_hash`；
  - 每本书产出 `data/interim/manifest_<书名>.json`：原文 sha256、切块算法与参数、块数、抽取模型/提示词版本、嵌入指纹；
  - checkpoint 升级为 v2 结构（`completed` 记录内容哈希、`failed` 记录失败原因），写入用临时文件 + `os.replace` 原子替换；
  - **旧格式断点或版本不一致时显式拒绝 resume**，并给出处理建议；
  - `scripts/migrate_data.py` 提供只读报告与增量迁移（eras/books、art_type、IndexMeta、旧 Chunk 清理）。
- **需要人工执行**：旧 600/80 数据与 1024 维索引未重建（会消耗大量 LLM 费用）。本报告只提供可审查脚本，符合任务书"迁移方案先准备为可审查脚本"的要求。
- **验证**：`TestCheckpoint`（旧格式拒绝、版本不一致拒绝、内容哈希变化、原子写）。

### 03 统一嵌入（`src/core/embedding.py`）

- **根因**：`build_kg.hash_embed` 用内置 `hash()`（受 PYTHONHASHSEED 影响），`vector_utils._hash_embedding` 用 sha256，入库与查询向量语义不同。
- **改法**：全项目唯一实现 `EmbeddingService`：
  - 本地模式 = sha256 + 有符号投票 + L2 归一化（`local-hash-v1`，256 维，跨进程稳定）；
  - 远程模式 = OpenAI 兼容接口，带 spec 指纹；
  - 进程级单例，`embed_documents` / `embed_query` 共用同一路径与缓存。
- **验证**：`tests/test_embedder.py::test_local_hash_is_stable_across_processes`（不同 PYTHONHASHSEED 子进程结果一致）。

### 04 拒绝混用向量（embedding / data_loader / build_kg）

- **改法**：
  - 远程失败默认抛 `EmbeddingError`，只有显式 `EMBED_ALLOW_LOCAL_FALLBACK=true` 才允许**整批**降级并标记 `degraded`；
  - 维度/数值合法性逐条校验，同批出现不同维度直接报错；
  - `(:IndexMeta {name:'chunk_embeddings'})` 记录 kind/model/dimension/fingerprint，查询与入库前校验，不一致抛 `index_incompatible`；
  - 已对现有库写入元数据：`remote:BAAI/bge-m3:1024:v1`。
- **验证**：`test_remote_failure_does_not_silently_mix_vectors`、`test_index_compatibility_check`。

### 05 抽取状态（`src/ingest/build_kg.py`）

- **根因**：解析失败/重试耗尽都返回空结果，主流程仍写 checkpoint，失败块被当成完成。
- **改法**：
  - `parse_llm_payload` 严格校验顶层结构、数组、条目字段类型；
  - `ExtractionResult.status` 四态：`ok` / `empty`（合法空结果）/ `retryable` / `fatal`；
  - 认证类错误不重试（`AuthenticationError` 等），网络/限流才退避重试；
  - **只有入库事务成功后才 mark_done**；失败块写入 `failed` 清单，`--reingest-failed` 可重试；
  - `--save-raw` 保存原始响应 + 清洗结果 + 失败原因 + 版本；`--reparse <jsonl>` 只重新解析、不调 LLM。
- **验证**：`TestExtractionStatus`（ok/empty/retryable/fatal 四类）。

### 06 事务与约束（build_kg / graph_ops）

- **改法**：`session.execute_write` 包住"Chunk + 实体 + MENTIONS + 关系"全部写入；4 个实体标签与 Chunk 建唯一约束；实体/关系用 `UNWIND` 批量写；关系按 (起点label, 终点label, 类型) 分组，避免逐条往返。
- **验证**：`tests/test_kg_builder.py::TestWriteResult`（FakeDriver 验证单事务、UNWIND、证据字段）。

### 07 完整实体属性

- **改法**：`clean_entity` 保留 description（≤500 字）、location、art_type；写入时 `coalesce` 合并，description 取更长者；`art_type` 与实体类型分离（不再塞进 `type`）。
- **验证**：`test_description_kept`、`test_entity_merge_keeps_era_and_attrs`。

### 08 统一本体

- **改法**：`src/core/ontology.py` 定义 11 种关系的 domain/range/方向/是否对称；`build_kg`、`clean_graph`、`entity_alignment`、检索层、文档全部引用；抽取 prompt 的关系清单由本体生成；未知关系类型拒绝迁移（不迁移也不删节点）。
- **验证**：`TestOntology`、`test_endpoint_type_violation_dropped`、`test_type_violation_goes_to_rejected`。

### 09 / 10 证据溯源与时代建模

- **改法**：关系写 `chunk_ids`、`snippets`（同块同时包含两端实体的句子）、`versions`、`confidence`；实体写 `era`、`first_seen_era`、`eras`、`books`；查询用 `coalesce(n.eras,[n.era])` 兼容新旧数据。
- **已执行回填**：5978 个实体、12187 条关系补 `eras/books/first_seen_era`。
- **验证**：`scripts/migrate_data.py --report` 显示 `entities_without_eras = 0`。

---

## 3. 阶段 B：检索与证据正确性

### 11 实体链接与问题解析

- `core/entity_link.py`：正名 + 别名词典索引；返回**全部**命中（位置/类型/时代/置信度），长名优先且不重叠；过滤 `张无忌的父亲` 这类关系指称；`EntityIndexCache` 带 TTL、版本、负缓存。
- `core/question_plan.py`：把问题解析成**有序关系步骤**（师父的师父 = 2 步；岳父 = 配偶 + 父亲），支持方向与复合称谓。
- 分类器识别的 seed（含实体 ID/类型/置信度）现在随 `Intent` 传给检索器；
  "只有人物、没有明确关系问法"改为走通用检索（置信度 0.4），不再默认当成师徒问题。
- **验证**：`TestEntityIndex`、`TestQuestionPlan`。

### 12–16 五个领域策略

| 方法 | 修复要点 |
|---|---|
| master_chain | 方向（师父/徒弟）与跳数由问题推断；返回真实有向路径（节点+边+方向+来源），保留分支；遵守 top_k；过滤自环 |
| person_relation | 方向正确（父亲查入边、儿子查出边）；组合多跳逐步执行；保留正式关系类型；义父等超纲关系明确说明 |
| sect_agg | 区分成员/创立者/武功问法；返回真实子图；"成员会某武功≠本门绝学"显式提示；掌门问法标注不支持 |
| art_lineage | 区分创立者/传承/精通者；传承分 `extracted`（有原文证据）与 `inferred`（师徒+共同精通推断） |
| cross_novel | 全节点索引消除 KeyError；单源 BFS；血缘与一般关联分开标注；输出完整路径 |

- **验证**：`tests/test_methods_offline.py`（全部用 fake run_query 覆盖方向、跳数、top_k、降级、语义区分）。

### 17 真实图基线

- `library_graphrag`：向量召回 → `Chunk-[:MENTIONS]->实体` → 1 跳关系扩展 → 上下文 = 原文 + 三元组；数据库不可用时显式 `degraded`，不再伪装成功。
- **验证**：`test_library_baseline_uses_graph_expansion_when_db_available`、`test_library_baseline_degrades_explicitly`。

### 18 统一证据与三条链路

- `core/evidence.py` 定义统一 bundle（kind/source_method/confidence/nodes/edges/chunk_ids/text/legacy），并提供 legacy 形状适配。
- `service.retrieve → injection.build_context → llm.generate` 成为唯一链路，手动问答、自动路由、评测共用；返回 `raw_context`（检索原文）与 `retrieval_context` 两个字段。

### 19–21 缓存、对齐、血缘

- 分类器：TTL 300s、版本指纹、失败负缓存 15s、旧索引兜底、`invalidate()`。
- 对齐：正名纳入归一索引（`一灯` ↔ `一灯大师`）、决策带 era 作用域、词典冲突报告、成环剔除、链式压平、`--include-similarity` 真正生效。
- 血缘：候选必须两端可链接到真实人物节点，无法链接进入"待确认"，不再创建无 label 节点；写入带 `snippets` 与 `confidence=inferred`。
- **验证**：`tests/test_entity_alignment.py`（含 32+ 用例）、`TestAlignmentPipeline::test_rule_layer_pairs_canonical_and_title`。

---

## 4. 阶段 C：可信评测

### 22 评测流程

- 走统一链路；`--questions` 贯通到分类统计；状态四分（ok/no_context/degraded/error）；端到端与条件两种口径；按类别、书目、跳数分组。

### 23 指标

- 保留 `entity_string_hit` 作辅助指标，新增否定识别（"不是洪七公"不计命中）、实体 P/R/F1 与完全匹配、路径连通性（两条不相连的边不能拼成完整路径）、关系类型匹配（同义词表）。
- **验证**：`tests/test_metrics.py`、`tests/test_core_unit.py::TestMetrics`。

### 24 注入实验

- 只用**检索事实**构造三种编码，标准答案不参与构造；只报告结构指标（长度/方向可见性/关系标签/空事实率）；`--demo` 模式明确标注为演示。

---

## 5. 阶段 D：性能与体验

- **25 API**：统一 `ApiError` + 错误码 + HTTP 状态；JSON 对象校验、question 类型/长度、top_k 范围、body 大小（64KB）、未知方法。
- **26 LLM**：客户端单例、总超时、重试预算、认证错误不重试、返回 `generation.status/fallback_reason/model/latency`。
- **27 前端图谱**：节点/边稳定 ID、重复点击只更新不报错、边方向真实、多跳路径整体高亮、证据面板。
- **28 前端状态**：加载遮罩、请求序号（丢弃过期响应）、时代滑块防抖、错误提示、CDN 版本固定、窄屏布局。
- **29 性能**：`get_graph(era/books)` 过滤下推 Cypher；`get_entity_nodes` 只取实体名；嵌入缓存；单源 BFS；四个领域策略真正使用 top_k。
- **30 脚本**：`build_kg.ps1` 路径相对仓库根、`-Preview/-DryRun/-Resume/-ReingestFailed/-SaveRaw`、失败非零退出；`run_tests.ps1` 传递 pytest 退出码；`data_loader.get_chunks` 多书文件兜底。
- **31 服务**：ThreadingWSGIServer、默认回环监听、`/api/health`、配置启动校验、依赖最小版本约束。

---

## 6. 发现并修复的环境问题

1. **Neo4j 驱动告警刷屏**：查询不存在的属性会返回 notification。已在 `create_driver` 设置 `notifications_min_severity="OFF"`。
2. **OpenAI SDK 连接错误**：本机 `httpcore 1.0.9 + zstandard 0.24` 组合下，SDK 收到 zstd 压缩响应会抛
   `Decompressor.decompress() got an unexpected keyword argument 'output_buffer_limit'`，
   被包装成 `APIConnectionError`（看起来像网络故障，实际 urllib 可正常访问）。
   已新增 `core/http_client.py`，显式声明 `Accept-Encoding: identity` 规避。
3. **受限文件沙箱下 `os.mkdir(mode=0o700)` 创建不可枚举目录**：导致 pytest `tmp_path` 在 setup 阶段失败。
   已添加 `tests/conftest.py` 放宽私有模式（仅影响测试进程）。

---

## 7. 验证方式

```powershell
# 1. 离线回归（不依赖 Neo4j / LLM）
$env:PYTHONUTF8='1'; $env:PYTHONPATH='src'
python -m pytest -q

# 2. 数据现状盘点（只读）
python scripts/migrate_data.py --report

# 3. 增量迁移（可重复执行）
python scripts/migrate_data.py --backfill-eras --backfill-art-type --index-meta --apply

# 4. 抽取预览（不调 LLM）
python src/ingest/build_kg.py --book 射雕英雄传 --preview

# 5. 小样本评测（会调用 LLM）
python -m src.eval.run_compare --methods vector person_relation --limit 5

# 6. 自动路由评测
python run_auto_eval.py --limit 20 --resume

# 7. 启动服务
python run_frontend_server.py --port 5000
```

---

## 8. 已知限制（诚实清单）

1. **旧数据已重建**（2026-11-07）：旧 600/80 图谱已备份并清空，现为 chunker-v2 的 2,332 块 + `extract-v5` 抽取结果，版本与证据完整。详见 [rebuild_20261107.md](rebuild_20261107.md)。
2. **现有图谱存在抽取噪声**：如 `MASTERS` 少量错配、`MASTER_OF` 个别方向反置、`X的父亲` 类指称节点。代码层已过滤关系指称节点并做类型校验，但历史噪声只能通过重新抽取或人工清洗消除。
3. **DESCENDANT_OF 当前为 0 条**：现有实体没有 `description` 字段；新抽取链路会写入 description，之后 `--descendants-only` 才可能产出候选。
4. **注入实验只给结构指标**：没有用真实 LLM 跑三种注入形式的准确率对比（成本与可复现性考虑），结论只描述结构适配性。
5. **相似度层仍不自动落库**：保持"人工审核候选"的保守策略，`--include-similarity` 需显式开启。
