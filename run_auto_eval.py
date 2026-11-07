# -*- coding: utf-8 -*-
"""自动路由评测（任务 32：保留完整答案与证据、增量保存、支持中断恢复）。

与 run_compare 的区别：这里评测的是"用户真实使用的入口" ask_auto，
即 意图识别 -> 自动路由 -> 注入 -> 生成 的全链路。

用法：
    python run_auto_eval.py                         # 全量
    python run_auto_eval.py --limit 20              # 前 20 题
    python run_auto_eval.py --resume                # 跳过已完成题（按 JSONL 断点）
"""
import sys
import json
import argparse
import logging
import time
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

logging.getLogger("neo4j").setLevel(logging.ERROR)

from generate.service import ask_auto  # noqa: E402
from eval.run_compare import load_questions  # noqa: E402
from eval.metrics import entity_string_hit  # noqa: E402

PROJECT = Path(__file__).resolve().parent
OUT_JSON = PROJECT / "output" / "auto_route_results.json"
OUT_SUMMARY = PROJECT / "output" / "auto_route_summary.txt"
OUT_JSONL = PROJECT / "output" / "auto_route_results.jsonl"


def _load_done() -> set:
    if not OUT_JSONL.exists():
        return set()
    done = set()
    for line in OUT_JSONL.read_text(encoding="utf-8").splitlines():
        try:
            done.add(json.loads(line)["id"])
        except (json.JSONDecodeError, KeyError):
            continue
    return done


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="只跑前 N 题（0=全部）")
    parser.add_argument("--questions", type=str, default="src/eval/questions_stage2.json")
    parser.add_argument("--resume", action="store_true", help="跳过 JSONL 里已完成的题")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    questions = load_questions(Path(args.questions))
    if args.limit > 0:
        questions = questions[:args.limit]
    done = _load_done() if args.resume else set()
    OUT_JSONL.parent.mkdir(parents=True, exist_ok=True)

    results = []
    by_intent = defaultdict(lambda: [0, 0])
    by_category = defaultdict(lambda: [0, 0])
    by_method = defaultdict(lambda: [0, 0])
    by_status = defaultdict(int)

    with OUT_JSONL.open("a", encoding="utf-8") as sink:
        for index, question in enumerate(questions):
            if question["id"] in done:
                continue
            started = time.perf_counter()
            try:
                result = ask_auto(question["question"], top_k=args.top_k)
                answer_text = result.get("answer_text", "") or ""
                hit = entity_string_hit(answer_text,
                                        question.get("acceptable_answers", []))
                record = {
                    "id": question["id"],
                    "question": question["question"],
                    "category": question.get("category", "其他"),
                    "book": question.get("source_hint", "未知"),
                    "hop": question.get("hop", 1),
                    "intent": result.get("intent", "?"),
                    "method": result.get("method_name", "?"),
                    "injection": result.get("injection", "?"),
                    "status": result.get("status", "?"),
                    "confidence": result.get("confidence"),
                    "seed_entity": result.get("seed_entity", ""),
                    "hit": hit,
                    "answer": answer_text,          # 完整答案，不截断
                    "evidence_count": len(result.get("evidence") or []),
                    "evidence": result.get("evidence") or [],
                    "debug_info": result.get("debug_info") or {},
                    "generation": result.get("generation") or {},
                    "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                }
                if result.get("error"):
                    record["error"] = result["error"]
            except Exception as exc:  # noqa: BLE001 - 单题失败不影响整体
                record = {"id": question["id"], "question": question["question"],
                          "category": question.get("category", "其他"),
                          "book": question.get("source_hint", "未知"),
                          "hop": question.get("hop", 1),
                          "intent": "error", "method": "?", "injection": "?",
                          "status": "error", "hit": False,
                          "answer": f"ERROR: {type(exc).__name__}: {exc}",
                          "evidence": [], "evidence_count": 0}
                by_intent["error"][1] += 1

            results.append(record)
            sink.write(json.dumps(record, ensure_ascii=False) + chr(10))
            sink.flush()

            if record["status"] != "error":
                by_intent[record["intent"]][0] += 1 if record["hit"] else 0
                by_intent[record["intent"]][1] += 1
                by_category[record["category"]][0] += 1 if record["hit"] else 0
                by_category[record["category"]][1] += 1
                by_method[record["method"]][0] += 1 if record["hit"] else 0
                by_method[record["method"]][1] += 1
            by_status[record["status"]] += 1
            mark = "OK" if record["hit"] else "--"
            print(f"[{index + 1}/{len(questions)}] {record['id']} -> "
                  f"{record['intent']}/{record['method']} [{record['status']}] {mark} "
                  f"{record['answer'][:40]}", flush=True)

    total = len(results)
    hits = sum(1 for r in results if r["hit"])
    acc = hits / total * 100 if total else 0.0

    lines = ["===== 自动路由评测（ask_auto）=====",
             f"总题数 {total}，命中 {hits}，端到端准确率 {acc:.2f}%",
             f"状态分布：{dict(by_status)}", ""]

    def dump(title, mapping):
        lines.append(title)
        for key, (hit, count) in sorted(mapping.items(),
                                        key=lambda item: -item[1][0] / max(item[1][1], 1)):
            lines.append(f"  {key}: {hit}/{count} = {hit / max(count, 1) * 100:.2f}%")
        lines.append("")

    dump("按意图（intent）：", by_intent)
    dump("按类别（category）：", by_category)
    dump("按路由方法（method）：", by_method)

    summary = chr(10).join(lines)
    print(summary, flush=True)
    OUT_SUMMARY.write_text(summary, encoding="utf-8")
    OUT_JSON.write_text(json.dumps({
        "summary": {"total": total, "hits": hits, "accuracy": acc,
                    "status": dict(by_status)},
        "by_intent": {k: {"hit": v[0], "total": v[1]} for k, v in by_intent.items()},
        "by_category": {k: {"hit": v[0], "total": v[1]} for k, v in by_category.items()},
        "by_method": {k: {"hit": v[0], "total": v[1]} for k, v in by_method.items()},
        "results": results,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"结果已写入 {OUT_JSON} 与 {OUT_JSONL}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
