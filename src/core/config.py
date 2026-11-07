"""统一配置加载与校验（任务 31）。

所有环境变量（数据库地址、LLM 密钥、嵌入模型等）都通过这里读取，
不要在业务代码里到处写 os.getenv。

设计要点：
- 保留 get_env 兼容旧代码；
- 新增带类型的读取函数与启动期校验 validate_config()；
- 配置不缓存到模块常量，测试里可以用 monkeypatch 注入。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

# 加载项目根目录的 .env 文件（按本文件位置定位仓库根，不依赖当前工作目录）
BASE_DIR = Path(__file__).resolve().parents[2]  # src/core/config.py -> 仓库根
load_dotenv(BASE_DIR / ".env")

PROJECT_ROOT = BASE_DIR

_TRUE = {"1", "true", "yes", "on", "y"}
_FALSE = {"0", "false", "no", "off", "n", ""}


def get_env(key: str, default: Optional[str] = None) -> Optional[str]:
    """读取环境变量，不存在时返回默认值。"""
    value = os.getenv(key)
    return default if value is None else value


def get_int(key: str, default: int, *, minimum: Optional[int] = None,
            maximum: Optional[int] = None) -> int:
    """读取整数配置并做范围校验；非法值回退默认值。"""
    raw = (os.getenv(key) or "").strip()
    try:
        value = int(raw) if raw else default
    except ValueError:
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def get_bool(key: str, default: bool = False) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    raw = raw.strip().lower()
    if raw in _TRUE:
        return True
    if raw in _FALSE:
        return False
    return default


@dataclass(frozen=True)
class Settings:
    """一次性读取的配置快照（便于日志、调试和测试注入）。"""

    neo4j_url: str
    neo4j_user: str
    neo4j_password: str
    llm_endpoint: str
    llm_model: str
    llm_token: str
    embed_endpoint: str
    embed_model: str
    embed_token: str
    embed_dim: str
    embed_allow_local_fallback: bool
    request_timeout: int
    max_context_chars: int
    llm_disable_thinking: bool
    gen_disable_thinking: bool
    llm_workers: int

    @property
    def has_llm(self) -> bool:
        return bool(self.llm_token and self.llm_endpoint)

    @property
    def has_remote_embedding(self) -> bool:
        return bool(self.embed_endpoint and self.embed_model)


def get_settings() -> Settings:
    """读取当前环境配置（每次调用都重新读，方便测试 monkeypatch）。"""
    return Settings(
        neo4j_url=get_env("NEO4J_URL", "bolt://localhost:7687") or "",
        neo4j_user=get_env("NEO4J_USER", "neo4j") or "",
        neo4j_password=get_env("NEO4J_PASSWORD", "") or "",
        llm_endpoint=get_env("LLM_ENDPOINT", "https://api.deepseek.com") or "",
        llm_model=get_env("LLM_MODEL", "deepseek-chat") or "",
        llm_token=get_env("LLM_TOKEN", "") or "",
        embed_endpoint=get_env("EMBED_ENDPOINT", "") or "",
        embed_model=get_env("EMBED_MODEL", "") or "",
        embed_token=get_env("EMBED_TOKEN", "") or "",
        embed_dim=(get_env("EMBED_DIM", "") or "").strip(),
        embed_allow_local_fallback=get_bool("EMBED_ALLOW_LOCAL_FALLBACK", False),
        request_timeout=get_int("REQUEST_TIMEOUT", 120, minimum=1, maximum=600),
        max_context_chars=get_int("MAX_CONTEXT_CHARS", 6000, minimum=500,
                                  maximum=100000),
        # DeepSeek V4.x 默认带"思考"，单块抽取要 30~90 秒；抽取/短答场景关掉思考
        # 可降到 4~5 秒（见 docs/optimization_report.md 的重建记录）
        llm_disable_thinking=get_bool("LLM_DISABLE_THINKING", True),
        # 答案生成默认仍关闭思考（短答场景，开思考会让评测慢 10 倍以上）
        gen_disable_thinking=get_bool("GEN_DISABLE_THINKING", True),
        llm_workers=get_int("LLM_WORKERS", 4, minimum=1, maximum=16),
    )


def validate_config(*, require_llm: bool = False,
                    require_neo4j: bool = True) -> List[str]:
    """启动期配置校验，返回问题清单（空列表表示通过）。

    不抛异常，方便服务启动时打印全部问题；需要强校验的调用方自行 raise。
    """
    problems: List[str] = []
    s = get_settings()
    if require_neo4j:
        if not s.neo4j_url:
            problems.append("NEO4J_URL 未配置")
        if not s.neo4j_user:
            problems.append("NEO4J_USER 未配置")
        if not s.neo4j_password:
            problems.append("NEO4J_PASSWORD 未配置（Neo4j 连接会失败）")
    if require_llm and not s.has_llm:
        problems.append("LLM_TOKEN / LLM_ENDPOINT 未配置，生成答案不可用")
    if s.has_remote_embedding and not s.embed_token:
        problems.append("配置了 EMBED_ENDPOINT/EMBED_MODEL 但没有 EMBED_TOKEN")
    if bool(s.embed_endpoint) != bool(s.embed_model):
        problems.append("EMBED_ENDPOINT 与 EMBED_MODEL 必须同时配置或同时留空")
    return problems


__all__ = ["BASE_DIR", "PROJECT_ROOT", "Settings", "get_env", "get_int",
           "get_bool", "get_settings", "validate_config"]
