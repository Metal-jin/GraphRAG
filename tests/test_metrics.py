from eval.metrics import category_name, evaluate_result, path_completeness, summarize_by_category


def test_explainability_metrics_for_two_hop_path():
    question = {"hop": 2, "acceptable_answers": ["王重阳"], "answer_entities": ["王重阳"]}
    evidence = [{"name": "郭靖", "depth": 0}, {"name": "洪七公", "depth": 1}, {"name": "王重阳", "depth": 2}]
    result = evaluate_result(question, "答案是王重阳", evidence)
    assert result["entity_hit"] is True
    assert result["path_completeness"] == 1.0
    assert result["evidence_sufficiency"] == 1.0


def test_category_normalization_and_breakdown():
    assert category_name({"category": "多跳武功"}) == "武功"
    rows = [{"category": "人物", "entity_hit": True, "path_completeness": 1, "evidence_sufficiency": 1}]
    assert summarize_by_category(rows)[0]["accuracy"] == 1.0


def test_stage2_dataset_covers_four_required_categories():
    from eval.run_compare import load_questions
    assert {category_name(q) for q in load_questions()} == {"人物", "武功", "门派", "综合"}
