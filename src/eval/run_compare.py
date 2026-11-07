"""E1 评测脚本（任务 22 / 23 重写）。

修复内容：
- 走**真实业务流程**：检索 -> 注入 -> 生成，与 ask_auto / 手动问答共用同一套函数；
- 分类统计使用**本次实际题集**，不再重新加载默认 questions.json；
- 区分四种状态：ok / no_context / degraded / error，降级与异常不再被算成"回答错误"；
- 题集、书目、类型、跳数、难度都可分组统计；
- 同时报告"以全部题目为分母"的端到端表现与"成功返回后"的条件表现。

运行示例（仓库根目录）：
    python -m src.eval.run_compare --methods vector master_chain person_relation
    python -m src.eval.run_compare --questions src/eval/questions_stage2.json --top-k 5
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from eval.metrics import (  # noqa: E402
    category_name, entity_hit, entity_string_hit, evaluate_result, normalize_text,
    summarize_by)

QUESTION_FILE = Path(__file__).with_name("questions.json")
DEFAULT_OUTPUT = PROJECT_ROOT / "output" / "compare_table.md"
DEFAULT_RESULT_JSON = PROJECT_ROOT / "output" / "compare_results.json"

DEFAULT_METHODS = ("vector", "library_graphrag", "master_chain", "sect_agg",
                   "art_lineage", "person_relation")

STATUS_OK = "ok"
STATUS_NO_CONTEXT = "no_context"
STATUS_DEGRADED = "degraded"
STATUS_ERROR = "error"


@dataclass
class ItemResult:
    """一道题、一个方法的一次完整运行结果。"""

    question_id: str
    method: str
    status: str = STATUS_ERROR
    answer_text: str = ""
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    latency_ms: Optional[float] = None
    error: str = ""
    debug_info: Dict[str, Any] = field(default_factory=dict)
    injection: str = ""
    generation_status: str = ""
    fallback_reason: str = ""
    retrieval_context: str = ""
    injected_context: str = ""
    entity_hit: bool = False
    metrics: Dict[str, Any] = field(default_factory=dict)


def load_questions(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """读取并校验题集结构。"""
    path = Path(path or QUESTION_FILE)
    data = json.loads(path.read_text(encoding="utf-8"))
    questions = data.get("questions") if isinstance(data, dict) else data
    if not isinstance(questions, list) or not questions:
        raise ValueError("问题集必须是非空的 questions 数组")
    required = {"id", "question", "answer_entities", "acceptable_answers"}
    seen = set()
    for item in questions:
        missing = required - set(item)
        if missing:
            raise ValueError(f"问题 {item.get('id', '<unknown>')} 缺少字段: {sorted(missing)}")
        if item["id"] in seen:
            raise ValueError(f"问题 ID 重复: {item['id']}")
        seen.add(item["id"])
    return questions


def import_project_methods() -> None:
    try:
        importlib.import_module("methods")
    except ModuleNotFoundError:
        try:
            importlib.import_module("src.methods")
        except ModuleNotFoundError:
            return


def run_one_method(method_name: str, question: Mapping[str, Any], top_k: int) -> ItemResult:
    """调用统一链路回答一道题，并把异常/降级转换成可报告状态。"""
    result = ItemResult(question_id=question["id"], method=method_name)
    started = time.perf_counter()
    try:
        from generate.injection import build_context, injection_name
        from generate.llm import generate
        from generate.service import retrieve

        answer = retrieve(question["question"], method_name, top_k)
        result.evidence = list(getattr(answer, "evidence", []) or [])
        result.debug_info = dict(getattr(answer, "debug_info", {}) or {})
        result.injection = injection_name(method_name)
        result.retrieval_context = getattr(answer, "raw_context", "") or ""
        context = build_context(method_name, result.evidence,
                                result.retrieval_context)
        result.injected_context = context
        generation = generate(question["question"], context)
        result.generation_status = generation.status
        result.fallback_reason = generation.fallback_reason

        if generation.status == "ok":
            result.answer_text = generation.text
            result.status = STATUS_OK
        elif generation.status == "no_context":
            result.answer_text = getattr(answer, "answer_text", "") or ""
            result.status = (STATUS_NO_CONTEXT if not context.strip() else STATUS_OK)
        else:
            result.answer_text = getattr(answer, "answer_text", "") or ""
            result.status = STATUS_DEGRADED

        result.entity_hit = entity_string_hit(result.answer_text,
                                              question.get("acceptable_answers", []))
        result.metrics = evaluate_result(question, result.answer_text, result.evidence)
    except Exception as exc:  # 单题失败不影响其它题
        result.status = STATUS_ERROR
        result.error = f"{type(exc).__name__}: {exc}"
        result.debug_info = {"traceback": traceback.format_exc(limit=3)}
    finally:
        result.latency_ms = round((time.perf_counter() - started) * 1000, 2)
    return result


def _summary_rows(results: List[ItemResult],
                  questions_by_id: Mapping[str, Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """把结果展开成可供 summarize_by 分组的行。"""
    rows = []
    for result in results:
        question = questions_by_id.get(result.question_id, {})
        rows.append({
            "method": result.method,
            "category": category_name(question),
            "book": question.get("source_hint", "未知"),
            "hop": str(question.get("hop", 1)),
            "difficulty": question.get("difficulty", "未标注"),
            "status": result.status,
            "entity_string_hit": result.entity_hit,
            **result.metrics,
        })
    return rows


def summarize(results: List[ItemResult],
              questions_by_id: Mapping[str, Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """按方法汇总：端到端（全部题）与条件（成功题）两种口径。"""
    methods = sorted({r.method for r in results})
    summary = []
    for method in methods:
        rows = [r for r in results if r.method == method]
        ok = [r for r in rows if r.status in (STATUS_OK, STATUS_NO_CONTEXT)]
        degraded = [r for r in rows if r.status == STATUS_DEGRADED]
        errors = [r for r in rows if r.status == STATUS_ERROR]
        hits = [r for r in rows if r.entity_hit]
        latencies = [r.latency_ms for r in rows if r.latency_ms is not None]
        eager_hits = [r for r in ok if r.entity_hit]
        summary.append({
            "method": method,
            "questions": len(rows),
            "ok": len(ok),
            "degraded": len(degraded),
            "errors": len(errors),
            "availability": round(len(ok) / len(rows), 4) if rows else 0.0,
            "entity_hits": len(hits),
            # 端到端：所有题做分母（降级/异常也计入未答对）
            "e2e_accuracy": round(len(hits) / len(rows), 4) if rows else 0.0,
            # 条件准确率：只在成功返回的题上计算
            "accuracy": round(len(eager_hits) / len(ok), 4) if ok else None,
            "avg_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else None,
        })
    return summary


def markdown_report(summary: List[Dict[str, Any]], results: List[ItemResult],
                    questions: List[Dict[str, Any]], top_k: int,
                    question_path: Path) -> str:
    """生成对比报告（分类统计使用本次题集，而不是默认文件）。"""
    generated = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    questions_by_id = {q["id"]: q for q in questions}
    rows = _summary_rows(results, questions_by_id)

    lines = [
        "# GraphRAG 方法对比评测结果",
        "",
        "> 由 src/eval/run_compare.py 自动生成。entity_string_hit 只是**辅助指标**，"
        "不等于事实准确率；结论需结合证据与人工复核。",
        "",
        f"- 生成时间：{generated}",
        f"- 题集：{question_path}（{len(questions)} 题）",
        f"- 统一 top_k：{top_k}",
        f"- 判分：答案文本命中 acceptable_answers 且非否定表述记为命中；"
        f"exact_match 要求 answer_entities 全部命中。",
        "",
        "## 汇总（端到端 vs 条件）",
        "",
        "| 方法 | 题数 | 成功 | 降级 | 异常 | 可用率 | 命中 | 端到端准确率 | 条件准确率 | 平均耗时(ms) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary:
        accuracy = "N/A" if row["accuracy"] is None else f"{row['accuracy']:.2%}"
        latency = "N/A" if row["avg_latency_ms"] is None else f"{row['avg_latency_ms']:.2f}"
        lines.append(
            f"| {row['method']} | {row['questions']} | {row['ok']} | {row['degraded']} | "
            f"{row['errors']} | {row['availability']:.2%} | {row['entity_hits']} | "
            f"{row['e2e_accuracy']:.2%} | {accuracy} | {latency} |")

    def table(title: str, key: str) -> None:
        lines.extend(["", f"## {title}", "",
                      f"| 方法 | {key} | 题数 | 准确率 | 完全匹配 | 路径完整性 | 证据充分性 |",
                      "|---|---|---:|---:|---:|---:|---:|"])
        for item in summarize_by(rows, ("method", key)):
            lines.append(
                f"| {item['method']} | {item[key]} | {item['questions']} | "
                f"{item['accuracy']:.2%} | {item['exact_match']:.2%} | "
                f"{item['path_completeness']:.2%} | {item['evidence_sufficiency']:.2%} |")

    table("分类别结果", "category")
    table("分书目结果", "book")
    table("分跳数结果", "hop")

    lines += ["", "## 指标解释", "",
              "- **端到端准确率**：命中题数 / 全部题数（异常与降级也算未答对）。",
              "- **条件准确率**：命中题数 / 成功返回题数。",
              "- **完全匹配（exact_match）**：answer_entities 全部命中才算 1。",
              "- **路径完整性**：证据路径必须**连通**且覆盖预期跳数，不连通的边不得分。",
              "- **证据充分性**：答案命中 × 证据覆盖预期关系类型。",
              "- **否定表述**（如「不是洪七公」）不计为命中。",
              "", "## 逐题结果", "",
              "| 题号 | 方法 | 状态 | 命中 | 注入 | 生成状态 | 回答/错误 |",
              "|---|---|---|---|---|---|---|"]
    for result in results:
        text = (result.answer_text if result.status != STATUS_ERROR else result.error)
        text = (text or "").replace("|", "\\|").replace(chr(10), " ")[:240]
        lines.append(f"| {result.question_id} | {result.method} | {result.status} | "
                     f"{'是' if result.entity_hit else '否'} | {result.injection} | "
                     f"{result.generation_status} | {text} |")
    return chr(10).join(lines) + chr(10)


def run(methods: Iterable[str], top_k: int, question_path: Path,
        output_path: Path, result_json: Path) -> int:
    methods = list(methods)
    questions = load_questions(question_path)
    questions_by_id = {q["id"]: q for q in questions}
    import_project_methods()
    results = [run_one_method(name, question, top_k)
               for name in methods for question in questions]
    summary = summarize(results, questions_by_id)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result_json.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        markdown_report(summary, results, questions, top_k, question_path),
        encoding="utf-8")
    payload = {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "questions_file": str(question_path),
        "top_k": top_k,
        "methods": methods,
        "question_count": len(questions),
        "summary": summary,
        "results": [r.__dict__ for r in results],
    }
    result_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    print(f"已完成：{len(questions)} 道题 x {len(methods)} 个方法")
    print(f"Markdown 报告：{output_path}")
    print(f"JSON 原始结果：{result_json}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="比较 GraphRAG 的多个问答方法")
    parser.add_argument("--methods", nargs="+", default=list(DEFAULT_METHODS))
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--questions", type=Path, default=QUESTION_FILE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--result-json", type=Path, default=DEFAULT_RESULT_JSON)
    parser.add_argument("--limit", type=int, default=0, help="只跑前 N 题（0=全部）")
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    if args.top_k <= 0:
        print("--top-k 必须是正整数", file=sys.stderr)
        raise SystemExit(2)
    questions_path = args.questions
    if args.limit:
        loaded = load_questions(questions_path)
        trimmed = loaded[:args.limit]
        # 限定子集写到报告同目录，不污染源码目录
        subset_path = args.output.parent / f"questions_limit_{args.limit}.json"
        subset_path.parent.mkdir(parents=True, exist_ok=True)
        subset_path.write_text(json.dumps({"questions": trimmed}, ensure_ascii=False),
                               encoding="utf-8")
        questions_path = subset_path
    raise SystemExit(run(args.methods, args.top_k, questions_path,
                         args.output, args.result_json))
