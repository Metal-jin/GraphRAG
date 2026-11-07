"""三种知识注入形式的对比实验（任务 24 重做）。

旧实现的问题：直接用 answer_entities 构造三种上下文，等于把标准答案泄漏进
输入，再拿"覆盖率"当结论；reasoning_structure_score 还是按类别手工写死的 1.0/0.5。

新实现：
- 默认使用**真实检索**得到的事实（evidence 里的边），三种形式只是同一批事实的
  不同编码，标准答案只用于最后评分；
- 没有检索事实时明确记录 empty，不拿 gold 补证据；
- 只报告**结构指标**（上下文长度、方向是否可辨、关系标签是否可见、事实数），
  不冒充 LLM 准确率；
- 保留一个 --demo 模式用于答辩演示，但在输出里标注 demo，且不参与结论。

运行：
    python -m src.eval.injection_experiment --questions src/eval/questions.json
    python -m src.eval.injection_experiment --demo     # 标注为演示
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence

_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from eval.metrics import category_name, compare_injection_forms  # noqa: E402

REL_CN = {"MASTER_OF": "师徒", "SPOUSE_OF": "夫妻", "PARENT_OF": "父母",
          "SWORN_BROTHER_OF": "结拜", "ENEMY_OF": "仇敌", "BELONGS_TO": "属于",
          "MASTERS": "精通", "FOUNDER_OF": "创立", "LOCATED_IN": "位于",
          "BRANCHED_FROM": "演化", "DESCENDANT_OF": "血缘"}


def _facts_from_evidence(evidence: Sequence[Mapping[str, Any]]) -> List[Dict[str, str]]:
    """只从检索证据里取事实，绝不使用 answer_entities。"""
    facts: List[Dict[str, str]] = []
    seen = set()
    for item in evidence or []:
        for edge in item.get("edges") or []:
            key = (edge.get("source"), edge.get("type"), edge.get("target"))
            if key in seen or not all(key):
                continue
            seen.add(key)
            facts.append({"source": str(key[0]), "rel": str(key[1]), "target": str(key[2])})
        if not item.get("edges"):
            for node in item.get("nodes") or []:
                name = node.get("name")
                if name and ("entity", name) not in seen:
                    seen.add(("entity", name))
                    facts.append({"source": str(name), "rel": "实体", "target": ""})
    return facts


def _contexts(facts: Sequence[Mapping[str, str]]) -> Dict[str, str]:
    """同一批事实的三种等价编码。"""
    triples = "\n".join(f"（{f['source']}，{REL_CN.get(f['rel'], f['rel'])}，{f['target']}）"
                        for f in facts)
    path = "\n".join(f"{f['source']} --[{REL_CN.get(f['rel'], f['rel'])}]--> {f['target']}"
                     for f in facts)
    entities: List[str] = []
    for fact in facts:
        for key in ("source", "target"):
            if fact[key] and fact[key] not in entities:
                entities.append(fact[key])
    subgraph = ("围绕实体的子图摘要：" + "、".join(entities) +
                "\n关系：" + "；".join(f"{REL_CN.get(f['rel'], f['rel'])}" for f in facts))
    return {"triples": triples, "path": path, "subgraph": subgraph}


def _retrieve_facts(question: Mapping[str, Any], top_k: int) -> List[Dict[str, str]]:
    """按问题的自动路由跑一次真实检索，拿到事实。"""
    from generate.intent_classifier import classify
    from generate.service import retrieve

    intent = classify(question["question"])
    answer = retrieve(question["question"], intent.method_name, top_k)
    return _facts_from_evidence(answer.evidence)


def _demo_facts(question: Mapping[str, Any]) -> List[Dict[str, str]]:
    """演示模式：用标准答案构造事实（明确标注，不作为实验结论）。"""
    relation = str(question.get("relation", "关系"))
    subject = str(question.get("question", "问题")).rstrip("？?")
    return [{"source": subject, "rel": relation, "target": entity}
            for entity in (question.get("answer_entities") or [])]


def run(output: Path, questions_path: Path, *, demo: bool = False,
        top_k: int = 5, limit: int = 0) -> Dict[str, Any]:
    from eval.run_compare import load_questions

    questions = load_questions(questions_path)
    if limit:
        questions = questions[:limit]

    rows: List[Dict[str, Any]] = []
    for question in questions:
        try:
            facts = _demo_facts(question) if demo else _retrieve_facts(question, top_k)
        except Exception as exc:  # 检索失败：记录为空，不补 gold
            facts = []
            error = f"{type(exc).__name__}: {exc}"
        else:
            error = ""
        contexts = _contexts(facts) if facts else {"triples": "", "path": "", "subgraph": ""}
        comparison = compare_injection_forms(facts, contexts)
        rows.append({"question_id": question["id"],
                     "category": category_name(question),
                     "fact_count": len(facts), "error": error,
                     "comparison": comparison})

    by_category: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        by_category.setdefault(row["category"], []).append(row["comparison"])

    summary = []
    for category, comparisons in sorted(by_category.items()):
        for form in ("triples", "path", "subgraph"):
            metrics = [c[form] for c in comparisons]
            summary.append({
                "category": category,
                "injection": form,
                "questions": len(metrics),
                "avg_context_chars": round(sum(m["context_chars"] for m in metrics) / len(metrics), 2),
                "direction_visible_rate": round(
                    sum(1 for m in metrics if m["has_direction"]) / len(metrics), 4),
                "relation_label_rate": round(
                    sum(1 for m in metrics if m["has_relation_label"]) / len(metrics), 4),
                "empty_rate": round(sum(1 for m in metrics if m["empty"]) / len(metrics), 4),
            })

    report = {
        "mode": "demo（使用标准答案构造，仅演示，不作为实验结论）" if demo else "retrieval-based",
        "description": "对同一批**检索事实**做三种等价编码，只比较结构指标；"
                       "未调用 LLM，因此不报告准确率。",
        "questions_file": str(questions_path),
        "top_k": top_k,
        "question_count": len(rows),
        "retrieval_error_count": sum(1 for r in rows if r["error"]),
        "empty_fact_count": sum(1 for r in rows if r["fact_count"] == 0),
        "summary": summary,
        "results": rows,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="知识注入形式的结构对比实验")
    parser.add_argument("--output", type=Path, default=Path("output/injection_experiment.json"))
    parser.add_argument("--questions", type=Path,
                        default=_SRC / "eval" / "questions.json")
    parser.add_argument("--demo", action="store_true",
                        help="演示模式：用标准答案构造事实（结果标注 demo）")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--limit", type=int, default=0)
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    report = run(args.output, args.questions, demo=args.demo,
                 top_k=args.top_k, limit=args.limit)
    print(f"[injection] mode={report['mode']} 题数={report['question_count']} "
          f"检索失败={report['retrieval_error_count']} 空事实={report['empty_fact_count']}")
    print(f"[injection] 结果：{args.output}")
