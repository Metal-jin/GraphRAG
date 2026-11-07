"""共享 HTTP 客户端工厂（环境兼容层）。

本机环境：httpcore 1.0.9 + zstandard 0.24 组合下，OpenAI SDK 收到
Content-Encoding: zstd 的响应时会抛
"Decompressor.decompress() got an unexpected keyword argument 'output_buffer_limit'"，
并被 SDK 包装成 APIConnectionError（看起来像网络故障）。

解决办法：显式声明 Accept-Encoding: identity，避免服务端返回压缩响应。
这不会改变任何业务语义，只是绕过上游依赖版本不兼容。
"""
from __future__ import annotations

from typing import Optional

_DEFAULT_HEADERS = {"Accept-Encoding": "identity"}


def build_http_client(timeout: float = 30.0):
    """返回一个禁用压缩协商的 httpx.Client；httpx 缺失时返回 None。"""
    try:
        import httpx
    except Exception:  # pragma: no cover - httpx 是 openai 的依赖，正常都存在
        return None
    return httpx.Client(headers=dict(_DEFAULT_HEADERS), timeout=timeout)


__all__ = ["build_http_client"]
