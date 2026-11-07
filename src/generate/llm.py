"""LLM 生成答案（任务 26 重写）。

变化：
- 客户端复用（模块级单例），避免每次请求新建 OpenAI 客户端；
- 总体超时 + 有限重试预算，认证/参数错误不再盲目重试；
- 返回结构化结果（状态、模型、耗时、降级原因），调用方不再"静默降级"；
- 系统指令、问题、证据分开，证据过长时按字符预算裁剪。
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from core.config import get_env, get_int, get_settings
from core.errors import ConfigError, GenerationUnavailableError
from core.http_client import build_http_client

SYSTEM_PROMPT = (
    "你是金庸武侠知识问答助手。只根据给定的检索资料回答，不要编造。"
    "如果资料不足，直接说明「根据现有资料无法回答」。"
)

USER_PROMPT_TEMPLATE = """问题：{question}

检索到的资料：
{context}

要求：
- 问"是谁/是什么"时直接回答名称，不要解释；
- 问"有哪些"时用顿号列出；
- 只根据资料回答；资料不足就说"根据现有资料无法回答"。

回答："""

RETRYABLE_ERRORS = {
    "APITimeoutError", "APIConnectionError", "RateLimitError", "InternalServerError",
    "ServiceUnavailableError", "Timeout", "ConnectionError", "APIStatusError",
}


class EmptyResponseError(RuntimeError):
    """上游返回了空响应（无 choices），按可重试处理。"""
FATAL_ERRORS = {
    "AuthenticationError", "PermissionDeniedError", "BadRequestError",
    "NotFoundError", "UnprocessableEntityError",
}

_client = None


@dataclass
class GenerationResult:
    text: str
    status: str          # ok / no_context / unavailable
    model: str = ""
    latency_ms: float = 0.0
    fallback_reason: str = ""
    attempts: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {"status": self.status, "model": self.model,
                "latency_ms": round(self.latency_ms, 2),
                "fallback_reason": self.fallback_reason,
                "attempts": self.attempts}


def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI
        settings = get_settings()
        if not settings.llm_token:
            raise ConfigError("缺少 LLM_TOKEN，无法调用生成模型")
        _client = OpenAI(api_key=settings.llm_token, base_url=settings.llm_endpoint,
                         timeout=settings.request_timeout, max_retries=0,
                         http_client=build_http_client(settings.request_timeout))
    return _client


def close_client() -> None:
    global _client
    _client = None


def _is_retryable(exc: Exception) -> bool:
    name = type(exc).__name__
    if name in FATAL_ERRORS:
        return False
    if isinstance(exc, EmptyResponseError):
        return True
    return name in RETRYABLE_ERRORS or isinstance(exc, (TimeoutError, ConnectionError))


def generate(question: str, context: str, *, max_chars: Optional[int] = None,
             max_attempts: int = 4) -> GenerationResult:
    """调用 LLM 生成答案；失败返回 status=unavailable（不抛给调用方）。"""
    started = time.perf_counter()
    settings = get_settings()
    if not context or not context.strip():
        return GenerationResult("未检索到相关内容。", "no_context", settings.llm_model,
                                (time.perf_counter() - started) * 1000)

    budget = max_chars or settings.max_context_chars
    context = context[:budget]
    prompt = USER_PROMPT_TEMPLATE.format(question=question, context=context)

    last_error = ""
    for attempt in range(1, max_attempts + 1):
        try:
            client = _get_client()
            kwargs: Dict[str, Any] = {
                "model": settings.llm_model,
                "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                             {"role": "user", "content": prompt}],
                "temperature": 0,
            }
            if settings.gen_disable_thinking:
                kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
            try:
                response = client.chat.completions.create(**kwargs)
            except Exception as exc:
                if type(exc).__name__ == "BadRequestError" and "extra_body" in kwargs:
                    kwargs.pop("extra_body")
                    response = client.chat.completions.create(**kwargs)
                else:
                    raise
            if response is None or not getattr(response, "choices", None):
                raise EmptyResponseError("上游返回空响应（无 choices）")
            text = (response.choices[0].message.content or "").strip()
            return GenerationResult(text or "（模型返回空内容）", "ok",
                                    settings.llm_model,
                                    (time.perf_counter() - started) * 1000,
                                    attempts=attempt)
        except Exception as exc:  # noqa: BLE001 - 统一转成降级状态
            last_error = f"{type(exc).__name__}: {exc}"
            if not _is_retryable(exc) or attempt >= max_attempts:
                break
            time.sleep(min(1.5 * attempt, 6))
    return GenerationResult("", "unavailable", settings.llm_model,
                            (time.perf_counter() - started) * 1000,
                            fallback_reason=last_error, attempts=max_attempts)


def generate_answer(question: str, context: str) -> str:
    """兼容旧接口：成功返回文本，失败抛 GenerationUnavailableError。"""
    result = generate(question, context)
    if result.status == "ok":
        return result.text
    if result.status == "no_context":
        return result.text
    raise GenerationUnavailableError("LLM 生成失败", detail=result.fallback_reason)


__all__ = ["GenerationResult", "generate", "generate_answer", "close_client",
           "SYSTEM_PROMPT"]
