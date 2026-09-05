# GraphRAG

天津大学 2026 知识工程综合实践

**金庸武侠领域的 GraphRAG 检索方法对比实验系统**：构建金庸武侠知识图谱，实现多种检索方法（纯向量基线、调库基线、自研 PPR 方法），用统一框架和同一套评测问题公平对比效果。

> 详见 [INTERFACE.md](INTERFACE.md)（接口约定，写代码前必读）

## 项目结构

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

## 分工

| 角色 | 负责 |
|---|---|
| A+D | 架构接口 + 自研 PPR 算法 |
| B   | 数据 + 图谱构建 |
| C   | 两个基线方法 |
| E1  | 评测 |
| E2  | 前端 + 生成服务 + Git/文档 |

## 快速开始

（待补充：环境配置、造数据、启动、评测的具体步骤）
