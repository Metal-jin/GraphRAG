"""
tests/test_clean_graph.py
B 的图谱清洗（方案 B）纯逻辑测试：别名组配置合法性、关系类型白名单、
Cypher 动态类型引用、迁移去重键。

原则与 test_kg_builder 一致：不依赖真实 Neo4j（只测纯函数）。
真实清洗请跑 `python src/ingest/clean_graph.py --dry-run` 预览。
"""
import pytest

from ingest.clean_graph import (
    ALLOWED_REL_TYPES,
    rel_key,
    quote_type,
    validate_groups,
)


class TestValidateGroups:
    def test_valid_groups_ok(self):
        groups = {
            "洪七公": {"label": "人物", "aliases": ["北丐", "九指神丐"]},
            "丐帮": {"label": "门派", "aliases": ["丐帮总舵"]},
        }
        validate_groups(groups, [])  # 不抛异常即通过

    def test_canonical_in_aliases_raises(self):
        groups = {
            "洪七公": {"label": "人物", "aliases": ["洪七公", "北丐"]},
        }
        with pytest.raises(ValueError):
            validate_groups(groups, [])

    def test_duplicate_alias_raises(self):
        groups = {
            "洪七公": {"label": "人物", "aliases": ["北丐", "北丐"]},
        }
        with pytest.raises(ValueError):
            validate_groups(groups, [])

    def test_name_in_multiple_groups_raises(self):
        groups = {
            "洪七公": {"label": "人物", "aliases": ["北丐"]},
            "北丐帮主": {"label": "人物", "aliases": ["北丐"]},
        }
        with pytest.raises(ValueError):
            validate_groups(groups, [])

    def test_name_in_both_group_and_drop_raises(self):
        groups = {
            "洪七公": {"label": "人物", "aliases": ["北丐"]},
        }
        with pytest.raises(ValueError):
            validate_groups(groups, ["北丐"])

    def test_illegal_label_raises(self):
        groups = {
            "洪七公": {"label": "组织", "aliases": ["北丐"]},
        }
        with pytest.raises(ValueError):
            validate_groups(groups, [])

    def test_empty_drop_name_raises(self):
        with pytest.raises(ValueError):
            validate_groups(
                {"洪七公": {"label": "人物", "aliases": ["北丐"]}},
                [""],
            )


class TestRelHelpers:
    def test_allowed_rels_cover_ontology(self):
        assert {"MASTER_OF", "MASTERS", "BELONGS_TO", "BRANCHED_FROM",
                "ENEMY_OF", "MENTIONS"} <= ALLOWED_REL_TYPES

    def test_quote_type_backticks(self):
        assert quote_type("MASTER_OF") == "`MASTER_OF`"

    def test_rel_key_tuple(self):
        assert rel_key("MASTER_OF", "n-123", "out") == ("MASTER_OF", "n-123", "out")
