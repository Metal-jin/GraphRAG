"""阶段二实体对齐系统（任务 08 / 20 / 21）。

三层对齐 + 一层后处理：
  ① RuleNormalizer   规则层：称谓后缀剥离 + 姓氏归一 + 噪声识别
  ② AliasDictionary  词典层：人工/累积的别名词典（JSON 落盘，可按 era 限定）
  ③ SimilarityAligner 相似度层：rapidfuzz + pypinyin 双路打分，默认只出 CSV
  ④ DescendantScanner 后处理：跨书血缘 DESCENDANT_OF 候选（必须能链接到真实实体）
  AlignmentPipeline 把以上串成流水线，落库走 ingest.graph_ops（幂等）。

相对旧版修复（对应任务 20/21）：
- 规则层把"归一后未变化的正名"也纳入索引，一灯 / 一灯大师 能配对；
- 归并决策按 era 作用域查找节点，跨书共享身份不会被错误拆分；
- 词典冲突、归并成环、链式归并都会被检测或压平；
- --include-similarity 真正生效（默认仍只导 CSV 供人工审核）；
- 后代扫描不再创建"无 label 的无主节点"，候选必须两端都存在于图谱中，
  且写入时带 evidence（chunk_id/snippet）与 confidence=inferred。

用法：
    python src/ingest/entity_alignment.py --dry-run
    python src/ingest/entity_alignment.py --apply
    python src/ingest/entity_alignment.py --candidates-only
    python src/ingest/entity_alignment.py --apply --include-similarity
    python src/ingest/entity_alignment.py --apply --descendants-only
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

_SRC_DIR = Path(__file__).resolve().parents[2] / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from neo4j import GraphDatabase
from rapidfuzz import fuzz
from pypinyin import lazy_pinyin

from core.config import get_settings
from core.ontology import ENTITY_LABEL_SET, NOISE_NAMES, is_noise_name
from ingest import graph_ops

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DICT_PATH = PROJECT_ROOT / "data" / "processed" / "alias_dict.json"
DEFAULT_CANDIDATES_PATH = PROJECT_ROOT / "data" / "interim" / "alignment_candidates.csv"

ENTITY_LABELS: Set[str] = set(ENTITY_LABEL_SET)
VALID_ERAS: Set[str] = {"射雕", "神雕", "倚天"}


# ============================================================
# ① 规则层
# ============================================================

class RuleNormalizer:
    """规则层：称谓后缀剥离 + 姓氏归一 + 噪声识别（纯函数）。"""

    # 只保留"不改变身份/性别"的安全称谓。
    # 帮主/夫人/姑娘/王爷等身份或性别后缀不在列，剥离会把不同的人合并。
    TITLE_SUFFIXES: Tuple[str, ...] = (
        "道长", "真人", "大师", "禅师", "师太", "国师",
        "大侠", "侠客", "女侠", "侠侣",
        "前辈", "老前辈", "老人家",
        "师父", "师傅", "恩师", "师尊",
        "兄台", "阁下", "足下",
    )

    SURNAME_VARIANTS: Dict[str, str] = {
        "诸葛氏": "诸葛", "欧阳氏": "欧阳", "上官氏": "上官", "令狐氏": "令狐",
        "司马氏": "司马", "南宫氏": "南宫", "慕容氏": "慕容",
    }

    def strip_title(self, name: str) -> str:
        for suffix in self.TITLE_SUFFIXES:
            if name.endswith(suffix) and len(name) > len(suffix):
                return name[: -len(suffix)]
        return name

    def normalize_surname(self, name: str) -> str:
        for old, new in self.SURNAME_VARIANTS.items():
            if name.startswith(old):
                return new + name[len(old):]
        return name

    def normalize(self, name: str) -> str:
        return self.strip_title(self.normalize_surname(name))

    @staticmethod
    def is_noise(name: str) -> bool:
        return is_noise_name(name)


# ============================================================
# ② 词典层
# ============================================================

@dataclass
class AliasEntry:
    """单条别名规则。applicable_eras 为空表示不限时代。"""

    alias: str
    canonical: str
    label: str
    applicable_eras: List[str] = field(default_factory=list)
    source: str = "人工"
    note: str = ""

    def matches(self, name: str, era: Optional[str], label: Optional[str]) -> bool:
        if self.alias != name:
            return False
        if label is not None and self.label != label:
            return False
        if era is not None and self.applicable_eras and era not in self.applicable_eras:
            return False
        return True

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "AliasEntry":
        return cls(alias=data["alias"], canonical=data["canonical"],
                   label=data["label"],
                   applicable_eras=list(data.get("applicable_eras", [])),
                   source=data.get("source", "人工"), note=data.get("note", ""))


class AliasDictionary:
    """别名词典层（同一 alias 可按 era 指向不同正名）。"""

    def __init__(self, entries: Optional[List[AliasEntry]] = None,
                 path: Optional[Path] = None):
        self.path = path or DEFAULT_DICT_PATH
        self.entries: List[AliasEntry] = entries or []

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "AliasDictionary":
        path = path or DEFAULT_DICT_PATH
        if not path.exists():
            return cls(path=path)
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(entries=[AliasEntry.from_dict(d) for d in data], path=path)

    def save(self, path: Optional[Path] = None) -> None:
        path = path or self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps([e.to_dict() for e in self.entries],
                                   ensure_ascii=False, indent=2), encoding="utf-8")

    def lookup(self, name: str, era: Optional[str] = None,
               label: Optional[str] = None) -> Optional[AliasEntry]:
        for entry in self.entries:
            if entry.matches(name, era, label):
                return entry
        return None

    def add(self, alias: str, canonical: str, label: str,
            applicable_eras: Optional[List[str]] = None,
            source: str = "人工", note: str = "") -> None:
        """新增或覆盖一条规则（同 alias + label + era 集合则覆盖）。"""
        eras = list(applicable_eras or [])
        for index, entry in enumerate(self.entries):
            if entry.alias == alias and entry.label == label and entry.applicable_eras == eras:
                self.entries[index] = AliasEntry(alias, canonical, label, eras, source, note)
                return
        self.entries.append(AliasEntry(alias, canonical, label, eras, source, note))

    def conflicts(self) -> List[Dict]:
        """同一 alias+label 指向多个不同正名（且时代集合可重叠）→ 冲突。"""
        groups: Dict[Tuple[str, str], List[AliasEntry]] = {}
        for entry in self.entries:
            groups.setdefault((entry.alias, entry.label), []).append(entry)
        problems = []
        for (alias, label), items in groups.items():
            canonicals = {i.canonical for i in items}
            if len(canonicals) > 1:
                problems.append({"alias": alias, "label": label,
                                 "canonicals": sorted(canonicals)})
        return problems


# ============================================================
# ③ 相似度层
# ============================================================

class SimilarityAligner:
    """rapidfuzz 字符相似 + pypinyin 拼音相似，双路取最大。"""

    def __init__(self, threshold: float = 0.85):
        if not 0.0 <= threshold <= 1.0:
            raise ValueError(f"threshold 必须在 [0,1]，收到 {threshold}")
        self.threshold = threshold

    @staticmethod
    def _to_pinyin(text: str) -> str:
        return " ".join(lazy_pinyin(text))

    def char_score(self, left: str, right: str) -> float:
        if left == right:
            return 1.0
        return max(fuzz.ratio(left, right) / 100.0,
                   fuzz.partial_ratio(left, right) / 100.0)

    def pinyin_score(self, left: str, right: str) -> float:
        lpy, rpy = self._to_pinyin(left), self._to_pinyin(right)
        if lpy == rpy:
            return 1.0
        return max(fuzz.ratio(lpy, rpy) / 100.0,
                   fuzz.partial_ratio(lpy, rpy) / 100.0)

    def score(self, left: str, right: str) -> float:
        return max(self.char_score(left, right), self.pinyin_score(left, right))

    def find_candidates(self, entities: List[Tuple[str, Optional[str], Optional[str]]],
                        label_filter: Optional[Set[str]] = None
                        ) -> List[Tuple[str, str, float, str]]:
        buckets: Dict[str, List[Tuple[str, Optional[str]]]] = {}
        for name, era, label in entities:
            if label_filter and label not in label_filter:
                continue
            if label is None:
                continue
            buckets.setdefault(label, []).append((name, era))

        candidates: List[Tuple[str, str, float, str]] = []
        for label, items in buckets.items():
            for i in range(len(items)):
                for j in range(i + 1, len(items)):
                    left, _ = items[i]
                    right, _ = items[j]
                    if abs(len(left) - len(right)) > 2:
                        continue
                    char = self.char_score(left, right)
                    pinyin = self.pinyin_score(left, right)
                    score = max(char, pinyin)
                    if score < self.threshold:
                        continue
                    name1, name2 = sorted([left, right])
                    candidates.append((name1, name2, round(score, 4),
                                       "char" if char >= pinyin else "pinyin"))
        candidates.sort(key=lambda item: -item[2])
        return candidates

    def write_candidates_csv(self, candidates: List[Tuple[str, str, float, str]],
                             path: Path,
                             metadata_lookup: Optional[Dict[Tuple[str, str], Dict]] = None
                             ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        metadata_lookup = metadata_lookup or {}
        meta_headers: List[str] = []
        for meta in metadata_lookup.values():
            for key in meta:
                if key not in meta_headers:
                    meta_headers.append(key)
        headers = ["name1", "name2", "score", "reason", "decision"] + meta_headers
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(headers)
            for name1, name2, score, reason in candidates:
                meta = metadata_lookup.get((name1, ""), {})
                writer.writerow([name1, name2, score, reason, ""] +
                                [meta.get(header, "") for header in meta_headers])


# ============================================================
# ④ 跨书血缘（DESCENDANT_OF）
# ============================================================

@dataclass
class DescendantCandidate:
    ancestor: str
    descendant: str
    kind: str
    evidence: str
    valid: bool = True
    reason: str = ""


class DescendantScanner:
    """从实体 description 扫描"X之后/之女/之子/后人"模式（纯后处理）。"""

    _SURNAMES = ("王李张刘陈杨赵黄周吴孙朱马胡郭何高林罗郑梁谢宋唐韩冯邓曹彭曾田董"
                 "袁潘于蒋蔡余杜叶程苏魏吕丁任沈姚卢姜崔钟谭陆汪范金石廖贾夏韦白邹孟熊"
                 "秦江尹薛段雷侯龙史陶黎贺顾毛郝龚邵钱覃武戴莫孔向汤")
    _SURNAME_RE = "[" + _SURNAMES + "]"
    _COMPOUND_RE = "(?:诸葛|欧阳|上官|司马|南宫|令狐|慕容)"
    _ANCESTOR_RE = "(?:" + _SURNAME_RE + "|" + _COMPOUND_RE + ")[一-龥]{1,3}"

    PATTERNS: List[Tuple[str, str]] = [
        ("(" + _ANCESTOR_RE + ")之后人?", "之后"),
        ("(" + _ANCESTOR_RE + ")之女", "之女"),
        ("(" + _ANCESTOR_RE + ")(?:与|和|跟)[一-龥]{2,3}之子", "之子"),
        ("(" + _ANCESTOR_RE + ")之子", "之子"),
        ("(" + _ANCESTOR_RE + ")之孙", "之孙"),
        ("(" + _ANCESTOR_RE + ")之孙女", "之孙女"),
        ("(" + _ANCESTOR_RE + ")的(?:女儿|闺女)", "之女"),
        ("(" + _ANCESTOR_RE + ")的(?:儿子|孩儿)", "之子"),
    ]

    def scan_entity(self, entity: Dict) -> List[Tuple[str, str, str]]:
        name = entity.get("name", "")
        description = entity.get("description") or ""
        if not description:
            return []
        results: List[Tuple[str, str, str]] = []
        for pattern, kind in self.PATTERNS:
            for match in re.finditer(pattern, description):
                results.append((match.group(1), name, kind))
        return list(set(results))

    def scan_entities(self, entities: List[Dict]) -> List[Tuple[str, str, str]]:
        results: List[Tuple[str, str, str]] = []
        for entity in entities:
            results.extend(self.scan_entity(entity))
        return results

    def build_candidates(self, entities: List[Dict],
                         known_names: Optional[Set[str]] = None
                         ) -> List[DescendantCandidate]:
        """生成候选并做身份校验：两端必须存在于图谱、不得自环。"""
        known = known_names if known_names is not None else {
            str(e.get("name", "")).strip() for e in entities}
        candidates: List[DescendantCandidate] = []
        seen = set()
        for ancestor, descendant, kind in self.scan_entities(entities):
            key = (ancestor, descendant)
            if key in seen:
                continue
            seen.add(key)
            evidence = ""
            for entity in entities:
                if entity.get("name") == descendant:
                    evidence = (entity.get("description") or "")[:160]
                    break
            if ancestor == descendant:
                candidates.append(DescendantCandidate(ancestor, descendant, kind, evidence,
                                                      valid=False, reason="自环血缘"))
            elif ancestor not in known:
                candidates.append(DescendantCandidate(ancestor, descendant, kind, evidence,
                                                      valid=False, reason="祖先实体不在图谱中"))
            elif descendant not in known:
                candidates.append(DescendantCandidate(ancestor, descendant, kind, evidence,
                                                      valid=False, reason="后代实体不在图谱中"))
            else:
                candidates.append(DescendantCandidate(ancestor, descendant, kind, evidence))
        return candidates


# ============================================================
# ⑤ 主流水线
# ============================================================

@dataclass
class AlignmentDecision:
    alias_name: str
    canonical_name: str
    label: str
    era: Optional[str]
    source: str
    score: str = ""
    note: str = ""


@dataclass
class AlignmentReport:
    discovered: List[AlignmentDecision] = field(default_factory=list)
    applied: int = 0
    skipped: int = 0
    errors: List[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [f"发现候选归并 {len(self.discovered)} 条"]
        by_source: Dict[str, int] = {}
        for decision in self.discovered:
            by_source[decision.source] = by_source.get(decision.source, 0) + 1
        for source, count in by_source.items():
            lines.append(f"  - {source}: {count}")
        lines.append(f"实际执行: 归并 {self.applied}，跳过 {self.skipped}，"
                     f"错误 {len(self.errors)}")
        return "\n".join(lines)


class AlignmentPipeline:
    """三层流水线 + DESCENDANT_OF 后处理。"""

    def __init__(self, dictionary: Optional[AliasDictionary] = None,
                 threshold: float = 0.85, dict_path: Optional[Path] = None):
        self.normalizer = RuleNormalizer()
        self.dictionary = dictionary or AliasDictionary.load(dict_path)
        self.similarity = SimilarityAligner(threshold=threshold)
        self.descendant_scanner = DescendantScanner()
        self._similarity_candidates: List[Tuple[str, str, float, str]] = []

    # ---------- 候选发现 ----------

    def discover_alignments(self, entities: List[Dict],
                            label_filter: Optional[Set[str]] = None,
                            include_similarity: bool = False) -> List[AlignmentDecision]:
        if label_filter is None:
            label_filter = ENTITY_LABELS
        decisions: List[AlignmentDecision] = []
        seen: Set[Tuple[str, str, str]] = set()

        def add(decision: AlignmentDecision) -> None:
            key = (decision.alias_name, decision.canonical_name, decision.label)
            if key in seen or decision.alias_name == decision.canonical_name:
                return
            seen.add(key)
            decisions.append(decision)

        usable = [e for e in entities
                  if e.get("label") in label_filter and not RuleNormalizer.is_noise(e.get("name", ""))]

        # ① 词典层
        canonical_names = {e["name"] for e in usable}
        for entity in usable:
            entry = self.dictionary.lookup(entity["name"], entity.get("era"), entity.get("label"))
            if entry and entry.canonical != entity["name"]:
                add(AlignmentDecision(entity["name"], entry.canonical,
                                      entity.get("label") or entry.label,
                                      entity.get("era"), "词典", note=entry.note))

        # ② 规则层：**所有实体**（含归一后未变化的）都进索引，才能让正名参与配对
        norm_groups: Dict[Tuple[str, str, Optional[str]], List[Dict]] = {}
        for entity in usable:
            name = entity["name"]
            normalized = self.normalizer.normalize(name)
            if len(normalized) < 2:
                continue
            norm_groups.setdefault((normalized, entity.get("label") or "?",
                                    entity.get("era")), []).append(entity)

        for (normalized, label, era), group in norm_groups.items():
            if len(group) < 2:
                continue
            canonical = self._choose_canonical(group, canonical_names)
            for entity in group:
                if entity["name"] == canonical:
                    continue
                # 只允许"更长名 -> 已确认正名"或"归一形式相同"的安全归并
                add(AlignmentDecision(entity["name"], canonical, label, era, "规则",
                                      note=f"归一形式={normalized}"))

        # ③ 相似度层：默认只出候选；显式 include_similarity 才进入决策
        ent_index = [(e["name"], e.get("era"), e.get("label")) for e in usable]
        self._similarity_candidates = self.similarity.find_candidates(
            ent_index, label_filter=label_filter)
        if include_similarity:
            for name1, name2, score, reason in self._similarity_candidates:
                canonical = self._choose_canonical(
                    [e for e in usable if e["name"] in (name1, name2)], canonical_names)
                alias = name2 if canonical == name1 else name1
                add(AlignmentDecision(alias, canonical, 
                                      next((e.get("label") for e in usable if e["name"] == alias), "?"),
                                      None, "相似度", score=str(score), note=reason))

        return self._flatten_and_validate(decisions)

    def _choose_canonical(self, group: List[Dict], known: Set[str]) -> str:
        """正名选择：词典正名 > 最长名字（同长度取字典序）。"""
        names = [e["name"] for e in group]
        for name in names:
            entry = self.dictionary.lookup(name, None, None)
            if entry and entry.canonical in names:
                return entry.canonical
        return sorted(names, key=lambda n: (-len(n), n))[0]

    def _flatten_and_validate(self, decisions: List[AlignmentDecision]) -> List[AlignmentDecision]:
        """链式归并压平 + 成环检测（任务 20）。"""
        mapping = {d.alias_name: d.canonical_name for d in decisions}
        invalid: Set[str] = set()
        for start in list(mapping):
            seen, current = set(), start
            while current in mapping:
                if current in seen:
                    invalid.update(seen)
                    break
                seen.add(current)
                current = mapping[current]
        flattened: List[AlignmentDecision] = []
        for decision in decisions:
            if decision.alias_name in invalid:
                continue
            target = decision.canonical_name
            hops = 0
            while target in mapping and hops < 8:
                target = mapping[target]
                hops += 1
            if target == decision.alias_name:
                continue
            flattened.append(AlignmentDecision(
                decision.alias_name, target, decision.label, decision.era,
                decision.source, decision.score,
                decision.note if target == decision.canonical_name
                else f"{decision.note}（链式归并）".strip()))
        # 去重（压平后可能出现重复 alias）
        unique: Dict[Tuple[str, str, str], AlignmentDecision] = {}
        for decision in flattened:
            unique.setdefault((decision.alias_name, decision.canonical_name, decision.label),
                              decision)
        return list(unique.values())

    # ---------- 后代扫描 ----------

    def discover_descendants(self, entities: List[Dict]) -> List[DescendantCandidate]:
        return self.descendant_scanner.build_candidates(entities)


# ============================================================
# ⑥ Neo4j 读写
# ============================================================

def _driver():
    from ingest.data_loader import create_driver
    return create_driver()


def fetch_all_entities(session, label_filter: Optional[Set[str]] = None) -> List[Dict]:
    if label_filter is None:
        label_filter = ENTITY_LABELS
    return session.run(
        "MATCH (n) WHERE any(l IN labels(n) WHERE l IN $labels) "
        "RETURN elementId(n) AS eid, "
        "       head([l IN labels(n) WHERE l IN $labels]) AS label, "
        "       n.name AS name, n.era AS era, coalesce(n.eras, []) AS eras, "
        "       n.description AS description, count { (n)--() } AS degree",
        labels=list(label_filter)).data()


def apply_alignments(session, decisions: List[AlignmentDecision],
                     dry_run: bool) -> Tuple[int, int, List[str]]:
    """把归并决策落到 Neo4j（幂等，底层走 ingest.graph_ops）。"""
    created_total = deleted_total = 0
    errors: List[str] = []

    for decision in decisions:
        try:
            # era 作用域：优先找同时代的节点，找不到再回退到任意时代（跨书共享身份）
            rows = session.run(
                "MATCH (a) WHERE a.name = $alias AND $label IN labels(a) "
                "RETURN elementId(a) AS eid, a.era AS era",
                {"alias": decision.alias_name, "label": decision.label}).data()
            if not rows:
                continue
            if decision.era:
                scoped = [r for r in rows if r["era"] == decision.era]
                if scoped:
                    rows = scoped
            if dry_run:
                print(f"  [dry-run] 将归并: {decision.alias_name} -> "
                      f"{decision.canonical_name} ({decision.label}, {decision.source})")
                continue
            stats = graph_ops.merge_into(
                session, decision.canonical_name, decision.label,
                [{"eid": r["eid"], "name": decision.alias_name} for r in rows],
                era=decision.era, dry_run=False)
            created_total += stats["created_edges"]
            deleted_total += stats["merged"]
            if stats["errors"]:
                errors.append(f"{decision.alias_name}: 未知关系类型，已跳过迁移")
            else:
                print(f"  [ok] {decision.alias_name} -> {decision.canonical_name} "
                      f"({decision.label}, {decision.source})")
        except Exception as exc:  # 单条失败不影响整批
            errors.append(f"{decision.alias_name}->{decision.canonical_name}: {exc}")
            print(f"  [err] {decision.alias_name} -> {decision.canonical_name}: {exc}")

    return created_total, deleted_total, errors


def apply_descendants(session, candidates: List[DescendantCandidate],
                      dry_run: bool) -> Tuple[int, int, List[Dict]]:
    """落库 DESCENDANT_OF：只连接**已存在的人物节点**，带证据与 confidence。"""
    created = skipped = 0
    pending: List[Dict] = []
    for candidate in candidates:
        if not candidate.valid:
            pending.append({"ancestor": candidate.ancestor,
                            "descendant": candidate.descendant,
                            "reason": candidate.reason})
            continue
        exists = session.run(
            "MATCH (a:人物 {name: $a}) MATCH (d:人物 {name: $d}) "
            "RETURN count(*) AS n",
            {"a": candidate.ancestor, "d": candidate.descendant}).single()["n"]
        if not exists:
            pending.append({"ancestor": candidate.ancestor,
                            "descendant": candidate.descendant,
                            "reason": "图谱中找不到两端人物节点"})
            continue
        if dry_run:
            created += 1
            print(f"  [dry-run] 将建 DESCENDANT_OF: {candidate.ancestor} -> "
                  f"{candidate.descendant} ({candidate.kind})")
            continue
        record = session.run(
            "MATCH (a:人物 {name: $a}) MATCH (d:人物 {name: $d}) "
            "MERGE (a)-[r:DESCENDANT_OF]->(d) "
            "ON CREATE SET r.kind = $kind, r.confidence = 'inferred', "
            "              r.source = 'description-scan', "
            "              r.snippets = [$evidence], r.versions = ['descendant-scan-v1'] "
            "RETURN r.confidence AS confidence",
            {"a": candidate.ancestor, "d": candidate.descendant,
             "kind": candidate.kind, "evidence": candidate.evidence}).single()
        created += 1 if record else 0
        skipped += 0 if record else 1
    return created, skipped, pending


# ============================================================
# ⑦ CLI
# ============================================================

def main() -> int:
    parser = argparse.ArgumentParser(description="实体对齐系统（规则 + 词典 + 相似度 + 血缘）")
    parser.add_argument("--dry-run", action="store_true", help="只报告，不改库")
    parser.add_argument("--apply", action="store_true", help="真正改库（默认 dry-run）")
    parser.add_argument("--candidates-only", action="store_true", help="只导 CSV")
    parser.add_argument("--labels", type=str, default="人物", help="逗号分隔的 label")
    parser.add_argument("--threshold", type=float, default=0.85, help="相似度阈值")
    parser.add_argument("--dict", type=str, default=None, help="别名词典路径")
    parser.add_argument("--candidates-csv", type=str, default=None, help="候选 CSV 输出")
    parser.add_argument("--descendants-only", action="store_true", help="只跑 DESCENDANT_OF")
    parser.add_argument("--include-similarity", action="store_true",
                        help="apply 时也包含相似度层（默认只导 CSV 供人工审核）")
    parser.add_argument("--report", type=str, default=None, help="报告输出路径（md）")
    args = parser.parse_args()

    label_filter = {s.strip() for s in args.labels.split(",") if s.strip()}
    csv_path = Path(args.candidates_csv) if args.candidates_csv else DEFAULT_CANDIDATES_PATH
    dict_path = Path(args.dict) if args.dict else DEFAULT_DICT_PATH
    apply = args.apply and not args.dry_run

    pipeline = AlignmentPipeline(dictionary=AliasDictionary.load(dict_path),
                                 threshold=args.threshold, dict_path=dict_path)
    for conflict in pipeline.dictionary.conflicts():
        print(f"[warn] 词典冲突：{conflict}")

    with _driver().session() as session:
        entities = fetch_all_entities(session, label_filter=label_filter)
        print(f"[align] 从 Neo4j 读到 {len(entities)} 个实体（label 过滤: {label_filter}）")

        if args.descendants_only:
            all_entities = fetch_all_entities(session)
            candidates = pipeline.discover_descendants(all_entities)
            valid = [c for c in candidates if c.valid]
            print(f"[descendant] 候选 {len(candidates)} 条，可落库 {len(valid)} 条")
            if not apply:
                for candidate in valid[:20]:
                    print(f"  [dry-run] {candidate.ancestor} -> {candidate.descendant} "
                          f"({candidate.kind})")
            else:
                created, skipped, pending = apply_descendants(session, candidates, dry_run=False)
                print(f"[descendant] 创建 {created}，跳过 {skipped}，待确认 {len(pending)}")
            return 0

        decisions = pipeline.discover_alignments(entities, label_filter=label_filter)
        print(f"[align] 发现 {len(decisions)} 条归并决策")
        by_source: Dict[str, int] = {}
        for decision in decisions:
            by_source[decision.source] = by_source.get(decision.source, 0) + 1
        for source, count in by_source.items():
            print(f"  - {source}: {count}")

        metadata_lookup: Dict[Tuple[str, str], Dict] = {}
        for entity in entities:
            metadata_lookup[(entity["name"], "")] = {
                "label": entity.get("label", ""), "era": entity.get("era", "") or "",
                "degree": entity.get("degree", 0)}
        pipeline.similarity.write_candidates_csv(pipeline._similarity_candidates,
                                                 csv_path, metadata_lookup)
        print(f"[align] 相似度候选 {len(pipeline._similarity_candidates)} 条已写入 "
              f"{csv_path}（仅作审核，不自动落库）")

        if args.candidates_only:
            return 0

        if apply:
            to_apply = decisions
            if not args.include_similarity:
                to_apply = [d for d in decisions if d.source != "相似度"]
            created, deleted, errors = apply_alignments(session, to_apply, dry_run=False)
            print(f"[align] 创建边 {created}，归并节点 {deleted}，错误 {len(errors)}")
            all_entities = fetch_all_entities(session)
            candidates = pipeline.discover_descendants(all_entities)
            created_d, skipped_d, pending = apply_descendants(session, candidates, dry_run=False)
            print(f"[descendant] 创建 {created_d}，跳过 {skipped_d}，待确认 {len(pending)}")
        else:
            print("[align] dry-run 模式：未改动数据库")
            for decision in decisions[:20]:
                print(f"  [dry-run] {decision.alias_name} -> {decision.canonical_name} "
                      f"({decision.label}, {decision.source})")
            if len(decisions) > 20:
                print(f"  ... 共 {len(decisions)} 条（仅显示前 20）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
