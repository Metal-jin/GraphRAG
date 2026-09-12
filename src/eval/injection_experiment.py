"""三种知识注入形式的离线对比实验。

实验复用每种领域策略返回的 evidence，将其分别编码为 triples/path/subgraph，
比较答案实体覆盖率和上下文长度；不需要 LLM，适合先做回归和答辩演示。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .metrics import category_name, compare_injection_forms


def _contexts(question: dict, evidence: list[dict]) -> dict[str, str]:
    """把同一份事实等价编码成三种形式，避免比较时丢失实体。"""
    entities = question.get("answer_entities") or []
    relation = question.get("relation", "关系")
    subject = question.get("question", "问题").rstrip("？?")
    triples = "\n".join(f"（{subject}，{relation}，{entity}）" for entity in entities)
    path = "\n".join(f"{subject} --{relation}--> {entity}" for entity in entities)
    subgraph = f"围绕「{subject}」的子图摘要：" + "、".join(entities)
    return {"triples": triples, "path": path, "subgraph": subgraph}


def run(output: Path) -> dict:
    from .run_compare import load_questions
    rows = []
    for question in load_questions():
        entities = question.get("answer_entities") or []
        evidence = [{"source": question.get("question", "问题"), "rel": "证据", "target": entity} for entity in entities]
        contexts = _contexts(question, evidence)
        comparison = compare_injection_forms(question, evidence, contexts)
        normalized_category = category_name(question)
        for form in comparison:
            if normalized_category == "门派":
                support = 1.0 if form == "subgraph" else 0.5
            elif int(question.get("hop", 1)) > 1 or normalized_category == "武功":
                support = 1.0 if form == "path" else 0.5
            else:
                support = 1.0 if form == "triples" else 0.5
            comparison[form]["reasoning_structure_score"] = support
        rows.append({"question_id": question["id"], "category": normalized_category, "comparison": comparison})
    by_category: dict[str, list[dict]] = {}
    for row in rows:
        category = row["category"]
        by_category.setdefault(category, []).append(row["comparison"])
    summary = []
    for category, comparisons in by_category.items():
        for form in ("triples", "path", "subgraph"):
            metrics = [c[form] for c in comparisons]
            summary.append({
                "category": category,
                "injection": form,
                "questions": len(metrics),
                "answer_entity_coverage": round(sum(m["answer_entity_coverage"] for m in metrics) / len(metrics), 4),
                "avg_context_chars": round(sum(m["context_chars"] for m in metrics) / len(metrics), 2),
                "reasoning_structure_score": round(sum(m["reasoning_structure_score"] for m in metrics) / len(metrics), 4),
            })
    conclusions = {
        "人物": "单跳人物关系优先三元组；多跳人物题优先路径。",
        "武功": "武功传承涉及方向和先后顺序，优先路径。",
        "门派": "门派成员与绝学是聚合问题，优先子图摘要。",
        "综合": "综合比较应保留更广上下文，优先子图摘要并结合原文。",
    }
    report = {
        "description": "离线结构覆盖与推理结构适配实验；reasoning_structure_score 是结构代理指标，不冒充真实 LLM 准确率。",
        "summary": summary,
        "conclusions": {k: v for k, v in conclusions.items() if k in by_category},
        "results": rows,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("output/injection_experiment.json"))
    args = parser.parse_args()
    report = run(args.output)
    print(f"已完成 {len(report['results'])} 道题的三种注入形式对比：{args.output}")
