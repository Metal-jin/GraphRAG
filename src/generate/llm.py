"""LLM 生成答案模块。

把检索到的证据（raw_context）喂给 LLM，生成简洁的答案。
这是"检索 → 生成"的最后一环，补上它系统才是完整的"问答系统"，
而不是只返回一段原文的"检索器"。
"""
from openai import OpenAI

from core.config import get_env


def generate_answer(question: str, context: str) -> str:
    """根据问题和检索到的上下文，用 LLM 生成简洁答案。

    失败时抛出异常，由调用方兜底（退回检索原文）。
    """
    if not context or not context.strip():
        return "未检索到相关内容。"

    client = OpenAI(
        api_key=get_env("LLM_TOKEN"),
        base_url=get_env("LLM_ENDPOINT", "https://api.deepseek.com"),
    )

    prompt = f"""你是金庸武侠知识问答助手。请根据下面检索到的资料，简洁准确地回答用户的问题。

问题：{question}

检索到的资料：
{context}

要求：
- 如果是问"是谁/是什么"，直接回答名称，不要解释；
- 如果是问"有哪些"，用顿号列出；
- 只根据资料回答，不要编造；
- 如果资料不足以回答，直接说"根据现有资料无法回答"。

回答："""

    response = client.chat.completions.create(
        model=get_env("LLM_MODEL", "deepseek-chat"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    return response.choices[0].message.content.strip()
