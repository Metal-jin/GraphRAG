"""统一问答服务（任务 18 / 25 / 26 重写）。

三条链路（手动问答 / 自动路由 / 评测）现在共用同一个
"检索 -> 注入 -> 生成" 流程，生成输入可复现：

    retrieve()  -> Answer（含统一证据）
    inject()    -> 注入文本（按方法选择 path/subgraph/triples/text）
    generate()  -> GenerationResult（含状态/降级原因/模型/耗时）

所有入口都做输入校验，并返回可解释的状态字段。
"""
from __future__ import annotations

import time
from dataclasses import replace
from typing import Any, Dict, List, Optional

from core.interfaces import Answer
from core.query import MAX_TOP_K, normalize_top_k
from core.registry import get_method, list_methods
from generate.injection import build_context, injection_name
from generate.intent_classifier import classify, get_classifier
from generate.llm import generate

import methods  # noqa: F401  触发 @register

MAX_QUESTION_CHARS = 500
_GRAPH_METHODS = {"master_chain", "person_relation", "sect_agg", "art_lineage",
                  "cross_novel"}
_MISSING_GRAPH_EVIDENCE = {"no_entity", "no_result", "no_relation", "unsupported_relation"}


class RequestError(ValueError):
    """请求参数非法（对应 HTTP 400）。"""


def _validate_question(question: Any) -> str:
    if not isinstance(question, str):
        raise RequestError("question 必须是字符串")
    text = question.strip()
    if not text:
        raise RequestError("question 不能为空")
    if len(text) > MAX_QUESTION_CHARS:
        raise RequestError(f"question 过长（>{MAX_QUESTION_CHARS} 字符）")
    return text


def _validate_method(method_name: Any) -> str:
    if not isinstance(method_name, str) or not method_name:
        raise RequestError("method_name 必须是非空字符串")
    available = list_methods()
    if method_name not in available:
        raise RequestError(f"未知方法：{method_name}；可用：{available}")
    return method_name


def get_available_methods() -> List[str]:
    """所有已注册的检索方法名（前端下拉框用）。"""
    return list_methods()


def retrieve(question: str, method_name: str, top_k: int = 5) -> Answer:
    """只做检索，不生成（评测/调试复用）。"""
    method = get_method(method_name)
    return method.ask(question, top_k=top_k)


def _retrieve_auto(question: str, method_name: str, top_k: int) -> Answer:
    answer = retrieve(question, method_name, top_k)
    status = (answer.debug_info or {}).get("status")
    if method_name not in _GRAPH_METHODS or status not in _MISSING_GRAPH_EVIDENCE:
        return answer
    fallback = retrieve(question, "vector", top_k)
    if not fallback.evidence or not fallback.raw_context.strip():
        return answer
    return replace(fallback, debug_info={
        **fallback.debug_info,
        "fallback_from": method_name,
        "fallback_reason": status,
    })


def _build_result(question: str, answer: Answer, *, method_name: str,
                  intent: Optional[Any] = None, started: float) -> Dict[str, Any]:
    injected = build_context(method_name, answer.evidence, answer.raw_context)
    generation = generate(question, injected)
    if generation.status == "ok":
        answer_text = generation.text
    elif generation.status == "no_context":
        answer_text = answer.answer_text
    else:
        answer_text = answer.answer_text  # 显式降级，保留检索结果

    retrieval_status = str((answer.debug_info or {}).get("status") or "")
    status = "ok"
    if retrieval_status in ("error", "degraded"):
        status = "error" if retrieval_status == "error" else "degraded"
    elif generation.status == "unavailable":
        status = "degraded"
    elif generation.status == "no_context" and not injected.strip():
        status = "no_context"

    result: Dict[str, Any] = {
        "answer_text": answer_text,
        "method_name": method_name,
        "injection": injection_name(method_name),
        "evidence": answer.evidence,
        "debug_info": answer.debug_info,
        "raw_context": injected,
        "retrieval_context": answer.raw_context,
        "status": status,
        "generation": generation.to_dict(),
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
    }
    if intent is not None:
        result.update({
            "intent": intent.intent,
            "seed_entity": intent.seed_entity,
            "reason": intent.reason,
            "confidence": intent.confidence,
            "scope": intent.scope.to_dict(),
            "matches": intent.matches,
            "classification": intent.to_dict(),
        })
    return result


def ask_question(question: str, method_name: str = "vector", top_k: int = 5) -> Dict[str, Any]:
    """手动指定方法的问答入口（阶段一用法，保留）。"""
    started = time.perf_counter()
    try:
        text = _validate_question(question)
        method_name = _validate_method(method_name)
        top_k = normalize_top_k(top_k)
    except RequestError as exc:
        return {"error": str(exc), "code": "invalid_request", "answer_text": "",
                "method_name": method_name if isinstance(method_name, str) else "",
                "evidence": [], "debug_info": {}, "raw_context": "",
                "status": "invalid_request", "injection": ""}

    try:
        answer = retrieve(text, method_name, top_k)
    except ValueError as exc:
        return {"error": str(exc), "code": "invalid_request", "answer_text": "",
                "method_name": method_name, "evidence": [], "debug_info": {},
                "raw_context": "", "status": "invalid_request", "injection": ""}
    except Exception as exc:  # 检索层未捕获的异常
        return {"error": f"{type(exc).__name__}: {exc}", "code": "retrieval_failed",
                "answer_text": "", "method_name": method_name, "evidence": [],
                "debug_info": {}, "raw_context": "",
                "status": "error", "injection": ""}

    return _build_result(question, answer, method_name=method_name, started=started)


def ask_auto(question: str, top_k: int = 5) -> Dict[str, Any]:
    """全自动问答入口：意图识别 -> 路由 -> 注入 -> 生成。"""
    started = time.perf_counter()
    try:
        text = _validate_question(question)
        top_k = normalize_top_k(top_k)
    except RequestError as exc:
        return {"error": str(exc), "code": "invalid_request", "answer_text": "",
                "method_name": "", "intent": "", "evidence": [], "debug_info": {},
                "raw_context": "", "status": "invalid_request", "injection": ""}

    try:
        intent = classify(text)
        method_name = intent.method_name
        if method_name not in list_methods():
            method_name = "vector"
        answer = _retrieve_auto(text, method_name, top_k)
        return _build_result(text, answer, method_name=answer.method_name, intent=intent,
                             started=started)
    except Exception as exc:  # 分类或检索失败
        return {"error": f"{type(exc).__name__}: {exc}", "code": "pipeline_failed",
                "answer_text": "", "method_name": "", "intent": "",
                "evidence": [], "debug_info": {}, "raw_context": "",
                "status": "error", "injection": ""}


def health() -> Dict[str, Any]:
    """服务健康信息（配置/索引/数据库）。"""
    from core.config import validate_config
    from ingest.data_loader import health_check
    from generate.intent_classifier import get_classifier
    return {"config_problems": validate_config(require_neo4j=True),
            "neo4j": health_check(),
            "intent_index_degraded": get_classifier().degraded_reason,
            "methods": list_methods()}


__all__ = ["ask_question", "ask_auto", "retrieve", "get_available_methods",
           "health", "RequestError", "MAX_TOP_K"]
