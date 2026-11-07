"""实体对齐系统测试（任务 08/20/21 的回归用例）。

纯函数测试，不依赖 Neo4j。
"""
import json

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
# ① RuleNormalizer
# ============================================================

class TestRuleNormalizer:
    def test_strip_title_keeps_identity_suffix(self):
        """安全契约：帮主/夫人/姑娘等身份后缀**不剥离**（避免误合并不同的人）。"""
        assert RuleNormalizer().strip_title("洪帮主") == "洪帮主"
        assert RuleNormalizer().strip_title("黄夫人") == "黄夫人"
        assert RuleNormalizer().strip_title("段姑娘") == "段姑娘"

    def test_strip_title_safe_suffix(self):
        assert RuleNormalizer().strip_title("一灯大师") == "一灯"
        assert RuleNormalizer().strip_title("郭大侠") == "郭"
        assert RuleNormalizer().strip_title("黄药师前辈") == "黄药师"

    def test_strip_title_keeps_short_intact(self):
        assert RuleNormalizer().strip_title("掌门") == "掌门"

    def test_strip_title_no_match_returns_input(self):
        assert RuleNormalizer().strip_title("洪七公") == "洪七公"

    def test_normalize_surname_zhuge(self):
        assert RuleNormalizer().normalize_surname("诸葛氏") == "诸葛"

    def test_normalize_surname_unchanged(self):
        assert RuleNormalizer().normalize_surname("黄药师") == "黄药师"

    def test_normalize_combo(self):
        assert RuleNormalizer().normalize("诸葛氏道长") == "诸葛"

    def test_is_noise_known(self):
        assert RuleNormalizer.is_noise("师父") is True
        assert RuleNormalizer.is_noise("白雕") is True
        assert RuleNormalizer.is_noise("汗血宝马") is True

    def test_is_noise_short(self):
        assert RuleNormalizer.is_noise("某") is True
        assert RuleNormalizer.is_noise("A") is True

    def test_is_noise_real_name(self):
        assert RuleNormalizer.is_noise("洪七公") is False
        assert RuleNormalizer.is_noise("杨过") is False


# ============================================================
# ② AliasDictionary
# ============================================================

class TestAliasDictionary:
    def test_load_default_returns_empty_if_missing(self, tmp_path):
        assert AliasDictionary.load(tmp_path / "nope.json").entries == []

    def test_lookup_match(self, tmp_path):
        path = tmp_path / "dict.json"
        path.write_text(json.dumps([{
            "alias": "九指神丐", "canonical": "洪七公",
            "label": "人物", "applicable_eras": ["射雕"],
            "source": "人工", "note": "",
        }], ensure_ascii=False), encoding="utf-8")
        entry = AliasDictionary.load(path).lookup("九指神丐", era="射雕", label="人物")
        assert entry is not None and entry.canonical == "洪七公"

    def test_lookup_era_mismatch(self, tmp_path):
        path = tmp_path / "dict.json"
        path.write_text(json.dumps([{
            "alias": "教主", "canonical": "张无忌",
            "label": "人物", "applicable_eras": ["倚天"],
        }], ensure_ascii=False), encoding="utf-8")
        dictionary = AliasDictionary.load(path)
        assert dictionary.lookup("教主", era="射雕", label="人物") is None
        assert dictionary.lookup("教主", era="倚天", label="人物") is not None

    def test_lookup_label_mismatch(self, tmp_path):
        path = tmp_path / "dict.json"
        path.write_text(json.dumps([{
            "alias": "魔教", "canonical": "明教", "label": "门派", "applicable_eras": [],
        }], ensure_ascii=False), encoding="utf-8")
        assert AliasDictionary.load(path).lookup("魔教", era="倚天", label="人物") is None

    def test_lookup_empty_eras_means_all(self, tmp_path):
        path = tmp_path / "dict.json"
        path.write_text(json.dumps([{
            "alias": "全真教", "canonical": "全真教", "label": "门派", "applicable_eras": [],
        }], ensure_ascii=False), encoding="utf-8")
        dictionary = AliasDictionary.load(path)
        assert dictionary.lookup("全真教", era="射雕") is not None
        assert dictionary.lookup("全真教", era="倚天") is not None

    def test_add_new_and_overwrite(self):
        dictionary = AliasDictionary()
        dictionary.add("张教主", "张无忌", "人物", ["倚天"])
        assert dictionary.lookup("张教主", "倚天", "人物").canonical == "张无忌"
        dictionary.add("张教主", "张翠山", "人物", ["倚天"])
        assert dictionary.lookup("张教主", "倚天", "人物").canonical == "张翠山"

    def test_same_alias_different_era_allowed(self):
        """同一别名在不同时代可以指向不同人物（任务 20）。"""
        dictionary = AliasDictionary()
        dictionary.add("教主", "张无忌", "人物", ["倚天"])
        dictionary.add("教主", "任我行", "人物", ["笑傲"])
        assert dictionary.lookup("教主", "倚天", "人物").canonical == "张无忌"
        assert dictionary.lookup("教主", "笑傲", "人物").canonical == "任我行"

    def test_conflicts_reported(self):
        """同一 alias + label 指向不同正名（时代集合可重叠）应被报告。"""
        dictionary = AliasDictionary(entries=[
            AliasEntry("教主", "张无忌", "人物", []),
            AliasEntry("教主", "张翠山", "人物", []),
        ])
        conflicts = dictionary.conflicts()
        assert conflicts and conflicts[0]["alias"] == "教主"

    def test_save_roundtrip(self, tmp_path):
        path = tmp_path / "out.json"
        dictionary = AliasDictionary()
        dictionary.add("北丐", "洪七公", "人物", ["射雕"])
        dictionary.save(path)
        assert AliasDictionary.load(path).lookup("北丐", "射雕", "人物").canonical == "洪七公"


# ============================================================
# ③ SimilarityAligner
# ============================================================

class TestSimilarityAligner:
    def test_score_identical(self):
        assert SimilarityAligner().score("洪七公", "洪七公") == 1.0

    def test_char_score_obvious_alias(self):
        assert SimilarityAligner().char_score("洪七公", "欧阳锋") < 0.5

    def test_pinyin_score_similar_pronunciation(self):
        assert SimilarityAligner().pinyin_score("黄药师", "黄藥師") == 1.0

    def test_find_candidates_returns_pairs_above_threshold(self):
        aligner = SimilarityAligner(threshold=0.85)
        candidates = aligner.find_candidates([
            ("洪七公", "射雕", "人物"),
            ("洪七公前辈", "射雕", "人物"),
            ("黄药师", "射雕", "人物"),
            ("欧阳锋", "射雕", "人物"),
        ], label_filter={"人物"})
        names = {(c[0], c[1]) for c in candidates}
        assert ("洪七公", "洪七公前辈") in names or ("洪七公前辈", "洪七公") in names

    def test_find_candidates_respects_label_filter(self):
        aligner = SimilarityAligner(threshold=0.5)
        candidates = aligner.find_candidates([
            ("张三", "射雕", "人物"),
            ("张三", "射雕", "门派"),
        ], label_filter={"人物"})
        assert candidates == []

    def test_threshold_validation(self):
        with pytest.raises(ValueError):
            SimilarityAligner(threshold=1.5)
        with pytest.raises(ValueError):
            SimilarityAligner(threshold=-0.1)


# ============================================================
# ④ DescendantScanner（任务 21）
# ============================================================

class TestDescendantScanner:
    def test_scan_yellow_dress_descendant(self):
        pairs = DescendantScanner().scan_entity({
            "name": "黄衫女子",
            "description": "她约莫二十七八岁年纪……乃杨过之后人",
        })
        assert ("杨过", "黄衫女子", "之后") in pairs

    def test_scan_daughter_pattern(self):
        assert ("郭靖", "郭襄", "之女") in DescendantScanner().scan_entity(
            {"name": "郭襄", "description": "郭靖之女"})

    def test_scan_son_pattern(self):
        pairs = DescendantScanner().scan_entity(
            {"name": "张无忌", "description": "张翠山与殷素素之子"})
        assert ("张翠山", "张无忌", "之子") in pairs

    def test_scan_ignores_unknown_surname(self):
        pairs = DescendantScanner().scan_entity({"name": "某人", "description": "许久之后……"})
        assert not any(pair[0] == "许久" for pair in pairs)

    def test_scan_empty_desc(self):
        assert DescendantScanner().scan_entity({"name": "X", "description": ""}) == []
        assert DescendantScanner().scan_entity({"name": "X", "description": None}) == []

    def test_candidates_require_known_entities(self):
        """任务 21：两端必须能在图谱中定位，否则进入待确认而不是直接落库。"""
        scanner = DescendantScanner()
        entities = [{"name": "黄衫女子", "description": "乃杨过之后人"}]
        candidates = scanner.build_candidates(entities, known_names={"黄衫女子"})
        assert candidates and not candidates[0].valid
        assert "祖先" in candidates[0].reason

    def test_candidates_valid_when_both_known(self):
        scanner = DescendantScanner()
        entities = [{"name": "黄衫女子", "description": "乃杨过之后人"},
                    {"name": "杨过", "description": "神雕大侠"}]
        candidates = scanner.build_candidates(entities, known_names={"黄衫女子", "杨过"})
        assert candidates and candidates[0].valid
        assert candidates[0].ancestor == "杨过"
        assert candidates[0].descendant == "黄衫女子"

    def test_self_loop_rejected(self):
        scanner = DescendantScanner()
        entities = [{"name": "郭靖", "description": "郭靖之女"}]
        candidates = scanner.build_candidates(entities, known_names={"郭靖"})
        assert any(not c.valid for c in candidates)


# ============================================================
# ⑤ AlignmentPipeline（任务 20）
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
        dictionary = AliasDictionary()
        dictionary.add("九指神丐", "洪七公", "人物", ["射雕"])
        pipeline = AlignmentPipeline(dictionary=dictionary)
        decisions = pipeline.discover_alignments(self._ents(), label_filter={"人物"})
        assert any(d.alias_name == "九指神丐" and d.canonical_name == "洪七公"
                   and d.source == "词典" for d in decisions)

    def test_noise_filtered(self):
        pipeline = AlignmentPipeline(dictionary=AliasDictionary())
        decisions = pipeline.discover_alignments(self._ents(), label_filter={"人物"})
        assert all(d.alias_name not in {"师父", "白雕"} for d in decisions)

    def test_rule_layer_pairs_canonical_and_title(self):
        """任务 20 回归：归一后未变化的正名也要参与配对。"""
        pipeline = AlignmentPipeline(dictionary=AliasDictionary())
        entities = [
            {"name": "一灯", "era": "射雕", "label": "人物", "description": ""},
            {"name": "一灯大师", "era": "射雕", "label": "人物", "description": ""},
        ]
        decisions = pipeline.discover_alignments(entities, label_filter={"人物"})
        pairs = {(d.alias_name, d.canonical_name) for d in decisions if d.source == "规则"}
        assert ("一灯", "一灯大师") in pairs or ("一灯大师", "一灯") in pairs

    def test_similarity_not_applied_by_default(self):
        pipeline = AlignmentPipeline(dictionary=AliasDictionary(), threshold=0.8)
        entities = [
            {"name": "洪七公", "era": "射雕", "label": "人物"},
            {"name": "洪七公前辈", "era": "射雕", "label": "人物"},
        ]
        default = pipeline.discover_alignments(entities, label_filter={"人物"})
        assert all(d.source != "相似度" for d in default)
        assert pipeline._similarity_candidates  # 候选仍然产出

    def test_similarity_applied_when_requested(self):
        pipeline = AlignmentPipeline(dictionary=AliasDictionary(), threshold=0.8)
        # 这两个名字规则层无法配对（归一后不同），只能靠相似度层
        entities = [
            {"name": "洪七公", "era": "射雕", "label": "人物"},
            {"name": "洪七", "era": "射雕", "label": "人物"},
        ]
        decisions = pipeline.discover_alignments(entities, label_filter={"人物"},
                                                 include_similarity=True)
        assert any(d.source == "相似度" for d in decisions)

    def test_chain_flattening(self):
        """A->B 与 B->C 应压平成 A->C，不留下指向中间节点的决策。"""
        dictionary = AliasDictionary()
        dictionary.add("北丐", "洪七公", "人物", [])
        dictionary.add("洪七公", "洪七公真人", "人物", [])
        pipeline = AlignmentPipeline(dictionary=dictionary)
        entities = [
            {"name": "北丐", "era": "射雕", "label": "人物"},
            {"name": "洪七公", "era": "射雕", "label": "人物"},
            {"name": "洪七公真人", "era": "射雕", "label": "人物"},
        ]
        decisions = pipeline.discover_alignments(entities, label_filter={"人物"})
        mapping = {d.alias_name: d.canonical_name for d in decisions}
        assert mapping.get("北丐") == "洪七公真人"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))  # noqa: F821
