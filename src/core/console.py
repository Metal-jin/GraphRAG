"""控制台编码适配。

Windows 上 stdout 被重定向到管道时，Python 默认用系统 locale 编码
（英文系统是 cp1252），此时打印中文会抛 UnicodeEncodeError——
`--help` 里的中文说明会让 CLI 直接以退出码 1 结束（GitHub Actions
windows-latest 就是这样失败的）。

这里提供统一的 UTF-8 输出设置，CLI 入口启动时调用一次即可。
"""
from __future__ import annotations

import sys


def ensure_utf8_console() -> None:
    """把 stdout/stderr 切到 UTF-8（无法切换时静默跳过）。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001 - 某些环境（被替换的流）不支持
            continue


__all__ = ["ensure_utf8_console"]
