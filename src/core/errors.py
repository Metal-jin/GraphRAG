"""项目统一异常类型。

任务清单 25/26 要求区分“无相关内容”“数据库不可用”“生成降级”等状态，
这里给出可被上层翻译成 HTTP 状态码 / 评测状态的异常族。
"""
from __future__ import annotations


class AppError(Exception):
    """项目内所有可预期异常的基类。"""

    code = "internal_error"
    http_status = 500

    def __init__(self, message: str, *, detail: str = ""):
        super().__init__(message)
        self.message = message
        self.detail = detail

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message,
                          "detail": self.detail}}


class ConfigError(AppError):
    code = "config_error"
    http_status = 500


class ValidationError(AppError):
    code = "invalid_request"
    http_status = 400


class NotFoundError(AppError):
    code = "not_found"
    http_status = 404


class DataUnavailableError(AppError):
    """数据库/数据源不可用（与“查到了但没内容”严格区分）。"""

    code = "data_unavailable"
    http_status = 503


class EmbeddingError(AppError):
    """嵌入服务失败或维度/模型不一致。"""

    code = "embedding_unavailable"
    http_status = 503


class IndexCompatibilityError(AppError):
    """索引与当前嵌入配置不兼容。"""

    code = "index_incompatible"
    http_status = 500


class ExtractionError(AppError):
    """LLM 抽取失败（与“合法空结果”区分）。"""

    code = "extraction_failed"
    http_status = 502


class GenerationUnavailableError(AppError):
    """LLM 生成不可用，调用方应显式降级并标注状态。"""

    code = "generation_unavailable"
    http_status = 502


__all__ = [
    "AppError", "ConfigError", "ValidationError", "NotFoundError",
    "DataUnavailableError", "EmbeddingError", "IndexCompatibilityError",
    "ExtractionError", "GenerationUnavailableError",
]
