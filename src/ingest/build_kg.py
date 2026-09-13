"""
ingest/build_kg.py
LLM 抽取实体关系 + 写入 Neo4j，构建"门派 → 人物 → 武功"层次知识图谱。

核心设计（对应 docs/ontology.md 和 docs/b_guide.md）：
1. 每个实体带 `era` 时代属性（射雕/神雕/倚天）。阶段一只有《射雕》，
   era 默认填"射雕"，但字段从一开始就支持——阶段二扩书不用改代码。
2. 图谱层次：门派 --BELONGS_TO--> 人物 --MASTERS--> 武功，
   武功传承不单独抽关系，靠"师徒 + 精通"组合由检索阶段推导。
3. 关系类型共 10 种（含新增 BRANCHED_FROM 门派演化）。
4. 同名实体用 MERGE 去重；夫妻/结拜/仇敌是双向关系，写两条边。
5. 文本块存成 Chunk 节点，建向量索引 text_embeddings + 全文索引 text_fulltext，
   并建 MENTIONS 边（chunk 提到了哪些实体，做证据溯源用）。
6. 支持断点续跑（checkpoint 记录已完成的 chunk_id）。

用法：
    python build_kg.py --limit 20          # 先抽 20 块试跑
    python build_kg.py                     # 全量
    python build_kg.py --resume            # 跳过已完成的块
    python build_kg.py --dry-run --limit 5 # 只调 LLM 看抽取结果，不写库
"""
import argparse
import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from openai import OpenAI
from neo4j import GraphDatabase

from core.config import get_env
from ingest.corpus import DEFAULT_OUT_PATH, infer_era

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INTERIM = PROJECT_ROOT / "data" / "interim"
CHECKPOINT_PATH = DEFAULT_INTERIM / "kg_checkpoint.json"  # 阶段一遗留（射雕），保持兼容


def checkpoint_path_for(chunks_path: Path) -> Path:
    """由 chunks 文件路径推出对应的 checkpoint 文件路径（每本书独立断点）。

    chunks_神雕侠侣.json -> kg_checkpoint_神雕侠侣.json
    chunks.json          -> kg_checkpoint.json（阶段一遗留名，保持兼容）
    """
    chunks_path = Path(chunks_path)
    stem = chunks_path.stem
    if stem.startswith("chunks"):
        stem = "kg_checkpoint" + stem[len("chunks"):]
    else:
        stem = stem + "_kg_checkpoint"
    return chunks_path.parent / (stem + ".json")

# ============ 本体定义（与 docs/ontology.md 保持一致） ============

ENTITY_LABELS = {"人物", "门派", "武功", "地点"}  # Neo4j 节点 label 直接用中文

RELATION_TYPES = {
    # 人际关系
    "MASTER_OF",         # 师徒：A 是 B 的师父（有向）
    "SPOUSE_OF",         # 夫妻（双向）
    "PARENT_OF",         # 父母子女（有向）
    "SWORN_BROTHER_OF",  # 结拜（双向）
    "ENEMY_OF",          # 仇敌（双向）
    # 层次关系
    "BELONGS_TO",        # A 属于门派 B（有向）
    "MASTERS",           # A 精通武功 B（有向）
    "FOUNDER_OF",        # A 创立门派 B（有向）
    "LOCATED_IN",        # A 位于地点 B（有向）
    # 演化关系（新增）
    "BRANCHED_FROM",     # B 门派由 A 衍生（有向）
}

BIDIRECTIONAL_RELS = {"SPOUSE_OF", "SWORN_BROTHER_OF", "ENEMY_OF"}

VALID_ERAS = {"射雕", "神雕", "倚天"}

# ============ 抽取 Prompt（b_guide.md 提供的模板，era 必带） ============

EXTRACT_PROMPT = """你是一个知识图谱抽取专家。请从以下金庸小说文本中提取实体和关系。

文本：
{chunk_text}

实体类型（每个实体都要带 era 时代属性，判断不了就留空）：
1. 人物：era（射雕/神雕/倚天）
2. 门派：era、location
3. 武功：type（内功/外功/轻功/暗器）
4. 地点

重要：实体的 name 一律使用「正式名字」，禁止使用称呼、绰号、简称。
- 反面例子（禁止）：七师父、那道士、柯老恩师、丘道长、马真人、七公、七兄、洪老叫化、丹阳子马钰、飞天蝙蝠柯镇恶
- 正面例子：洪七公、马钰、柯镇恶、丘处机、王重阳
- 遇到"七公/北丐/洪帮主"等称呼，请识别为「洪七公」（用正名）

关系类型（方向要正确，严格只用以下 10 种，不要自造其他关系）：
- MASTER_OF（师徒）：A 是 B 的师父，箭头从师父指向徒弟
- SPOUSE_OF（夫妻，双向）
- PARENT_OF（父母子女）：A 是 B 的父母
- SWORN_BROTHER_OF（结拜，双向）
- ENEMY_OF（仇敌，双向）
- BELONGS_TO（所属门派）：A 属于门派 B
- MASTERS（精通武功）：A 精通武功 B
- FOUNDER_OF（创立门派）：A 创立门派 B
- LOCATED_IN（位于地点）：A 位于地点 B
- BRANCHED_FROM（门派演化，可选）

师徒关系（MASTER_OF）的特殊约束，务必遵守：
1. 只在「明确有师徒名分或正式传过武功」时才抽 MASTER_OF。
2. 以下关系都不是师徒，不要抽成 MASTER_OF：
   - 夫妻 → 用 SPOUSE_OF；仇敌/对手 → 用 ENEMY_OF
   - 父母子女 → 用 PARENT_OF；岳父/义父/义兄 → 不抽
   - 同门师兄弟 → 不抽；师祖/太师祖 → 隔代，不要直接抽成 MASTER_OF
3. 一个人最多 3~5 个师父，超过说明抽错了。
4. 禁止循环：A 的师父不能反过来又是 A 的徒弟。

注意：FATHER_OF/MOTHER_OF/SON_OF 等一律统一为 PARENT_OF；HUSBAND_OF/WIFE_OF 统一为 SPOUSE_OF。

只返回 JSON，格式：
{{"entities": [{{"name": "...", "type": "人物", "era": "射雕"}}], "relationships": [{{"source": "...", "target": "...", "type": "MASTER_OF"}}]}}
只返回 JSON，不要其他内容。"""

# ============ 嵌入（向量索引用） ============

EMBED_DIM = 256  # 本地哈希嵌入的维度


def hash_embed(text: str, dim: int = EMBED_DIM) -> List[float]:  # 该函数输入文本内容字符串，输出哈希向量
    """本地哈希嵌入（兜底方案）：不依赖外部服务。

    原理：对每个字符做 hash 投票，得到固定维度向量后归一化。
    语义精度不如真模型，但零成本、可复现，够基线跑通。
    """
    import numpy as np

    vec = np.zeros(dim, dtype=np.float32)
    for ch in text:
        vec[hash(ch) % dim] += 1.0
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec.tolist()


def make_embedder() -> Callable[[List[str]], List[List[float]]]:
    """根据配置返回嵌入函数：留空用本地哈希，填了用 OpenAI 兼容 API。"""
    endpoint = get_env("EMBED_ENDPOINT", "")
    model = get_env("EMBED_MODEL", "")
    token = get_env("EMBED_TOKEN", "")

    if endpoint and model:
        client = OpenAI(base_url=endpoint, api_key=token or "EMPTY")

        def _remote(texts: List[str]) -> List[List[float]]:
            resp = client.embeddings.create(model=model, input=texts)
            return [d.embedding for d in resp.data]

        return _remote

    def _local(texts: List[str]) -> List[List[float]]:
        return [hash_embed(t) for t in texts]

    return _local


# ============ LLM 抽取 ============

def get_llm_client() -> OpenAI:  # 该函数返回 LLM 客户端（默认 DeepSeek，OpenAI 兼容协议）
    """LLM 客户端（默认 DeepSeek，OpenAI 兼容协议）。"""
    return OpenAI(
        base_url=get_env("LLM_ENDPOINT", "https://api.deepseek.com"),
        api_key=get_env("LLM_TOKEN", ""),
    )


def parse_llm_json(raw: str) -> Dict[str, List[Dict]]:  # 该函数输入 LLM 返回的 JSON 字符串，输出解析后的字典
    """解析 LLM 返回的 JSON，容错处理常见的格式问题。

    - 剥掉 ```json ... ``` 代码块包裹
    - 截取第一个 { 到最后一个 } 之间的内容
    - 解析失败返回空结果（不中断整个流程）
    """
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        # 去掉可能残留的 "json" 前缀
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    # 截取最外层大括号
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        return {"entities": [], "relationships": []}
    try:
        data = json.loads(raw[start:end + 1])
    except json.JSONDecodeError:
        return {"entities": [], "relationships": []}
    return {
        "entities": data.get("entities") or [],
        "relationships": data.get("relationships") or [],
    }


def clean_entity(ent: Dict, default_era: str) -> Optional[Dict]:
    """清洗单个实体：类型/era 合法化，名字规范化。

    era 规则：LLM 给了合法值就用；给错或没给则用 default_era
    （阶段一整本书都是射雕，这是可靠先验）。
    """
    name = str(ent.get("name", "")).strip()
    etype = str(ent.get("type", "")).strip()
    art_type = ""

    # LLM 可能把武功类别（内功/外功/轻功/暗器）误填进 type 字段，归一化
    if etype in {"内功", "外功", "轻功", "暗器"}:
        art_type, etype = etype, "武功"

    if not name or etype not in ENTITY_LABELS:
        return None

    era = str(ent.get("era", "")).strip()
    if era not in VALID_ERAS:
        era = default_era

    out = {"name": name, "type": etype, "era": era}
    # 门派带 location；武功带类别（art_type：内功/外功/轻功/暗器）
    if etype == "门派":
        out["location"] = str(ent.get("location", "")).strip()
    elif etype == "武功":
        if not art_type:
            for key in ("art_type", "subtype", "category", "kind"):
                val = str(ent.get(key, "")).strip()
                if val:
                    art_type = val
                    break
        out["art_type"] = art_type
    return out


def clean_relationship(rel: Dict, entity_names: set) -> Optional[Dict]:
    """清洗单个关系：类型白名单校验 + 两端实体必须存在。"""
    source = str(rel.get("source", "")).strip()
    target = str(rel.get("target", "")).strip()
    rtype = str(rel.get("type", "")).strip().upper()
    if rtype not in RELATION_TYPES:  # 如果关系类型不在白名单里，就跳过
        return None
    if source not in entity_names or target not in entity_names:  # 如果两端实体都不在白名单里，就跳过
        return None
    if source == target:  # 如果两端实体相同，就跳过
        return None
    return {"source": source, "target": target, "type": rtype}


# ============ Neo4j 写入 ============

# 实体 MERGE：同名只留一个节点；era 只在为空时补（不覆盖已写值）
MERGE_ENTITY = """
MERGE (n:`{label}` {{name: $name}})
ON CREATE SET n.era = $era
ON MATCH SET n.era = coalesce(n.era, $era)
"""

MERGE_RELATION = """
MATCH (a:`{s_label}` {{name: $source}}), (b:`{t_label}` {{name: $target}})
MERGE (a)-[:`{rtype}`]->(b)
"""

MERGE_CHUNK = """
MERGE (c:Chunk {chunk_id: $chunk_id})
SET c.chapter = $chapter, c.text = $text, c.embedding = $embedding,
    c.book = $book, c.era = $era
"""

MERGE_MENTIONS = """
MATCH (c:Chunk {{chunk_id: $chunk_id}}), (e:`{label}` {{name: $name}})
MERGE (c)-[:MENTIONS]->(e)
"""

CREATE_VECTOR_INDEX = """
CREATE VECTOR INDEX text_embeddings IF NOT EXISTS
FOR (c:Chunk) ON (c.embedding)
OPTIONS {indexConfig: {
  `vector.dimensions`: $dim,
  `vector.similarity_function`: 'cosine'
}}
"""

CREATE_FULLTEXT_INDEX = """
CREATE FULLTEXT INDEX text_fulltext IF NOT EXISTS
FOR (c:Chunk) ON EACH [c.text]
"""


class KGBuilder:
    """抽取 + 入库的主类。把 driver / llm / embedder 作为依赖注入，
    方便测试时用假对象替换（见 tests/test_kg_builder.py）。"""

    def __init__(self, driver, llm: OpenAI, embedder: Callable,
                 model: str = "deepseek-chat", default_era: str = "射雕",
                 checkpoint_path: Path = CHECKPOINT_PATH):  # 初始化KGBuilder 类
        self.driver = driver  # Neo4j 数据库驱动，用于写入数据
        self.llm = llm  # LLM 客户端，用于调用 LLM 模型
        self.embedder = embedder  # 嵌入函数，用于将文本转换为向量
        self.model = model  # LLM 模型，默认 DeepSeek Chat
        self.default_era = default_era  # 默认 era，用于处理 era 为空的情况
        self.checkpoint_path = Path(checkpoint_path)  # 断点文件（每本书独立）

    # ---------- 抽取 ----------

    def extract_chunk(self, chunk: Dict,
                      max_retries: int = 3) -> Dict[str, List[Dict]]:  # 该函数输入文本块字典，输出实体关系字典
        """调 LLM 抽取一个文本块的实体关系，带重试。

        era 优先级：chunk 自带的 era（corpus.py 按书名注入）> default_era。
        """
        era = str(chunk.get("era") or "").strip() or self.default_era
        prompt = EXTRACT_PROMPT.format(chunk_text=chunk["text"])
        last_err = None
        for attempt in range(max_retries):
            try:
                resp = self.llm.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.0,
                )
                raw = resp.choices[0].message.content or ""
                return self._postprocess(parse_llm_json(raw), era)
            except Exception as e:  # 网络/限流等临时错误，退避重试
                last_err = e
                time.sleep(2 ** attempt)
        print(f"[build_kg] chunk {chunk['chunk_id']} 抽取失败：{last_err}")
        return {"entities": [], "relationships": []}

    def _postprocess(self, data: Dict[str, List[Dict]],
                     era: Optional[str] = None) -> Dict[str, List[Dict]]:  # 该函数输入实体关系字典，输出清洗后的实体关系字典
        """清洗：实体规范化 + 关系白名单过滤 + 双向关系展开。

        era 参数缺省时用 self.default_era（兼容旧调用方式）。
        """
        era = era or self.default_era
        entities = []
        seen = set()
        for ent in data["entities"]:
            cleaned = clean_entity(ent, era)
            if cleaned and (cleaned["type"], cleaned["name"]) not in seen:
                seen.add((cleaned["type"], cleaned["name"]))
                entities.append(cleaned)

        by_name = {}  # 同名不同类型的兜底：取第一个出现的类型
        for e in entities:
            by_name.setdefault(e["name"], e["type"])
        names = set(by_name)

        relationships = []
        seen_rel = set()
        for rel in data["relationships"]:
            cleaned = clean_relationship(rel, names)
            if not cleaned:
                continue
            directions = [(cleaned["source"], cleaned["target"])]
            if cleaned["type"] in BIDIRECTIONAL_RELS:
                directions.append((cleaned["target"], cleaned["source"]))
            for s, t in directions:
                key = (s, t, cleaned["type"])
                if key not in seen_rel:
                    seen_rel.add(key)
                    relationships.append({"source": s, "target": t,
                                         "type": cleaned["type"]})
        return {"entities": entities, "relationships": relationships}

    # ---------- 入库 ----------

    def ensure_indexes(self):  # 该函数确保向量索引和全文索引存在
        """建向量索引 + 全文索引（幂等，重复执行不报错）。"""
        with self.driver.session() as session:
            sample = self.embedder(["维度探测"])[0]
            session.run(CREATE_VECTOR_INDEX, dim=len(sample))
            session.run(CREATE_FULLTEXT_INDEX)

    def write_result(self, chunk: Dict, result: Dict[str, List[Dict]]):  # 该函数输入文本块字典和实体关系字典，写入 Neo4j
        """把一个块的抽取结果写入 Neo4j（MERGE 幂等，可重复执行）。"""
        entities = result["entities"]
        embeddings = self.embedder([chunk["text"]])

        with self.driver.session() as session:
            # 1. Chunk 节点（文本 + 向量 + 书名/era 元信息）
            session.run(MERGE_CHUNK, chunk_id=chunk["chunk_id"],
                        chapter=chunk.get("chapter", ""),
                        text=chunk["text"], embedding=embeddings[0],
                        book=chunk.get("book", ""), era=chunk.get("era", ""))

            # 2. 实体节点
            for ent in entities:
                props = {"name": ent["name"], "era": ent["era"]}
                if ent["type"] == "门派" and ent.get("location"):
                    props["location"] = ent["location"]
                if ent["type"] == "武功" and ent.get("art_type"):
                    props["type"] = ent["art_type"]  # 武功类别存 type 属性
                session.run(MERGE_ENTITY.format(label=ent["type"]), **props)
                # MENTIONS：证据溯源用（这个块提到了这个实体）
                session.run(MERGE_MENTIONS.format(label=ent["type"]),
                            chunk_id=chunk["chunk_id"], name=ent["name"])

            # 3. 关系（两端按实体类型加 label 匹配）
            type_of = {}
            for ent in entities:
                type_of.setdefault(ent["name"], ent["type"])
            for rel in result["relationships"]:
                s_label = type_of.get(rel["source"])
                t_label = type_of.get(rel["target"])
                if not s_label or not t_label:
                    continue  # 两端不在本批实体里（数据库里可能也没有），跳过
                session.run(
                    MERGE_RELATION.format(s_label=s_label, t_label=t_label,
                                          rtype=rel["type"]),
                    source=rel["source"], target=rel["target"],
                )

    # ---------- 主流程 ----------

    def run(self, chunks: List[Dict], limit: Optional[int] = None, 
            resume: bool = False, dry_run: bool = False) -> Dict[str, int]:  # 该函数输入文本块列表，输出统计信息字典，处理流程，实践开始
        """批量处理：抽取 → 入库 → 记 checkpoint（每本书独立断点文件）。"""
        done = set()
        if resume and self.checkpoint_path.exists():
            done = set(json.loads(self.checkpoint_path.read_text(encoding="utf-8")))
            print(f"[build_kg] 断点续跑（{self.checkpoint_path.name}），已完成 {len(done)} 块")

        todo = [c for c in chunks if c["chunk_id"] not in done]
        if limit is not None:
            todo = todo[:limit]
        print(f"[build_kg] 待处理 {len(todo)} 块（总 {len(chunks)}）")

        if not dry_run:
            self.ensure_indexes()

        stats = {"chunks": 0, "entities": 0, "relationships": 0}
        for i, chunk in enumerate(todo):
            result = self.extract_chunk(chunk)
            stats["chunks"] += 1
            stats["entities"] += len(result["entities"])
            stats["relationships"] += len(result["relationships"])

            if dry_run:
                print(f"--- chunk {chunk['chunk_id']} ({chunk['chapter']}) ---")
                print(json.dumps(result, ensure_ascii=False, indent=1))
            else:
                self.write_result(chunk, result)
                done.add(chunk["chunk_id"])
                self.checkpoint_path.write_text(
                    json.dumps(sorted(done)), encoding="utf-8")

            if (i + 1) % 20 == 0:
                print(f"[build_kg] 进度 {i + 1}/{len(todo)}，"
                      f"累计实体 {stats['entities']}，关系 {stats['relationships']}")

        print(f"[build_kg] 完成：{stats}")
        return stats


# ============ 命令行入口 ============

def main():  # 主函数，处理命令行参数和流程控制
    parser = argparse.ArgumentParser(description="LLM 抽取 + Neo4j 入库（多书）")
    parser.add_argument("--chunks", type=str, default=None,
                        help="chunks 文件路径；默认按 --book 定位，都不填用阶段一的 chunks.json")
    parser.add_argument("--book", type=str, default=None,
                        help="书名（如 神雕侠侣）：自动定位 data/interim/chunks_<书名>.json 并推断 era")
    parser.add_argument("--limit", type=int, default=None, help="只处理前 N 块")
    parser.add_argument("--resume", action="store_true", help="断点续跑")
    parser.add_argument("--dry-run", action="store_true",
                        help="只抽取打印结果，不写库")
    parser.add_argument("--era", type=str, default=None,
                        help="era 缺省值；不填则按书名自动推断（射雕/神雕/倚天）")
    args = parser.parse_args()

    # 定位 chunks 文件：--chunks 显式指定 > --book 书名定位 > 阶段一默认
    if args.chunks:
        chunks_path = Path(args.chunks)
    elif args.book:
        chunks_path = DEFAULT_INTERIM / f"chunks_{args.book}.json"
    else:
        chunks_path = DEFAULT_OUT_PATH

    if not chunks_path.exists():
        hint = f"，请先跑：python corpus.py --source data/source/{args.book}.txt" if args.book else ""
        raise SystemExit(f"找不到 chunks 文件：{chunks_path}{hint}")

    # era 推断：显式 --era > 书名/chunks 文件名推断 > 射雕（阶段一默认）
    era = args.era or infer_era(args.book or chunks_path.stem) or "射雕"
    ckpt_path = checkpoint_path_for(chunks_path)

    chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
    print(f"[build_kg] 读入 {len(chunks)} 块（{chunks_path.name}），"
          f"era 缺省值 = {era}，checkpoint = {ckpt_path.name}")

    if not get_env("LLM_TOKEN"):
        raise SystemExit("缺少 LLM_TOKEN，请先复制 .env.example 为 .env 并填写")

    llm = get_llm_client()
    embedder = make_embedder()

    if args.dry_run:
        builder = KGBuilder(driver=None, llm=llm, embedder=embedder,
                            model=get_env("LLM_MODEL", "deepseek-chat"),
                            default_era=era, checkpoint_path=ckpt_path)
        builder.run(chunks, limit=args.limit, dry_run=True)
        return

    driver = GraphDatabase.driver(
        get_env("NEO4J_URL", "bolt://localhost:7687"),
        auth=(get_env("NEO4J_USER", "neo4j"),
              get_env("NEO4J_PASSWORD", "")),
    )
    try:
        builder = KGBuilder(driver=driver, llm=llm, embedder=embedder,
                            model=get_env("LLM_MODEL", "deepseek-chat"),
                            default_era=era, checkpoint_path=ckpt_path)
        builder.run(chunks, limit=args.limit, resume=args.resume)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
