"""B 的造图测试（任务 05/06/07/08 的回归用例）。

原则：不依赖真实 Neo4j 和 LLM，用假对象替换，任何人 clone 后都能跑。
真实链路用 build_kg.py --preview / --dry-run 手工验证。
"""
import json

import pytest

from ingest.corpus import ChunkParams, chunk_offsets, sliding_chunks, split_chapters
from ingest.build_kg import (
    BIDIRECTIONAL_RELS, CheckpointStore, ExtractionResult, KGBuilder, RELATION_TYPES,
    STATUS_EMPTY, STATUS_FATAL, STATUS_OK, STATUS_RETRYABLE,
    clean_entity, clean_relationship, parse_llm_json, parse_llm_payload,
)


# ============ 1. 切块测试（任务 01） ============

class TestCorpus:
    def test_split_chapters(self):
        text = "第一章 风雪惊变\n正文甲。\n正文乙。\n第二章 江南七怪\n正文丙。"
        chapters = split_chapters(text)
        assert [c["chapter"] for c in chapters] == ["第一章 风雪惊变", "第二章 江南七怪"]
        assert "正文甲" in chapters[0]["text"]
        assert "正文丙" in chapters[1]["text"]

    def test_split_chapters_no_marker(self):
        chapters = split_chapters("没有任何章节标记的一小段文本。")
        assert len(chapters) == 1
        assert chapters[0]["chapter"] == "全文"

    def test_sliding_overlap(self):
        text = "字" * 1500
        chunks = sliding_chunks(text, size=600, overlap=80)
        assert len(chunks) >= 3
        assert chunks[0][-80:] == chunks[1][:80]
        assert "".join(chunks).startswith(text[:600])
        assert text[-50:] in "".join(chunks)

    def test_sliding_short_text(self):
        assert sliding_chunks("很短", size=600, overlap=80) == ["很短"]

    def test_tail_merge(self):
        text = "字" * 1000
        chunks = sliding_chunks(text, size=600, overlap=80)
        assert all(len(c) >= 80 for c in chunks)

    def test_offsets_cover_whole_text_without_loss(self):
        """任务 01 验收：去掉重叠后能按偏移还原原文。"""
        text = "。".join(f"第{i}句内容" for i in range(400))
        spans = chunk_offsets(text, 500, 60)
        rebuilt = text[spans[0][0]:spans[0][1]]
        previous_end = spans[0][1]
        for start, end in spans[1:]:
            assert start <= previous_end, "相邻块必须重叠或相接"
            rebuilt += text[previous_end:end]
            previous_end = end
        assert rebuilt == text

    def test_offsets_no_punctuation_long_text(self):
        text = "啊" * 5000
        spans = chunk_offsets(text, 1500, 200)
        assert spans[0][0] == 0 and spans[-1][1] == len(text)
        assert all(end - start <= 1500 for start, end in spans)

    @pytest.mark.parametrize("size,overlap", [(0, 0), (-1, 0), (100, 100), (100, 150), (100, -1)])
    def test_invalid_params_rejected(self, size, overlap):
        with pytest.raises(ValueError):
            ChunkParams(size=size, overlap=overlap).validate()


# ============ 2. LLM 返回解析（任务 05） ============

class TestParseLLMPayload:
    def test_plain_json(self):
        raw = '{"entities": [{"name": "郭靖", "type": "人物", "era": "射雕"}], "relationships": []}'
        data, error = parse_llm_payload(raw)
        assert error == ""
        assert data["entities"][0]["name"] == "郭靖"

    def test_code_fence(self):
        raw = '\n{"entities": [], "relationships": [{"source": "a", "target": "b", "type": "MASTER_OF"}]}\n'
        data, error = parse_llm_payload(raw)
        assert error == ""
        assert data["relationships"][0]["type"] == "MASTER_OF"

    def test_garbage_is_error_not_empty(self):
        data, error = parse_llm_payload("抱歉，我无法处理这个请求。")
        assert data is None
        assert "JSON" in error

    def test_wrong_field_type_is_error(self):
        data, error = parse_llm_payload('{"entities": "郭靖", "relationships": []}')
        assert data is None
        assert "entities" in error

    def test_legacy_parse_returns_empty_on_error(self):
        assert parse_llm_json("抱歉") == {"entities": [], "relationships": []}


# ============ 3. 实体/关系清洗（任务 07/08） ============

class TestCleanEntity:
    def test_normal(self):
        ent = clean_entity({"name": "郭靖", "type": "人物", "era": "射雕"}, "射雕")
        assert ent == {"name": "郭靖", "type": "人物", "era": "射雕"}

    def test_era_missing_uses_default(self):
        assert clean_entity({"name": "黄蓉", "type": "人物"}, "射雕")["era"] == "射雕"
        assert clean_entity({"name": "黄蓉", "type": "人物", "era": "唐朝"}, "射雕")["era"] == "射雕"

    def test_era_valid_kept(self):
        assert clean_entity({"name": "杨过", "type": "人物", "era": "神雕"}, "射雕")["era"] == "神雕"

    def test_art_type_in_type_field(self):
        ent = clean_entity({"name": "降龙十八掌", "type": "外功", "era": "射雕"}, "射雕")
        assert ent["type"] == "武功"
        assert ent["art_type"] == "外功"

    def test_sect_location(self):
        ent = clean_entity({"name": "桃花岛", "type": "门派", "era": "射雕",
                            "location": "东海"}, "射雕")
        assert ent["location"] == "东海"

    def test_description_kept(self):
        """任务 07：description 必须保留，后代扫描才能用。"""
        ent = clean_entity({"name": "黄衫女子", "type": "人物", "era": "倚天",
                            "description": "她乃杨过之后人"}, "倚天")
        assert ent["description"] == "她乃杨过之后人"

    def test_bad_type_dropped(self):
        assert clean_entity({"name": "X", "type": "神兽"}, "射雕") is None
        assert clean_entity({"name": "", "type": "人物"}, "射雕") is None

    def test_noise_name_dropped(self):
        assert clean_entity({"name": "白雕", "type": "人物"}, "射雕") is None


class TestCleanRelationship:
    NAMES = {"洪七公", "郭靖", "降龙十八掌", "丐帮"}
    TYPES = {"洪七公": "人物", "郭靖": "人物",
             "降龙十八掌": "武功", "丐帮": "门派"}

    def test_valid(self):
        rel = clean_relationship({"source": "洪七公", "target": "郭靖",
                                  "type": "MASTER_OF"}, self.NAMES, self.TYPES)
        assert rel == {"source": "洪七公", "target": "郭靖", "type": "MASTER_OF"}

    def test_unknown_type_dropped(self):
        assert clean_relationship({"source": "洪七公", "target": "郭靖",
                                   "type": "TEACHER_OF"}, self.NAMES, self.TYPES) is None

    def test_endpoint_not_in_entities_dropped(self):
        assert clean_relationship({"source": "王重阳", "target": "郭靖",
                                   "type": "MASTER_OF"}, self.NAMES, self.TYPES) is None

    def test_self_loop_dropped(self):
        assert clean_relationship({"source": "郭靖", "target": "郭靖",
                                   "type": "ENEMY_OF"}, self.NAMES, self.TYPES) is None

    def test_endpoint_type_violation_dropped(self):
        """任务 08：门派 -> 武功 的 MASTER_OF 必须被拒。"""
        assert clean_relationship({"source": "丐帮", "target": "降龙十八掌",
                                   "type": "MASTER_OF"}, self.NAMES, self.TYPES) is None


# ============ 4. 抽取后处理（双向关系 / 拒绝清单） ============

class TestPostprocess:
    def _builder(self):
        return KGBuilder(driver=None, llm=None, embedder=None, default_era="射雕")

    def test_bidirectional_expanded(self):
        data = {"entities": [{"name": "郭靖", "type": "人物", "era": "射雕"},
                             {"name": "黄蓉", "type": "人物", "era": "射雕"}],
                "relationships": [{"source": "郭靖", "target": "黄蓉", "type": "SPOUSE_OF"}]}
        result = self._builder()._postprocess(data)
        pairs = {(r["source"], r["target"]) for r in result["relationships"]}
        assert pairs == {("郭靖", "黄蓉"), ("黄蓉", "郭靖")}

    def test_directed_not_duplicated(self):
        data = {"entities": [{"name": "洪七公", "type": "人物"},
                             {"name": "郭靖", "type": "人物"}],
                "relationships": [{"source": "洪七公", "target": "郭靖", "type": "MASTER_OF"}]}
        assert len(self._builder()._postprocess(data)["relationships"]) == 1

    def test_duplicate_entities_merged(self):
        data = {"entities": [{"name": "郭靖", "type": "人物"},
                             {"name": "郭靖", "type": "人物"}], "relationships": []}
        assert len(self._builder()._postprocess(data)["entities"]) == 1

    def test_relation_endpoint_missing(self):
        data = {"entities": [{"name": "郭靖", "type": "人物"}],
                "relationships": [{"source": "郭靖", "target": "江南七怪", "type": "MASTER_OF"}]}
        assert self._builder()._postprocess(data)["relationships"] == []

    def test_type_violation_goes_to_rejected(self):
        data = {"entities": [{"name": "丐帮", "type": "门派"},
                             {"name": "降龙十八掌", "type": "武功"}],
                "relationships": [{"source": "丐帮", "target": "降龙十八掌",
                                   "type": "MASTER_OF"}]}
        result = self._builder()._postprocess(data)
        assert result["relationships"] == []
        assert any("类型" in item["reason"] for item in result["rejected"])


# ============ 5. 抽取状态（任务 05） ============

class FakeMessage:
    def __init__(self, content):
        self.content = content


class FakeChoice:
    def __init__(self, content):
        self.message = FakeMessage(content)


class FakeResponse:
    def __init__(self, content):
        self.choices = [FakeChoice(content)]


class FakeCompletions:
    def __init__(self, contents):
        self.contents = list(contents)

    def create(self, **kwargs):
        content = self.contents.pop(0)
        if isinstance(content, Exception):
            raise content
        return FakeResponse(content)


class FakeLLM:
    def __init__(self, contents):
        self.chat = type("Chat", (), {"completions": FakeCompletions(contents)})()


class TestExtractionStatus:
    def _builder(self, contents):
        return KGBuilder(driver=None, llm=FakeLLM(contents), embedder=None)

    def test_ok(self):
        builder = self._builder(['{"entities": [{"name": "郭靖", "type": "人物"}], "relationships": []}'])
        result = builder.extract_chunk({"chunk_id": "c0", "text": "郭靖"})
        assert result.status == STATUS_OK
        assert result.entities[0]["name"] == "郭靖"

    def test_legal_empty(self):
        builder = self._builder(['{"entities": [], "relationships": []}'])
        result = builder.extract_chunk({"chunk_id": "c0", "text": "一段没有实体的文字"})
        assert result.status == STATUS_EMPTY

    def test_invalid_json_is_retryable_not_empty(self, monkeypatch):
        monkeypatch.setattr("ingest.build_kg.time.sleep", lambda *_: None)
        builder = self._builder(["不是 JSON", "不是 JSON", "不是 JSON"])
        result = builder.extract_chunk({"chunk_id": "c0", "text": "x"})
        assert result.status == STATUS_RETRYABLE
        assert result.error

    def test_auth_error_is_fatal(self, monkeypatch):
        class AuthenticationError(Exception):
            pass

        monkeypatch.setattr("ingest.build_kg.time.sleep", lambda *_: None)
        builder = self._builder([AuthenticationError("bad key")])
        result = builder.extract_chunk({"chunk_id": "c0", "text": "x"})
        assert result.status == STATUS_FATAL


# ============ 6. Neo4j 写入（任务 06：事务 + UNWIND） ============

class FakeTx:
    def __init__(self, log):
        self.log = log

    def run(self, query, **params):
        self.log.append((query, params))
        return self


class FakeSession:
    def __init__(self, log):
        self.log = log

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def run(self, query, **params):
        self.log.append((query, params))
        return self

    def execute_write(self, fn, *args):
        return fn(FakeTx(self.log), *args)


class FakeDriver:
    def __init__(self):
        self.log = []

    def session(self):
        return FakeSession(self.log)


class TestWriteResult:
    def _builder(self, fake_driver):
        return KGBuilder(driver=fake_driver, llm=None,
                         embedder=lambda texts: [[0.1] * 8 for _ in texts],
                         default_era="射雕", book="射雕英雄传")

    def _result(self, entities, relationships=None):
        return ExtractionResult(STATUS_OK, entities, relationships or [])

    def test_entity_merge_keeps_era_and_attrs(self):
        fd = FakeDriver()
        self._builder(fd).write_result(
            {"chunk_id": "c0", "chapter": "第一章", "text": "测试文本",
             "book": "射雕英雄传", "era": "射雕"},
            self._result([{"name": "郭靖", "type": "人物", "era": "射雕",
                           "description": "大侠"}]))
        queries = " || ".join(q for q, _ in fd.log)
        assert "MERGE (n:人物" in queries
        assert "first_seen_era" in queries and "n.eras" in queries
        assert "description" in queries
        rows = [p for q, p in fd.log if "UNWIND $rows AS row" in q][0]["rows"]
        assert rows[0]["description"] == "大侠"
        assert rows[0]["book"] == "射雕英雄传"

    def test_chunk_node_and_mentions(self):
        fd = FakeDriver()
        self._builder(fd).write_result(
            {"chunk_id": "c7", "chapter": "第二章", "text": "洪七公传授降龙十八掌",
             "book": "射雕英雄传", "era": "射雕", "content_hash": "abc"},
            self._result([{"name": "洪七公", "type": "人物", "era": "射雕"}]))
        queries = " || ".join(q for q, _ in fd.log)
        assert "MERGE (c:Chunk" in queries
        assert "embedding" in queries
        assert "MENTIONS" in queries
        assert "dataset_version" in queries

    def test_relationship_gets_evidence(self):
        fd = FakeDriver()
        self._builder(fd).write_result(
            {"chunk_id": "c1", "chapter": "第一章",
             "text": "洪七公把降龙十八掌传给郭靖。", "book": "射雕英雄传", "era": "射雕"},
            self._result(
                [{"name": "洪七公", "type": "人物", "era": "射雕"},
                 {"name": "郭靖", "type": "人物", "era": "射雕"}],
                [{"source": "洪七公", "target": "郭靖", "type": "MASTER_OF"}]))
        rel_calls = [(q, p) for q, p in fd.log if "MERGE (a)-[r:MASTER_OF]" in q]
        assert len(rel_calls) == 1
        query, params = rel_calls[0]
        assert "r.chunk_ids" in query and "r.snippets" in query and "r.versions" in query
        assert params["chunk_id"] == "c1"
        assert "洪七公" in params["rows"][0]["snippet"]

    def test_relation_types_match_ontology(self):
        assert BIDIRECTIONAL_RELS <= RELATION_TYPES
        assert "DESCENDANT_OF" in RELATION_TYPES


# ============ 7. Checkpoint（任务 02） ============

class TestCheckpoint:
    def test_legacy_list_format_rejected(self, tmp_path):
        path = tmp_path / "kg_checkpoint.json"
        path.write_text(json.dumps([0, 1, 2]), encoding="utf-8")
        store = CheckpointStore(path, book="射雕英雄传", dataset_version="chunker-v2")
        store.load()
        assert store.incompatibility
        with pytest.raises(Exception):
            store.load_or_raise()

    def test_dataset_version_mismatch_rejected(self, tmp_path):
        path = tmp_path / "ckpt.json"
        store = CheckpointStore(path, book="b", dataset_version="chunker-v2",
                                source_sha256="aaa")
        store.mark_done("b::chunker-v2::0", "hash")
        other = CheckpointStore(path, book="b", dataset_version="chunker-v1",
                                source_sha256="aaa")
        other.load()
        assert other.incompatibility

    def test_content_hash_change_is_not_done(self, tmp_path):
        path = tmp_path / "ckpt.json"
        store = CheckpointStore(path, book="b", dataset_version="v", source_sha256="s")
        store.mark_done("c0", "hash-a")
        assert store.is_done("c0", "hash-a")
        assert not store.is_done("c0", "hash-b")

    def test_atomic_write_produces_valid_json(self, tmp_path):
        path = tmp_path / "ckpt.json"
        store = CheckpointStore(path, book="b", dataset_version="v", source_sha256="s")
        store.mark_done("c0", "h")
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["completed"]["c0"] == "h"
        assert not path.with_suffix(".json.tmp").exists()


# ============ 8. data_loader 文件兜底（任务 30） ============

class TestDataLoaderFallback:
    def test_get_chunks_fallback_to_file(self, tmp_path, monkeypatch):
        chunks_file = tmp_path / "chunks.json"
        chunks_file.write_text(json.dumps([
            {"chunk_id": 0, "chapter": "第一章", "text": "内容"},
        ], ensure_ascii=False), encoding="utf-8")

        import ingest.data_loader as dl
        monkeypatch.setattr(dl, "DEFAULT_OUT_DIR", tmp_path / "nonexistent")
        monkeypatch.setattr(dl, "DEFAULT_OUT_PATH", chunks_file)

        def _no_database():
            raise RuntimeError("neo4j not available in unit test")

        monkeypatch.setattr(dl, "get_driver", _no_database)
        chunks = dl.get_chunks()
        assert len(chunks) == 1
        assert chunks[0]["text"] == "内容"

    def test_get_chunks_prefers_multi_book_files(self, tmp_path, monkeypatch):
        (tmp_path / "chunks_射雕英雄传.json").write_text(json.dumps([
            {"chunk_id": "射雕英雄传::chunker-v2::0", "book": "射雕英雄传",
             "era": "射雕", "text": "a"}], ensure_ascii=False), encoding="utf-8")
        (tmp_path / "chunks_神雕侠侣.json").write_text(json.dumps([
            {"chunk_id": "神雕侠侣::chunker-v2::0", "book": "神雕侠侣",
             "era": "神雕", "text": "b"}], ensure_ascii=False), encoding="utf-8")

        import ingest.data_loader as dl
        monkeypatch.setattr(dl, "DEFAULT_OUT_DIR", tmp_path)
        monkeypatch.setattr(dl, "get_driver", lambda: (_ for _ in ()).throw(RuntimeError("down")))
        chunks = dl.get_chunks()
        assert {c["book"] for c in chunks} == {"射雕英雄传", "神雕侠侣"}


# ============ 9. 实体属性首次创建即写入（回归） ============

class TestCreateBranchAttributes:
    def test_on_create_includes_description_location_art_type(self):
        fd = FakeDriver()
        builder = KGBuilder(driver=fd, llm=None,
                            embedder=lambda texts: [[0.1] * 8 for _ in texts],
                            default_era="射雕", book="射雕英雄传")
        builder.write_result(
            {"chunk_id": "c0", "chapter": "第一章", "text": "桃花岛在东海",
             "book": "射雕英雄传", "era": "射雕"},
            ExtractionResult(STATUS_OK, [
                {"name": "黄药师", "type": "人物", "era": "射雕",
                 "description": "东邪，桃花岛主"},
                {"name": "桃花岛", "type": "门派", "era": "射雕", "location": "东海"},
                {"name": "落英神剑掌", "type": "武功", "era": "射雕", "art_type": "外功"},
            ], []))

        entity_queries = [q for q, _ in fd.log if "MERGE (n:" in q]
        assert entity_queries, "没有生成实体写入语句"
        for query in entity_queries:
            create_block = query.split("ON MATCH SET")[0]
            assert "n.description" in create_block
            assert "n.location" in create_block
            assert "n.art_type" in create_block

        # 实体按 label 分组写入，需要把所有分组里的 rows 汇总
        rows = [row for q, p in fd.log if "MERGE (n:" in q for row in p["rows"]]
        by_name = {row["name"]: row for row in rows}
        assert by_name["黄药师"]["description"] == "东邪，桃花岛主"
        assert by_name["桃花岛"]["location"] == "东海"
        assert by_name["落英神剑掌"]["art_type"] == "外功"

    def test_empty_attributes_become_null(self):
        fd = FakeDriver()
        builder = KGBuilder(driver=fd, llm=None,
                            embedder=lambda texts: [[0.1] * 8 for _ in texts],
                            default_era="射雕")
        builder.write_result(
            {"chunk_id": "c1", "chapter": "第一章", "text": "郭靖",
             "book": "射雕英雄传", "era": "射雕"},
            ExtractionResult(STATUS_OK, [
                {"name": "郭靖", "type": "人物", "era": "射雕"}], []))
        query = [q for q, _ in fd.log if "MERGE (n:" in q][0]
        create_block = query.split("ON MATCH SET")[0]
        # 空字符串不写入，避免把 null 覆盖成 ""
        assert "THEN null ELSE row.description END" in create_block
        assert "THEN null ELSE row.location END" in create_block
        assert "THEN null ELSE row.art_type END" in create_block


# ============ 10. --dry-run 不写断点（回归） ============

class TestDryRunCheckpoint:
    CHUNKS = [
        {"chunk_id": "b::chunker-v2::0", "text": "郭靖", "book": "射雕英雄传",
         "era": "射雕", "content_hash": "h0"},
        {"chunk_id": "b::chunker-v2::1", "text": "黄蓉", "book": "射雕英雄传",
         "era": "射雕", "content_hash": "h1"},
    ]

    def _builder(self, llm, path):
        return KGBuilder(driver=None, llm=llm, embedder=None,
                         default_era="射雕", book="射雕英雄传",
                         checkpoint_path=path, dataset_version="chunker-v2")

    def test_dry_run_success_does_not_create_checkpoint(self, tmp_path, capsys):
        path = tmp_path / "kg_checkpoint.json"
        llm = FakeLLM(['{"entities": [{"name": "郭靖", "type": "人物"}], "relationships": []}'] * 2)
        store = CheckpointStore(path, book="射雕英雄传", dataset_version="chunker-v2")
        self._builder(llm, path).run(self.CHUNKS, dry_run=True, checkpoint=store)
        assert not path.exists(), "dry-run 不应创建断点文件"
        assert store.completed == {} and store.failed == {}

    def test_dry_run_failure_does_not_touch_checkpoint(self, tmp_path, monkeypatch):
        monkeypatch.setattr("ingest.build_kg.time.sleep", lambda *_: None)
        path = tmp_path / "kg_checkpoint.json"
        llm = FakeLLM(["不是 JSON", "不是 JSON", "不是 JSON",
                       "不是 JSON", "不是 JSON", "不是 JSON"])
        store = CheckpointStore(path, book="射雕英雄传", dataset_version="chunker-v2")
        stats = self._builder(llm, path).run(self.CHUNKS, dry_run=True, checkpoint=store)
        assert stats[STATUS_RETRYABLE] == 2
        assert not path.exists(), "dry-run 抽取失败也不应写断点"

    def test_dry_run_does_not_modify_existing_checkpoint(self, tmp_path):
        path = tmp_path / "kg_checkpoint.json"
        store = CheckpointStore(path, book="射雕英雄传", dataset_version="chunker-v2")
        store.mark_done("b::chunker-v2::0", "h0")
        before = path.read_text(encoding="utf-8")

        llm = FakeLLM(['{"entities": [], "relationships": []}'] * 1)
        store2 = CheckpointStore(path, book="射雕英雄传", dataset_version="chunker-v2")
        self._builder(llm, path).run(self.CHUNKS[1:], dry_run=True, checkpoint=store2)
        assert path.read_text(encoding="utf-8") == before

    def test_real_run_still_writes_checkpoint(self, tmp_path):
        path = tmp_path / "kg_checkpoint.json"
        store = CheckpointStore(path, book="射雕英雄传", dataset_version="chunker-v2")
        llm = FakeLLM(['{"entities": [], "relationships": []}'] * 1)
        # driver=None → write_result 返回 0，但仍应记录完成（事务占位）
        self._builder(llm, path).run(self.CHUNKS[:1], dry_run=False, checkpoint=store)
        assert path.exists()
        assert "b::chunker-v2::0" in json.loads(path.read_text(encoding="utf-8"))["completed"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))