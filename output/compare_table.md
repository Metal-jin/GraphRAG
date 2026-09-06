# GraphRAG 方法对比评测结果

> 这是 E1 提供的评测输出占位文件。请在 C/D 方法合并、数据和配置准备完成后，在项目根目录运行：
>
> `python -m src.eval.run_compare`

## 当前状态

| 项目 | 状态 |
|---|---|
| 评测问题集 | 已准备 50 道，见 `src/eval/questions.json` |
| 自动评分脚本 | 已准备，见 `src/eval/run_compare.py` |
| 实际四方法数据 | 待方法、语料、LLM 和 Neo4j 环境准备后生成 |

脚本会自动覆盖本文件，并额外生成 `output/compare_results.json` 保存逐题原始回答。
