"""
ingest/corpus.py
语料切块：把金庸小说整本 txt 切成适合 LLM 抽取的文本块。

设计要点：
1. 先按"第X章"切成章节，保留章节信息（后续排查抽取问题用）。
2. 章节内再按固定长度滑窗切块，块间少量重叠（overlap），
   保证跨块的句子/关系不被切断。
3. 阶段二多书支持：每本书一个输出文件 chunks_<书名>.json，
   每块带 book / era 元信息，chunk_id 带书名前缀（跨书唯一，
   避免不同书的 Chunk 节点在 Neo4j 里 MERGE 到一起）。

chunk 结构（与 C、D 约定的格式）：
    {
        "chunk_id": "神雕侠侣::0",       # 书名前缀 + 章内编号（跨书唯一）
        "book": "神雕侠侣",              # 所属书名（= 源文件名去 .txt）
        "era": "神雕",                   # 时代（射雕/神雕/倚天，由书名推断）
        "chapter": "第一章 风月无情",     # 所属章节标题
        "text": "……"                     # 文本内容
    }

用法：
    python corpus.py                            # 处理 data/source/ 下所有 txt（每书一个输出）
    python corpus.py --source data/source/神雕侠侣.txt   # 只处理一本书
    python corpus.py --source 路径 --out 路径    # 指定输出（单书时）
"""
import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Optional

# 项目根目录（src/ingest/ 的上两级）
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_DIR = PROJECT_ROOT / "data" / "source"
DEFAULT_OUT_DIR = PROJECT_ROOT / "data" / "interim"
DEFAULT_OUT_PATH = DEFAULT_OUT_DIR / "chunks.json"  # 阶段一遗留（射雕），保持兼容

# ---------- 可调参数 ----------
CHUNK_SIZE = 600   # 每块目标字数（几百字，指引要求）
OVERLAP = 80       # 块间重叠字数
# ------------------------------

# 匹配 "第一章" "第12回" 这类章节标题（书里两种写法都可能出现）
CHAPTER_PATTERN = re.compile(
    r"^(第[零一二三四五六七八九十百千两\d]+[章回卷节].*)$",
    re.MULTILINE,
)


def infer_era(book: str) -> Optional[str]:
    """从书名推断 era（射雕/神雕/倚天）。

    阶段二的三本书按文件名关键词匹配；识别不了返回 None
    （调用方应报错，避免 era 标错造成跨书污染）。
    """
    for key, era in (("射雕", "射雕"), ("神雕", "神雕"), ("倚天", "倚天")):
        if key in book:
            return era
    return None


def load_text(path: Path) -> str:     # 该函数输入相关路径，输出文本内容字符串
    """读取 txt 文件，统一转成 UTF-8 文本。

    优先 UTF-8，失败则尝试 GBK（老牌 txt 常见编码），都失败直接报错。
    """
    raw = Path(path).read_bytes()    # 打开指定的 .txt 文件，把里面的内容全部读出来
    for enc in ("utf-8", "gb18030"):  # 优先尝试 UTF-8 编码，如果不行再尝试 GBK 编码
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError(f"无法识别文件编码：{path}")
    # 统一换行符、去掉行首尾空白
    text = text.replace("\r\n", "\n").replace("\r", "\n") # 把所有乱七八糟的换行符号，全部统一成标准的 \n
    lines = [ln.strip() for ln in text.split("\n")]  # 以每行为单位，去掉每行首尾的空格
    return "\n".join(lines).strip()  # 把所有行重新组合起来，去掉首尾的空格


def split_chapters(text: str) -> List[Dict[str, str]]:  # 该函数输入文本内容字符串，输出标题与正文的列表
    """把整本书按章节切开。
    返回 [{"chapter": 标题, "text": 正文}]。
    如果一本书一个章节标题都匹配不到，就把整本书当作一章处理（兜底）。
    """
    matches = list(CHAPTER_PATTERN.finditer(text))  # 找到所有匹配的章节标题
    chapters: List[Dict[str, str]] = []

    if not matches: # 如果没有匹配的章节标题，就把整本书当作一章处理
        return [{"chapter": "全文", "text": text}]

    # 章节标题之前如果有内容（比如书名页、楔子），单独作为一章
    if matches[0].start() > 0:
        head = text[: matches[0].start()].strip()
        if head:
            chapters.append({"chapter": "开篇", "text": head})

    for i, m in enumerate(matches):  # 遍历所有匹配的章节标题以切出每个章节
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)  # 如果是最后一章，就到文本末尾
        body = text[start:end].strip()
        if body:  # 跳过空章节
            chapters.append({"chapter": m.group(1).strip(), "text": body})
    return chapters


def sliding_chunks(text: str, size: int = CHUNK_SIZE, overlap: int = OVERLAP) -> List[str]:
    """
    滑窗切块：每块 size 字，块间重叠 overlap 字。

    最后一块太短（< overlap）时并入前一块，避免产生碎块。
    """
    if len(text) <= size:  # 如果文本长度小于等于块大小，就直接返回一个块
        return [text]

    chunks: List[str] = []
    step = size - overlap  # 每次前进的步长，等于块大小减去重叠字数
    start = 0
    while start < len(text):
        piece = text[start:start + size]
        chunks.append(piece)
        if start + size >= len(text):
            break
        start += step

    # 合并尾部碎块：如果最后一块太短，就并入前一块
    if len(chunks) >= 2 and len(chunks[-1]) < overlap:
        chunks[-2] = chunks[-2] + chunks[-1]
        chunks.pop()
    return chunks


def build_chunks(source_path: Path, out_path: Optional[Path] = None,
                 size: int = CHUNK_SIZE, overlap: int = OVERLAP) -> List[Dict]:
    """
    主流程：txt → 章节切分 → 滑窗切块 → 写 chunks_<书名>.json。

    调用相应函数，完成切块任务。
    自己给每一小块编号（书名前缀，跨书唯一）、贴标签（属于哪本书/哪一章/哪个 era）。

    最后把全部结果保存成 JSON 文件，顺便还返回一份给调用它的代码。
    out_path 不填时默认写到 data/interim/chunks_<书名>.json。

    返回 chunk 列表（同时也落盘，供 build_kg.py 和 data_loader.py 使用）。
    """
    source_path = Path(source_path)
    book = source_path.stem  # 书名 = 文件名去掉 .txt
    era = infer_era(book)
    if era is None:
        raise ValueError(
            f"无法从书名推断 era：{book}（当前只支持 射雕/神雕/倚天 三书，"
            f"请检查文件名，或扩充 infer_era 的映射）"
        )

    if out_path is None:
        out_path = DEFAULT_OUT_DIR / f"chunks_{book}.json"

    text = load_text(source_path)
    chapters = split_chapters(text)

    all_chunks: List[Dict] = []
    for ch in chapters:
        for piece in sliding_chunks(ch["text"], size, overlap):
            if not piece.strip():
                continue
            all_chunks.append({
                "chunk_id": f"{book}::{len(all_chunks)}",  # 书名前缀，跨书唯一
                "book": book,
                "era": era,
                "chapter": ch["chapter"],
                "text": piece,
            })

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(all_chunks, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    return all_chunks


def main():  # 主函数，用于命令行调用，规定命令行输入输出规范
    parser = argparse.ArgumentParser(description="金庸小说语料切块（多书）")
    parser.add_argument("--source", type=str, default=None,
                        help="单个 txt 文件路径；不填则处理 data/source/ 下所有 txt")
    parser.add_argument("--out", type=str, default=None,
                        help="输出路径；默认 data/interim/chunks_<书名>.json")
    parser.add_argument("--size", type=int, default=CHUNK_SIZE, help="每块字数")
    parser.add_argument("--overlap", type=int, default=OVERLAP, help="块间重叠字数")
    args = parser.parse_args()

    if args.source:  # 如果指定了单个 txt 文件路径，就只处理这个文件，否则处理 data/source/ 下所有 txt
        sources = [Path(args.source)]
    else:
        sources = sorted(DEFAULT_SOURCE_DIR.glob("*.txt"))
        if not sources:
            raise SystemExit(f"目录里没有 txt：{DEFAULT_SOURCE_DIR}，请用 --source 指定")

    if args.out and len(sources) > 1:
        raise SystemExit("--out 只在处理单本书（--source）时可用；多书模式每本书自动输出独立文件")

    for src in sources:  # 遍历所有 txt 文件，开始切块操作
        chunks = build_chunks(src, Path(args.out) if args.out else None,
                              args.size, args.overlap)
        out_file = Path(args.out) if args.out else DEFAULT_OUT_DIR / f"chunks_{src.stem}.json"
        total_chars = sum(len(c["text"]) for c in chunks)
        print(f"[corpus] {src.name} -> {len(chunks)} 块，共 {total_chars} 字，"
              f"era = {chunks[0]['era'] if chunks else '?'}，已写入 {out_file}")


if __name__ == "__main__":  # 如果直接运行这个文件，就调用 main 函数
    main()
