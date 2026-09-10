"""师徒链检索（master_chain）。

领域策略之一：针对"跨代际师徒关系"问题（如"郭靖的师父的师父是谁"），
沿 MASTER_OF 关系反向走多跳，返回完整师徒链作为证据。

与通用基线（vector / library_graphrag）的区别：
- 基线只做"找相似文本块"，不理解"师徒"这种领域关系；
- 本策略定向沿 MASTER_OF 反向遍历，直接得到师徒链，证据更可解释。
"""

from typing import Any, Dict, List, Optional

from core.interfaces import Answer, QAMethod
from core.registry import register
from ingest.data_loader import get_graph, run_query


def _find_seed_person(question: str) -> Optional[str]:
    """从问题中识别起始人物（简单字符串匹配，长名优先）。

    阶段一用简单匹配够用；阶段二可换成 LLM 实体链接提高准确率。
    长名优先是为了避免"黄"误匹配到"黄蓉"而非"黄药师"。
    """
    try:
        graph = get_graph()
    except Exception:
        return None
    people = [
        n.get("name", "")
        for n in graph.get("nodes", [])
        if n.get("type") == "人物"
    ]
    people = [p for p in people if p]
    for name in sorted(people, key=len, reverse=True):
        if name in question:
            return name
    return None


@register("master_chain")
class MasterChainMethod(QAMethod):
    name = "master_chain"

    def __init__(self, data_loader: Any = None, chunks=None):
        # 领域策略直接复用 data_loader 的 run_query，data_loader 参数保留以对齐接口
        self.data_loader = data_loader
        self.chunks = chunks

    def ask(self, question: str, top_k: int = 5) -> Answer: # 师徒链检索方法的 ask 方法
        if not isinstance(question, str) or not question.strip():
            raise ValueError("question 必须是非空字符串")

        seed = _find_seed_person(question)
        if not seed: # 未能从问题中识别出人物实体
            return Answer(
                answer_text="未能从问题中识别出人物实体。",
                method_name=self.name,
                evidence=[],
                debug_info={"question": question, "seed": None},
                raw_context="",
            )

        # 沿 MASTER_OF 反向走 1~3 跳，得到各代师父（含深度，便于整理成链）
        try:
            rows: List[Dict[str, Any]] = run_query(
                """
                MATCH path = (p:人物 {name: $name})<-[:MASTER_OF*1..3]-(master:人物)
                RETURN master.name AS name, length(path) AS depth
                ORDER BY depth, master.name
                """,
                {"name": seed},
            )
        except Exception as e:  # Neo4j 未启动 / 未入库时给出友好提示
            return Answer(
                answer_text=f"查询师徒链失败（请确认 Neo4j 已启动、数据已入库）：{e}",
                method_name=self.name,
                evidence=[],
                debug_info={"seed": seed, "error": str(e)},
                raw_context="",
            )

        if not rows:
            return Answer(
                answer_text=f"图谱中没有找到 {seed} 的师父信息。",
                method_name=self.name,
                evidence=[{"seed": seed, "chain": []}],
                debug_info={"seed": seed, "hit_count": 0},
                raw_context=f"{seed} 无师徒链",
            )

        # 整理成可解释的师徒链：[(名字, 深度), ...]
        chain = [{"name": seed, "depth": 0}]
        chain += [{"name": r["name"], "depth": r["depth"]} for r in rows]

        # 生成答案文本：郭靖 的师父是 马钰；马钰 的师父是 ...
        parts = []
        for i in range(1, len(chain)):
            parts.append(f"{chain[i - 1]['name']} 的师父是 {chain[i]['name']}")
        answer_text = "；".join(parts) + "。"

        return Answer( # 师徒链检索方法的返回值
            answer_text=answer_text,
            method_name=self.name,
            evidence=chain,
            debug_info={"seed": seed, "hit_count": len(rows)},
            raw_context="\n".join(
                f"{c['name']}（第 {c['depth']} 代）" for c in chain
            ),
        )
