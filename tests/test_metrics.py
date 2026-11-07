"""可解释性指标测试（任务 23 重做后的契约）。"""
from core.evidence import make_bundle, make_edge
from eval.metrics import (category_name, entity_prf, entity_string_hit,
                          evaluate_result, is_negated, path_completeness,
                          summarize_by_category)


def _path_evidence(edges):
    return [make_bundle("path", source_method="master_chain",
                        edges=[make_edge(**edge) for edge in edges])]


def test_two_hop_path_full_credit():
    question = {"hop": 2, "acceptable_answers": ["王重阳"],
                "answer_entities": ["王重阳"], "relation": "师父"}
    evidence = _path_evidence([
        {"source": "郭靖", "target": "洪七公", "rel_type": "MASTER_OF",
         "direction": "backward"},
        {"source": "洪七公", "target": "王重阳", "rel_type": "MASTER_OF",
         "direction": "backward"},
    ])
    result = evaluate_result(question, "答案是王重阳", evidence)
    assert result["entity_string_hit"] is True
    assert result["path_completeness"] == 1.0
    assert result["evidence_sufficiency"] == 1.0


def test_negation_is_not_a_hit():
    assert is_negated("答案不是洪七公", "洪七公")
    assert entity_string_hit("洪七公", ["洪七公"])
    assert not entity_string_hit("答案不是洪七公", ["洪七公"])


def test_multi_entity_requires_all():
    question = {"answer_entities": ["洪七公", "郭靖"]}
    partial = entity_prf("只有洪七公", ["洪七公", "郭靖"])
    assert partial["exact_match"] == 0.0 and partial["recall"] == 0.5
    full = entity_prf("洪七公与郭靖", ["洪七公", "郭靖"])
    assert full["exact_match"] == 1.0


def test_disconnected_path_scores_zero_for_multihop():
    evidence = _path_evidence([
        {"source": "A", "target": "B", "rel_type": "MASTER_OF"},
        {"source": "C", "target": "D", "rel_type": "MASTER_OF"},
    ])
    assert path_completeness({"hop": 2}, evidence) == 0.5  # 只能覆盖 1 跳，不是完整路径


def test_category_normalization_and_breakdown():
    assert category_name({"category": "多跳武功"}) == "武功"
    assert category_name({"category": "门派"}) == "门派"
    rows = [{"method": "m", "category": "人物", "status": "ok", "entity_hit": True,
             "path_completeness": 1, "evidence_sufficiency": 1}]
    assert summarize_by_category(rows)[0]["accuracy"] == 1.0


def test_stage2_dataset_covers_four_required_categories():
    from eval.run_compare import load_questions
    assert {category_name(q) for q in load_questions()} == {"人物", "武功", "门派", "综合"}
