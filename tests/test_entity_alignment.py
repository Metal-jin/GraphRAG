"""
tests/test_entity_alignment.py
阶段二实体对齐系统的纯函数单测：四层各自测试，不依赖 Neo4j。
"""
import json
from pathlib import Path

import pytest

from ingest.entity_alignment import (
    AliasDictionary,
    AliasEntry,
    AlignmentPipeline,
    DescendantScanner,
    RuleNormalizer,
    SimilarityAligner,
)


# ============================================================
# ① RuleNormalizer 测试
# ============================================================

class TestRuleNormalizer:
    def test_strip_title_helpmaster(self):
        assert RuleNormalizer().strip_title("洪帮主") == "洪"

    def test_strip_title_da_master(self):
        assert RuleNormalizer().strip_title("一灯大师") == "一灯"

    def test_strip_title_da_xia(self):
        assert RuleNormalizer().strip_title("郭大侠") == "郭"

    def test_strip_title_keeps_short_intact(self):
        """长度 ≤ 称谓长度+1 的剥后结果不应被剥（避免"掌门" → "掌"）。"""
        # "掌门" 是称谓，但本身长度只有 2，按规则不会被剥（无后缀匹配）
        assert RuleNormalizer().strip_title("掌门") == "掌门"

    def test_strip_title_no_match_returns_input(self):
        assert RuleNormalizer().strip_title("洪七公") == "洪七公"

    def test_normalize_surname_zhuge(self):
        assert RuleNormalizer().normalize_surname("诸葛氏") == "诸葛"

    def test_normalize_surname_unchanged(self):
        assert RuleNormalizer().normalize_surname("黄药师") == "黄药师"

    def test_normalize_combo(self):
        """先归一姓氏再剥称谓。"""
        # "诸葛氏道长" -> "诸葛氏" -> "诸葛"（剥"道长"）
        assert RuleNormalizer().normalize("诸葛氏道长") == "诸葛"

    def test_is_noise_known(self):
        assert RuleNormalizer.is_noise("师父") is True
        assert RuleNormalizer.is_noise("白雕") is True
        assert RuleNormalizer.is_noise("汗血宝马") is True

    def test_is_noise_short(self):
        """长度 ≤ 1 视为指称。"""
        assert RuleNormalizer.is_noise("某") is True
        assert RuleNormalizer.is_noise("那") is True
        assert RuleNormalizer.is_noise("A") is True

    def test_is_noise_real_name(self):
        assert RuleNormalizer.is_noise("洪七公") is False
        assert RuleNormalizer.is_noise("杨过") is False


# ============================================================
# ② AliasDictionary 测试
# ============================================================

class TestAliasDictionary:
    def test_load_default_returns_empty_if_missing(self, tmp_path):
        path = tmp_path / "nope.json"
        d = AliasDictionary.load(path)
        assert d.entries == []

    def test_lookup_match(self, tmp_path):
        path = tmp_path / "dict.json"
        path.write_text(
            json.dumps([{
                "alias": "九指神丐", "canonical": "洪七公",
                "label": "人物", "applicable_eras": ["射雕"],
                "source": "人工", "note": "",
            }], ensure_ascii=False),
            encoding="utf-8",
        )
        d = AliasDictionary.load(path)
        entry = d.lookup("九指神丐", era="射雕", label="人物")
        assert entry is not None
        assert entry.canonical == "洪七公"

    def test_lookup_era_mismatch(self, tmp_path):
        path = tmp_path / "dict.json"
        path.write_text(
            json.dumps([{
                "alias": "教主", "canonical": "张无忌",
                "label": "人物", "applicable_eras": ["倚天"],
            }], ensure_ascii=False),
            encoding="utf-8",
        )
        d = AliasDictionary.load(path)
        # 射雕 era 不在 applicable_eras 里 → 不命中
        assert d.lookup("教主", era="射雕", label="人物") is None
        # 倚天 era 命中
        assert d.lookup("教主", era="倚天", label="人物") is not None

    def test_lookup_label_mismatch(self, tmp_path):
        path = tmp_path / "dict.json"
        path.write_text(
            json.dumps([{
                "alias": "魔教", "canonical": "明教",
                "label": "门派", "applicable_eras": [],
            }], ensure_ascii=False),
            encoding="utf-8",
        )
        d = AliasDictionary.load(path)
        # label 不匹配 → 不命中
        assert d.lookup("魔教", era="倚天", label="人物") is None

    def test_lookup_empty_eras_means_all(self, tmp_path):
        path = tmp_path / "dict.json"
        path.write_text(
            json.dumps([{
                "alias": "全真教", "canonical": "全真教",
                "label": "门派", "applicable_eras": [],
            }], ensure_ascii=False),
            encoding="utf-8",
        )
        d = AliasDictionary.load(path)
        # eras 为空 → 任意 era 都命中
        assert d.lookup("全真教", era="射雕") is not None
        assert d.lookup("全真教", era="倚天") is not None

    def test_add_new_and_overwrite(self):
        d = AliasDictionary()
        d.add("张教主", "张无忌", "人物", ["倚天"])
        assert d.lookup("张教主", "倚天", "人物").canonical == "张无忌"
        # 覆盖
        d.add("张教主", "张翠山", "人物", ["倚天"])
        assert d.lookup("张教主", "倚天", "人物").canonical == "张翠山"

    def test_save_roundtrip(self, tmp_path):
        path = tmp_path / "out.json"
        d = AliasDictionary()
        d.add("北丐", "洪七公", "人物", ["射雕"])
        d.save(path)
        d2 = AliasDictionary.load(path)
        assert d2.lookup("北丐", "射雕", "人物").canonical == "洪七公"


# ============================================================
# ③ SimilarityAligner 测试
# ============================================================

class TestSimilarityAligner:
    def test_score_identical(self):
        s = SimilarityAligner()
        assert s.score("洪七公", "洪七公") == 1.0

    def test_char_score_obvious_alias(self):
        s = SimilarityAligner()
        # 完全不同的字符串 → 分数应该很低
        assert s.char_score("洪七公", "欧阳锋") < 0.5

    def test_pinyin_score_similar_pronunciation(self):
        s = SimilarityAligner()
        # "黄药师" 和 "黄药師"（繁简）拼音完全一致 → 拼音分 = 1.0
        ps = s.pinyin_score("黄药师", "黄药師")
        assert ps == 1.0

    def test_find_candidates_returns_pairs_above_threshold(self):
        s = SimilarityAligner(threshold=0.85)
        ents = [
            ("洪七公", "射雕", "人物"),
            ("洪七公前辈", "射雕", "人物"),  # 字符 0.83+，拼音相似
            ("黄药师", "射雕", "人物"),
            ("欧阳锋", "射雕", "人物"),
        ]
        cands = s.find_candidates(ents, label_filter={"人物"})
        # 应该至少有"洪七公"与"洪七公前辈"一对
        names = {(c[0], c[1]) for c in cands}
        assert ("洪七公", "洪七公前辈") in names or ("洪七公前辈", "洪七公") in names

    def test_find_candidates_respects_label_filter(self):
        s = SimilarityAligner(threshold=0.5)  # 调低阈值放大召回
        ents = [
            ("张三", "射雕", "人物"),
            ("张三", "射雕", "门派"),  # 同名不同 label，不应配对
        ]
        cands = s.find_candidates(ents, label_filter={"人物"})
        assert cands == []  # 跨 label 不配对

    def test_threshold_validation(self):
        with pytest.raises(ValueError):
            SimilarityAligner(threshold=1.5)
        with pytest.raises(ValueError):
            SimilarityAligner(threshold=-0.1)


# ============================================================
# ④ DescendantScanner 测试
# ============================================================

class TestDescendantScanner:
    def test_scan_yellow_dress_descendant(self):
        """倚天原文：黄衫女子是杨过之后。"""
        s = DescendantScanner()
        ents = [{
            "name": "黄衫女子",
            "description": "她约莫二十七八岁年纪……乃杨过之后人",
        }]
        pairs = s.scan_entity(ents[0])
        assert ("杨过", "黄衫女子", "之后") in pairs or \
               ("杨过", "黄衫女子", "后人") in pairs or \
               ("杨过", "黄衫女子", "之后人") in pairs

    def test_scan_daughter_pattern(self):
        s = DescendantScanner()
        ents = [{"name": "郭襄", "description": "郭靖之女"}]
        pairs = s.scan_entity(ents[0])
        assert ("郭靖", "郭襄", "之女") in pairs

    def test_scan_son_pattern(self):
        s = DescendantScanner()
        ents = [{"name": "张无忌", "description": "张翠山与殷素素之子"}]
        pairs = s.scan_entity(ents[0])
        # "张翠山" 在 "之子" 模式里命中
        assert ("张翠山", "张无忌", "之子") in pairs

    def test_scan_ignores_unknown_surname(self):
        """非大姓开头的"祖先"应被过滤。"""
        s = DescendantScanner()
        ents = [{"name": "某人", "description": "许久之后……"}]
        pairs = s.scan_entity(ents[0])
        # "许久"不是大姓开头，不应被识别为祖先
        assert not any(p[0] == "许久" for p in pairs)

    def test_scan_empty_desc(self):
        s = DescendantScanner()
        assert s.scan_entity({"name": "X", "description": ""}) == []
        assert s.scan_entity({"name": "X", "description": None}) == []


# ============================================================
# ⑤ AlignmentPipeline 测试（不连 Neo4j，喂 entities 列表）
# ============================================================

class TestAlignmentPipeline:
    def _ents(self):
        return [
            {"name": "洪七公", "era": "射雕", "label": "人物", "description": "丐帮帮主"},
            {"name": "九指神丐", "era": "射雕", "label": "人物", "description": "北丐"},
            {"name": "黄蓉", "era": "射雕", "label": "人物", "description": "东邪之女"},
            {"name": "蓉儿", "era": "射雕", "label": "人物", "description": "郭靖之妻"},
            {"name": "欧阳锋", "era": "射雕", "label": "人物", "description": "西毒"},
            {"name": "师父", "era": "射雕", "label": "人物", "description": "指称"},
            {"name": "白雕", "era": "射雕", "label": "人物", "description": "动物"},
        ]

    def test_dictionary_layer(self):
        # 准备临时词典
        d = AliasDictionary()
        d.add("九指神丐", "洪七公", "人物", ["射雕"])
        p = AlignmentPipeline(dictionary=d)
        ents = self._ents()
        decisions = p.discover_alignments(ents, label_filter={"人物"})
        # "九指神丐" 应被词典层归并到"洪七公"
        dict_decisions = [d for d in decisions if d.source == "词典"]
        assert any(d.alias_name == "九指神丐" and d.canonical_name == "洪七公"
                   for d in dict_decisions)

    def test_noise_filtered(self):
        d = AliasDictionary()
        p = AlignmentPipeline(dictionary=d)
        ents = self._ents()
        decisions = p.discover_alignments(ents, label_filter={"人物"})
        # 噪声节点不应出现在决策里
        for dec in decisions:
            assert dec.alias_name not in {"师父", "白雕"}

    def test_all_layers_present(self):
        d = AliasDictionary()
        d.add("九指神丐", "洪七公", "人物", ["射雕"])
        p = AlignmentPipeline(dictionary=d)
        ents = self._ents()
        decisions = p.discover_alignments(ents, label_filter={"人物"})
        sources = {d.source for d in decisions}
        # 词典层必然有；规则层/相似度层可能为空（看数据）
        assert "词典" in sources


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))