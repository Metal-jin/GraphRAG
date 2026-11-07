"""跨书人物关联检索（cross_novel）——任务 16 重写。

修复内容：
- 路径可以经过门派/地点/武功，不再对 node_map 只含人物而抛 KeyError('丐帮')；
- 单人物模式用一次单源 BFS（bfs_paths）替代"每个候选重新 BFS"；
- 明确关联语义：普通关联（同门/同地）与血缘关联（DESCENDANT_OF）分开标注；
- 输出完整路径与中间关系，而不只是首尾两个人名；
- 遵守 top_k 与 max_hops。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.entity_link import EntityIndex
from core.interfaces import Answer, QAMethod
from core.registry import register
from retrieve.graph_algorithms import bfs_paths, shortest_path

RELATION_NAMES = {
    "MASTER_OF": "师徒", "SPOUSE_OF": "夫妻", "PARENT_OF": "父母",
    "SWORN_BROTHER_OF": "结拜", "ENEMY_OF": "仇敌", "BELONGS_TO": "同门",
    "MASTERS": "精通", "FOUNDER_OF": "创立", "LOCATED_IN": "所在",
    "BRANCHED_FROM": "演化", "DESCENDANT_OF": "血缘",
}


def _era(node: Optional[Dict[str, Any]]) -> str:
    if not node:
        return "未知"
    return str(node.get("era") or node.get("book") or "未知")


def _node_type(node: Optional[Dict[str, Any]]) -> str:
    if not node:
        return ""
    return str(node.get("type") or node.get("label") or "")


def _relation_cn(rel: str) -> str:
    return RELATION_NAMES.get(rel, rel)


@register("cross_novel")
class CrossNovelMethod(QAMethod):
    """跨书人物关联检索。"""

    name = "cross_novel"

    def __init__(self, data_loader: Any = None,
                 graph: Optional[Dict[str, Any]] = None, max_hops: int = 4,
                 entity_index: Optional[EntityIndex] = None):
        self.data_loader = data_loader
        self.graph = graph
        self.max_hops = max(max_hops, 1)
        self.entity_index = entity_index

    # ---------- 数据 ----------

    def _load_graph(self) -> Dict[str, Any]:
        if self.graph is not None:
            return self.graph
        if self.data_loader is not None and hasattr(self.data_loader, "get_graph"):
            return self.data_loader.get_graph()
        from ingest.data_loader import get_graph
        return get_graph()

    def _index(self, graph: Dict[str, Any]) -> EntityIndex:
        if self.entity_index is not None:
            return self.entity_index
        return EntityIndex(entities=graph.get("nodes") or [])

    # ---------- 证据 ----------

    @staticmethod
    def _evidence(path: Dict[str, Any],
                  node_map: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """整理可展示的路径证据（完整节点 + 关系，不丢中间环节）。"""
        edges = []
        for edge in path.get("edges", []):
            edges.append({
                "source": edge.get("source", ""),
                "target": edge.get("target", ""),
                "type": edge.get("type", ""),
                "direction": "forward",
                "chunk_ids": edge.get("chunk_ids", []) or [],
                "snippets": [],
                "confidence": "extracted",
            })
        is_blood = any(e["type"] == "DESCENDANT_OF" for e in edges)
        eras = [_era(node_map[name]) for name in path["path"] if name in node_map]
        relation_text = " -> ".join(
            f"{e['source']}--[{_relation_cn(e['type'])}]-->{e['target']}" for e in edges)
        return {
            "kind": "path",
            "source_method": "cross_novel",
            "confidence": "extracted",
            "seed": path["source"],
            "complete": True,
            "nodes": [{"id": f"{_node_type(node_map.get(name))}::{name}", "name": name,
                       "type": _node_type(node_map.get(name)),
                       "era": _era(node_map.get(name))} for name in path["path"]],
            "edges": edges,
            "chunk_ids": sorted({c for e in edges for c in e["chunk_ids"]}),
            "text": relation_text,
            # 兼容旧字段（前端/旧测试使用）
            "source": path["source"], "target": path["target"],
            "distance": path["distance"], "path": path["path"],
            "eras": eras, "cross_book": len(set(eras)) > 1,
            "blood_relation": is_blood,
            "legacy": {"path": path["path"], "distance": path["distance"]},
        }

    # ---------- 主流程 ----------

    def ask(self, question: str, top_k: int = 5) -> Answer:
        if not isinstance(question, str) or not question.strip():
            raise ValueError("question 必须是非空字符串")
        if top_k <= 0:
            return Answer("没有要求返回的关联结果。", self.name,
                          debug_info={"status": "no_result"})
        try:
            graph = self._load_graph()
        except Exception as exc:
            return Answer(f"读取知识图谱失败：{exc}", self.name,
                          debug_info={"error": str(exc), "status": "error"})
        node_map = {str(n.get("name", "")).strip(): n for n in graph.get("nodes", [])
                    if n.get("name")}
        index = self._index(graph)
        matches = index.link(question, labels=["人物"])
        seeds = []
        for match in matches:
            if match.canonical not in seeds:
                seeds.append(match.canonical)
        if not seeds:
            return Answer("未能从问题中识别出人物实体。", self.name,
                          debug_info={"seeds": [], "status": "no_entity"})

        paths: List[Dict[str, Any]] = []
        if len(seeds) >= 2:
            # 明确问两个人之间的关系：只算这些配对
            for position, source in enumerate(seeds):
                for target in seeds[position + 1:]:
                    found = shortest_path(graph, source, target, self.max_hops)
                    if found["distance"] is not None:
                        paths.append(self._evidence(found, node_map))
        else:
            # 只提到一个人：一次 BFS 找到所有其他时代人物
            source = seeds[0]
            source_era = _era(node_map.get(source))
            reachable = bfs_paths(graph, source, self.max_hops)
            for target, found in reachable.items():
                target_node = node_map.get(target)
                if not target_node or _node_type(target_node) != "人物":
                    continue
                if _era(target_node) == source_era:
                    continue
                paths.append(self._evidence(found, node_map))

        paths.sort(key=lambda item: (not item["blood_relation"],
                                     item["distance"], item["target"]))
        paths = paths[:top_k]
        if not paths:
            return Answer("没有找到满足时代差异条件的跨书人物关联。", self.name,
                          debug_info={"seeds": seeds, "path_count": 0,
                                      "max_hops": self.max_hops,
                                      "status": "no_result"})

        lines = []
        for item in paths:
            kind = "血缘关联" if item["blood_relation"] else "一般关联"
            relation_text = " -> ".join(
                f"{e['source']}--[{_relation_cn(e['type'])}]-->{e['target']}"
                for e in item["edges"])
            lines.append(f"{item['source']} 与 {item['target']}：{kind}，"
                         f"关系距离 {item['distance']} 跳（{relation_text}）")
        answer_text = "跨书人物关联：" + "；".join(lines) + "。"

        return Answer(
            answer_text=answer_text, method_name=self.name, evidence=paths,
            debug_info={"seeds": seeds, "path_count": len(paths),
                        "max_hops": self.max_hops,
                        "blood_count": sum(1 for p in paths if p["blood_relation"]),
                        "status": "ok"},
            raw_context="\n".join(lines))


__all__ = ["CrossNovelMethod"]
