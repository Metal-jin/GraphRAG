"""统一嵌入模块（任务 03 / 04）。

项目里曾经有两套互不兼容的本地哈希嵌入（build_kg 用内置 hash()，vector_utils
用 sha256），跨进程结果不一致，入库与查询也换了算法。现在全项目只有这一份实现：

- 配置了 EMBED_ENDPOINT/EMBED_MODEL 时使用远程嵌入（语义向量）；
- 否则使用稳定哈希嵌入（词法兜底，sha256 + 有符号投票，跨进程可复现）；
- 任何一次嵌入都带 EmbeddingSpec（kind/model/维度/版本），用于索引兼容性校验；
- 远程失败不静默混用本地向量：默认抛 EmbeddingError；只有显式配置
  EMBED_ALLOW_LOCAL_FALLBACK=true 才允许整批降级，并标记 degraded。

索引兼容性约定：Neo4j 中 (:IndexMeta {name:'chunk_embeddings'}) 记录
model_id / dimension / version，写入前必须与本模块的 spec 一致。
"""
from __future__ import annotations

import hashlib
import math
import re
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from core.config import get_env, get_int, get_settings
from core.errors import EmbeddingError, IndexCompatibilityError

# 词法兜底嵌入的版本：算法或分词一变就必须改这个字符串
LOCAL_HASH_VERSION = "local-hash-v1"
LOCAL_HASH_DIM = 256

# 与历史 vector_utils 完全一致的分词：单个汉字 或 连续的字母数字串
TOKEN_RE = re.compile(r"[\u4e00-\u9fff]|[a-zA-Z0-9_]+")


def tokenize(text: str) -> List[str]:
    return TOKEN_RE.findall((text or "").lower())


def local_hash_embed(text: str, dim: int = LOCAL_HASH_DIM) -> List[float]:
    """确定性词袋哈希向量（sha256，有符号投票，L2 归一化）。

    跨进程、跨机器、跨 Python 版本结果一致；同一算法版本保证旧新数据可比。
    """
    vector = [0.0] * dim
    for token in tokenize(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dim
        vector[index] += 1.0 if digest[4] & 1 else -1.0
    norm = math.sqrt(sum(x * x for x in vector))
    if norm:
        return [x / norm for x in vector]
    return vector


@dataclass(frozen=True)
class EmbeddingSpec:
    """嵌入方案的身份标识，用于索引兼容性校验。"""

    kind: str          # "remote" | "local-hash"
    model_id: str      # 远程模型名，或 local-hash 版本
    dimension: int
    version: str = "v1"

    @property
    def fingerprint(self) -> str:
        return f"{self.kind}:{self.model_id}:{self.dimension}:{self.version}"

    def to_meta(self) -> Dict[str, object]:
        return {"kind": self.kind, "model_id": self.model_id,
                "dimension": self.dimension, "version": self.version,
                "fingerprint": self.fingerprint}


def assert_index_compatible(stored: Optional[Dict], spec: EmbeddingSpec) -> None:
    """校验索引元数据与当前嵌入方案一致；不一致直接报错，不允许静默复用。"""
    if not stored:
        return
    stored_dim = stored.get("dimension")
    stored_fp = stored.get("fingerprint")
    if stored_dim is not None and int(stored_dim) != spec.dimension:
        raise IndexCompatibilityError(
            f"向量索引维度 {stored_dim} 与当前嵌入方案 {spec.dimension} 不一致",
            detail=f"索引记录={stored}，当前={spec.to_meta()}；"
                   f"请重建索引或修正 EMBED_* 配置，不能混用不同模型的向量")
    if stored_fp and stored_fp != spec.fingerprint:
        raise IndexCompatibilityError(
            f"向量索引模型版本与当前配置不一致：{stored_fp} != {spec.fingerprint}",
            detail="请重建索引或恢复原嵌入模型配置")


class EmbeddingService:
    """全项目唯一的嵌入入口（带缓存、批处理、维度校验）。"""

    def __init__(self, *, endpoint: Optional[str] = None, model: Optional[str] = None,
                 token: Optional[str] = None, allow_local_fallback: Optional[bool] = None,
                 declared_dim: Optional[int] = None, cache_size: int = 4096):
        settings = get_settings()
        self.endpoint = (endpoint if endpoint is not None else settings.embed_endpoint).strip()
        self.model = (model if model is not None else settings.embed_model).strip()
        self.token = (token if token is not None else settings.embed_token).strip()
        if allow_local_fallback is None:
            allow_local_fallback = settings.embed_allow_local_fallback
        self.allow_local_fallback = bool(allow_local_fallback)
        self._declared_dim = declared_dim
        self._remote_dim: Optional[int] = None
        self._cache: "OrderedDict[Tuple[str, str], List[float]]" = OrderedDict()
        self._cache_size = max(16, int(cache_size))
        self._client = None
        self.degraded = False
        self.last_error: Optional[str] = None

    # ---------- 配置 ----------

    @classmethod
    def from_env(cls) -> "EmbeddingService":
        settings = get_settings()
        dim = int(settings.embed_dim) if settings.embed_dim.isdigit() else None
        return cls(declared_dim=dim)

    @property
    def uses_remote(self) -> bool:
        return bool(self.endpoint and self.model)

    @property
    def spec(self) -> EmbeddingSpec:
        if self.uses_remote:
            dim = self._declared_dim or self._remote_dim or 0
            return EmbeddingSpec("remote", self.model, dim or 0)
        return EmbeddingSpec("local-hash", LOCAL_HASH_VERSION, LOCAL_HASH_DIM)

    # ---------- 公共 API ----------

    def embed_documents(self, texts: Sequence[str]) -> List[List[float]]:
        """批量嵌入（入库 / 离线检索）。"""
        return self._embed_many(list(texts), purpose="document")

    def embed_query(self, text: str) -> List[float]:
        """单条查询嵌入（与入库共用同一 spec）。"""
        return self._embed_many([text], purpose="query")[0]

    def __call__(self, texts: Sequence[str]) -> List[List[float]]:
        """兼容旧代码的 embedder([...]) 调用形式。"""
        return self.embed_documents(texts)

    # ---------- 内部 ----------

    def _embed_many(self, texts: List[str], *, purpose: str) -> List[List[float]]:
        if not texts:
            return []
        self.degraded = False
        if not self.uses_remote:
            return [self._cached_local(t) for t in texts]

        missing = [t for t in texts if self._cache_key(t) not in self._cache]
        if missing:
            try:
                vectors = self._remote_embed(missing)
            except Exception as exc:  # 远程失败
                self.last_error = f"{type(exc).__name__}: {exc}"
                if not self.allow_local_fallback:
                    raise EmbeddingError(
                        "嵌入服务调用失败，拒绝回退到不兼容的本地向量",
                        detail=f"{self.last_error}；如确需降级请显式设置 "
                               f"EMBED_ALLOW_LOCAL_FALLBACK=true 并重建索引") from exc
                self.degraded = True
                vectors = [local_hash_embed(t) for t in missing]
                if self._declared_dim and self._declared_dim != LOCAL_HASH_DIM:
                    raise EmbeddingError(
                        "本地兜底向量维度与索引不一致，已中止",
                        detail=f"索引维度={self._declared_dim}，本地={LOCAL_HASH_DIM}")
            for text, vector in zip(missing, vectors):
                self._validate_vector(vector)
                self._remember(text, vector)
        return [self._cache[self._cache_key(t)] for t in texts]

    def _cached_local(self, text: str) -> List[float]:
        key = self._cache_key(text)
        if key not in self._cache:
            self._remember(text, local_hash_embed(text))
        return self._cache[key]

    def _cache_key(self, text: str) -> Tuple[str, str]:
        digest = hashlib.sha256((text or "").encode("utf-8")).hexdigest()
        return (self.spec.fingerprint, digest)

    def _remember(self, text: str, vector: List[float]) -> None:
        key = self._cache_key(text)
        self._cache[key] = vector
        self._cache.move_to_end(key)
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)

    def _validate_vector(self, vector: Iterable[float]) -> None:
        values = list(vector)
        if not values or not all(isinstance(v, (int, float)) for v in values):
            raise EmbeddingError("嵌入服务返回了非数值向量")
        if not all(math.isfinite(v) for v in values):
            raise EmbeddingError("嵌入服务返回了非有限数值（NaN/Inf）")
        if self._declared_dim and len(values) != self._declared_dim:
            raise EmbeddingError(
                f"嵌入维度与约定不一致：{len(values)} != {self._declared_dim}",
                detail="请检查 EMBED_DIM / 模型是否被更换")
        if self._remote_dim is None:
            self._remote_dim = len(values)
        elif self._remote_dim != len(values):
            raise EmbeddingError(
                f"同一批数据出现不同维度的向量：{self._remote_dim} vs {len(values)}")

    def _remote_embed(self, texts: List[str]) -> List[List[float]]:
        if self._client is None:
            from openai import OpenAI
            from core.http_client import build_http_client
            timeout = get_int("EMBED_TIMEOUT", 30, minimum=1, maximum=300)
            self._client = OpenAI(api_key=self.token or "EMPTY",
                                  base_url=self.endpoint, timeout=timeout,
                                  http_client=build_http_client(timeout))
        # 限流/瞬时网络错误重试一次；认证/参数错误直接抛出
        attempts = get_int("EMBED_RETRIES", 2, minimum=1, maximum=5)
        last_error: Optional[Exception] = None
        for attempt in range(1, attempts + 1):
            try:
                resp = self._client.embeddings.create(model=self.model, input=texts)
                return [list(d.embedding) for d in resp.data]
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                name = type(exc).__name__
                if name in {"AuthenticationError", "PermissionDeniedError",
                            "BadRequestError", "NotFoundError"}:
                    raise
                if attempt < attempts:
                    time.sleep(min(1.5 * attempt, 4))
        raise last_error  # type: ignore[misc]

    def close(self) -> None:
        self._client = None
        self._cache.clear()


_DEFAULT_SERVICE: Optional[EmbeddingService] = None


def get_embedder(refresh: bool = False) -> EmbeddingService:
    """进程级单例（任务 03：抽取/入库/检索/离线都必须走同一个实例）。"""
    global _DEFAULT_SERVICE
    if refresh or _DEFAULT_SERVICE is None:
        _DEFAULT_SERVICE = EmbeddingService.from_env()
    return _DEFAULT_SERVICE


def reset_embedder() -> None:
    global _DEFAULT_SERVICE
    if _DEFAULT_SERVICE is not None:
        _DEFAULT_SERVICE.close()
    _DEFAULT_SERVICE = None


__all__ = ["EmbeddingService", "EmbeddingSpec", "LOCAL_HASH_DIM",
           "LOCAL_HASH_VERSION", "local_hash_embed", "tokenize",
           "assert_index_compatible", "get_embedder", "reset_embedder"]
