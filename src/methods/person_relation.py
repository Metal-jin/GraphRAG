"""人物关系检索（person_relation）——任务 13 / 11 重写。

修复内容：
- 区分方向：问"父亲"查入边（别人 -> 我），问"儿子"查出边（我 -> 别人）；
- 保留正式关系类型（PARENT_OF/SPOUSE_OF/...），不再统一成"父母子女"；
- 支持组合多跳（岳父 = 配偶 -> 父亲；"X 的师父的师父"由关系计划逐步执行）；
- 每一步带来源块证据；义父/岳父等超出现有 schema 的关系明确说明边界。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.entity_link import EntityIndex
from core.evidence import make_bundle, make_node
from core.interfaces import Answer, QAMethod
from core.question_plan import focus_person_question, plan_relations, traverse_plan
from core.registry import register
from methods._common import (current_index, ensure_question, no_entity_answer,
                             resolve_scope, resolve_top_k)

# 明确说明"本体没有建模"的亲属称谓（不硬塞进 PARENT_OF）
UNSUPPORTED_RELATIONS = {
    "义父": "义父属于结拜/收养关系，当前本体没有对应关系类型",
    "义母": "义母属于结拜/收养关系，当前本体没有对应关系类型",
    "干爹": "干爹属于收养关系，当前本体没有对应关系类型",
    "干娘": "干娘属于收养关系，当前本体没有对应关系类型",
    "侄子": "侄子属于旁系亲属，当前本体没有对应关系类型",
    "外甥": "外甥属于旁系亲属，当前本体没有对应关系类型",
}


@register("person_relation")
class PersonRelationMethod(QAMethod):
    name = "person_relation"

    def __init__(self, data_loader: Any = None, chunks=None,
                 entity_index: Optional[EntityIndex] = None,
                 run_query: Any = None):
        self.data_loader = data_loader
        self.chunks = chunks
        self.entity_index = entity_index
        self._run_query = run_query

    def _query(self):
        if self._run_query is not None:
            return self._run_query
        from ingest.data_loader import run_query
        return run_query

    def ask(self, question: str, top_k: int = 5) -> Answer:
        question = ensure_question(question, self.name)
        top_k = resolve_top_k(top_k)
        scope = resolve_scope(question)

        index = current_index(self.data_loader, self.entity_index)
        aliases = index.alias_mapping("人物")
        focused, people = focus_person_question(question, index.link(question, labels=["人物"]), aliases)
        if not people:
            return no_entity_answer(self.name, question, "人物", scope)
        seed = people[0].canonical

        steps = plan_relations(focused, people)
        if not steps:
            unsupported = [text for word, text in UNSUPPORTED_RELATIONS.items() if word in question]
            if unsupported:
                return Answer(
                    answer_text=f"无法回答：{unsupported[0]}。",
                    method_name=self.name, evidence=[],
                    debug_info={"question": question, "seed": seed,
                                "status": "unsupported_relation"},
                    raw_context="")
            return Answer(
                answer_text="未能识别问题涉及的关系类型。",
                method_name=self.name, evidence=[],
                debug_info={"question": question, "seed": seed,
                            "status": "no_relation"},
                raw_context="")

        result = traverse_plan(self._query(), seed, steps, limit=top_k, aliases=aliases)
        if result.get("error"):
            return Answer(
                answer_text=f"查询人物关系失败（请确认 Neo4j 已启动、数据已入库）：{result['error']}",
                method_name=self.name, evidence=[],
                debug_info={"seed": seed, "error": result["error"],
                            "status": "error"},
                raw_context="")

        step_details = [step.to_dict() for step in steps]
        keywords = "的".join(dict.fromkeys(step.keyword for step in steps))
        if not result["paths"]:
            return Answer(
                answer_text=f"图谱中没有找到 {seed} 的{keywords}完整路径。",
                method_name=self.name, evidence=[],
                debug_info={"seed": seed, "steps": step_details,
                            "hit_count": 0, "stopped_at": result["stopped_at"],
                            "status": "no_result"},
                raw_context="")

        evidence = []
        for path in result["paths"]:
            edges = path["edges"]
            text = "；".join(f"（{e['source']}，{e['type']}，{e['target']}）" for e in edges)
            evidence.append(make_bundle(
                "path", source_method=self.name, seed=seed, complete=True,
                nodes=[make_node(name, "人物") for name in path["names"]],
                edges=edges,
                text=text, legacy={"steps": step_details, "final": [path["names"][-1]]},
            ))
        targets = result["final"]
        answer_text = f"{seed} 的{keywords}候选：{'、'.join(targets)}。"
        return Answer(
            answer_text=answer_text, method_name=self.name, evidence=evidence,
            debug_info={"question": question, "seed": seed, "steps": step_details,
                        "hit_count": len(result["edges"]), "path_count": len(evidence),
                        "scope": scope.to_dict(), "stopped_at": "", "status": "ok"},
            raw_context="\n".join(item["text"] for item in evidence))
