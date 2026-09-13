"""
ingest/entity_alignment.py
阶段二实体对齐系统 —— B 任务核心模块（升级自阶段一 clean_graph.py 的手工 alias 方案）。

三层对齐 + 一层后处理：
  ① RuleNormalizer  规则层：称谓后缀剥离 + 姓氏归一 + 噪声识别
  ② AliasDictionary 词典层：人工/累积的核心别名词典（JSON 落盘）
  ③ SimilarityAligner 相似度层：rapidfuzz + pypinyin 双路打分，dry-run 输出 CSV
  ④ DescendantScanner 后处理：跨书血缘 DESCENDANT_OF 模式扫描
  ↑ AlignmentPipeline 把以上串成一条流水线，跑 Neo4j（幂等 MERGE）。

设计原则：
- 三层各自纯函数 + 单元可测，流水线只负责编排和落库。
- 任何层都能独立 dry-run，绝不直接改库。
- 与 clean_graph.py 共存：阶段一已清洗过的图不被破坏；阶段二新抽取的实体
  走 AlignmentPipeline 走三层归并。
- 所有"副作用"（Neo4j 写、Cypher 字符串拼接）集中在 _neo4j 模块里。

用法：
    python src/ingest/entity_alignment.py --dry-run            # 全流程预览
    python src/ingest/entity_alignment.py --apply               # 真正改库
    python src/ingest/entity_alignment.py --candidates-only    # 只导 CSV 不落库
    python src/ingest/entity_alignment.py --labels 人物          # 只对齐指定 label
    python src/ingest/entity_alignment.py --threshold 0.85      # 相似度阈值
    python src/ingest/entity_alignment.py --descendants-only    # 只跑 DESCENDANT_OF
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

# 自举 PYTHONPATH=src：让脚本能从命令行直接跑（不依赖 pytest / 不依赖 build_kg.ps1）
# 与 src/eval/run_compare.py 的处理一致
_SRC_DIR = Path(__file__).resolve().parents[2] / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from neo4j import GraphDatabase
from rapidfuzz import fuzz
from pypinyin import lazy_pinyin

from core.config import get_env


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DICT_PATH = PROJECT_ROOT / "data" / "processed" / "alias_dict.json"
DEFAULT_CANDIDATES_PATH = PROJECT_ROOT / "data" / "interim" / "alignment_candidates.csv"

# Neo4j 标签白名单（与 build_kg / clean_graph 保持一致）
ENTITY_LABELS: Set[str] = {"人物", "门派", "武功", "地点"}

# 写边时允许的关系类型（含 MENTIONS 溯源边）
ALLOWED_REL_TYPES: Set[str] = {
    "MASTER_OF", "MASTERS", "BELONGS_TO", "LOCATED_IN", "PARENT_OF",
    "SPOUSE_OF", "SWORN_BROTHER_OF", "ENEMY_OF", "FOUNDER_OF",
    "BRANCHED_FROM", "MENTIONS", "DESCENDANT_OF",  # 阶段二新增 DESCENDANT_OF
}

VALID_ERAS: Set[str] = {"射雕", "神雕", "倚天"}

# 噪声节点（指称/动物误抽）—— 阶段一已识别，阶段二继承并允许扩充
NOISE_NAMES: Set[str] = {
    "师父", "大师父", "白雕", "汗血宝马", "小红马",
    "神雕", "大雕", "雕儿",        # 神雕侠侣中的大雕（避免和小说名混淆）
    "某", "某人", "那汉", "那女子",  # 指称代词
}


# ============================================================
# ① 规则层
# ============================================================

class RuleNormalizer:
    """规则层：称谓后缀剥离 + 姓氏归一 + 噪声识别。

    设计目标：纯函数，零外部依赖，方便单测。
    称谓剥离是启发式的，可能误伤（比如"段姑娘"会被剥成"段"），
    所以只作为"候选归并信号"，不强制覆盖原名。
    """

    # 称谓后缀（命中后缀即剥掉，剥掉的剩余部分做归一候选）
    TITLE_SUFFIXES: Tuple[str, ...] = (
        # 只保留「不改变身份/性别」的安全称谓；帮主/夫人/姑娘/王爷等
        # 身份或性别后缀会区分不同的人，剥离会导致误归并（如耶律帮主/耶律夫人都剥成耶律）。
        # 宗教头衔（同人不同称谓，安全）
        "道长", "真人", "大师", "禅师", "师太", "国师",
        # 敬称（不改变身份，安全）
        "大侠", "侠客", "女侠", "侠侣",
        # 辈分/敬称
        "前辈", "老前辈", "老人家",
        # 师徒称谓（编号类误伤由 len<2 过滤）
        "师父", "师傅", "恩师", "师尊",
        # 通用敬称
        "兄台", "阁下", "足下",
    )

    # 姓氏归一（"X氏" 去 "氏"，复姓保留）
    SURNAME_VARIANTS: Dict[str, str] = {
        "诸葛氏": "诸葛",
        "欧阳氏": "欧阳",
        "上官氏": "上官",
        "令狐氏": "令狐",
        "司马氏": "司马",
        "南宫氏": "南宫",
        "慕容氏": "慕容",
    }

    def strip_title(self, name: str) -> str:
        """剥称谓后缀（无匹配返回原名）。

        例："洪帮主" -> "洪"，"段姑娘" -> "段"。
        剥后剩余长度 < 1 的不剥（避免把 "掌门" 剥成空串）。
        """
        for suf in self.TITLE_SUFFIXES:
            if name.endswith(suf) and len(name) > len(suf):
                return name[: -len(suf)]
        return name

    def normalize_surname(self, name: str) -> str:
        """姓氏归一（"诸葛氏" -> "诸葛"，"诸葛氏道长" -> "诸葛道长"），其他原样返回。"""
        for old, new in self.SURNAME_VARIANTS.items():
            if name.startswith(old):
                return new + name[len(old):]
        return name

    def normalize(self, name: str) -> str:
        """组合调用：先归一姓氏，再剥称谓。"""
        n = self.normalize_surname(name)
        n = self.strip_title(n)
        return n

    @staticmethod
    def is_noise(name: str) -> bool:
        """判断是不是指称/动物类噪声节点。"""
        if name in NOISE_NAMES:
            return True
        # 长度 ≤ 1 的节点视为指称（如 "某"、"那"）
        if len(name) <= 1:
            return True
        # 全是助词/代词
        if name in {"之", "其", "此人", "那人", "此人", "某人"}:
            return True
        return False


# ============================================================
# ② 词典层
# ============================================================

@dataclass
class AliasEntry:
    """单条别名规则。"""

    alias: str                  # 别名（被归并的名字）
    canonical: str              # 正名（归并到谁）
    label: str                  # 实体类型：人物/门派/武功/地点
    applicable_eras: List[str]  # 适用的 era 列表，空列表表示全部 era
    source: str = "人工"         # 人工/规则/相似度
    note: str = ""              # 备注（如"射雕五绝之一"）

    def matches(self, name: str, era: Optional[str], label: Optional[str]) -> bool:
        """判断给定 (名字, era, label) 是否命中本条规则。"""
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
    def from_dict(cls, d: Dict) -> "AliasEntry":
        # 兼容老数据：缺字段时给默认值
        return cls(
            alias=d["alias"],
            canonical=d["canonical"],
            label=d["label"],
            applicable_eras=list(d.get("applicable_eras", [])),
            source=d.get("source", "人工"),
            note=d.get("note", ""),
        )


class AliasDictionary:
    """别名词典层。"""

    def __init__(self, entries: List[AliasEntry] = None, path: Optional[Path] = None):
        self.path = path or DEFAULT_DICT_PATH
        self.entries: List[AliasEntry] = entries or []

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "AliasDictionary":
        """从 JSON 文件加载，文件不存在则返回空词典。"""
        path = path or DEFAULT_DICT_PATH
        if not path.exists():
            return cls(path=path)
        data = json.loads(path.read_text(encoding="utf-8"))
        entries = [AliasEntry.from_dict(d) for d in data]
        return cls(entries=entries, path=path)

    def save(self, path: Optional[Path] = None) -> None:
        """保存到 JSON（pretty + UTF-8）。"""
        path = path or self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = [e.to_dict() for e in self.entries]
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def lookup(self, name: str, era: Optional[str] = None,
               label: Optional[str] = None) -> Optional[AliasEntry]:
        """查 (name, era, label) 命中的别名规则。"""
        for e in self.entries:
            if e.matches(name, era, label):
                return e
        return None

    def add(self, alias: str, canonical: str, label: str,
            applicable_eras: List[str], source: str = "人工", note: str = "") -> None:
        """新增或覆盖一条规则（同 alias+label 则覆盖）。"""
        for i, e in enumerate(self.entries):
            if e.alias == alias and e.label == label:
                self.entries[i] = AliasEntry(alias, canonical, label,
                                             list(applicable_eras), source, note)
                return
        self.entries.append(AliasEntry(alias, canonical, label,
                                       list(applicable_eras), source, note))


# ============================================================
# ③ 相似度层
# ============================================================

class SimilarityAligner:
    """相似度层：rapidfuzz 字符相似 + pypinyin 拼音相似，双路取最大。

    threshold 判定方式：max(char_score, pinyin_score) >= threshold 才视为候选。
    默认阈值 0.85（经验值，误合并率可控）。
    """

    def __init__(self, threshold: float = 0.85):
        if not 0.0 <= threshold <= 1.0:
            raise ValueError(f"threshold 必须在 [0,1]，收到 {threshold}")
        self.threshold = threshold

    @staticmethod
    def _to_pinyin(s: str) -> str:
        """中文串 -> 拼音串（无声调，空格分隔）。"""
        return " ".join(lazy_pinyin(s))

    def char_score(self, a: str, b: str) -> float:
        """字符级相似度（[0,1]），基于 rapidfuzz 的 ratio + partial_ratio 取最大。

        partial_ratio 能识别子串关系（如"洪七公"被"洪七公前辈"完全包含），
        适合"短正名+长称谓"模式。
        """
        if a == b:
            return 1.0
        r1 = fuzz.ratio(a, b) / 100.0
        r2 = fuzz.partial_ratio(a, b) / 100.0
        return max(r1, r2)

    def pinyin_score(self, a: str, b: str) -> float:
        """拼音级相似度（[0,1]），同 char_score 用 partial_ratio。"""
        pa, pb = self._to_pinyin(a), self._to_pinyin(b)
        if pa == pb:
            return 1.0
        r1 = fuzz.ratio(pa, pb) / 100.0
        r2 = fuzz.partial_ratio(pa, pb) / 100.0
        return max(r1, r2)

    def score(self, a: str, b: str) -> float:
        """综合相似度（[0,1]），取字符/拼音两条路最大。"""
        return max(self.char_score(a, b), self.pinyin_score(a, b))

    def find_candidates(self,
                        entities: List[Tuple[str, Optional[str], Optional[str]]],
                        label_filter: Optional[Set[str]] = None
                        ) -> List[Tuple[str, str, float, str]]:
        """在 [(name, era, label), ...] 列表里找可归并候选。

        返回 [(name1, name2, score, reason), ...]，
        name1 < name2 字典序，方便后续去重。
        仅在同 label 内部配对；跨 label 不配对（防人物/地名混淆）。
        长度差 > 2 跳过（极端长度差基本不可能是别名）。
        """
        # 按 label 分桶
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
                    a, ea = items[i]
                    b, eb = items[j]
                    if abs(len(a) - len(b)) > 2:
                        continue
                    cs = self.char_score(a, b)
                    ps = self.pinyin_score(a, b)
                    s = max(cs, ps)
                    if s < self.threshold:
                        continue
                    # 选择正名：短名优先（启发式：长名更可能是称谓/全称）
                    name1, name2 = sorted([a, b])
                    reason = "char" if cs >= ps else "pinyin"
                    candidates.append((name1, name2, round(s, 4), reason))
        # 按分数倒序
        candidates.sort(key=lambda x: -x[2])
        return candidates

    def write_candidates_csv(self,
                             candidates: List[Tuple[str, str, float, str]],
                             path: Path,
                             metadata_lookup: Optional[Dict[Tuple[str, str], Dict]] = None,
                             ) -> None:
        """导出 dry-run CSV：name1, name2, score, reason, decision, meta...。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        meta_headers: List[str] = []
        meta_lookup = metadata_lookup or {}
        # 探测 meta 列
        for k, m in meta_lookup.items():
            for h in m.keys():
                if h not in meta_headers:
                    meta_headers.append(h)

        headers = ["name1", "name2", "score", "reason", "decision"] + meta_headers
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(headers)
            for n1, n2, sc, rs in candidates:
                row = [n1, n2, sc, rs, ""]
                for h in meta_headers:
                    row.append("")
                # 填 meta（两个名字各查一次，列分别追加）
                # 为简化，每个 meta 列填 name1 的 meta（同名实体同属性）
                m1 = meta_lookup.get((n1, ""), {})
                for idx, h in enumerate(meta_headers):
                    row[5 + idx] = m1.get(h, "")
                w.writerow(row)


# ============================================================
# ④ 跨书血缘（DESCENDANT_OF）后处理
# ============================================================

class DescendantScanner:
    """跨书血缘后处理：从实体的 description 字段扫描"X之后/之女/之子/后人"模式。

    设计：不动抽取 prompt，纯后处理，零 LLM 成本。
    输出候选三元组 (ancestor_name, descendant_name, kind)，
    供人工审核或自动落库（DESCENDANT_OF 关系）。
    """

    # 金庸小说高频姓氏（去除"许/徐/万/严"等冷门姓氏，避免误识）
    _SURNAMES = "王李张刘陈杨赵黄周吴孙朱马胡郭何高林罗郑梁谢宋唐韩冯邓曹彭曾田董袁潘于蒋蔡余杜叶程苏魏吕丁任沈姚卢姜崔钟谭陆汪范金石廖贾夏韦白邹孟熊秦江尹薛段雷侯龙史陶黎贺顾毛郝龚邵钱覃武戴莫孔向汤"
    _SURNAME_RE = f"[{_SURNAMES}]"
    _COMPOUND_RE = "(?:诸葛|欧阳|上官|司马|南宫|令狐|慕容)"
    # 祖先名：大姓/复姓开头 + 1~3 个汉字
    _ANCESTOR_RE = f"(?:{_SURNAME_RE}|{_COMPOUND_RE})[\u4e00-\u9fff]{{1,3}}"

    # 模式：捕获组 1 = 祖先名（已用大姓锚定），捕获组 2 = 血缘指称
    # "与Y/和Y" 是中文里常见的合称表达（"张翠山与殷素素之子"），先尝试
    PATTERNS: List[Tuple[str, str]] = [
        (rf"({_ANCESTOR_RE})之后人?", "之后"),
        (rf"({_ANCESTOR_RE})之女", "之女"),
        # "X与Y之子" / "X和Y之子"：先尝试这条，让 group(1) 优先匹配较前的祖先
        (rf"({_ANCESTOR_RE})(?:与|和|跟)[\u4e00-\u9fff]{{2,3}}之子", "之子"),
        (rf"({_ANCESTOR_RE})之子", "之子"),
        (rf"({_ANCESTOR_RE})之孙", "之孙"),
        (rf"({_ANCESTOR_RE})之孙女", "之孙女"),
        (rf"({_ANCESTOR_RE})的(?:女儿|闺女)", "之女"),
        (rf"({_ANCESTOR_RE})的(?:儿子|孩儿)", "之子"),
    ]

    def scan_entity(self, entity: Dict) -> List[Tuple[str, str, str]]:
        """扫描单个实体的 description，输出候选 (ancestor, descendant, kind) 列表。

        entity 格式：{"name": "...", "description": "..."}
        """
        name = entity.get("name", "")
        desc = entity.get("description") or ""
        if not desc:
            return []

        results: List[Tuple[str, str, str]] = []
        for pattern, kind in self.PATTERNS:
            for m in re.finditer(pattern, desc):
                ancestor = m.group(1)
                # 正则已用大姓锚定，此处无需再过滤
                results.append((ancestor, name, kind))
        # 去重（同一对多次出现）
        return list(set(results))

    def scan_entities(self, entities: List[Dict]) -> List[Tuple[str, str, str]]:
        """批量扫描所有实体。"""
        results: List[Tuple[str, str, str]] = []
        for e in entities:
            results.extend(self.scan_entity(e))
        return results


# ============================================================
# ⑤ 主流水线
# ============================================================

@dataclass
class AlignmentDecision:
    """一条归并决策（待人工或自动落库）。"""

    alias_name: str          # 被归并的名字
    canonical_name: str      # 归并到的正名
    label: str
    era: Optional[str]       # None 表示跨 era
    source: str              # 规则/词典/相似度
    score: str = ""          # 相似度分（仅相似度层有值）
    note: str = ""


@dataclass
class AlignmentReport:
    """落库报告（dry-run 和 apply 都填）。"""

    discovered: List[AlignmentDecision] = field(default_factory=list)
    applied: int = 0
    skipped: int = 0
    errors: List[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [f"发现候选归并 {len(self.discovered)} 条"]
        by_src: Dict[str, int] = {}
        for d in self.discovered:
            by_src[d.source] = by_src.get(d.source, 0) + 1
        for src, cnt in by_src.items():
            lines.append(f"  - {src}: {cnt}")
        lines.append(f"实际执行: 归并 {self.applied}，跳过 {self.skipped}，错误 {len(self.errors)}")
        return "\n".join(lines)


class AlignmentPipeline:
    """三层流水线 + DESCENDANT_OF 后处理。"""

    def __init__(self,
                 dictionary: Optional[AliasDictionary] = None,
                 threshold: float = 0.85,
                 dict_path: Optional[Path] = None):
        self.normalizer = RuleNormalizer()
        self.dictionary = dictionary or AliasDictionary.load(dict_path)
        self.similarity = SimilarityAligner(threshold=threshold)
        self.descendant_scanner = DescendantScanner()

    # ---------- 候选发现（不落库） ----------

    def discover_alignments(self,
                            entities: List[Dict],
                            label_filter: Optional[Set[str]] = None,
                            ) -> List[AlignmentDecision]:
        """三层串联：词典 → 规则 → 相似度，返回所有候选决策。

        entities 元素格式：{"name", "era", "label", "description", "degree"}.
        """
        if label_filter is None:
            label_filter = ENTITY_LABELS

        decisions: List[AlignmentDecision] = []
        seen: Set[Tuple[str, str, str]] = set()  # (alias, canonical, label) 去重

        def _add(d: AlignmentDecision):
            key = (d.alias_name, d.canonical_name, d.label)
            if key in seen:
                return
            seen.add(key)
            decisions.append(d)

        # ① 词典层（最高优先级，命中即归并）
        for e in entities:
            if label_filter and e.get("label") not in label_filter:
                continue
            entry = self.dictionary.lookup(e["name"], e.get("era"), e.get("label"))
            if entry and entry.canonical != e["name"]:
                _add(AlignmentDecision(
                    alias_name=e["name"],
                    canonical_name=entry.canonical,
                    label=e.get("label") or entry.label,
                    era=e.get("era"),
                    source="词典",
                    note=entry.note,
                ))

        # ② 规则层：称谓剥离产生候选归并（和库内已有名字配对）
        # 思路：对每个实体，先做规则归一；如果归一后与别的实体的归一结果相同，
        # 且 label 相同且 era 相近，视为可归并。
        # 关键约束：归一结果长度 ≥ 2（避免"黄"类单字归并），且要求 era 一致。
        norm_groups: Dict[Tuple[str, str, Optional[str]], List[Dict]] = {}  # (norm, label, era) -> entities
        for e in entities:
            if label_filter and e.get("label") not in label_filter:
                continue
            if RuleNormalizer.is_noise(e["name"]):
                continue
            norm = self.normalizer.normalize(e["name"])
            if norm == e["name"] or len(norm) < 2:
                continue  # 没产生新形式 或 归一结果太短（单字易误判）
            key = (norm, e.get("label") or "?", e.get("era"))
            norm_groups.setdefault(key, []).append(e)

        for (norm_name, label, era), group in norm_groups.items():
            if len(group) < 2:
                continue
            # 选最长的作为正名（启发式：完整名比剥后名更准）
            canonical = max(group, key=lambda x: len(x["name"]))["name"]
            for e in group:
                if e["name"] == canonical:
                    continue
                _add(AlignmentDecision(
                    alias_name=e["name"],
                    canonical_name=canonical,
                    label=label,
                    era=era,
                    source="规则",
                    note=f"归一形式={norm_name}",
                ))

        # ③ 相似度层：rapidfuzz + pypinyin 双路
        # 注意：相似度层只用于"发现候选"，不进入 decisions（防止误归并），
        # 候选由 main() 写入 CSV 让人工审核；审核通过后由人工加到 alias_dict.json。
        # 这样设计是因为相似度层在"同姓不同人"case 上有天然缺陷（如郭京/郭靖）。
        ent_index = [(e["name"], e.get("era"), e.get("label"))
                     for e in entities
                     if e.get("label") in label_filter and not RuleNormalizer.is_noise(e["name"])]
        self._similarity_candidates = self.similarity.find_candidates(
            ent_index, label_filter=label_filter)
        # 不把相似度候选加入 decisions；由 main() 显式决定是否落库

        return decisions


def _driver():
    """Neo4j 驱动（与 clean_graph.py 保持一致的配置）。"""
    return GraphDatabase.driver(
        get_env("NEO4J_URL", "bolt://localhost:7687"),
        auth=(get_env("NEO4J_USER", "neo4j"), get_env("NEO4J_PASSWORD", "")),
    )


def fetch_all_entities(session,
                       label_filter: Optional[Set[str]] = None) -> List[Dict]:
    """从 Neo4j 读全部实体（按 label 过滤）。"""
    if label_filter is None:
        label_filter = ENTITY_LABELS
    rows = session.run(
        """
        MATCH (n)
        WHERE any(l IN labels(n) WHERE l IN $labels)
        RETURN elementId(n) AS eid,
               head([l IN labels(n) WHERE l IN $labels]) AS label,
               n.name AS name,
               n.era AS era,
               n.description AS description,
               count { (n)--() } AS degree
        """,
        labels=list(label_filter),
    ).data()
    return rows


def fetch_descendants(session) -> List[Dict]:
    """从 Neo4j 读实体（含 description），专门给 DESCENDANT_OF 扫描用。"""
    return fetch_all_entities(session)


def apply_alignments(session,
                     decisions: List[AlignmentDecision],
                     dry_run: bool) -> Tuple[int, int, List[str]]:
    """把归并决策落到 Neo4j（幂等）。

    复用 clean_graph.py 的 _absorb_props / _migrate_edges 逻辑的简化版：
    - 找 alias 节点和 canonical 节点（如果 canonical 不存在则创建）
    - 把 alias 的关系全迁到 canonical（同名同类关系去重）
    - 删 alias 节点
    - 把 alias 名追加到 canonical.aliases 数组

    返回 (created_edges_count, deleted_nodes_count, errors)。
    """
    from ingest.clean_graph import _absorb_props  # 复用 props 合并函数

    created_total = deleted_total = 0
    errors: List[str] = []

    for d in decisions:
        try:
            if dry_run:
                # dry-run：只统计
                row = session.run(
                    "MATCH (a {name: $alias}) WHERE $label IN labels(a) "
                    "RETURN count(a) AS n",
                    {"alias": d.alias_name, "label": d.label},
                ).single()
                if row and row["n"] > 0:
                    print(f"  [dry-run] 将归并: {d.alias_name} -> {d.canonical_name} ({d.label}, {d.source})")
                continue

            # 真实落库
            # 1. 找 alias 节点
            alias_nodes = session.run(
                "MATCH (a {name: $alias}) WHERE $label IN labels(a) "
                "RETURN elementId(a) AS eid",
                {"alias": d.alias_name, "label": d.label},
            ).data()
            if not alias_nodes:
                continue

            # 2. 确保 canonical 节点存在（不存在则创建）
            canonical_eid = session.run(
                "MATCH (c {name: $canon}) WHERE $label IN labels(c) "
                "RETURN elementId(c) AS eid",
                {"canon": d.canonical_name, "label": d.label},
            ).single()
            if canonical_eid:
                canonical_eid = canonical_eid["eid"]
            else:
                res = session.run(
                    f"CREATE (c:{d.label} {{name: $canon}}) "
                    "RETURN elementId(c) AS eid",
                    {"canon": d.canonical_name},
                ).single()
                canonical_eid = res["eid"]

            # 3. 迁移别名节点的属性 + 关系
            for an in alias_nodes:
                if an["eid"] == canonical_eid:
                    continue
                # 合并标量属性
                _absorb_props(session, canonical_eid, an["eid"], d.alias_name)
                # 迁移关系（用 Cypher 一次性把出/入边复制过去，已存在的跳过）
                moved = session.run(
                    """
                    MATCH (a) WHERE elementId(a) = $a
                    MATCH (c) WHERE elementId(c) = $c
                    OPTIONAL MATCH (a)-[r]->(x) WHERE NOT elementId(x) = $a
                    WITH c, a, collect({dir: 'out', t: type(r), x: elementId(x), p: properties(r)}) AS out_rels
                    OPTIONAL MATCH (x)-[r]->(a) WHERE NOT elementId(x) = $a
                    WITH c, a, out_rels,
                         collect({dir: 'in', t: type(r), x: elementId(x), p: properties(r)}) AS in_rels
                    RETURN out_rels + in_rels AS rels
                    """,
                    {"a": an["eid"], "c": canonical_eid},
                ).single()
                rels = (moved["rels"] if moved else []) or []
                for r in rels:
                    if not r or not r.get("t"):
                        continue
                    if r["t"] not in ALLOWED_REL_TYPES:
                        continue
                    if r["dir"] == "out":
                        # 检查边是否已存在
                        exists = session.run(
                            f"MATCH (c) WHERE elementId(c) = $c "
                            f"MATCH (x) WHERE elementId(x) = $x "
                            f"MATCH (c)-[:`{r['t']}`]->(x) RETURN count(*) AS n",
                            {"c": canonical_eid, "x": r["x"]},
                        ).single()["n"]
                        if exists == 0:
                            session.run(
                                f"MATCH (c) WHERE elementId(c) = $c "
                                f"MATCH (x) WHERE elementId(x) = $x "
                                f"CREATE (c)-[rel:`{r['t']}`]->(x) SET rel += $p",
                                {"c": canonical_eid, "x": r["x"], "p": r["p"] or {}},
                            )
                            created_total += 1
                    else:  # in
                        exists = session.run(
                            f"MATCH (c) WHERE elementId(c) = $c "
                            f"MATCH (x) WHERE elementId(x) = $x "
                            f"MATCH (x)-[:`{r['t']}`]->(c) RETURN count(*) AS n",
                            {"c": canonical_eid, "x": r["x"]},
                        ).single()["n"]
                        if exists == 0:
                            session.run(
                                f"MATCH (c) WHERE elementId(c) = $c "
                                f"MATCH (x) WHERE elementId(x) = $x "
                                f"CREATE (x)-[rel:`{r['t']}`]->(c) SET rel += $p",
                                {"c": canonical_eid, "x": r["x"], "p": r["p"] or {}},
                            )
                            created_total += 1
                # 4. 删除 alias 节点
                session.run(
                    "MATCH (a) WHERE elementId(a) = $a DETACH DELETE a",
                    {"a": an["eid"]},
                )
                deleted_total += 1
                print(f"  [ok] {d.alias_name} -> {d.canonical_name} ({d.label}, {d.source})")
        except Exception as e:
            errors.append(f"{d.alias_name}->{d.canonical_name}: {e}")
            print(f"  [err] {d.alias_name} -> {d.canonical_name}: {e}")

    return created_total, deleted_total, errors


def apply_descendants(session,
                      pairs: List[Tuple[str, str, str]],
                      dry_run: bool) -> Tuple[int, int]:
    """把 DESCENDANT_OF 候选落到 Neo4j（幂等：MERGE）。"""
    created = skipped = 0
    for ancestor, descendant, kind in pairs:
        if dry_run:
            row = session.run(
                "MATCH (a {name: $a})-[r:DESCENDANT_OF]->(d {name: $d}) "
                "RETURN count(r) AS n",
                {"a": ancestor, "d": descendant},
            ).single()
            if row and row["n"] > 0:
                skipped += 1
            else:
                print(f"  [dry-run] 将建 DESCENDANT_OF: {ancestor} -> {descendant} ({kind})")
                created += 1
            continue
        # 真实落库
        # 确保两端节点存在
        for nm in (ancestor, descendant):
            session.run(
                "MERGE (n {name: $nm}) "
                "ON CREATE SET n:DESCENDANT_TEMP",
                {"nm": nm},
            )
            # 删临时标签
            session.run(
                "MATCH (n {name: $nm}) REMOVE n:DESCENDANT_TEMP",
                {"nm": nm},
            )
        # 创建 DESCENDANT_OF 关系（kind 写入 properties）
        result = session.run(
            """
            MATCH (a {name: $a})
            MATCH (d {name: $d})
            MERGE (a)-[r:DESCENDANT_OF]->(d)
            ON CREATE SET r.kind = $kind
            RETURN r.kind AS k
            """,
            {"a": ancestor, "d": descendant, "kind": kind},
        ).single()
        if result and result["k"] == kind:
            created += 1
        else:
            skipped += 1
    return created, skipped


def main():
    parser = argparse.ArgumentParser(description="阶段二实体对齐系统（规则+词典+相似度）")
    parser.add_argument("--dry-run", action="store_true", help="只报告，不改库")
    parser.add_argument("--apply", action="store_true", help="真正改库（默认 dry-run）")
    parser.add_argument("--candidates-only", action="store_true",
                        help="只导 CSV，不执行 apply（最安全）")
    parser.add_argument("--labels", type=str, default="人物",
                        help="逗号分隔的 label 列表，默认只对齐人物（最稳）")
    parser.add_argument("--threshold", type=float, default=0.85,
                        help="相似度阈值（0-1）")
    parser.add_argument("--dict", type=str, default=None, help="别名词典 JSON 路径")
    parser.add_argument("--candidates-csv", type=str, default=None,
                        help="候选 CSV 输出路径")
    parser.add_argument("--descendants-only", action="store_true",
                        help="只跑 DESCENDANT_OF 后处理")
    parser.add_argument("--include-similarity", action="store_true",
                        help="apply 时也包含相似度层归并（默认 dry-run 仅生成候选 CSV）")
    parser.add_argument("--report", type=str, default=None,
                        help="报告输出路径（md）")
    args = parser.parse_args()

    label_filter = {s.strip() for s in args.labels.split(",") if s.strip()}
    csv_path = Path(args.candidates_csv) if args.candidates_csv else DEFAULT_CANDIDATES_PATH
    dict_path = Path(args.dict) if args.dict else DEFAULT_DICT_PATH

    pipeline = AlignmentPipeline(
        dictionary=AliasDictionary.load(dict_path),
        threshold=args.threshold,
        dict_path=dict_path,
    )

    with _driver().session() as session:
        entities = fetch_all_entities(session, label_filter=label_filter)
        print(f"[align] 从 Neo4j 读到 {len(entities)} 个实体（label 过滤: {label_filter}）")

        if args.descendants_only:
            ents = fetch_descendants(session)
            pairs = pipeline.descendant_scanner.scan_entities(ents)
            print(f"[descendant] 扫描到 {len(pairs)} 条 DESCENDANT_OF 候选")
            if args.dry_run or not args.apply:
                for a, d, k in pairs[:20]:
                    print(f"  [dry-run] {a} -> {d} ({k})")
                if len(pairs) > 20:
                    print(f"  ... 共 {len(pairs)} 条（仅显示前 20）")
            else:
                c, s = apply_descendants(session, pairs, dry_run=False)
                print(f"[descendant] 创建 {c}，跳过已存在 {s}")
            return

        decisions = pipeline.discover_alignments(entities, label_filter=label_filter)
        print(f"[align] 发现 {len(decisions)} 条归并决策")
        by_src: Dict[str, int] = {}
        for d in decisions:
            by_src[d.source] = by_src.get(d.source, 0) + 1
        for s, c in by_src.items():
            print(f"  - {s}: {c}")

        # 导 CSV（仅相似度层，进 candidates CSV 等人工审核）
        meta_lookup: Dict[Tuple[str, str], Dict] = {}
        for e in entities:
            meta_lookup[(e["name"], "")] = {
                "label": e.get("label", ""),
                "era": e.get("era", "") or "",
                "degree": e.get("degree", 0),
            }
        sim_candidates = getattr(pipeline, "_similarity_candidates", [])
        pipeline.similarity.write_candidates_csv(sim_candidates, csv_path, meta_lookup)
        print(f"[align] 相似度候选 {len(sim_candidates)} 条已写入 {csv_path}（仅作审核，不自动落库）")

        if args.candidates_only:
            return

        if args.apply and not args.dry_run:
            # 默认只 apply 词典 + 规则层（安全）；相似度层需 --include-similarity 才 apply
            to_apply = decisions
            if not args.include_similarity:
                to_apply = [d for d in decisions if d.source != "相似度"]
                sim_count = len(decisions) - len(to_apply)
                if sim_count > 0:
                    print(f"[align] 相似度层 {sim_count} 条归默认仅生成候选 CSV，"
                          f"如需落库请加 --include-similarity")
            created, deleted, errors = apply_alignments(session, to_apply, dry_run=False)
            print(f"[align] 创建边 {created}，删除别名节点 {deleted}，错误 {len(errors)}")
            # 同时落 DESCENDANT_OF
            ents = fetch_descendants(session)
            pairs = pipeline.descendant_scanner.scan_entities(ents)
            print(f"[descendant] 扫描到 {len(pairs)} 条 DESCENDANT_OF 候选")
            c, s = apply_descendants(session, pairs, dry_run=False)
            print(f"[descendant] 创建 {c}，跳过 {s}")
        else:
            print("[align] dry-run 模式：未改动数据库")
            # 仅预览前 20 条决策
            for d in decisions[:20]:
                print(f"  [dry-run] {d.alias_name} -> {d.canonical_name} "
                      f"({d.label}, {d.source}{', score=' + d.score if d.score else ''})")
            if len(decisions) > 20:
                print(f"  ... 共 {len(decisions)} 条（仅显示前 20）")


if __name__ == "__main__":
    sys.exit(main())