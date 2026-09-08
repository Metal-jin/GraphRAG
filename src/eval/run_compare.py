"""
E1 评测脚本：用同一套问题、同一个 top_k，批量比较多个问答方法。

这份代码特意只依赖 Python 标准库和项目已有的 core 接口，原因是：
1. 评测脚本不应该自己实现检索算法；它只负责“出题、调用、打分、汇总”。
2. C/D 的方法可能还没有合并到当前分支，所以缺失的方法要被记录为 unavailable，
   而不是让整场评测直接崩溃。
3. 中文答案可能带有“答案是……”等解释文字，因此评分先做轻量归一化，
   再判断标准答案实体是否出现在回答中。最终报告必须同时保留原始答案，便于人工复核。

运行示例（在仓库根目录）：
    python -m src.eval.run_compare --methods vector library_graphrag master_chain sect_agg art_lineage
    python -m src.eval.run_compare --methods vector --top-k 5 --output output/compare_table.md

也可以使用 pytest 对本文件中的纯函数做回归测试；不需要 Neo4j 或 LLM。
"""

from __future__ import annotations

import argparse
import importlib
import json
import re
import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
# 允许从项目根目录执行 `python -m src.eval.run_compare` 时，方法内部仍然
# 可以按照项目约定使用 `from core...` 导入。pytest.ini 也采用同样的 src 布局。
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
QUESTION_FILE = Path(__file__).with_name("questions.json")
DEFAULT_OUTPUT = PROJECT_ROOT / "output" / "compare_table.md"
DEFAULT_RESULT_JSON = PROJECT_ROOT / "output" / "compare_results.json"

# README 中约定的五个方法名（两个基线 + 三个领域策略）。用户可以通过 --methods 只跑其中几个。
DEFAULT_METHODS = ("vector", "library_graphrag", "master_chain", "sect_agg", "art_lineage")


@dataclass
class ItemResult:
    """一道题、一个方法的一次运行结果。"""

    question_id: str
    method: str
    status: str
    answer_text: str = ""
    entity_hit: bool = False
    latency_ms: float | None = None
    error: str = ""
    debug_info: dict[str, Any] = field(default_factory=dict)


def normalize_text(text: str) -> str:
    """对中英文标点、空白和大小写做统一处理。

    这里不能使用激进分词或同义词模型，否则评测结果会混入第二套模型的偏差。
    归一化只删除明显不影响实体匹配的字符；真正的“是否答对”仍由 gold 别名决定。
    """
    if text is None:
        return ""
    text = str(text).strip().lower()
    # 去除 Markdown、常见中文标点和空白，但保留中文、英文、数字。
    text = re.sub(r"[`*_#~。，、；：！？（）()【】\[\]{}“”‘’\"'：:,.!?;\s]+", "", text)
    return text


def entity_hit(answer_text: str, acceptable_answers: Iterable[str]) -> bool:
    """判断回答中是否出现任意一个人工确认过的标准答案/别名。"""
    answer = normalize_text(answer_text)
    if not answer:
        return False
    return any(normalize_text(alias) and normalize_text(alias) in answer for alias in acceptable_answers)


def load_questions(path: Path = QUESTION_FILE) -> list[dict[str, Any]]:
    """读取并检查问题集的最小结构，尽早发现 JSON 被误改的问题。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    questions = data.get("questions") if isinstance(data, dict) else data
    if not isinstance(questions, list) or not questions:
        raise ValueError("问题集必须是非空的 questions 数组")
    required = {"id", "question", "answer_entities", "acceptable_answers"}
    seen: set[str] = set()
    for item in questions:
        missing = required - set(item)
        if missing:
            raise ValueError(f"问题 {item.get('id', '<unknown>')} 缺少字段: {sorted(missing)}")
        if item["id"] in seen:
            raise ValueError(f"问题 ID 重复: {item['id']}")
        seen.add(item["id"])
    return questions


def import_project_methods() -> None:
    """导入方法包，触发各方法文件上的 @register 装饰器。

    当前仓库可能只有骨架，导入失败不能在这里静默吞掉；真正的缺失方法由
    run_one_method 捕获并写入报告。这样既保留异常信息，也可以继续跑其他方法。
    """
    try:
        importlib.import_module("methods")
    except ModuleNotFoundError:
        # 使用 python -m src.eval.run_compare 时，src 会作为包根目录；下面的兼容
        # 分支让直接设置 PYTHONPATH=src 后执行也能工作。
        try:
            importlib.import_module("src.methods")
        except ModuleNotFoundError:
            return


def _get_method(method_name: str):
    """从统一注册表取得方法实例，并兼容两种导入方式。"""
    try:
        from core.registry import get_method
    except ModuleNotFoundError:
        from src.core.registry import get_method
    return get_method(method_name)


def run_one_method(method_name: str, question: Mapping[str, Any], top_k: int) -> ItemResult:
    """调用一个方法回答一道题，并把异常转换成可报告的失败记录。"""
    result = ItemResult(question_id=question["id"], method=method_name, status="error")
    started = time.perf_counter()
    try:
        method = _get_method(method_name)
        answer = method.ask(question["question"], top_k=top_k)
        # 检索 → 生成：把检索上下文喂给 LLM，生成简洁答案
        raw_context = getattr(answer, "raw_context", "") or ""
        if raw_context:
            try:
                from generate.llm import generate_answer
                result.answer_text = generate_answer(question["question"], raw_context)
            except Exception:
                result.answer_text = getattr(answer, "answer_text", "") or ""
        else:
            result.answer_text = getattr(answer, "answer_text", "") or ""
        result.debug_info = getattr(answer, "debug_info", {}) or {}
        result.entity_hit = entity_hit(result.answer_text, question["acceptable_answers"])
        result.status = "ok"
    except Exception as exc:  # 评测不能因单个方法/单道题失败而丢掉其他结果
        result.error = f"{type(exc).__name__}: {exc}"
        result.debug_info = {"traceback": traceback.format_exc(limit=3)}
    finally:
        result.latency_ms = round((time.perf_counter() - started) * 1000, 2)
    return result


def summarize(results: list[ItemResult], question_count: int) -> list[dict[str, Any]]:
    """按方法汇总核心指标。

    accuracy 的分母是该方法实际返回成功结果的题数；availability 另列出成功率，
    避免把“方法没装好”与“方法回答错误”混成一个数字。
    """
    methods = sorted({r.method for r in results})
    summary = []
    for method in methods:
        rows = [r for r in results if r.method == method]
        ok = [r for r in rows if r.status == "ok"]
        hits = [r for r in ok if r.entity_hit]
        latencies = [r.latency_ms for r in ok if r.latency_ms is not None]
        summary.append({
            "method": method,
            "questions": question_count,
            "available": len(ok),
            "availability": round(len(ok) / question_count, 4) if question_count else 0,
            "entity_hits": len(hits),
            "accuracy": round(len(hits) / len(ok), 4) if ok else None,
            # 当前问题集每题要求一个答案实体（部分题允许多个等价答案），
            # 所以“关键实体召回率”与准确率数值相同，但保留这个字段是为了
            # 对齐课程要求；以后扩展到多实体问题时可改成实体级分母。
            "entity_recall": round(len(hits) / len(ok), 4) if ok else None,
            "avg_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else None,
        })
    return summary


def markdown_report(summary: list[dict[str, Any]], results: list[ItemResult], top_k: int) -> str:
    """生成可直接放进答辩材料的 Markdown 对比表。"""
    generated = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    lines = [
        "# GraphRAG 方法对比评测结果",
        "",
        "> 本表由 `src/eval/run_compare.py` 自动生成。准确率和关键实体召回率是当前阶段的自动指标，最终结论仍需结合证据和人工复核。",
        "",
        f"- 生成时间：`{generated}`",
        f"- 评测问题数：`{summary[0]['questions'] if summary else 0}`",
        f"- 统一 `top_k`：`{top_k}`",
        "- 自动判分：回答文本命中该题 `acceptable_answers` 中任一实体或别名即记为命中。",
        "",
        "## 汇总",
        "",
        "| 方法 | 可用题数 | 可用率 | 实体命中数 | 准确率 | 关键实体召回率 | 平均耗时(ms) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary:
        accuracy = "N/A" if row["accuracy"] is None else f"{row['accuracy']:.2%}"
        latency = "N/A" if row["avg_latency_ms"] is None else f"{row['avg_latency_ms']:.2f}"
        recall = "N/A" if row["entity_recall"] is None else f"{row['entity_recall']:.2%}"
        lines.append(f"| {row['method']} | {row['available']}/{row['questions']} | {row['availability']:.2%} | {row['entity_hits']} | {accuracy} | {recall} | {latency} |")
    lines += ["", "## 指标解释", "", "- **可用率**：方法成功返回 `Answer` 的题数 / 总题数。", "- **准确率**：自动判分成功题数 / 方法成功返回题数；方法不可用不会被误算成回答错误。", "- **关键实体召回率**：标准实体被召回的题数 / 方法成功返回题数；当前每题只要求一个实体，因此数值与准确率相同。", "- **平均耗时**：从调用 `ask()` 到返回或抛出异常的单题平均耗时。", "- 本阶段未自动判“关系方向、证据完整性、答案幻觉”；这些应在有真实图谱和 LLM 输出后人工复核或继续扩展指标。", "", "## 逐题结果", "", "| 题号 | 方法 | 状态 | 实体命中 | 回答/错误 |", "|---|---|---|---|---|"]
    for row in results:
        text = row.answer_text if row.status == "ok" else row.error
        text = text.replace("|", "\\|").replace("\n", " ")[:240]
        lines.append(f"| {row.question_id} | {row.method} | {row.status} | {'是' if row.entity_hit else '否'} | {text} |")
    return "\n".join(lines) + "\n"


def run(methods: Iterable[str], top_k: int, question_path: Path, output_path: Path, result_json: Path) -> int:
    """完整执行一次评测；返回适合命令行使用的退出码。"""
    methods = list(methods)
    questions = load_questions(question_path)
    import_project_methods()
    results = [run_one_method(name, question, top_k) for name in methods for question in questions]
    summary = summarize(results, len(questions))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result_json.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown_report(summary, results, top_k), encoding="utf-8")
    result_json.write_text(json.dumps({"summary": summary, "results": [r.__dict__ for r in results]}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已完成：{len(questions)} 道题 × {len(methods)} 个方法")
    print(f"Markdown 报告：{output_path}")
    print(f"JSON 原始结果：{result_json}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="比较 GraphRAG 的多个问答方法")
    parser.add_argument("--methods", nargs="+", default=list(DEFAULT_METHODS), help="要运行的方法名，默认运行五种方法")
    parser.add_argument("--top-k", type=int, default=5, help="传给每个方法 ask() 的 top_k，默认 5")
    parser.add_argument("--questions", type=Path, default=QUESTION_FILE, help="问题集 JSON 路径")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Markdown 报告路径")
    parser.add_argument("--result-json", type=Path, default=DEFAULT_RESULT_JSON, help="逐题 JSON 结果路径")
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    if args.top_k <= 0:
        print("--top-k 必须是正整数", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(run(args.methods, args.top_k, args.questions, args.output, args.result_json))
