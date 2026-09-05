# GraphRAG —— 金庸武侠知识图谱问答系统

天津大学 2026 知识工程综合实践

**项目简介**：构建金庸武侠知识图谱，实现多种检索方法（纯向量基线、调库基线、自研 PPR 方法），用统一框架和同一套评测问题公平对比效果。

> ⚠️ 写代码前，请先读完本文件，再看 `INTERFACE.md` 和 `src/core/interfaces.py`。

---

## 一、项目结构

```
src/
  core/       框架核心：接口、方法注册表、配置
  methods/    检索方法实现（vector / library_graphrag / hipporag2）
  retrieve/   检索算法细节（向量工具、PPR 实现）
  ingest/     数据构建：切块、抽取、入库、数据读取
  generate/   统一问答入口
  eval/       评测：问题集、指标、对比脚本
docs/         文档：本体、算法说明、评测报告
frontend/     前端界面
scripts/      一键运行脚本
tests/        测试
data/         语料（默认不进 git）
output/       评测输出
```

---

## 二、团队分工

| 角色 | 分支名 | 负责目录 | 一句话职责 |
|---|---|---|---|
| A+D（组长） | `feature/d-ppr` | `src/core/`、`src/methods/hipporag2.py` | 架构接口 + 自研 PPR 算法 |
| B | `feature/b-ingest` | `src/ingest/`、`docs/ontology.md` | 数据 + 图谱构建 |
| C | `feature/c-baseline` | `src/methods/vector.py`、`library_graphrag.py`、`src/retrieve/vector_utils.py` | 两个基线方法 |
| E1 | `feature/e1-eval` | `src/eval/`、`output/` | 评测 |
| E2 | `feature/e2-frontend` | `src/generate/`、`frontend/` | 前端 + 生成服务 |

> 只改自己负责的目录，不要动别人的文件。**需要改公共文件（如 `interfaces.py`）时，先在群里说一声。**

---

## 三、快速开始（组员必读）

### 第 0 步：准备环境

你需要装好：

1. **Python 3.10+**（推荐 3.12）
2. **git**
3. **Neo4j**（本地安装，或用 Docker，见第 4 步后）

### 第 1 步：下载项目

打开 PowerShell，执行：

```powershell
git clone https://github.com/Metal-jin/GraphRAG.git
cd GraphRAG
```

### 第 2 步：切到自己的分支

```powershell
git checkout feature/b-ingest
```

> 把 `feature/b-ingest` 换成你自己的分支名（见上面分工表）。

### 第 3 步：安装依赖

```powershell
pip install -r requirements.txt
```

### 第 4 步：配置 .env

```powershell
Copy-Item .env.example .env
```

然后用记事本打开 `.env`，把 `你的数据库密码`、`你的LLM密钥` 替换成真实值。

> ⚠️ `.env` 里有真实密码，**绝对不能提交到 git**（`.gitignore` 已帮你忽略，但自己也要注意）。

---

## 四、各组员的具体任务

### B（数据 + 图谱构建）

1. 找金庸小说语料，放进 `data/source/`（**不提交 git**）。
2. 写 `src/ingest/corpus.py`：把语料切成文本块。
3. 写 `src/ingest/build_kg.py`：用 LLM 抽取实体关系，写入 Neo4j，建索引。
4. 写 `src/ingest/data_loader.py`：提供 `get_chunks()`、`get_graph()`、`search_by_vector()` 等函数给 C、D 用。
5. 本体清单（实体/关系类型）参考 `docs/ontology.md`。

> 重点：`data_loader.py` 的返回格式**要先和 C、D 约定好**再写。

### C（两个基线方法）

1. 写 `src/methods/vector.py`：纯向量基线（不用图谱）。
2. 写 `src/methods/library_graphrag.py`：调 `neo4j-graphrag` 库的图检索。
3. 写 `src/retrieve/vector_utils.py`：向量检索工具，供 D 复用。
4. 两个方法都要实现 `QAMethod` 接口（见 `src/core/interfaces.py`），并用 `@register` 注册。

### E1（评测）

1. 写 `src/eval/questions.json`：约 50 个金庸多跳问题。
2. 写 `src/eval/run_compare.py`：自动跑多个方法、生成对比表。
3. 定评测指标（准确率/召回率），写清楚"怎么算对"。

### E2（前端 + 生成服务）

1. 写 `src/generate/service.py`：统一问答入口（调方法、调 LLM）。
2. 写 `frontend/index.html`：图谱展示 + 切换方法 + 问答 + 高亮证据。
3. 维护 `README.md` 和 `INTERFACE.md`（接口内容由组长定）。

---

## 五、日常开发流程（提交代码）

每次改完代码，走这三步：

```powershell
git add .
git commit -m "说明你改了什么"
git push
```

> - `commit -m` 后面写清楚，比如"完成 vector 基线方法"。
> - **每天下班前 push 一次**，别攒着。
> - **提交前先跑测试**：`python -m pytest`，通过了再 commit。

---

## 六、常见问题（FAQ）

### 1. clone 时提示输入用户名密码，密码填什么？

- 用户名：你的 GitHub 用户名
- 密码：**不是 GitHub 登录密码**，是 Personal Access Token（PAT）。
- 获取方法：GitHub → Settings → Developer settings → Personal access tokens → 生成一个，勾选 `repo` 权限，复制那串 `ghp_` 开头的字符。

### 2. 连不上 GitHub（`Connection was reset` / `Could not connect`）

- 网络问题，稍后重试，或挂代理（VPN）。
- 如果用了代理，确认代理软件开着。

### 3. 运行 Python 文件报 `ModuleNotFoundError: No module named 'core'`

- **不要直接 `python xxx.py` 运行**，改用 pytest 跑测试：
  ```powershell
  python -m pytest
  ```
- 项目用了 `src/` 布局，`pytest.ini` 已经配置好了模块路径，直接用 pytest 就行。

### 4. 连不上 Neo4j

- 确认 Neo4j 已经启动。
- 确认 `.env` 里的 `NEO4J_URL`、`NEO4J_USER`、`NEO4J_PASSWORD` 填对了。
- Neo4j 默认地址：`bolt://localhost:7687`。

### 5. 提交冲突（`push` 被拒绝）

- 说明你的分支和远程不一致。**先别乱操作**，在群里问组长，让组长帮忙处理。

### 6. `pip install` 太慢或失败

- 用国内镜像源加速：
  ```powershell
  pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
  ```
- 其他可用镜像：阿里云 `https://mirrors.aliyun.com/pypi/simple/`、中科大 `https://pypi.mirrors.ustc.edu.cn/simple/`

### 7. Python 版本不兼容 / 报语法错误

- 本项目推荐 **Python 3.10 ~ 3.13**。
- 查看版本：`python --version`
- 如果版本太老（如 3.7），请升级 Python，或用 conda 创建新环境：
  ```powershell
  conda create -n graphrag python=3.12 -y
  conda activate graphrag
  ```

### 8. 分支切换失败（`git checkout` 报错）

- 先确认没有未提交的改动：`git status` 应该显示干净。
- 如果有改动，先提交（`git add .` → `git commit -m "..."`）或丢弃，再切换分支。
- 确认分支名拼写正确，可查看所有分支：`git branch -a`

---

## 七、注意事项（铁律）

1. **`.env` 绝对不能提交**。里面是真实密码，泄漏了要改密码。
2. **金庸原文不要提交**。`data/source/` 已被忽略，原文留在本地即可。
3. **只在自己的分支上开发**，不要直接在 `main` 上改。
4. **只改自己负责的目录**，动公共文件前先群里说一声。
5. **提交前跑测试**，测试过了再 push。
6. **频繁 commit**，别攒一大坨。
7. **用 AI 写代码可以，但必须能讲清楚每一行**（答辩会问）。

---

## 八、接口约定

详见 [`INTERFACE.md`](INTERFACE.md)。所有检索方法都必须实现 `QAMethod` 接口、返回统一的 `Answer` 结构，这是全组的对接基础。
