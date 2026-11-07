"""测试环境适配（Windows + 受限文件沙箱 + 强制离线）。

1. 本机 DSH 文件沙箱下 os.mkdir(path, 0o700) 会创建**当前进程也无法枚举**的目录，
   导致 pytest 的 tmp_path fixture 在 setup 阶段就 PermissionError。
   这里只放宽"私有模式"（0o700 一类），不影响正常目录权限语义。
2. 测试必须完全离线：即使仓库里有 .env 配置了远程嵌入/LLM，也不允许测试真的去
   调用付费接口。这里在导入任何业务模块前把相关环境变量清空，
   配合 autouse fixture 重置嵌入单例。
"""
import os

os.environ["EMBED_ENDPOINT"] = ""
os.environ["EMBED_MODEL"] = ""
os.environ["EMBED_TOKEN"] = ""
os.environ["EMBED_ALLOW_LOCAL_FALLBACK"] = "false"
os.environ["LLM_ENDPOINT"] = ""
os.environ["LLM_TOKEN"] = ""

import pytest  # noqa: E402

_original_mkdir = os.mkdir


def _mkdir(path, mode=0o777, *args, **kwargs):
    if isinstance(mode, int) and (mode & 0o077) == 0:
        mode = 0o777
    return _original_mkdir(path, mode, *args, **kwargs)


os.mkdir = _mkdir


@pytest.fixture(autouse=True)
def _offline_embedding():
    """每个测试前后重置嵌入单例，保证不会复用远程客户端。"""
    from core import embedding
    embedding.reset_embedder()
    yield
    embedding.reset_embedder()
