"""
core/config.py
统一配置加载：从 .env 文件读取配置。

所有环境变量（数据库地址、LLM 密钥、嵌入模型等）都通过这里读取，
不要在业务代码里到处写 os.getenv。
"""
import os

from dotenv import load_dotenv

# 加载项目根目录的 .env 文件
load_dotenv()


def get_env(key: str, default: str = None) -> str:
    """读取环境变量，不存在时返回默认值。"""
    return os.getenv(key, default)
