"""核心模块单测（任务 08/11/18/23 的回归用例）。"""
import json

import pytest

from core.evidence import (evidence_entity_names, make_bundle, make_edge, make_node,
                           normalize_evidence, render_evidence)
from core.entity_link import EntityIndex
from core.ontology import (BIDIRECTIONAL_RELS, RELATIONS, RELATION_TYPES,
                           is_noise_name, validate_relation)
from core.query import detect_scope, normalize_top_k
from core.question_plan import plan_relations, traverse_plan
from eval.metrics import (entity_prf, entity_string_hit, evaluate_result,
                          path_completeness, path_is_continuous)


# ============ 本体（任务 08） ============

class TestOntology:
    def test_relation_endpoint_rules(self):
        assert validate_relation("MASTER_OF", "人物", "人物")[0]
        assert not validate_relation("MASTER_OF", "门派", "武功")[0]
        assert not validate_relation("BELONGS_TO", "人物", "人物")[0]
        assert validate_relation("BELONGS_TO", "人物", "门派")[0]
        assert not validate_relation("UNKNOWN_REL", "人物", "人物")[0]

    def test_symmetric_relations(self):
        assert BIDIRECTIONAL_RELS == {"SPOUSE_OF", "SWORN_BROTHER_OF", "ENEMY_OF"}

    def test_descendant_direction_documented(self):
        spec = RELATIONS["DESCENDANT_OF"]
        assert spec.domains == frozenset({"人物"})
        assert "祖先" in spec.description

    def test_noise_names(self):
        assert is_noise_name("师父") and is_noise_name("某")
        assert not is_noise_name("洪七公")


# ============ 证据契约（任务 18） ============

class TestEvidence:
    def test_normalize_legacy_shapes(self):
        legacy = [
            {"name": "郭靖", "depth": 0},
            {"from": "洪七公", "to": "郭靖"},
            {"person": "黄蓉", "arts": ["打狗棒法"]},
            {"source": "黄药师", "rel": "父母", "target": "黄蓉"},
            {"chunk_id": "c1", "text": "原文", "score": 0.9},
        ]
        bundles = normalize_evidence("test", legacy)
        assert [b["kind"] for b in bundles] == ["chain", "art", "member", "triple", "chunk"]
        assert bundles[4]["text"] == "原文"

    def test_bundle_has_required_fields(self):
        bundle = make_bundle("path", source_method="m",
                             nodes=[make_node("郭靖", "人物")],
                             edges=[make_edge("郭靖", "洪七公", "MASTER_OF",
                                              direction="backward", chunk_ids=["c1"])])
        for key in ("kind", "source_method", "confidence", "seed", "complete",
                    "nodes", "edges", "chunk_ids", "text", "legacy"):
            assert key in bundle
        assert bundle["chunk_ids"] == ["c1"]

    def test_render_keeps_direction(self):
        bundle = make_bundle("path", source_method="m",
                             edges=[make_edge("郭靖", "洪七公", "MASTER_OF",
                                              direction="backward")])
        text = render_evidence([bundle])
        assert "<-" in text and "师徒" in text

    def test_entity_names_collected(self):
        bundle = make_bundle("path", source_method="m",
                             nodes=[make_node("郭靖", "人物")],
                             edges=[make_edge("郭靖", "洪七公", "MASTER_OF")])
        assert set(evidence_entity_names([bundle])) == {"郭靖", "洪七公"}


# ============ 实体链接（任务 11） ============

class TestEntityIndex:
    def _index(self):
        return EntityIndex(entities=[
            {"name": "郭靖", "label": "人物", "era": "射雕"},
            {"name": "洪七公", "label": "人物", "era": "射雕"},
            {"name": "黄药师", "label": "人物", "era": "射雕"},
            {"name": "降龙十八掌", "label": "武功", "era": "射雕"},
            {"name": "张无忌的父亲", "label": "人物", "era": "倚天"},
            {"name": "张无忌", "label": "人物", "era": "倚天"},
        ], aliases=[{"alias": "北丐", "canonical": "洪七公", "label": "人物",
                      "applicable_eras": ["射雕"]}])

    def test_links_multiple_entities(self):
        matches = self._index().link("郭靖和洪七公是什么关系？")
        assert [m.canonical for m in matches] == ["郭靖", "洪七公"]

    def test_prefers_longest_name(self):
        matches = self._index().link("黄药师的女儿")
        assert matches[0].canonical == "黄药师"

    def test_alias_resolves_to_canonical(self):
        matches = self._index().link("北丐是谁")
        assert matches[0].canonical == "洪七公"
        assert matches[0].is_alias

    def test_relation_designation_filtered(self):
        """任务 11 回归：'张无忌的父亲' 这类指称不能抢走 '张无忌'。"""
        matches = self._index().link("张无忌的父亲是谁？")
        assert matches[0].canonical == "张无忌"

    def test_label_filter(self):
        matches = self._index().link("降龙十八掌", labels=["武功"])
        assert matches and matches[0].label == "武功"
        assert self._index().link("降龙十八掌", labels=["人物"]) == []


# ============ 问题解析（任务 11/13） ============

class TestQuestionPlan:
    def test_two_master_hops(self):
        steps = plan_relations("郭靖的师父的师父是谁？")
        assert len(steps) == 2
        assert all(s.relation == "MASTER_OF" and s.direction == "in" for s in steps)

    def test_disciple_direction(self):
        steps = plan_relations("洪七公的徒弟有哪些？")
        assert steps[0].relation == "MASTER_OF" and steps[0].direction == "out"

    def test_father_direction(self):
        steps = plan_relations("黄蓉的父亲是谁？")
        assert steps[0].relation == "PARENT_OF" and steps[0].direction == "in"

    def test_composite_relation(self):
        steps = plan_relations("郭靖的岳父是谁？")
        assert [s.relation for s in steps] == ["SPOUSE_OF", "PARENT_OF"]

    def test_no_relation(self):
        assert plan_relations("谁更厉害") == []

    def test_guniang_is_not_a_parent_keyword(self):
        assert plan_relations("谁是他追求的姑娘？") == []
        assert plan_relations("他的娘是谁？")[0].relation == "PARENT_OF"

    def test_traverse_plan_follows_direction(self):
        calls = []

        def fake_run(cypher, params):
            calls.append(cypher)
            if "->(b:人物)" in cypher:  # out
                return [{"source": "洪七公", "target": "郭靖",
                         "type": "MASTER_OF", "chunk_ids": [], "snippets": []}]
            return []

        result = traverse_plan(fake_run, "洪七公",
                               plan_relations("洪七公的徒弟是谁"), limit=5)
        assert result["final"] == ["郭靖"]
        assert result["edges"][0]["direction"] == "forward"


# ============ 指标（任务 23） ============

class TestMetrics:
    def test_negation_not_counted(self):
        assert not entity_string_hit("答案不是洪七公", ["洪七公"])
        assert entity_string_hit("答案是洪七公", ["洪七公"])

    def test_multi_entity_exact_match(self):
        question = {"answer_entities": ["洪七公", "郭靖"]}
        assert entity_prf("洪七公和郭靖", ["洪七公", "郭靖"])["exact_match"] == 1.0
        partial = entity_prf("只有洪七公", ["洪七公", "郭靖"])
        assert partial["exact_match"] == 0.0
        assert partial["recall"] == 0.5

    def test_disconnected_edges_get_no_path_credit(self):
        evidence = [{"edges": [
            {"source": "A", "target": "B", "type": "MASTER_OF", "direction": "forward"},
            {"source": "C", "target": "D", "type": "MASTER_OF", "direction": "forward"},
        ]}]
        continuous, covered = path_is_continuous(evidence)
        assert continuous and covered == 1
        # 两条互不相连的边最多只能覆盖 1 跳，绝不能被当成完整 2 跳路径
        assert path_completeness({"hop": 2}, evidence) == 0.5
        assert path_completeness({"hop": 2}, evidence) < 1.0

    def test_connected_two_hop_path_full_credit(self):
        evidence = [{"edges": [
            {"source": "郭靖", "target": "洪七公", "type": "MASTER_OF", "direction": "backward"},
            {"source": "洪七公", "target": "王重阳", "type": "MASTER_OF", "direction": "backward"},
        ]}]
        assert path_completeness({"hop": 2}, evidence) == 1.0  # 两跳都在同一条链上
        assert path_is_continuous(evidence)[1] == 2

    def test_evaluate_result_shape(self):
        question = {"hop": 1, "acceptable_answers": ["洪七公"],
                    "answer_entities": ["洪七公"], "relation": "师父"}
        result = evaluate_result(question, "洪七公", [{
            "edges": [{"source": "郭靖", "target": "洪七公",
                       "type": "MASTER_OF", "direction": "backward"}]}])
        for key in ("entity_hit", "entity_string_hit", "exact_match",
                    "path_completeness", "path_validity", "evidence_sufficiency"):
            assert key in result
        assert result["entity_string_hit"] is True
        assert result["evidence_sufficiency"] >= 0.5


# ============ 注入（任务 24：不泄漏标准答案） ============

class TestInjection:
    def test_build_context_uses_evidence_not_gold(self):
        from generate.injection import build_context
        bundle = make_bundle("path", source_method="master_chain",
                             edges=[make_edge("郭靖", "洪七公", "MASTER_OF",
                                              direction="backward")])
        text = build_context("master_chain", [bundle], "")
        assert "洪七公" in text
        # 标准答案没有被注入（这里没有 answer_entities 参与）
        assert "acceptable_answers" not in text

    def test_empty_evidence_falls_back_to_raw_context(self):
        from generate.injection import build_context
        assert build_context("vector", [], "原始上下文") == "原始上下文"

    def test_budget_truncates(self):
        from generate.injection import build_context
        bundle = make_bundle("path", source_method="m",
                             edges=[make_edge(f"实体{i}", f"实体{i+1}", "MASTER_OF")
                                    for i in range(50)])
        text = build_context("master_chain", [bundle], "", budget=80)
        assert len(text) <= 200


# ============ 查询范围 ============

class TestQueryScope:
    def test_detect_era(self):
        assert detect_scope("南宋时期丐帮有哪些绝学").eras == ("射雕", "神雕")
        assert detect_scope("倚天屠龙记里张无忌的师父").eras == ("倚天",)

    def test_top_k_normalization(self):
        assert normalize_top_k(None) == 5
        assert normalize_top_k(0) == 5
        assert normalize_top_k(-3) == 5
        assert normalize_top_k(999) == 50
        assert normalize_top_k(3) == 3

# ============ 图谱归并：Cypher 拼接回归（任务 20） ============

class _FakeRecord:
    def __init__(self, payload):
        self._payload = payload

    def single(self):
        return self._payload

    def data(self):
        return self._payload if isinstance(self._payload, list) else [self._payload]


class _FakeSession:
    """记录所有执行的 Cypher，用于校验拼接正确性。"""

    def __init__(self, edges):
        self.queries = []
        self.params = []
        self._edges = edges

    def run(self, query, params=None):
        self.queries.append(query)
        self.params.append(params or {})
        if "RETURN type(r) AS t" in query:
            return _FakeRecord(self._edges)
        if query.startswith("MATCH (c) WHERE elementId(c) = $c"):
            return _FakeRecord({"n": 0})
        return _FakeRecord([])


class TestGraphOpsQueries:
    def test_migrate_edges_cypher_is_balanced(self):
        from ingest import graph_ops

        session = _FakeSession([
            {"t": "MASTER_OF", "xid": "n-2", "props": {}, "dir": "out"},
            {"t": "MENTIONS", "xid": "n-3", "props": {}, "dir": "in"},
        ])
        created, skipped, dropped = graph_ops.migrate_edges(
            session, "n-1", "n-9", {"n-1", "n-9"})
        assert created == 2 and skipped == 0 and dropped == 0
        for query in session.queries:
            assert query.count("(") == query.count(")"), f"括号不平衡：{query}"
            assert "RETURN count(r) AS n" in query or "CREATE" in query \
                or "RETURN type(r)" in query

    def test_migrate_edges_rejects_unknown_relation(self):
        from ingest import graph_ops

        session = _FakeSession([{"t": "SOMETHING_NEW", "xid": "n-2",
                                 "props": {}, "dir": "out"}])
        try:
            graph_ops.migrate_edges(session, "n-1", "n-9", {"n-1", "n-9"})
        except graph_ops.UnknownRelationError:
            pass
        else:
            raise AssertionError("未知关系类型应抛 UnknownRelationError")
        # 未迁移、未删除
        assert not any("CREATE" in q for q in session.queries)

# ============ 关系证据约束与 PARENT_OF 二次校验 ============

class TestRelationEvidence:
    TEXT = ("郭啸天是郭靖的父亲。李萍扶着她回进屋内，给她斟茶。"
            "郭襄没料到竟一击成功，喜出望外。黄药师是郭襄的外公。")

    def test_evidence_must_be_substring(self):
        from ingest.relation_evidence import validate_relationship

        ok, reason, evidence = validate_relationship(
            {"source": "郭啸天", "target": "郭靖", "type": "PARENT_OF",
             "evidence": "郭啸天是郭靖的父亲。"}, self.TEXT)
        assert ok and evidence == "郭啸天是郭靖的父亲。"

        ok, reason, _ = validate_relationship(
            {"source": "郭啸天", "target": "郭靖", "type": "PARENT_OF",
             "evidence": "郭啸天生下了郭靖"}, self.TEXT)   # 改写过的句子
        assert not ok and "子串" in reason

    def test_parent_of_requires_kinship_cue(self):
        from ingest.relation_evidence import validate_relationship

        # 证据句是原文子串，但没有亲属表述 → 拒绝
        ok, reason, _ = validate_relationship(
            {"source": "李萍", "target": "郭靖", "type": "PARENT_OF",
             "evidence": "李萍扶着她回进屋内，给她斟茶。"}, self.TEXT)
        assert not ok and "亲属" in reason

    def test_parent_of_cooccurrence_is_rejected(self):
        """回归：'郭襄' 与 '郭靖' 同段出现，但没有亲属表述 → 不能当父子关系。"""
        from ingest.relation_evidence import validate_relationship

        ok, reason, _ = validate_relationship(
            {"source": "郭襄", "target": "郭靖", "type": "PARENT_OF"}, self.TEXT)
        assert not ok

    def test_parent_of_with_cue_passes_without_evidence_field(self):
        from ingest.relation_evidence import validate_relationship

        text = "郭啸天是郭靖的父亲。"
        ok, _, evidence = validate_relationship(
            {"source": "郭啸天", "target": "郭靖", "type": "PARENT_OF"}, text)
        assert ok and "父亲" in evidence

    def test_non_strict_type_keeps_cooccurrence(self):
        from ingest.relation_evidence import validate_relationship

        text = "洪七公把降龙十八掌传给了郭靖。"
        ok, _, evidence = validate_relationship(
            {"source": "洪七公", "target": "郭靖", "type": "MASTER_OF"}, text)
        assert ok and "传" in evidence

    def test_gate_splits_kept_and_rejected(self):
        from ingest.relation_evidence import gate_relationships

        kept, rejected = gate_relationships([
            {"source": "郭啸天", "target": "郭靖", "type": "PARENT_OF",
             "evidence": "郭啸天是郭靖的父亲。"},
            {"source": "郭襄", "target": "郭靖", "type": "PARENT_OF",
             "evidence": "郭襄没料到竟一击成功，喜出望外。"},
        ], self.TEXT)
        assert len(kept) == 1 and kept[0]["source"] == "郭啸天"
        assert len(rejected) == 1 and "亲属" in rejected[0]["reason"]
        assert kept[0]["evidence"] == "郭啸天是郭靖的父亲。"
