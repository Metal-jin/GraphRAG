"""五个检索方法的离线测试（任务 12/13/14/15/16 的回归用例）。

全部通过注入 fake run_query / graph 完成，不依赖 Neo4j。
"""
import pytest

from core.entity_link import EntityIndex
from methods.art_lineage import ArtLineageMethod
from methods.cross_novel import CrossNovelMethod
from methods.master_chain import MasterChainMethod
from methods.person_relation import PersonRelationMethod
from methods.sect_agg import SectAggMethod

PEOPLE = [
    {"name": "郭靖", "label": "人物", "era": "射雕"},
    {"name": "洪七公", "label": "人物", "era": "射雕"},
    {"name": "黄蓉", "label": "人物", "era": "射雕"},
    {"name": "黄药师", "label": "人物", "era": "射雕"},
    {"name": "张无忌", "label": "人物", "era": "倚天"},
    {"name": "张三丰", "label": "人物", "era": "倚天"},
    {"name": "丐帮", "label": "门派", "era": "射雕"},
    {"name": "武当派", "label": "门派", "era": "倚天"},
    {"name": "降龙十八掌", "label": "武功", "era": "射雕"},
]


def index():
    return EntityIndex(entities=PEOPLE)


# ============ 师徒链（任务 12） ============

class TestMasterChain:
    def test_upward_path_is_directed(self):
        def fake_run(cypher, params):
            assert "<-[:MASTER_OF*1..1]-" in cypher
            return [{"names": ["郭靖", "洪七公"],
                     "rels": [{"chunk_ids": ["c1"], "snippets": ["洪七公收郭靖为徒"]}],
                     "depth": 1}]

        answer = MasterChainMethod(entity_index=index(), run_query=fake_run)            .ask("郭靖的师父是谁？", top_k=5)
        assert answer.debug_info["direction"] == "up"
        bundle = answer.evidence[0]
        assert bundle["edges"][0]["direction"] == "backward"
        assert bundle["chunk_ids"] == ["c1"]
        assert "洪七公" in answer.answer_text

    def test_downward_direction_detected(self):
        captured = {}

        def fake_run(cypher, params):
            captured["cypher"] = cypher
            return [{"names": ["洪七公", "郭靖"], "rels": [{}], "depth": 1}]

        MasterChainMethod(entity_index=index(), run_query=fake_run)            .ask("洪七公的徒弟有哪些？", top_k=5)
        assert "-[:MASTER_OF*1..1]->" in captured["cypher"]

    def test_hop_count_from_question(self):
        captured = {}

        def fake_run(cypher, params):
            captured["cypher"] = cypher
            return []

        MasterChainMethod(entity_index=index(), run_query=fake_run)            .ask("郭靖的师父的师父是谁？", top_k=5)
        assert "*2..2]-" in captured["cypher"]

    def test_named_subject_after_unsupported_relation(self):
        people = EntityIndex(entities=[
            {"name": name, "label": "人物"} for name in ("张无忌", "义父", "谢逊", "成昆")
        ])

        def fake_run(cypher, params):
            assert params["name"] == "谢逊"
            assert "<-[:MASTER_OF*1..1]-" in cypher
            return [{"names": ["谢逊", "成昆"], "rels": [{}], "depth": 1}]

        answer = MasterChainMethod(entity_index=people, run_query=fake_run).ask(
            "张无忌的义父谢逊的师父是谁？")
        assert [n["name"] for n in answer.evidence[0]["nodes"]] == ["谢逊", "成昆"]

    def test_respects_top_k(self):
        rows = [{"names": ["郭靖", f"师父{i}"], "rels": [{}], "depth": 1} for i in range(20)]

        def fake_run(cypher, params):
            return rows

        answer = MasterChainMethod(entity_index=index(), run_query=fake_run)            .ask("郭靖的师父是谁？", top_k=3)
        assert len(answer.evidence) <= 3

    def test_no_entity(self):
        answer = MasterChainMethod(entity_index=index(), run_query=lambda *a: [])            .ask("谁是最厉害的人？", top_k=5)
        assert answer.debug_info["status"] == "no_entity"


# ============ 人物关系（任务 13） ============

class TestPersonRelation:
    def test_father_queries_incoming_edge(self):
        captured = []

        def fake_run(cypher, params):
            captured.append(cypher)
            if "-[r:PARENT_OF]->(b:人物) WHERE b.name IN $names" in cypher:
                return [{"source": "黄药师", "target": "黄蓉", "type": "PARENT_OF",
                         "chunk_ids": ["c9"], "snippets": ["黄药师之女黄蓉"]}]
            return []

        answer = PersonRelationMethod(entity_index=index(), run_query=fake_run)            .ask("黄蓉的父亲是谁？", top_k=5)
        assert any("-[r:PARENT_OF]->(b:人物) WHERE b.name IN $names" in c for c in captured)
        assert "黄药师" in answer.answer_text
        assert answer.evidence[0]["edges"][0]["direction"] == "backward"

    def test_son_queries_outgoing_edge(self):
        captured = []

        def fake_run(cypher, params):
            captured.append(cypher)
            return []

        PersonRelationMethod(entity_index=index(), run_query=fake_run)            .ask("黄药师的儿子是谁？", top_k=5)
        assert any("(a:人物)-[r:PARENT_OF]->(b:人物) WHERE a.name IN $names" in c
                   for c in captured)

    def test_composite_relation_two_steps(self):
        calls = []

        def fake_run(cypher, params):
            calls.append((cypher, params["names"]))
            if "SPOUSE_OF" in cypher and params["names"] == ["郭靖"]:
                return [{"source": "郭靖", "target": "黄蓉", "type": "SPOUSE_OF",
                         "chunk_ids": [], "snippets": []}]
            if "PARENT_OF" in cypher and params["names"] == ["黄蓉"]:
                return [{"source": "黄药师", "target": "黄蓉", "type": "PARENT_OF",
                         "chunk_ids": [], "snippets": []}]
            return []

        answer = PersonRelationMethod(entity_index=index(), run_query=fake_run)            .ask("郭靖的岳父是谁？", top_k=5)
        assert "黄药师" in answer.answer_text
        assert answer.debug_info["steps"][0]["relation"] == "SPOUSE_OF"

    def test_unsupported_relation_is_explained(self):
        answer = PersonRelationMethod(entity_index=index(), run_query=lambda *a: [])            .ask("郭靖的义父是谁？", top_k=5)
        assert answer.debug_info["status"] == "unsupported_relation"

    def test_named_intermediate_constrains_lookup_before_limit(self):
        people = EntityIndex(entities=[
            {"name": name, "label": "人物"}
            for name in ("张无忌", "父亲", "张翠山", "张三丰", "张五侠", "殷素素")
        ], aliases=[{"alias": "张五侠", "canonical": "张翠山", "label": "人物"}])

        def fake_run(cypher, params):
            if "PARENT_OF" in cypher:
                assert "a.name IN $targets" in cypher
                assert params["targets"] == ["张翠山", "张五侠"]
                return [{"source": "张五侠", "target": "张无忌", "type": "PARENT_OF",
                         "chunk_ids": ["parent"]}]
            assert params["names"] == ["张翠山", "张五侠"]
            return [{"source": "张三丰", "target": "张翠山", "type": "MASTER_OF",
                     "chunk_ids": ["master"]}]

        answer = PersonRelationMethod(entity_index=people, run_query=fake_run).ask(
            "张无忌的父亲张翠山的师父是谁？", top_k=1)
        assert answer.debug_info["steps"][0]["target"] == "张翠山"
        path, = answer.evidence
        assert [node["name"] for node in path["nodes"]] == ["张无忌", "张翠山", "张三丰"]
        assert path["chunk_ids"] == ["master", "parent"]
        from generate.injection import build_context
        context = build_context(answer.method_name, answer.evidence, answer.raw_context)
        assert "张翠山 ->" in context and "张三丰 ->" in context
        assert "\n" not in context

    def test_does_not_return_partial_branch_as_answer(self):
        def fake_run(cypher, params):
            if "SPOUSE_OF" in cypher:
                return [{"source": "郭靖", "target": "黄蓉", "type": "SPOUSE_OF"}]
            return []

        answer = PersonRelationMethod(entity_index=index(), run_query=fake_run).ask(
            "郭靖的妻子的师父是谁？")
        assert answer.debug_info["status"] == "no_result"
        assert not answer.evidence and not answer.raw_context


# ============ 门派聚合（任务 14） ============

class TestSectAgg:
    def test_members_keep_connections(self):
        def fake_run(cypher, params):
            if "BELONGS_TO" in cypher and "MASTERS" not in cypher and "FOUNDER_OF" not in cypher:
                return [{"person": "郭靖", "era": "射雕",
                         "chunk_ids": ["c1"], "snippets": []}]
            return []

        answer = SectAggMethod(entity_index=index(), run_query=fake_run)            .ask("丐帮有哪些成员？", top_k=5)
        bundle = answer.evidence[0]
        assert bundle["edges"][0]["type"] == "BELONGS_TO"
        assert answer.debug_info["kind"] == "members"

    def test_founder_question(self):
        def fake_run(cypher, params):
            if "FOUNDER_OF" in cypher:
                return [{"person": "张三丰", "chunk_ids": [], "snippets": []}]
            return []

        answer = SectAggMethod(entity_index=index(), run_query=fake_run)            .ask("谁创立了武当派？", top_k=5)
        assert answer.debug_info["kind"] == "founder"
        assert "张三丰" in answer.answer_text

    @pytest.mark.parametrize("question", [
        "张三丰创建了哪个门派？",
        "张无忌的父亲张翠山的师父张三丰创立了什么门派？",
    ])
    def test_founder_as_subject(self, question):
        people = EntityIndex(entities=PEOPLE + [{"name": "张翠山", "label": "人物"}])

        def fake_run(cypher, params):
            assert "FOUNDER_OF" in cypher and params["name"] == "张三丰"
            return [{"sect": "武当派", "chunk_ids": ["c1"], "snippets": []}]

        answer = SectAggMethod(entity_index=people, run_query=fake_run).ask(question)
        assert answer.debug_info["seed"] == "张三丰"
        assert "武当派" in answer.answer_text

    def test_arts_question_marks_caveat(self):
        def fake_run(cypher, params):
            if "MASTERS" in cypher and "BELONGS_TO" in cypher:
                return [{"person": "郭靖", "art": "降龙十八掌",
                         "chunk_ids": [], "snippets": []}]
            return []

        answer = SectAggMethod(entity_index=index(), run_query=fake_run)            .ask("丐帮有哪些绝学？", top_k=5)
        assert "降龙十八掌" in answer.answer_text
        assert "不等于" in answer.answer_text  # 明确说明不是绝学

    def test_leader_question_is_flagged(self):
        def fake_run(cypher, params):
            return []

        answer = SectAggMethod(entity_index=index(), run_query=fake_run)            .ask("丐帮的帮主是谁？", top_k=5)
        assert answer.debug_info.get("leader_unsupported") is True


# ============ 武功传承（任务 15） ============

class TestArtLineage:
    def test_inferred_vs_extracted(self):
        def fake_run(cypher, params):
            if "MASTER_OF" in cypher:
                return [
                    {"source": "洪七公", "target": "郭靖",
                     "chunk_ids": ["c1"], "snippets": ["洪七公传授降龙十八掌"]},
                    {"source": "郭靖", "target": "耶律齐", "chunk_ids": [], "snippets": []},
                ]
            return []

        answer = ArtLineageMethod(entity_index=index(), run_query=fake_run)            .ask("降龙十八掌传给了谁？", top_k=5)
        assert "有原文证据" in answer.answer_text
        assert "推断" in answer.answer_text
        edges = answer.evidence[0]["edges"]
        assert {e["confidence"] for e in edges} == {"extracted", "inferred"}

    def test_origin_question(self):
        def fake_run(cypher, params):
            if "BRANCHED_FROM" in cypher:
                return [{"source": "降龙二十八掌", "chunk_ids": []}]
            return []

        answer = ArtLineageMethod(entity_index=index(), run_query=fake_run)            .ask("降龙十八掌源自哪里？", top_k=5)
        assert answer.debug_info["kind"] == "origin"
        assert "降龙二十八掌" in answer.answer_text

    def test_no_entity(self):
        answer = ArtLineageMethod(entity_index=index(), run_query=lambda *a: [])            .ask("谁最厉害？", top_k=5)
        assert answer.debug_info["status"] == "no_entity"


# ============ 跨书关联（任务 16） ============

class TestCrossNovel:
    def _graph(self):
        return {
            "nodes": [
                {"name": "杨过", "type": "人物", "era": "神雕"},
                {"name": "小龙女", "type": "人物", "era": "神雕"},
                {"name": "丐帮", "type": "门派", "era": "神雕"},
                {"name": "黄衫女子", "type": "人物", "era": "倚天"},
            ],
            "edges": [
                {"source": "杨过", "target": "丐帮", "type": "BELONGS_TO"},
                {"source": "杨过", "target": "小龙女", "type": "SPOUSE_OF"},
                {"source": "小龙女", "target": "黄衫女子", "type": "DESCENDANT_OF"},
            ],
        }

    def test_path_through_non_person_does_not_crash(self):
        """任务 16 回归：路径经过门派节点时不再 KeyError。"""
        answer = CrossNovelMethod(graph=self._graph()).ask("杨过和丐帮有什么关系？", top_k=5)
        assert answer.method_name == "cross_novel"
        assert answer.debug_info["status"] in ("ok", "no_result")

    def test_blood_relation_flagged(self):
        answer = CrossNovelMethod(graph=self._graph()).ask("杨过和黄衫女子有什么关联？", top_k=5)
        assert answer.evidence
        assert answer.evidence[0]["blood_relation"] is True
        assert answer.evidence[0]["distance"] == 2

    def test_output_contains_intermediate_relations(self):
        answer = CrossNovelMethod(graph=self._graph()).ask("杨过和黄衫女子有什么关联？", top_k=5)
        assert "夫妻" in answer.answer_text or "血缘" in answer.answer_text

    def test_no_entity(self):
        answer = CrossNovelMethod(graph=self._graph()).ask("谁最厉害？", top_k=5)
        assert answer.debug_info["status"] == "no_entity"
