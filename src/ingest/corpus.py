"""
ingest/corpus.py
语料切块：把金庸小说整本 txt 切成适合 LLM 抽取的文本块。

设计要点：
1. 先按"第X章"切成章节，保留章节信息（后续排查抽取问题用）。
2. 章节内再按固定长度滑窗切块，块间少量重叠（overlap），
   保证跨块的句子/关系不被切断。
3. 输出统一的 chunks.json，供 build_kg.py 消费。

chunk 结构（与 C、D 约定的格式）：
    {
        "chunk_id": 0,                # 全局唯一编号
        "chapter": "第一章 风雪惊变",  # 所属章节标题
        "text": "……"                  # 文本内容
    }

用法：
    python corpus.py                          # 默认处理 data/source/ 下所有 txt
    python corpus.py --source 路径 --out 路径  # 指定输入输出
"""
import argparse
import json
import re
from pathlib import Path
from typing import Dict, List

# 项目根目录（src/ingest/ 的上两级）
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_DIR = PROJECT_ROOT / "data" / "source"
DEFAULT_OUT_PATH = PROJECT_ROOT / "data" / "interim" / "chunks.json"

# ---------- 可调参数 ----------
CHUNK_SIZE = 600   # 每块目标字数（几百字，指引要求）
OVERLAP = 80       # 块间重叠字数
# ------------------------------

# 匹配 "第一章" "第12回" 这类章节标题（书里两种写法都可能出现）
CHAPTER_PATTERN = re.compile(
    r"^(第[零一二三四五六七八九十百千两\d]+[章回卷节].*)$",
    re.MULTILINE,
)


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


def build_chunks(source_path: Path, out_path: Path = DEFAULT_OUT_PATH, 
                 size: int = CHUNK_SIZE, overlap: int = OVERLAP) -> List[Dict]: # 该函数输入相关路径，输出 chunk 列表
    """
    主流程：txt → 章节切分 → 滑窗切块 → 写 chunks.json。
    
    调用相应函数，完成切块任务。
    自己给每一小块编号、贴标签（属于哪一章）。
    
    最后把全部结果保存成 JSON 文件，顺便还返回一份给调用它的代码

    返回 chunk 列表（同时也落盘，供 build_kg.py 和 data_loader.py 使用）。
    """
    text = load_text(source_path)
    chapters = split_chapters(text)

    all_chunks: List[Dict] = []
    for ch in chapters:
        for piece in sliding_chunks(ch["text"], size, overlap):
            if not piece.strip():
                continue
            all_chunks.append({
                "chunk_id": len(all_chunks),
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
    parser = argparse.ArgumentParser(description="金庸小说语料切块")
    parser.add_argument("--source", type=str, default=None,
                        help="单个 txt 文件路径；不填则处理 data/source/ 下所有 txt")
    parser.add_argument("--out", type=str, default=str(DEFAULT_OUT_PATH),
                        help="输出 chunks.json 路径")
    parser.add_argument("--size", type=int, default=CHUNK_SIZE, help="每块字数")
    parser.add_argument("--overlap", type=int, default=OVERLAP, help="块间重叠字数")
    args = parser.parse_args()

    if args.source:  # 如果指定了单个 txt 文件路径，就只处理这个文件，否则处理 data/source/ 下所有 txt
        sources = [Path(args.source)]
    else:
        sources = sorted(DEFAULT_SOURCE_DIR.glob("*.txt"))
        if not sources:
            raise SystemExit(f"目录里没有 txt：{DEFAULT_SOURCE_DIR}，请用 --source 指定")

    for src in sources:  # 遍历所有 txt 文件，开始切块操作
        chunks = build_chunks(src, Path(args.out), args.size, args.overlap)
        total_chars = sum(len(c["text"]) for c in chunks)
        print(f"[corpus] {src.name} -> {len(chunks)} 块，共 {total_chars} 字，"
              f"已写入 {args.out}")


if __name__ == "__main__":  # 如果直接运行这个文件，就调用 main 函数
    main()
