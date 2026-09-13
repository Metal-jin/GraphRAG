# -*- coding: utf-8 -*-
"""自动路由评测：意图分类 + 领域策略 + 知识注入 的整体效果。"""
import sys
import json
import time
import argparse
import logging
from pathlib import Path
from collections import defaultdict

# 抑制 Neo4j driver 的 warning（id deprecated / location 不存在等刷屏信息）
logging.getLogger("neo4j").setLevel(logging.ERROR)

PROJECT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "src"))

from src.generate.service import ask_auto
from src.eval.run_compare import load_questions, entity_hit


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="只跑前 N 题（0=全部）")
    parser.add_argument("--questions", type=str, default="src/eval/questions_stage2.json")
    args = parser.parse_args()

    questions = load_questions(Path(args.questions))
    if args.limit > 0:
        questions = questions[:args.limit]

    results = []
    by_intent = defaultdict(lambda: [0, 0])
    by_category = defaultdict(lambda: [0, 0])
    by_method = defaultdict(lambda: [0, 0])

    for i, q in enumerate(questions):
        try:
            r = ask_auto(q["question"], top_k=5)
            answer = r.get("answer_text", "")
            hit = entity_hit(answer, q.get("acceptable_answers", []))
            intent = r.get("intent", "?")
            method = r.get("method_name", "?")
            results.append({"id": q["id"], "question": q["question"],
                            "intent": intent, "method": method,
                            "hit": hit, "answer": answer[:60]})
            by_intent[intent][0] += 1 if hit else 0
            by_intent[intent][1] += 1
            by_category[q.get("category", "其他")][0] += 1 if hit else 0
            by_category[q.get("category", "其他")][1] += 1
            by_method[method][0] += 1 if hit else 0
            by_method[method][1] += 1
            print(f"[{i+1}/{len(questions)}] {q['id']} -> {intent}/{method} {'✓' if hit else '✗'} {answer[:30]}", flush=True)
        except Exception as e:
            results.append({"id": q["id"], "question": q["question"],
                            "intent": "error", "method": "?", "hit": False,
                            "answer": f"ERROR: {e}"})
            by_intent["error"][0] += 0
            by_intent["error"][1] += 1
            print(f"[{i+1}/{len(questions)}] {q['id']} ERROR: {e}", flush=True)

    total = len(results)
    hits = sum(1 for r in results if r["hit"])
    acc = hits / total * 100 if total else 0

    lines = []
    lines.append(f"===== 自动路由评测（ask_auto）=====")
    lines.append(f"总题数 {total}，命中 {hits}，准确率 {acc:.2f}%")
    lines.append("")

    def dump(title, d):
        lines.append(title)
        for k, (h, t) in sorted(d.items(), key=lambda x: -x[1][0] / max(x[1][1], 1)):
            lines.append(f"  {k}: {h}/{t} = {h/t*100:.2f}%")
        lines.append("")

    dump("按意图（intent）：", by_intent)
    dump("按类别（category）：", by_category)
    dump("按路由方法（method）：", by_method)

    summary = "\n".join(lines)
    print(summary, flush=True)
    Path("output/auto_route_summary.txt").write_text(summary, encoding="utf-8")
    out = {"summary": {"total": total, "hits": hits, "accuracy": acc},
           "by_intent": {k: {"hit": v[0], "total": v[1]} for k, v in by_intent.items()},
           "by_category": {k: {"hit": v[0], "total": v[1]} for k, v in by_category.items()},
           "by_method": {k: {"hit": v[0], "total": v[1]} for k, v in by_method.items()},
           "results": results}
    Path("output/auto_route_results.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("结果已写入 output/auto_route_results.json", flush=True)


if __name__ == "__main__":
    main()
