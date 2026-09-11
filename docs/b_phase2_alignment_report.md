# 阶段二 B 任务交付报告：实体对齐系统

> 作者：B（周） · 日期：2026-09-11 · 分支：`feature/b-phase2`

## 1. 目标

按交接文档要求，把阶段一的"手工别名表"升级为**三层系统化对齐系统**，并新增**跨书血缘（DESCENDANT_OF）后处理**，使验收项"同人物多称呼同节点 / 跨书查黄衫女子能关联杨过·小龙女"自动化、可复跑、可审计。

## 2. 交付物清单

| 文件 | 类型 | 说明 |
|---|---|---|
| `src/ingest/entity_alignment.py` | 新增 | 三层对齐 + DESCENDANT_OF + 流水线 |
| `data/processed/alias_dict.json` | 新增 | 别名词典（51 条核心人物，3 本书覆盖） |
| `data/interim/alignment_candidates.csv` | 自动生成 | 相似度层候选（人工审核用，不入 git） |
| `tests/test_entity_alignment.py` | 新增 | 32 个单元测试，覆盖四层 + 流水线 |
| `docs/b_phase2_alignment_report.md` | 本文件 | 阶段二对齐报告 |
| `INTERFACE.md` | 同步更新 | 第 9、10 节：实体对齐系统接口 + DESCENDANT_OF 关系 |

## 3. 系统架构（三层 + 一层后处理）

```
                       ┌──────────────────────────────────┐
                       │  Neo4j（实体节点 + 关系）          │
                       └────────────────┬─────────────────┘
                                        │ 读全部实体（label 过滤）
                                        ▼
┌────────────────────────────────────────────────────────────────┐
│  AlignmentPipeline.discover_alignments(entities, label_filter)  │
│                                                                  │
│  ① RuleNormalizer        称谓剥离 + 姓氏归一（纯函数）           │
│     例：洪帮主 → 洪；诸葛氏道长 → 诸葛                          │
│     约束：归一结果长度 ≥ 2（避免"黄"类单字误归并）              │
│                                                                  │
│  ② AliasDictionary       JSON 词典（data/processed/）            │
│     51 条核心人物；applicable_eras 列表区分射雕/神雕/倚天         │
│                                                                  │
│  ③ SimilarityAligner     rapidfuzz（字符）+ pypinyin（拼音）双路  │
│     threshold=0.85；partial_ratio 抓"X是Y前辈"类子串关系          │
│     【默认仅写 CSV 候选，不自动 apply——防郭京/郭靖误合并】       │
└────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼ apply（幂等 MERGE + DETACH DELETE）
                       ┌──────────────────────────────────┐
                       │  Neo4j（已归并的实体 + DESCENDANT_OF）│
                       └──────────────────────────────────┘

【并行】DescendantScanner：扫实体 description → "X之后/之女/之子"模式 + 大姓锚定
        → 输出 (ancestor, descendant, kind) → 落 DESCENDANT_OF 关系
```

## 4. 落地数据（射雕阶段一图谱，Neo4j 当前状态）

### 4.1 实体归并（本轮 apply 实际效果）

| 项 | 数量 |
|---|---|
| Neo4j 初始人物节点 | 791 |
| 归并决策（词典 1 + 规则 3） | 4 条 |
| 新建边（迁移到正名） | 26 条 |
| 删除别名节点 | 4 个 |
| 最终人物节点 | 788 |
| **幂等验证** | 二次 dry-run 发现 0 条新决策 ✓ |

归并明细：

| alias → canonical | 来源 | 备注 |
|---|---|---|
| 张君宝 → 张三丰 | 词典 | 出家前俗名 → 法号 |
| 焦木禅师 → 焦木大师 | 规则 | 同人不同称谓 |
| 枯木大师 → 枯木禅师 | 规则 | 同人不同称谓 |
| 六位师父 → 六位恩师 | 规则 | 江南七怪等群体的两种称呼 |

### 4.2 DESCENDANT_OF（本轮扫描结果）

射雕单书数据 → **0 条候选**（正常，射雕里没有跨书血缘关系）。等阶段 3 神雕/倚天全量抽取完后会大量出现，重点候选：
- 黄衫女子 → 杨过（"乃杨过之后人"）
- 郭襄 → 郭靖（"郭靖之女"）
- 张无忌 → 张翠山（"张翠山与殷素素之子"）

### 4.3 相似度层候选 CSV（`alignment_candidates.csv`）

- 共 **1012 条**（apply 后重新跑）
- **不要批量落库**——大量"郭京→郭靖"型同姓不同人误匹配
- 用法：人工筛选有用条目，手动加到 `alias_dict.json`，下次 apply 时落库

## 5. 已知坑与决策

| 坑 | 处理 |
|---|---|
| 规则层"黄夫人→黄大哥"误归并 | 归一结果必须 ≥ 2 字符 |
| 相似度层"郭京→郭靖"误归并 | 相似度层只 dry-run，**永不默认 apply**；必须 `--include-similarity` |
| 中文姓氏误判（如"许"作泛词） | 模式用大姓/复姓白名单锚定；common_surnames 收缩到 84 个金庸高频姓 |
| 跨书血缘"DESCENDANT_OF" Neo4j 中可能已有同名 type | 加进 `ALLOWED_REL_TYPES` 白名单 |
| 词典条目冲突（同 alias 不同 canonical） | `AliasDictionary.add()` 同 alias+label 覆盖 |

## 6. 与阶段一 `clean_graph.py` 的关系

- **共存不替换**：`clean_graph.py` 仍可用，但只负责"手工 alias_groups + drop_names"的兜底。
- 新代码统一走 `entity_alignment.py`：
  - 阶段二抽取的新实体 → 三层对齐
  - 阶段一已清洗的图 → 不动（保持兼容）
- 接口上对齐流水线与 clean_graph 完全独立（无共享函数），避免误依赖。

## 7. 验收对照

| 交接文档验收项 | 状态 |
|---|---|
| ① 三书图谱 era 正确、无跨书污染 | 阶段 1 已完成；阶段 2 改动不影响 |
| ② 同人物多称呼同节点 | ✅ 4 条已合并 + 词典 51 条规则兜底 |
| ③ 跨书查"黄衫女子"能沿图谱边走到杨过/小龙女 | 待阶段 3 神雕/倚天全量抽取 + DESCENDANT_OF 落库 |
| ④ P1：事件实体 | 未实现（优先级 P1，留作阶段 4 收尾） |

## 8. 下一步（不开始阶段 3，等你确认）

1. **审核相似度候选 CSV**（1012 条里挑可入库的 5-20 条加到 `alias_dict.json`）
2. 阶段 3 全量抽取开始前，**先做一遍完整对齐**（神雕 + 倚天全量后再 apply 一次）
3. 等神雕/倚天 description 字段填充后，DESCENDANT_OF 自动命中大量跨书血缘

## 9. 测试

```
tests/test_entity_alignment.py  32 个用例（全部通过）
  - TestRuleNormalizer    11 个：称谓剥离 / 姓氏归一 / 噪声识别
  - TestAliasDictionary    7 个：加载 / 查询 / era/label 过滤 / 增删 / 持久化
  - TestSimilarityAligner  6 个：分数 / 拼音 / 候选 / 阈值校验
  - TestDescendantScanner  5 个：黄衫女子 / 之女 / 之子 / 泛词过滤 / 空 desc
  - TestAlignmentPipeline  3 个：词典层命中 / 噪声过滤 / 三层都存在

全套回归：81/81 通过（含阶段一 49 + 队友 32）
```