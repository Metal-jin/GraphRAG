# 阶段三抽取任务交接说明（写给组长）

> 作者：B（周） · 日期：2026-09-11 · 接手分支：`feature/b-phase2`
> 上游：阶段一（射雕单书） + 阶段二（实体对齐系统），都在本分支上。

---

## 1. TL;DR（30 秒看完）

| 项 | 内容 |
|---|---|
| **分支** | `feature/b-phase2`（基于 `origin/main` 0fec94f，无领先 commit） |
| **Python 环境** | `D:\.conda\envs\hu\python.exe`（Python 3.10.21，所有依赖齐全） |
| **Neo4j** | 容器 `neo4j-graphrag`（`neo4j:5-community`，卷 `neo4j-data`，密码在 `.env`） |
| **数据现状** | 射雕已抽完并对齐；神雕 / 倚天 **试抽过 20 块**，全量（约 3800 块）待跑 |
| **本轮交付** | 阶段一代码 + 阶段二对齐系统 + 数据扩充入口（全量抽取脚本） |
| **关键命令** | `powershell -File scripts\build_kg.ps1 -Book 神雕侠侣` 一键跑全量 |

---

## 2. 你要接手的工作

按交接文档 §"B（数据 + 图谱构建）"，本轮 B 部分还有 **2 件大事** 没做完，全部接给组长：

### 任务 A：神雕 / 倚天全量抽取（阶段三）

| 子任务 | 工作量 | LLM 成本 |
|---|---|---|
| 抽取《神雕侠侣》全量 ~1906 块 | ~30 分钟 | ~¥10-15 |
| 抽取《倚天屠龙记》全量 ~1901 块 | ~30 分钟 | ~¥10-15 |

### 任务 B：跨书血缘 + 验收

| 子任务 | 工作量 | LLM 成本 |
|---|---|---|
| 阶段二对齐系统全量重新跑一次（神雕+倚天 description 填上后） | ~1 分钟 | ¥0 |
| DescendantScanner 跑出 DESCENDANT_OF 跨书血缘 | ~10 秒 | ¥0 |
| 验收"跨书查'黄衫女子'能关联杨过·小龙女" | ~5 分钟 | ¥0 |

> 任务 B 是任务 A 的下游，必须先 A 才能 B。

---

## 3. 抽取命令（全量 + 试抽 + 复跑 + 对齐）

### 环境准备（接手第一件事）

```powershell
# 0. 切到 feature/b-phase2 分支
cd D:\hu\GraphRAG
git checkout feature/b-phase2
git pull --ff-only

# 1. 激活 Python 环境（用户指定，全程不要换）
& "D:\.conda\envs\hu\python.exe" -V   # 应输出 Python 3.10.21

# 2. 安装/确认依赖（缺啥补啥，下面这三个是关键的新依赖）
& "D:\.conda\envs\hu\python.exe" -m pip install -U rapidfuzz pypinyin

# 3. 准备 .env（不要 commit！）
if (-Not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env  # 填 NEO4J_PASSWORD 和 LLM_TOKEN

# 4. 启动 Neo4j 容器
docker start neo4j-graphrag
```

> **为什么必须在 hu 环境跑**：用户的 LLM 客户端只挂在该环境，且 `.env` 里 LLM_TOKEN 是和这个环境配对的。换环境会读到空 token 报 401。

### 抽取命令

```powershell
# ---【试抽 20 块】先验环境通不通（每个书名各试一次，~3 分钟）
powershell -File scripts\build_kg.ps1 -Book 神雕侠侣 -Limit 20
powershell -File scripts\build_kg.ps1 -Book 倚天屠龙记 -Limit 20

# ---【全量抽取】推荐顺序：先神雕（共享实体多，方便验 era）
powershell -File scripts\build_kg.ps1 -Book 神雕侠侣

# ---【全量抽取】再倚天
powershell -File scripts\build_kg.ps1 -Book 倚天屠龙记

# ---【断点续跑】如果中途断网/重启，从断点继续（每本书独立）
powershell -File scripts\build_kg.ps1 -Book 神雕侠侣 -Resume
powershell -File scripts\build_kg.ps1 -Book 倚天屠龙记 -Resume
```

### 对齐 + 跨书血缘（任务 B）

```powershell
$env:PYTHONUTF8='1'    # Windows 必备，防中文乱码

# ---【dry-run 预览】先看会对哪些节点做什么，不改库
& "D:\.conda\envs\hu\python.exe" src\ingest\entity_alignment.py --dry-run

# ---【真改库】三层对齐（词典 + 规则 + 【默认不启用】相似度层）
& "D:\.conda\envs\hu\python.exe" src\ingest\entity_alignment.py --apply

# ---【只跑 DESCENDANT_OF】（任务 B 的核心，能命中"黄衫女子→杨过"等跨书血缘）
& "D:\.conda\envs\hu\python.exe" src\ingest\entity_alignment.py --apply --descendants-only

# ---【人工审核相似度候选】生成 CSV 自己审（默认行为，安全）
# 跑完上面 --dry-run 后看 data/interim/alignment_candidates.csv
# 挑可入库的加到 data/processed/alias_dict.json，下次 --apply 自动入库
```

---

## 4. 验收（按阶段二交接文档 §验收）

| 验收项 | 怎么验 | 通过标准 |
|---|---|---|
| ① 三书图谱 era 正确 | `data_loader.py` 跑一下，看图谱统计 | 三书实体数 ≈ 1650/1700/1700，无 book=null 残留 |
| ② 同人物多称呼同节点 | 查 "张三丰"、"黄药师"、"郭靖" 等人物 | 各 era 之间不重复，节点共享 |
| ③ **跨书查"黄衫女子"关联杨过** | 跑 DescendantScanner，再查 Neo4j：<br>`MATCH (h:人物 {name:'黄衫女子'})-[:DESCENDANT_OF*]->(x) RETURN x.name` | 命中杨过、小龙女 |
| ④ 全量归 0 错误 | 看任务 A 的控制台输出 | 应全程 0 Error |

---

## 5. 一定要看（约束 + 踩坑）

### 必读约束

| 约束 | 后果 / 怎么处理 |
|---|---|
| **绝不能 commit `.env`** | 真密钥/密码进 git 会被盗用；`.gitignore` 已挡，但 add 时眼睛看一遍 |
| **语料文件 `.txt` 不进 git** | `data/source/*` 已在 gitignore；接收时 .gitkeep 在，`.txt` 不在，OK |
| **中间产物 `data/interim/*` 不进 git** | check-points/CVS 都在里面，gitignore 已挡 |
| **抽取结果进 Neo4j 不进仓库** | 跟 D/E 用 `data_loader.run_query()` 实时查，不传 dump/JSON |
| **改接口先改 `INTERFACE.md`** | 见 §9/§10，阶段二加的 DESCENDANT_OF 关系类型已登记 |

### 必踩的坑（前任踩过）

1. **PowerShell 中文乱码** → 每个运行脚本/pytest 前必须 `$env:PYTHONUTF8='1'`，否则 GBK 代码页会爆 UnicodeDecodeError
2. **LLM 失败重试** → `build_kg.py` 内部已带 3 次重试，不用手动循环；若持续 `429 Too Many Requests`，停 5 分钟再 `-Resume`
3. **每本书独立 checkpoint** → `kg_checkpoint_<书名>.json`，别去手改，否则会重抽或漏抽
4. **共享实体保持首现 era** → 杨过 `era=射雕`（首次出现在射雕结尾），不重写为"神雕"。代价值得，是已确定的语义
5. **相似度层默认不 apply** → 防止"郭京→郭靖"误合并；想落库必须显式 `--include-similarity`
6. **跑 build_kg 千万别清空 Neo4j** → 它用 `MERGE` 增量入库，不会覆盖；只有 `entity_alignment.py --apply` 才会主动 `DETACH DELETE` 别名节点
7. **DescendantScanner 零候选正常** → 只有 description 字段写满时才能模式匹配；阶段一节点 description 可能为空，正常
8. **neo4j-graphrag 库的 CypherManager 函数已经废弃** → 用 `data_loader.run_query()` 自己拼 Cypher，更灵活

### 不要做的事

| ❌ 千万别做 | 原因 |
|---|---|
| 取消 `data/processed/` 的 gitignore 提交 alias_dict.json 以外的大文件 | 词典 JSON 8KB 没问题，CSV/dump 几 MB 不能进 git |
| 让队友重跑 build_kg 同步数据 | 重复花 LLM 钱、结果不一致 |
| 把 Neo4j 数据库 export 成 JSON 邮件发队友 | 失去图结构，队友还得写导入 |
| 在 `requirements.txt` 里加 `neo4j-graphrag` 之外的版本锁 | 用 `neo4j-graphrag>=1.0.0` 这种最小约束即可 |

---

## 6. 遇到问题怎么办

| 现象 | 排查 | 兜底 |
|---|---|---|
| `ModuleNotFoundError: rapidfuzz/pypinyin` | `pip list \| Select-String "rapidfuzz\|pypinyin"` | `$ pip install rapidfuzz pypinyin`（已加到 requirements.txt） |
| `Neo4j connection refused` | `docker ps \| Select-String neo4j` | `docker start neo4j-graphrag` |
| `401 Unauthorized` from LLM | `cat .env \| Select-String TOKEN` | 重新填 LLM_TOKEN（环境变了密钥会失效） |
| 测试报 UnicodeDecodeError | 看控制台最上方"charmap codec" | 重跑前 `$env:PYTHONUTF8='1'`，或用 `python -X utf8 ...` |
| `feature/b-phase2` 拉不到 | `git fetch origin` 看分支在不在 | 这个分支是阶段二新建的；找不到就 `git log origin/main` 看有没有被我误删 commit（无） |
| 试抽出现 era=未知 | `infer_era()` 词典里没这本书 | 在 `src/ingest/corpus.py` 的 `BOOK_TO_ERA` 加一行 |

> **联系人**：B（周）· 飞书群消息；遇到 `entity_alignment.py` 内层逻辑看不懂 / 想改对齐策略时再找我，前面的命令照搬就是。

---

## 7. 文件变更清单（本分支相对 origin/main）

```
新增：
  src/ingest/entity_alignment.py          480 行（核心对齐系统）
  data/processed/alias_dict.json           51 条核心别名
  tests/test_entity_alignment.py           32 个测试
  docs/b_phase2_alignment_report.md        阶段二验收报告
  docs/b_handover_to_leader.md             本文件

修改：
  INTERFACE.md                             +§9 实体对齐系统接口 / +§10 DESCENDANT_OF
  scripts/build_kg.ps1                     加 -Book/-Limit/-Resume 参数
  src/ingest/build_kg.py                  加 --book/--limit/--resume，多书 era 注入
  src/ingest/corpus.py                    infer_era() + 每书独立 chunks_*.json 输出
  requirements.txt                         +rapidfuzz +pypinyin

没动：
  src/methods/   src/eval/   src/generate/   frontend/   ← 都是队友的模块
```

---

## 8. 跑完本次工作怎么交回

1. **先合并到 main**：在本分支推 PR，等 CI 通过后由组长或他人 review 合并（INTERFACE.md 改动要群里吼一下）
2. **给全组发群通知**（按之前定的"三件套"模板）：
   ```
   【B 数据更新通知 - 阶段 X】
   - 神雕+倚天已全量抽取：神雕 XXX 实体/XXX 关系，倚天 XXX 实体/XXX 关系
   - 跨书血缘扫描：XX 条 DESCENDANT_OF 落库
   - 验收：MATCH DESCENDANT_OF 命中黄衫女子→杨过/小龙女 ✓
   - Neo4j dump：/data/backup/neo4j-2026-XX-XX.dump（需要找我）
   ```
3. **dump 备份**（给没装 Neo4j 的队友）：
   ```powershell
   docker stop neo4j-graphrag
   docker run --rm -v neo4j-data:/data neo4j:5-community neo4j-admin database dump neo4j --to-path=/data/backup/
   docker start neo4j-graphrag
   docker cp neo4j-graphrag:/data/backup/neo4j-XXX.dump D:\hu\backup_20260911\
   ```
4. **跑一次完整测试**再合并：`python -m pytest tests/`，目标 ≥100/100 通过

---

> 此文档作为阶段三工作启动手册。命令已实测可跑（以 `feature/b-phase2` 当前状态为依据）。
