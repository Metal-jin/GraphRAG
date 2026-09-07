"""
tests/test_kg_builder.py
B 的造图测试：切块、抽取结果清洗、Neo4j 写入语句、data_loader 兜底。

设计原则：不依赖真实的 Neo4j 和 LLM 服务（用假对象替换），
这样任何人 clone 下来 `python -m pytest` 都能跑，CI/队友本地也一样。
真实链路的端到端验证用 build_kg.py --limit 20 手工跑。
"""
import json

import pytest

from ingest.corpus import sliding_chunks, split_chapters
from ingest.build_kg import (
    BIDIRECTIONAL_RELS,
    RELATION_TYPES,
    clean_entity,
    clean_relationship,
    parse_llm_json,
    KGBuilder,
)


# ============ 1. 切块测试 ============

class TestCorpus:
    def test_split_chapters(self):
        text = "第一章 风雪惊变\n正文甲。\n正文乙。\n第二章 江南七怪\n正文丙。"
        chapters = split_chapters(text)
        assert [c["chapter"] for c in chapters] == ["第一章 风雪惊变", "第二章 江南七怪"]
        assert "正文甲" in chapters[0]["text"]
        assert "正文丙" in chapters[1]["text"]

    def test_split_chapters_no_marker(self):
        """没有章节标题时整本书当一章（兜底）。"""
        chapters = split_chapters("没有任何章节标记的一小段文本。")
        assert len(chapters) == 1
        assert chapters[0]["chapter"] == "全文"

    def test_sliding_overlap(self):
        """块间必须有重叠，且拼起来不丢内容。"""
        text = "字" * 1500
        chunks = sliding_chunks(text, size=600, overlap=80)
        assert len(chunks) >= 3
        # 相邻两块的重叠 = 上一块尾部 == 下一块开头
        assert chunks[0][-80:] == chunks[1][:80]
        # 首块从 0 开始，最后一块覆盖到结尾
        assert "".join(chunks) .startswith(text[:600])
        assert text[-50:] in "".join(chunks)

    def test_sliding_short_text(self):
        """短文本直接一整块。"""
        assert sliding_chunks("很短", size=600, overlap=80) == ["很短"]

    def test_tail_merge(self):
        """尾部碎块并入前一块，不产生碎块。"""
        text = "字" * 1000
        chunks = sliding_chunks(text, size=600, overlap=80)
        assert all(len(c) >= 80 for c in chunks)


# ============ 2. LLM 返回解析测试 ============

class TestParseLLMJson:
    def test_plain_json(self):
        raw = '{"entities": [{"name": "郭靖", "type": "人物", "era": "射雕"}], "relationships": []}'
        data = parse_llm_json(raw)
        assert data["entities"][0]["name"] == "郭靖"

    def test_code_fence(self):
        """LLM 常见的 ```json 包裹。"""
        raw = '```json\n{"entities": [], "relationships": [{"source": "a", "target": "b", "type": "MASTER_OF"}]}\n```'
        data = parse_llm_json(raw)
        assert data["relationships"][0]["type"] == "MASTER_OF"

    def test_garbage(self):
        """解析失败不抛异常，返回空结果。"""
        data = parse_llm_json("抱歉，我无法处理这个请求。")
        assert data == {"entities": [], "relationships": []}


# ============ 3. 实体/关系清洗测试 ============

class TestCleanEntity:
    def test_normal(self):
        ent = clean_entity({"name": "郭靖", "type": "人物", "era": "射雕"}, "射雕")
        assert ent == {"name": "郭靖", "type": "人物", "era": "射雕"}

    def test_era_missing_uses_default(self):
        """era 没给/给错 → 填默认值（阶段一=射雕）。"""
        ent = clean_entity({"name": "黄蓉", "type": "人物"}, "射雕")
        assert ent["era"] == "射雕"
        ent = clean_entity({"name": "黄蓉", "type": "人物", "era": "唐朝"}, "射雕")
        assert ent["era"] == "射雕"

    def test_era_valid_kept(self):
        """阶段二：合法 era 原样保留。"""
        ent = clean_entity({"name": "杨过", "type": "人物", "era": "神雕"}, "射雕")
        assert ent["era"] == "神雕"

    def test_art_type_in_type_field(self):
        """LLM 把武功类别填进 type 字段 → 归一化为武功 + art_type。"""
        ent = clean_entity({"name": "降龙十八掌", "type": "外功", "era": "射雕"}, "射雕")
        assert ent["type"] == "武功"
        assert ent["art_type"] == "外功"

    def test_sect_location(self):
        ent = clean_entity({"name": "桃花岛", "type": "门派", "era": "射雕",
                            "location": "东海"}, "射雕")
        assert ent["location"] == "东海"

    def test_bad_type_dropped(self):
        assert clean_entity({"name": "X", "type": "神兽"}, "射雕") is None
        assert clean_entity({"name": "", "type": "人物"}, "射雕") is None


class TestCleanRelationship:
    NAMES = {"洪七公", "郭靖", "降龙十八掌"}

    def test_valid(self):
        rel = clean_relationship({"source": "洪七公", "target": "郭靖",
                                  "type": "MASTER_OF"}, self.NAMES)
        assert rel == {"source": "洪七公", "target": "郭靖", "type": "MASTER_OF"}

    def test_unknown_type_dropped(self):
        assert clean_relationship({"source": "洪七公", "target": "郭靖",
                                   "type": "TEACHER_OF"}, self.NAMES) is None

    def test_endpoint_not_in_entities_dropped(self):
        """关系两端必须出现在本批实体里。"""
        assert clean_relationship({"source": "王重阳", "target": "郭靖",
                                   "type": "MASTER_OF"}, self.NAMES) is None

    def test_self_loop_dropped(self):
        assert clean_relationship({"source": "郭靖", "target": "郭靖",
                                   "type": "ENEMY_OF"}, self.NAMES) is None


# ============ 4. 抽取后处理（双向关系展开） ============

class TestPostprocess:
    def _builder(self):
        return KGBuilder(driver=None, llm=None, embedder=None, default_era="射雕")

    def test_bidirectional_expanded(self):
        data = {
            "entities": [
                {"name": "郭靖", "type": "人物", "era": "射雕"},
                {"name": "黄蓉", "type": "人物", "era": "射雕"},
            ],
            "relationships": [
                {"source": "郭靖", "target": "黄蓉", "type": "SPOUSE_OF"},
            ],
        }
        result = self._builder()._postprocess(data)
        pairs = {(r["source"], r["target"]) for r in result["relationships"]}
        assert pairs == {("郭靖", "黄蓉"), ("黄蓉", "郭靖")}

    def test_directed_not_duplicated(self):
        data = {
            "entities": [
                {"name": "洪七公", "type": "人物"},
                {"name": "郭靖", "type": "人物"},
            ],
            "relationships": [
                {"source": "洪七公", "target": "郭靖", "type": "MASTER_OF"},
            ],
        }
        result = self._builder()._postprocess(data)
        assert len(result["relationships"]) == 1

    def test_duplicate_entities_merged(self):
        data = {"entities": [
            {"name": "郭靖", "type": "人物"},
            {"name": "郭靖", "type": "人物"},
        ], "relationships": []}
        result = self._builder()._postprocess(data)
        assert len(result["entities"]) == 1

    def test_relation_endpoint_missing(self):
        """关系一端实体没抽出来 → 关系丢弃，不报错。"""
        data = {
            "entities": [{"name": "郭靖", "type": "人物"}],
            "relationships": [{"source": "郭靖", "target": "江南七怪",
                               "type": "MASTER_OF"}],
        }
        result = self._builder()._postprocess(data)
        assert result["relationships"] == []


# ============ 5. Neo4j 写入测试（FakeDriver） ============

class FakeSession:
    def __init__(self, log):
        self.log = log

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def run(self, query, **params):
        self.log.append((query, params))


class FakeDriver:
    def __init__(self):
        self.log = []

    def session(self):
        return FakeSession(self.log)


class TestWriteResult:
    def _builder(self, fake_driver):
        return KGBuilder(driver=fake_driver, llm=None,
                         embedder=lambda texts: [[0.1] * 8 for _ in texts],
                         default_era="射雕")

    def test_entity_merge_with_era(self):
        """实体 MERGE 必须带 era 参数（阶段一就要有这个字段）。"""
        fd = FakeDriver()
        self._builder(fd).write_result(
            {"chunk_id": 0, "chapter": "第一章", "text": "测试文本"},
            {"entities": [{"name": "郭靖", "type": "人物", "era": "射雕"}],
             "relationships": []},
        )
        merge_calls = [q for q, _ in fd.log if "MERGE (n:" in q and "郭靖" not in q]
        assert any("MERGE (n:`人物`" in q for q, _ in fd.log)
        era_params = [p for q, p in fd.log
                      if q.startswith("\nMERGE (n:") and p.get("name") == "郭靖"]
        assert era_params and era_params[0]["era"] == "射雕"

    def test_chunk_node_and_mentions(self):
        fd = FakeDriver()
        self._builder(fd).write_result(
            {"chunk_id": 7, "chapter": "第二章", "text": "洪七公传授降龙十八掌"},
            {"entities": [{"name": "洪七公", "type": "人物", "era": "射雕"}],
             "relationships": []},
        )
        queries = " || ".join(q for q, _ in fd.log)
        assert "MERGE (c:Chunk" in queries       # Chunk 节点
        assert "embedding" in queries             # 向量写进去了
        assert "MENTIONS" in queries              # 证据溯源边

    def test_relationship_direction(self):
        """有向关系按 source→target 写。"""
        fd = FakeDriver()
        self._builder(fd).write_result(
            {"chunk_id": 1, "chapter": "第一章", "text": "文本"},
            {"entities": [
                {"name": "洪七公", "type": "人物", "era": "射雕"},
                {"name": "郭靖", "type": "人物", "era": "射雕"},
            ],
             "relationships": [
                 {"source": "洪七公", "target": "郭靖", "type": "MASTER_OF"},
             ]},
        )
        rel_calls = [(q, p) for q, p in fd.log if "MERGE (a)-[" in q]
        assert len(rel_calls) == 1
        q, p = rel_calls[0]
        assert "MASTER_OF" in q
        assert p == {"source": "洪七公", "target": "郭靖"}

    def test_all_relation_types_in_whitelist(self):
        """本体一致性：双向关系集合 ⊆ 关系白名单。"""
        assert BIDIRECTIONAL_RELS <= RELATION_TYPES
        assert len(RELATION_TYPES) == 10  # 9 个 + BRANCHED_FROM


# ============ 6. data_loader 兜底测试 ============

class TestDataLoader:
    def test_get_chunks_fallback_to_file(self, tmp_path, monkeypatch):
        """Neo4j 不可用/连不上时，get_chunks 兜底读 chunks.json。"""
        chunks_file = tmp_path / "chunks.json"
        chunks_file.write_text(json.dumps([
            {"chunk_id": 0, "chapter": "第一章", "text": "内容"},
        ], ensure_ascii=False), encoding="utf-8")

        import ingest.data_loader as dl
        monkeypatch.setattr(dl, "DEFAULT_OUT_PATH", chunks_file)

        def _no_database():
            raise RuntimeError("neo4j not available in unit test")

        # 显式模拟"连不上库"，保证在任何环境（包括本地已装 Neo4j 时）都测兜底路径
        monkeypatch.setattr(dl, "get_driver", _no_database)
        chunks = dl.get_chunks()
        assert chunks == [{"chunk_id": 0, "chapter": "第一章", "text": "内容"}]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
