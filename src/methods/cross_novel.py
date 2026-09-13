"""阶段二任务 C：跨书人物关联检索。

识别问题中的人物后，计算人物之间的最短路径，并将关系距离、时代和路径
封装进统一 Answer。graph 参数用于离线测试；正式运行可注入 data_loader。
"""

from typing import Any, Dict, List, Optional

from core.interfaces import Answer, QAMethod
from core.registry import register
from retrieve.graph_algorithms import shortest_path


def _people(graph: Dict[str, Any]) -> List[Dict[str, Any]]:
    """只保留有人名的人物节点。"""
    return [node for node in graph.get("nodes", [])
            if node.get("type") == "人物" and str(node.get("name", "")).strip()]


def _find_people(question: str, graph: Dict[str, Any]) -> List[str]:
    """长名字优先进行简单实体匹配，避免短名字抢先匹配。"""
    names = {str(node["name"]).strip() for node in _people(graph)}
    return [name for name in sorted(names, key=lambda x: (-len(x), x)) if name in question]


def _era(node: Dict[str, Any]) -> str:
    return str(node.get("era") or "未知")


@register("cross_novel")
class CrossNovelMethod(QAMethod):
    """跨书人物关联检索方法。"""

    name = "cross_novel"

    def __init__(self, data_loader: Any = None, graph: Optional[Dict[str, Any]] = None,
                 max_hops: int = 4):
        self.data_loader = data_loader
        self.graph = graph
        self.max_hops = max(max_hops, 1)

    def _load_graph(self) -> Dict[str, Any]:
        """优先使用测试图，再使用注入的数据加载器，最后才导入默认 loader。"""
        if self.graph is not None:
            return self.graph
        if self.data_loader is not None and hasattr(self.data_loader, "get_graph"):
            return self.data_loader.get_graph()
        from ingest.data_loader import get_graph  # 延迟导入，保证离线测试不依赖数据库。
        return get_graph()

    @staticmethod
    def _evidence(path: Dict[str, Any], node_map: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """整理前端可展示的路径证据。"""
        return {"source": path["source"], "target": path["target"],
                "distance": path["distance"], "path": path["path"],
                "edges": path["edges"],
                "eras": [_era(node_map[name]) for name in path["path"]]}

    def ask(self, question: str, top_k: int = 5) -> Answer:
        if not isinstance(question, str) or not question.strip():
            raise ValueError("question 必须是非空字符串")
        if top_k <= 0:
            return Answer("没有要求返回的关联结果。", self.name)
        try:
            graph = self._load_graph()
        except Exception as exc:
            return Answer(f"读取知识图谱失败：{exc}", self.name,
                          debug_info={"error": str(exc)})

        seeds = _find_people(question, graph)
        if not seeds:
            return Answer("未能从问题中识别出人物实体。", self.name,
                          debug_info={"seeds": []})
        people = _people(graph)
        node_map = {str(node["name"]): node for node in people}
        paths = []
        if len(seeds) >= 2:
            # 问题提到多个角色时，计算每一对角色的最短路径。
            for index, source in enumerate(seeds):
                for target in seeds[index + 1:]:
                    found = shortest_path(graph, source, target, self.max_hops)
                    if found["distance"] is not None:
                        paths.append(self._evidence(found, node_map))
        else:
            # 只提到一个角色时，寻找其他时代中可达的角色作为跨书候选。
            source = seeds[0]
            source_era = _era(node_map[source])
            for target, node in node_map.items():
                if target == source or _era(node) == source_era:
                    continue
                found = shortest_path(graph, source, target, self.max_hops)
                if found["distance"] is not None:
                    paths.append(self._evidence(found, node_map))
        paths.sort(key=lambda item: (item["distance"], item["target"]))
        paths = paths[:top_k]
        if not paths:
            return Answer("没有找到满足时代差异条件的跨书人物关联。", self.name,
                          debug_info={"seeds": seeds, "path_count": 0})
        lines = [f"{item['source']} → {item['target']}（关系距离 {item['distance']} 跳，"
                 f"时代：{'、'.join(item['eras'])}）" for item in paths]
        return Answer("跨书人物关联：" + "；".join(lines) + "。", self.name,
                      evidence=paths,
                      debug_info={"seeds": seeds, "path_count": len(paths),
                                  "max_hops": self.max_hops},
                      raw_context="\n".join(lines))


__all__ = ["CrossNovelMethod"]
