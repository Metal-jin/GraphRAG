"""语料切块（任务 01 / 02 / 30）。

设计要点：
1. 先按章节标题切章，章节内再切块——**绝不跨章节混合正文**；
2. 切块优先落在句子/段落边界（。！？；换行），比固定字符滑窗更不容易切断关系；
3. 每个块记录**字符区间 [offset, end)**，重叠按字符起止位置维护，
   因此“去掉重叠后能按偏移还原原文”，也不会出现尾部重复拼接；
4. 参数强校验：size > 0、0 <= overlap < size，函数与 CLI 用同一套校验；
5. chunk 身份带数据版本：book::chunker-v2::序号，内容哈希单独记录，
   便于区分“逻辑 ID”和“内容指纹”（任务 02）；
6. 每本书输出 manifest（原文指纹 + 切块算法/参数 + 块数），供 build_kg 版本校验。

注意：文中所有长度都是**字符数**，不是模型 token 数。

chunk 结构：
    {
        "chunk_id": "射雕英雄传::chunker-v2::0",   # 含数据版本，跨书唯一
        "logical_id": "射雕英雄传::0",             # 不带版本，便于人读
        "book": "射雕英雄传",
        "era": "射雕",
        "chapter": "第一章 风雪惊变",
        "offset": 0, "end": 1500,                  # 章节内字符区间
        "content_hash": "…",                       # 正文 sha256 前 16 位
        "text": "……"
    }

用法：
    python corpus.py                                   # 处理 data/source/ 下所有 txt
    python corpus.py --source data/source/神雕侠侣.txt   # 只处理一本
    python corpus.py --size 1200 --overlap 150         # 覆盖默认 1500/200
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

# 自举 sys.path：允许 `python src/ingest/corpus.py` 直接运行（不依赖 PYTHONPATH）
_SRC_DIR = Path(__file__).resolve().parents[1]
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from core.ontology import infer_era  # noqa: E402  单一本体：书名 -> 时代

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_DIR = PROJECT_ROOT / "data" / "source"
DEFAULT_OUT_DIR = PROJECT_ROOT / "data" / "interim"
DEFAULT_INTERIM = DEFAULT_OUT_DIR  # 兼容旧名（build_kg 等模块使用）
DEFAULT_OUT_PATH = DEFAULT_OUT_DIR / "chunks.json"  # 阶段一遗留（射雕），保持兼容

# ---------- 可调参数 ----------
CHUNK_SIZE = 1500   # 每块目标字符数（较大方案）
OVERLAP = 200       # 块间重叠字符数
CHUNKER_VERSION = "chunker-v2"
# ------------------------------

# 匹配 "第一章" "第12回" 这类章节标题
CHAPTER_PATTERN = re.compile(
    r"^(第[零一二三四五六七八九十百千两\d]+[章回卷节].*)$",
    re.MULTILINE,
)

# 句末标点（用作切块优先边界）
SENTENCE_END = re.compile(r"[。！？!?；;…\n]+")


@dataclass(frozen=True)
class ChunkParams:
    """切块参数。所有长度单位都是字符。"""

    size: int = CHUNK_SIZE
    overlap: int = OVERLAP
    version: str = CHUNKER_VERSION

    def validate(self) -> "ChunkParams":
        if self.size <= 0:
            raise ValueError(f"size 必须大于 0（当前 {self.size}）")
        if self.overlap < 0:
            raise ValueError(f"overlap 不能为负数（当前 {self.overlap}）")
        if self.overlap >= self.size:
            raise ValueError(
                f"overlap({self.overlap}) 必须小于 size({self.size})，否则滑窗不会前进")
        return self

    @property
    def id_prefix(self) -> str:
        return self.version

    def to_dict(self) -> Dict[str, object]:
        return {"size": self.size, "overlap": self.overlap, "version": self.version}


def validate_params(size: int, overlap: int) -> ChunkParams:
    """CLI 与函数共用的参数校验。"""
    return ChunkParams(size=int(size), overlap=int(overlap)).validate()


# ============ 文本读取 / 章节切分 ============

def load_text(path: Path) -> str:
    """读取 txt 文件，统一转成 UTF-8 文本（UTF-8 优先，其次 GB18030）。"""
    raw = Path(path).read_bytes()
    for enc in ("utf-8", "gb18030"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError(f"无法识别文件编码：{path}")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.strip() for ln in text.split("\n")]
    return "\n".join(lines).strip()


def split_chapters(text: str) -> List[Dict[str, str]]:
    """按章节标题切分，返回 [{"chapter": 标题, "text": 正文}]。"""
    matches = list(CHAPTER_PATTERN.finditer(text))
    chapters: List[Dict[str, str]] = []
    if not matches:
        return [{"chapter": "全文", "text": text}]
    if matches[0].start() > 0:
        head = text[: matches[0].start()].strip()
        if head:
            chapters.append({"chapter": "开篇", "text": head})
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            chapters.append({"chapter": m.group(1).strip(), "text": body})
    return chapters


# ============ 切块算法 ============

def _sentence_ends(text: str) -> List[int]:
    """返回所有句末位置（字符下标，右开区间）以及文本末尾。"""
    ends = [m.end() for m in SENTENCE_END.finditer(text)]
    if not ends or ends[-1] != len(text):
        ends.append(len(text))
    return ends


def chunk_offsets(text: str, size: int = CHUNK_SIZE,
                  overlap: int = OVERLAP) -> List[Tuple[int, int]]:
    """把一个章节切成字符区间列表 [(start, end), ...]。

    保证：
    - 区间覆盖整章、顺序不颠倒、不丢字；
    - 相邻区间重叠 >= overlap（最后一块可能不足，会被并入前一块）；
    - 优先在句末位置断开；遇到没有标点的长段落退回固定滑窗。
    """
    params = ChunkParams(size=size, overlap=overlap).validate()
    n = len(text)
    if n == 0:
        return []
    if n <= params.size:
        return [(0, n)]

    ends = _sentence_ends(text)
    spans: List[Tuple[int, int]] = []
    start = 0
    while start < n:
        target = start + params.size
        candidates = [e for e in ends if start < e <= target]
        if candidates:
            end = candidates[-1]
        else:
            end = min(target, n)
        # 句子边界过近会导致碎块，退回固定长度
        if end - start < max(1, params.size // 3) and end < n:
            end = min(target, n)
        end = max(end, min(n, start + 1))
        spans.append((start, end))
        if end >= n:
            break
        next_start = end - params.overlap
        # 回退到句末边界，避免把一句话切成两半（只会让重叠更长）
        snap = [e for e in ends if start < e <= next_start]
        if snap:
            next_start = snap[-1]
        if next_start <= start:
            next_start = start + 1
        start = next_start

    # 尾部碎块并入前一块（直接延长前一块的 end，不重复拼接正文）
    if len(spans) >= 2 and (spans[-1][1] - spans[-1][0]) < params.overlap:
        last_start, last_end = spans.pop()
        prev_start, _ = spans[-1]
        spans[-1] = (prev_start, last_end)
    return spans


def sliding_chunks(text: str, size: int = CHUNK_SIZE,
                   overlap: int = OVERLAP) -> List[str]:
    """兼容旧接口：返回切好的文本块列表。"""
    return [text[s:e] for s, e in chunk_offsets(text, size, overlap)]


# ============ 构建 ============

def content_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


def file_fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def manifest_path(book: str, out_dir: Optional[Path] = None) -> Path:
    return Path(out_dir or DEFAULT_OUT_DIR) / f"manifest_{book}.json"


def load_manifest(book: str, out_dir: Optional[Path] = None) -> Optional[Dict]:
    path = manifest_path(book, out_dir)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def build_chunks(source_path: Path, out_path: Optional[Path] = None,
                 size: int = CHUNK_SIZE, overlap: int = OVERLAP,
                 *, write_manifest_file: bool = True) -> List[Dict]:
    """主流程：txt -> 章节 -> 句子友好滑窗 -> chunks_<书名>.json + manifest。"""
    params = validate_params(size, overlap)
    source_path = Path(source_path)
    book = source_path.stem
    era = infer_era(book)
    if era is None:
        raise ValueError(
            f"无法从书名推断 era：{book}（只支持 "
            f"{'/'.join(sorted({b for b in ['射雕英雄传','神雕侠侣','倚天屠龙记']}))}，"
            f"请检查文件名，或扩充 core.ontology.BOOK_TO_ERA）")

    if out_path is None:
        out_path = DEFAULT_OUT_DIR / f"chunks_{book}.json"

    text = load_text(source_path)
    chapters = split_chapters(text)

    all_chunks: List[Dict] = []
    index = 0
    for chapter in chapters:
        body = chapter["text"]
        for start, end in chunk_offsets(body, params.size, params.overlap):
            piece = body[start:end]
            if not piece.strip():
                continue
            all_chunks.append({
                "chunk_id": f"{book}::{params.id_prefix}::{index}",
                "logical_id": f"{book}::{index}",
                "book": book,
                "era": era,
                "chapter": chapter["chapter"],
                "offset": start,
                "end": end,
                "content_hash": content_hash(piece),
                "text": piece,
            })
            index += 1

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(all_chunks, ensure_ascii=False, indent=1),
                        encoding="utf-8")

    if write_manifest_file:
        write_manifest(book, source_path, params, all_chunks, out_path,
                       out_dir=out_path.parent)
    return all_chunks


def write_manifest(book: str, source_path: Path, params: ChunkParams,
                   chunks: Sequence[Dict], chunks_path: Path,
                   *, out_dir: Optional[Path] = None,
                   extraction: Optional[Dict] = None,
                   embedding: Optional[Dict] = None) -> Dict:
    """写数据集 manifest（任务 02：切块/图谱/向量索引/checkpoint 版本一致）。"""
    manifest = {
        "book": book,
        "era": chunks[0]["era"] if chunks else infer_era(book),
        "dataset_version": params.version,
        "chunker": params.to_dict(),
        "source": {
            "file": Path(source_path).name,
            "sha256": file_fingerprint(Path(source_path)) if Path(source_path).exists() else "",
        },
        "chunks_file": Path(chunks_path).name,
        "chunk_count": len(chunks),
        "total_chars": sum(len(c["text"]) for c in chunks),
        "char_unit": "unicode-code-point（字符，不是 token）",
        "extraction": extraction or {},
        "embedding": embedding or {},
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
    }
    path = manifest_path(book, out_dir)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return manifest


def update_manifest(book: str, *, out_dir: Optional[Path] = None,
                    **sections: Dict) -> Optional[Dict]:
    """更新 manifest 的若干段落（如 extraction / embedding 指纹）。"""
    manifest = load_manifest(book, out_dir)
    if manifest is None:
        return None
    for key, value in sections.items():
        if isinstance(value, dict):
            manifest.setdefault(key, {}).update(value)
        else:
            manifest[key] = value
    manifest_path(book, out_dir).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return manifest


# ============ CLI ============

def main() -> None:
    parser = argparse.ArgumentParser(description="金庸小说语料切块（多书、句子友好、版本化）")
    parser.add_argument("--source", type=str, default=None,
                        help="单个 txt 文件路径；不填则处理 data/source/ 下所有 txt")
    parser.add_argument("--out", type=str, default=None,
                        help="输出路径；默认 data/interim/chunks_<书名>.json")
    parser.add_argument("--size", type=int, default=CHUNK_SIZE,
                        help="每块目标字符数（默认：%(default)s）")
    parser.add_argument("--overlap", type=int, default=OVERLAP,
                        help="块间重叠字符数（默认：%(default)s）")
    args = parser.parse_args()

    try:
        validate_params(args.size, args.overlap)
    except ValueError as exc:
        raise SystemExit(f"参数非法：{exc}")

    if args.source:
        sources = [Path(args.source)]
    else:
        sources = sorted(DEFAULT_SOURCE_DIR.glob("*.txt"))
        if not sources:
            raise SystemExit(f"目录里没有 txt：{DEFAULT_SOURCE_DIR}，请用 --source 指定")

    if args.out and len(sources) > 1:
        raise SystemExit("--out 只在处理单本书（--source）时可用；多书模式每本书自动输出独立文件")

    for src in sources:
        chunks = build_chunks(src, Path(args.out) if args.out else None,
                              args.size, args.overlap)
        out_file = Path(args.out) if args.out else DEFAULT_OUT_DIR / f"chunks_{src.stem}.json"
        total_chars = sum(len(c["text"]) for c in chunks)
        print(f"[corpus] {src.name} -> {len(chunks)} 块（{CHUNKER_VERSION}，"
              f"{args.size}/{args.overlap} 字符），共 {total_chars} 字符，"
              f"era = {chunks[0]['era'] if chunks else '?'}，已写入 {out_file}")
        print(f"[corpus] manifest: {manifest_path(src.stem)}")


if __name__ == "__main__":
    main()
