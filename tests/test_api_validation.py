"""API 层与统一入口的输入校验（任务 25 / 26 的回归用例）。"""
import io
import json

import pytest

import run_frontend_server as server
from core.interfaces import Answer
from generate import service
from generate.intent_classifier import Intent
from generate.llm import GenerationResult
from generate.service import ask_auto, ask_question


def environ_with_body(payload, method="POST", path="/api/ask"):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return {"REQUEST_METHOD": method, "PATH_INFO": path,
            "QUERY_STRING": "", "CONTENT_LENGTH": str(len(body)),
            "wsgi.input": io.BytesIO(body)}


class Recorder:
    def __init__(self):
        self.status = None
        self.headers = None

    def __call__(self, status, headers):
        self.status = status
        self.headers = headers


def call(payload, method="POST", path="/api/ask"):
    recorder = Recorder()
    body = environ_with_body(payload, method, path)
    chunks = server.application(body, recorder)
    return recorder, json.loads(b"".join(chunks).decode("utf-8"))


# ============ 服务层校验 ============

class TestServiceValidation:
    def test_non_string_question(self):
        result = ask_question(123, "vector")
        assert result["status"] == "invalid_request"
        assert "字符串" in result["error"]

    def test_empty_question(self):
        assert ask_question("   ", "vector")["status"] == "invalid_request"

    def test_too_long_question(self):
        assert ask_question("啊" * 501, "vector")["status"] == "invalid_request"

    def test_unknown_method(self):
        result = ask_question("郭靖是谁", "not_a_method")
        assert result["status"] == "invalid_request"
        assert "未知方法" in result["error"]

    def test_ask_auto_rejects_non_string(self):
        assert ask_auto(None)["status"] == "invalid_request"


@pytest.mark.parametrize("graph_status,methods", [
    ("no_result", ["person_relation", "vector"]),
    ("ok", ["person_relation"]),
])
def test_auto_searches_text_only_when_graph_evidence_is_missing(monkeypatch, graph_status, methods):
    monkeypatch.setattr(service, "classify", lambda _: Intent("person_relation", "person_relation"))
    calls = []
    generations = []

    def retrieve(question, method, top_k):
        calls.append(method)
        if method == "person_relation" and graph_status == "no_result":
            return Answer("没有找到关系", method, debug_info={"status": graph_status})
        return Answer("资料", method, evidence=[{"text": "找到可用资料"}],
                      raw_context="找到可用资料", debug_info={"status": "ok"})

    def generate(question, context):
        generations.append(context)
        return GenerationResult("回答", "ok")

    monkeypatch.setattr(service, "retrieve", retrieve)
    monkeypatch.setattr(service, "generate", generate)
    result = service.ask_auto("某人物的父亲是谁？")

    assert calls == methods
    assert len(generations) == 1
    assert "找到可用资料" in generations[0]
    assert result["method_name"] == methods[-1]
    assert result["classification"]["method_name"] == "person_relation"
    assert result["debug_info"].get("fallback_reason") == (
        "no_result" if graph_status == "no_result" else None)


# ============ HTTP 层校验 ============

class TestHttpValidation:
    def test_malformed_json(self):
        recorder = Recorder()
        body = {"REQUEST_METHOD": "POST", "PATH_INFO": "/api/ask", "QUERY_STRING": "",
                "CONTENT_LENGTH": "5", "wsgi.input": io.BytesIO(b"{bad}")}
        chunks = server.application(body, recorder)
        payload = json.loads(b"".join(chunks).decode("utf-8"))
        assert "400" in recorder.status
        assert payload["error"]["code"] == "invalid_json"

    def test_array_body_rejected(self):
        recorder, payload = call([1, 2, 3])
        assert "400" in recorder.status
        assert payload["error"]["code"] == "invalid_request"

    def test_number_question_rejected(self):
        recorder, payload = call({"question": 42})
        assert "400" in recorder.status
        assert payload["error"]["code"] == "invalid_request"

    def test_unknown_method_rejected(self):
        recorder, payload = call({"question": "郭靖是谁", "method_name": "nope"})
        assert "400" in recorder.status
        assert payload["error"]["code"] == "invalid_method"

    def test_bad_top_k_rejected(self):
        recorder, payload = call({"question": "郭靖是谁", "top_k": 0})
        assert "400" in recorder.status
        assert payload["error"]["code"] == "invalid_request"

    def test_payload_too_large(self):
        recorder = Recorder()
        body = {"REQUEST_METHOD": "POST", "PATH_INFO": "/api/ask", "QUERY_STRING": "",
                "CONTENT_LENGTH": str(server.MAX_BODY_BYTES + 1),
                "wsgi.input": io.BytesIO(b"{}")}
        chunks = server.application(body, recorder)
        assert "413" in recorder.status

    def test_unknown_route(self):
        recorder, payload = call({}, method="GET", path="/nope")
        assert "404" in recorder.status
        assert payload["error"]["code"] == "not_found"

    def test_missing_node_id(self):
        recorder = Recorder()
        body = {"REQUEST_METHOD": "GET", "PATH_INFO": "/api/node/neighbor",
                "QUERY_STRING": "", "CONTENT_LENGTH": "0",
                "wsgi.input": io.BytesIO(b"")}
        chunks = server.application(body, recorder)
        assert "400" in recorder.status


# ============ 图数据格式 ============

class TestGraphFormat:
    def test_edge_ids_are_stable_and_directed(self):
        payload = server._to_vis_format(
            [{"name": "郭靖", "type": "人物"}, {"name": "洪七公", "type": "人物"}],
            [{"source": "洪七公", "target": "郭靖", "type": "MASTER_OF"},
             {"source": "洪七公", "target": "郭靖", "type": "MASTER_OF"}])
        assert len(payload["nodes"]) == 2
        assert len(payload["edges"]) == 1  # 重复边被合并
        edge = payload["edges"][0]
        assert edge["id"] == "洪七公|MASTER_OF|郭靖"
        assert edge["from"] == "洪七公" and edge["to"] == "郭靖"

    def test_extract_path_keeps_multihop(self):
        result = {"seed_entity": "郭靖", "evidence": [{
            "edges": [
                {"source": "郭靖", "target": "洪七公", "type": "MASTER_OF"},
                {"source": "洪七公", "target": "王重阳", "type": "MASTER_OF"},
            ]}]}
        path = server._extract_path(result)
        assert path["nodes"] == ["郭靖", "洪七公", "王重阳"]
        assert len(path["edges"]) == 2
