"""任务 C 跨书人物关联的离线测试。"""

from methods.cross_novel import CrossNovelMethod


def test_cross_novel_returns_path_and_distance():
    graph = {
        "nodes": [
            {"name": "杨过", "type": "人物", "era": "神雕侠侣"},
            {"name": "小龙女", "type": "人物", "era": "神雕侠侣"},
            {"name": "黄衫女子", "type": "人物", "era": "倚天屠龙记"},
        ],
        "edges": [
            {"source": "杨过", "target": "小龙女", "type": "SPOUSE_OF"},
            {"source": "小龙女", "target": "黄衫女子", "type": "INHERITS"},
        ],
    }
    answer = CrossNovelMethod(graph=graph).ask("杨过和黄衫女子有什么关联？")
    assert answer.method_name == "cross_novel"
    assert answer.evidence[0]["distance"] == 2
    assert answer.evidence[0]["path"] in (
        ["杨过", "小龙女", "黄衫女子"],
        ["黄衫女子", "小龙女", "杨过"],
    )
    assert "跨书人物关联" in answer.answer_text
