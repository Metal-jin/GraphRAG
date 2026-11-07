"""LLM 抽取实体关系 + 写入 Neo4j（任务 05/06/07/08/09/10/30）。

核心改动（相对阶段二版本）：
1. 抽取状态显式化：成功 / 合法空结果 / 可重试失败 / 不可重试失败，
   只有**入库事务成功**后才写 checkpoint，失败块进入重试清单；
2. 一个文本块的所有写入在**同一事务**内完成（session.execute_write）；
   实体与 Chunk 建立唯一约束，重复执行幂等；
3. 完整保存实体属性（description / location / art_type），打通后代扫描；
4. 本体校验单一来源 core.ontology：关系类型白名单 + 两端实体类型校验，
   非法关系进入 rejected 清单而不是静默写入；
5. 关系绑定证据：chunk_id / snippet / 抽取值版本 / 来源书目与时代，
   同一事实的多个来源以数组累积，不再互相覆盖；
6. 时代建模：era 只是首次出现时代，另存 eras / books，跨书人物不会在后续时代消失；
7. checkpoint 带数据版本与原文指纹，旧格式/参数不兼容时**显式拒绝 resume**。

用法（在仓库根目录、PYTHONPATH=src 下）：
    python src/ingest/build_kg.py --book 射雕英雄传 --preview              # 只预览，不调 LLM
    python src/ingest/build_kg.py --book 射雕英雄传 --limit 20 --dry-run  # 调 LLM 不写库
    python src/ingest/build_kg.py --book 射雕英雄传                        # 真实入库
    python src/ingest/build_kg.py --resume                                 # 多书断点续跑
"""
from __future__ import annotations

import argparse
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from neo4j import GraphDatabase
from openai import OpenAI

from core.config import get_env, get_settings
from core.embedding import (EmbeddingService, assert_index_compatible,
                            get_embedder, local_hash_embed)
from core.errors import IndexCompatibilityError
from core.ontology import (ART_TYPES, BIDIRECTIONAL_RELS, ENTITY_LABELS,
                           RELATION_TYPES, VALID_ERAS, entity_prompt_block,
                           infer_era, is_noise_name, relation_prompt_block,
                           validate_relation)
from ingest.corpus import (CHUNKER_VERSION, DEFAULT_INTERIM, DEFAULT_OUT_PATH,
                           load_manifest, update_manifest)
from ingest.relation_evidence import gate_relationships

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHECKPOINT_PATH = DEFAULT_INTERIM / "kg_checkpoint.json"  # 阶段一遗留（射雕）

PROMPT_VERSION = "extract-v5"  # v5：关系必须给出原文证据句；PARENT_OF 需亲属表述
CHECKPOINT_FORMAT = 2

# 抽取状态
STATUS_OK = "ok"                    # 抽取成功且有实体/关系
STATUS_EMPTY = "empty"              # JSON 合法、清洗后确实没有实体（合法空结果）
STATUS_RETRYABLE = "retryable"      # 网络/限流/JSON 解析失败，可重试
STATUS_FATAL = "fatal"              # 认证/参数错误，不应重试

# 标签 -> ASCII 约束名（约束名用 ASCII，避免依赖中文标识符）
LABEL_SLUG = {"人物": "person", "门派": "sect", "武功": "art", "地点": "place"}

BACKTICK = chr(96)  # Cypher 里需要反引号时用它拼，避免与源码引号混淆


def _q(identifier: str) -> str:
    """给 Cypher 标识符加反引号。"""
    return BACKTICK + identifier + BACKTICK


# ============ 抽取 Prompt（关系清单来自 core.ontology，避免漂移） ============

EXTRACT_PROMPT_TEMPLATE = """你是一个知识图谱抽取专家。请从以下金庸小说文本中提取实体和关系。

文本：
{chunk_text}

实体类型（每个实体都要带 era 时代属性，判断不了就留空）：
{entity_block}

关系类型（方向要正确，严格只用以下关系，不要自造）：
{relation_block}

注意：FATHER_OF/MOTHER_OF/SON_OF 等一律统一为 PARENT_OF；HUSBAND_OF/WIFE_OF 统一为 SPOUSE_OF。
description 只写原文对该实体的描述，不要编造。

关系的硬性要求（不满足就不要输出这条关系）：
- 只抽取原文**明确写出**的关系；不得因为两人同时出现、同属一个门派、彼此认识就推断关系。
- 每条关系必须带 evidence 字段：原文中**逐字**支持该关系的一句话，不要改写、不要翻译、不要拼接。
- PARENT_OF 只有在原文明确写出父母子女关系时才抽取（父、母、爹、娘、儿子、女儿、之子、之女、所生、生下 等）。
- SPOUSE_OF / SWORN_BROTHER_OF / ENEMY_OF 同样必须原文明确写出。

只返回 JSON，格式：
{{"entities": [{{"name": "...", "type": "人物", "era": "射雕", "description": "..."}},
              {{"name": "...", "type": "门派", "era": "射雕", "location": "..."}},
              {{"name": "...", "type": "武功", "era": "射雕", "art_type": "外功"}}],
 "relationships": [{{"source": "...", "target": "...", "type": "MASTER_OF",
                    "evidence": "原文中逐字支持该关系的一句话"}}]}}
只返回 JSON，不要其他内容。"""


def build_prompt(chunk_text: str) -> str:
    return EXTRACT_PROMPT_TEMPLATE.format(
        chunk_text=chunk_text,
        entity_block=entity_prompt_block(),
        relation_block=relation_prompt_block(),
    )


# ============ 嵌入（统一走 core.embedding，保留旧接口名） ============

def hash_embed(text: str, dim: int = 256) -> List[float]:
    """兼容旧调用：本地稳定哈希嵌入（已统一到 core.embedding）。"""
    return local_hash_embed(text, dim)


def make_embedder() -> EmbeddingService:
    """兼容旧调用：返回进程级统一嵌入器。"""
    return get_embedder()


def embed_texts(embedder, texts: List[str]) -> List[List[float]]:
    """同时支持 EmbeddingService 与"函数式 embedder"（测试/离线注入用）。"""
    if embedder is None:
        return [[] for _ in texts]
    if hasattr(embedder, "embed_documents"):
        return embedder.embed_documents(texts)
    return [list(vector) for vector in embedder(texts)]


# ============ LLM 抽取与结果解析 ============

@dataclass
class ExtractionResult:
    status: str
    entities: List[Dict] = field(default_factory=list)
    relationships: List[Dict] = field(default_factory=list)
    rejected: List[Dict] = field(default_factory=list)
    raw: str = ""
    error: str = ""
    attempts: int = 0
    model: str = ""
    prompt_version: str = PROMPT_VERSION
    written: Dict[str, int] = field(default_factory=dict)

    @property
    def is_success(self) -> bool:
        return self.status in (STATUS_OK, STATUS_EMPTY)

    def to_log_record(self, chunk_id: str) -> Dict:
        return {"chunk_id": chunk_id, "status": self.status,
                "error": self.error, "attempts": self.attempts,
                "entities": self.entities, "relationships": self.relationships,
                "rejected": self.rejected, "model": self.model,
                "prompt_version": self.prompt_version, "written": self.written,
                "raw": self.raw[:4000],
                "at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")}


def _strip_code_fence(raw: str) -> str:
    text = (raw or "").strip()
    fence = BACKTICK * 3
    if text.startswith(fence):
        text = text.strip(BACKTICK)
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    return text


def parse_llm_payload(raw: str) -> Tuple[Optional[Dict], str]:
    """解析并**校验类型**；返回 (payload, 错误说明)。payload 为 None 表示失败。"""
    text = _strip_code_fence(raw)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None, "响应中没有 JSON 对象"
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        return None, f"JSON 解析失败：{exc}"
    if not isinstance(data, dict):
        return None, f"顶层结构不是对象：{type(data).__name__}"
    entities = data.get("entities", [])
    relationships = data.get("relationships", [])
    if not isinstance(entities, list):
        return None, f"entities 不是数组：{type(entities).__name__}"
    if not isinstance(relationships, list):
        return None, f"relationships 不是数组：{type(relationships).__name__}"
    for item in entities:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            return None, "entities 中存在非对象或缺少字符串 name 的条目"
    for item in relationships:
        if not isinstance(item, dict):
            return None, "relationships 中存在非对象条目"
        for key in ("source", "target", "type"):
            if not isinstance(item.get(key), str):
                return None, f"relationships 条目缺少字符串字段 {key}"
        if item.get("evidence") is not None and not isinstance(item.get("evidence"), str):
            return None, "relationships 条目的 evidence 必须是字符串"
    return {"entities": entities, "relationships": relationships}, ""


def parse_llm_json(raw: str) -> Dict[str, List[Dict]]:
    """兼容旧接口：解析失败返回空结果（不区分状态，供旧测试/旧调用方使用）。"""
    data, _ = parse_llm_payload(raw)
    if data is None:
        return {"entities": [], "relationships": []}
    return {"entities": data["entities"], "relationships": data["relationships"]}


def clean_entity(ent: Dict, default_era: str) -> Optional[Dict]:
    """清洗单个实体：类型/era 合法化，名字规范化，保留 description/location/art_type。"""
    name = str(ent.get("name", "")).strip()
    etype = str(ent.get("type", "")).strip()
    art_type = ""

    # LLM 可能把武功类别（内功/外功/轻功/暗器）误填进 type 字段
    if etype in ART_TYPES:
        art_type, etype = etype, "武功"

    if not name or etype not in ENTITY_LABELS or is_noise_name(name):
        return None

    era = str(ent.get("era", "")).strip()
    if era not in VALID_ERAS:
        era = default_era

    out: Dict[str, Any] = {"name": name, "type": etype, "era": era}
    description = str(ent.get("description", "") or "").strip()
    if description:
        out["description"] = description[:500]
    if etype == "门派":
        location = str(ent.get("location", "") or "").strip()
        if location:
            out["location"] = location
    elif etype == "武功":
        if not art_type:
            for key in ("art_type", "subtype", "category", "kind"):
                value = str(ent.get(key, "") or "").strip()
                if value:
                    art_type = value
                    break
        if art_type:
            out["art_type"] = art_type
    return out


def clean_relationship(rel: Dict, entity_names: Iterable[str],
                       entity_types: Optional[Dict[str, str]] = None) -> Optional[Dict]:
    """清洗单个关系：类型白名单 + 两端实体存在 + 两端类型合法。"""
    source = str(rel.get("source", "")).strip()
    target = str(rel.get("target", "")).strip()
    rtype = str(rel.get("type", "")).strip().upper()
    names = set(entity_names or [])
    if rtype not in RELATION_TYPES:
        return None
    if source not in names or target not in names:
        return None
    if source == target:
        return None
    if entity_types is not None:
        ok, _reason = validate_relation(rtype, entity_types.get(source),
                                        entity_types.get(target))
        if not ok:
            return None
    out: Dict[str, Any] = {"source": source, "target": target, "type": rtype}
    evidence = str(rel.get("evidence", "") or "").strip()
    if evidence:
        out["evidence"] = evidence[:300]
    return out


def reject_reason(rel: Dict, entity_names: Iterable[str],
                  entity_types: Optional[Dict[str, str]]) -> str:
    """给出被拒关系的具体原因（写进 rejected 清单，便于审计）。"""
    source = str(rel.get("source", "")).strip()
    target = str(rel.get("target", "")).strip()
    rtype = str(rel.get("type", "")).strip().upper()
    names = set(entity_names or [])
    if rtype not in RELATION_TYPES:
        return f"未知关系类型 {rtype!r}"
    if source not in names or target not in names:
        return "关系端点不在本块实体中"
    if source == target:
        return "自环关系"
    ok, reason = validate_relation(rtype, (entity_types or {}).get(source),
                                   (entity_types or {}).get(target))
    return "" if ok else reason


def _is_fatal_error(exc: Exception) -> bool:
    """认证/参数类错误不应重试；网络/限流类可以。"""
    name = type(exc).__name__
    return name in {"AuthenticationError", "PermissionDeniedError",
                    "BadRequestError", "NotFoundError", "UnprocessableEntityError"}


def _split_sentences(text: str) -> List[str]:
    return [s for s in re.split(r"(?<=[。！？!?；;])", text or "") if s.strip()]


class KGBuilder:
    """抽取 + 入库的主类。driver / llm / embedder 依赖注入，方便测试替换。"""

    def __init__(self, driver, llm, embedder,
                 model: str = "deepseek-chat", default_era: str = "射雕",
                 checkpoint_path: Path = CHECKPOINT_PATH,
                 book: str = "", dataset_version: str = CHUNKER_VERSION,
                 save_raw: bool = False, disable_thinking: bool = True):
        self.driver = driver
        self.llm = llm
        self.embedder = embedder
        self.model = model
        self.default_era = default_era
        self.checkpoint_path = Path(checkpoint_path)
        self.book = book
        self.dataset_version = dataset_version
        self.save_raw = save_raw
        self.disable_thinking = disable_thinking

    # ---------- 抽取 ----------

    def extract_chunk(self, chunk: Dict, max_retries: int = 3) -> ExtractionResult:
        era = str(chunk.get("era") or "").strip() or self.default_era
        prompt = build_prompt(chunk["text"])
        last_error = ""
        for attempt in range(1, max_retries + 1):
            try:
                kwargs: Dict[str, Any] = {
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.0,
                }
                if self.disable_thinking:
                    kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
                try:
                    resp = self.llm.chat.completions.create(**kwargs)
                except Exception as exc:
                    # 部分兼容端点不认识 thinking 参数 → 去掉重试一次
                    if type(exc).__name__ == "BadRequestError" and "extra_body" in kwargs:
                        kwargs.pop("extra_body")
                        resp = self.llm.chat.completions.create(**kwargs)
                    else:
                        raise
                raw = (resp.choices[0].message.content or "")
            except Exception as exc:  # 网络/限流/认证
                last_error = f"{type(exc).__name__}: {exc}"
                if _is_fatal_error(exc):
                    return ExtractionResult(STATUS_FATAL, raw="", error=last_error,
                                            attempts=attempt, model=self.model)
                time.sleep(min(2 ** (attempt - 1), 8))
                continue
            data, error = parse_llm_payload(raw)
            if data is None:
                last_error = error
                time.sleep(min(2 ** (attempt - 1), 8))
                continue
            processed = self._postprocess(data, era, chunk.get("book", ""))
            # 二次校验：证据句必须是原文子串；PARENT_OF 必须有亲属表述
            kept, rejected_evidence = gate_relationships(
                processed["relationships"], chunk["text"])
            processed["relationships"] = kept
            processed["rejected"].extend(rejected_evidence)
            status = STATUS_OK if (processed["entities"] or processed["relationships"]) else STATUS_EMPTY
            return ExtractionResult(status, processed["entities"],
                                    processed["relationships"], processed["rejected"],
                                    raw=raw, attempts=attempt, model=self.model)
        return ExtractionResult(STATUS_RETRYABLE, raw="", error=last_error,
                                attempts=max_retries, model=self.model)

    def _postprocess(self, data: Dict[str, List[Dict]],
                     era: Optional[str] = None,
                     book: str = "") -> Dict[str, List[Dict]]:
        """清洗：实体规范化 + 关系白名单/类型校验 + 双向关系展开 + 拒绝清单。"""
        era = era or self.default_era
        entities: List[Dict] = []
        seen = set()
        for ent in data.get("entities", []):
            cleaned = clean_entity(ent, era)
            if not cleaned:
                continue
            key = (cleaned["type"], cleaned["name"])
            if key in seen:
                continue
            seen.add(key)
            entities.append(cleaned)

        by_name: Dict[str, str] = {}
        conflicts: List[Dict] = []
        for entity in entities:
            existing = by_name.get(entity["name"])
            if existing and existing != entity["type"]:
                conflicts.append({"name": entity["name"], "types": [existing, entity["type"]]})
                continue
            by_name.setdefault(entity["name"], entity["type"])
        names = set(by_name)

        relationships: List[Dict] = []
        rejected: List[Dict] = []
        seen_rel = set()
        for rel in data.get("relationships", []):
            cleaned = clean_relationship(rel, names, by_name)
            if not cleaned:
                reason = reject_reason(rel, names, by_name)
                if reason:
                    rejected.append({"raw": rel, "reason": reason})
                continue
            directions = [(cleaned["source"], cleaned["target"])]
            if cleaned["type"] in BIDIRECTIONAL_RELS:
                directions.append((cleaned["target"], cleaned["source"]))
            for source, target in directions:
                key = (source, target, cleaned["type"])
                if key not in seen_rel:
                    seen_rel.add(key)
                    entry = {"source": source, "target": target,
                             "type": cleaned["type"]}
                    if cleaned.get("evidence"):
                        entry["evidence"] = cleaned["evidence"]
                    relationships.append(entry)
        return {"entities": entities, "relationships": relationships,
                "rejected": rejected + [{"type": "entity_type_conflict", **c} for c in conflicts]}

    # ---------- 证据 ----------

    @staticmethod
    def extract_snippet(text: str, source: str, target: str, max_len: int = 160) -> str:
        """从原文块里截取同时包含两个实体的句子作为关系证据（任务 09）。"""
        if not text:
            return ""
        for sentence in _split_sentences(text):
            if source in sentence and target in sentence:
                return sentence.strip()[:max_len]
        for sentence in _split_sentences(text):
            if source in sentence or target in sentence:
                return sentence.strip()[:max_len]
        return text.strip()[:max_len]

    # ---------- Neo4j 写入 ----------

    def ensure_schema(self) -> Dict[str, Any]:
        """建立唯一约束 + 索引，并校验向量索引与当前嵌入方案兼容。"""
        if self.driver is None:
            return {}
        embedder = self.embedder
        probe = embed_texts(embedder, ["维度探测"])[0] if embedder else []
        spec = embedder.spec if hasattr(embedder, "spec") else None
        existing_dim = None

        def _safe_schema(query: str, **params) -> None:
            """多进程并发建索引/约束时，IF NOT EXISTS 不是原子操作：
            后到的进程可能收到 EquivalentSchemaRuleAlreadyExists，
            或者在建约束时与其它进程死锁。这些都按"已就绪"处理，不中断构建。"""
            for attempt in range(2):
                try:
                    session.run(query, **params)
                    return
                except Exception as exc:  # noqa: BLE001
                    text = str(exc)
                    if ("EquivalentSchemaRuleAlreadyExists" in text
                            or "already exists" in text
                            or "ConstraintCreationFailed" in text):
                        return  # 已存在 / 数据里已有重复值（约束可选，跳过即可）
                    transient = ("DeadlockDetected" in text
                                 or "TransientError" in text)
                    if transient and attempt == 0:
                        time.sleep(1.0)
                        continue
                    if transient:
                        return
                    raise

        with self.driver.session() as session:
            for label, slug in LABEL_SLUG.items():
                _safe_schema(
                    f"CREATE CONSTRAINT entity_{slug}_name IF NOT EXISTS "
                    f"FOR (n:{label}) REQUIRE n.name IS UNIQUE")
            _safe_schema(
                "CREATE CONSTRAINT chunk_id_unique IF NOT EXISTS "
                "FOR (c:Chunk) REQUIRE c.chunk_id IS UNIQUE")
            # 并发进程同时写 IndexMeta 会产生重复节点（MERGE 无唯一约束时不原子）
            _safe_schema(
                "CREATE CONSTRAINT index_meta_name IF NOT EXISTS "
                "FOR (m:IndexMeta) REQUIRE m.name IS UNIQUE")

            existing = session.run(
                "MATCH (c:Chunk) WHERE c.embedding IS NOT NULL "
                "RETURN size(c.embedding) AS dim LIMIT 1").single()
            existing_dim = existing["dim"] if existing else None
            if spec and existing_dim and spec.dimension and existing_dim != spec.dimension:
                raise IndexCompatibilityError(
                    f"已有向量索引维度 {existing_dim} 与当前嵌入方案 {spec.dimension} 不一致",
                    detail="请先重建索引，或恢复原来的 EMBED_* 配置")
            if spec and spec.dimension:
                from ingest.data_loader import read_index_meta, write_index_meta
                stored = read_index_meta()
                assert_index_compatible(stored, spec)
                if not stored:
                    write_index_meta(spec.to_meta())
                options = (f"OPTIONS {{indexConfig: {{{_q('vector.dimensions')}: $dim, "
                           f"{_q('vector.similarity_function')}: 'cosine'}}}}")
                _safe_schema(
                    f"CREATE VECTOR INDEX text_embeddings IF NOT EXISTS "
                    f"FOR (c:Chunk) ON (c.embedding) {options}", dim=spec.dimension)
            _safe_schema(
                "CREATE FULLTEXT INDEX text_fulltext IF NOT EXISTS "
                "FOR (c:Chunk) ON EACH [c.text]")
        return {"embedding_dim": len(probe) if probe else None,
                "existing_dim": existing_dim}

    def write_result(self, chunk: Dict, result: ExtractionResult) -> Dict[str, int]:
        """一个块的全部写入放在同一事务里（任务 06）。

        向量在**事务外**计算：嵌入是网络调用，放进事务会长时间占用事务与连接。
        """
        if self.driver is None:
            return {"entities": 0, "relationships": 0}
        embedding = (embed_texts(self.embedder, [chunk["text"]])[0]
                     if self.embedder else None)
        with self.driver.session() as session:
            return session.execute_write(self._write_tx, chunk, result, embedding)

    def _write_tx(self, tx, chunk: Dict, result: ExtractionResult,
                  embedding: Optional[List[float]] = None) -> Dict[str, int]:
        chunk_id = chunk["chunk_id"]
        book = chunk.get("book", self.book)
        era = chunk.get("era") or self.default_era

        tx.run(
            "MERGE (c:Chunk {chunk_id: $chunk_id}) "
            "SET c.chapter = $chapter, c.text = $text, c.book = $book, c.era = $era, "
            "    c.dataset_version = $dataset_version, c.content_hash = $content_hash, "
            "    c.offset = $offset, c.end = $end "
            "FOREACH (_ IN CASE WHEN $embedding IS NULL THEN [] ELSE [1] END | "
            "  SET c.embedding = $embedding)",
            chunk_id=chunk_id, chapter=chunk.get("chapter", ""), text=chunk["text"],
            book=book, era=era,
            dataset_version=chunk.get("dataset_version", self.dataset_version),
            content_hash=chunk.get("content_hash", ""), offset=chunk.get("offset"),
            end=chunk.get("end"), embedding=embedding)

        by_label: Dict[str, List[Dict]] = {}
        for entity in result.entities:
            by_label.setdefault(entity["type"], []).append(entity)

        entity_count = 0
        for label, rows in by_label.items():
            tx.run(
                "UNWIND $rows AS row "
                f"MERGE (n:{label} {{name: row.name}}) "
                "ON CREATE SET n.era = row.era, n.first_seen_era = row.era, "
                "              n.eras = [row.era], n.books = [row.book], "
                "              n.description = CASE WHEN row.description = '' "
                "                                    THEN null ELSE row.description END, "
                "              n.location = CASE WHEN row.location = '' "
                "                                THEN null ELSE row.location END, "
                "              n.art_type = CASE WHEN row.art_type = '' "
                "                                THEN null ELSE row.art_type END "
                "ON MATCH SET n.eras = CASE WHEN row.era IN coalesce(n.eras, []) "
                "                      THEN coalesce(n.eras, []) ELSE coalesce(n.eras, []) + row.era END, "
                "              n.books = CASE WHEN row.book IN coalesce(n.books, []) "
                "                      THEN coalesce(n.books, []) ELSE coalesce(n.books, []) + row.book END, "
                "              n.first_seen_era = coalesce(n.first_seen_era, n.era, row.era), "
                "              n.era = coalesce(n.era, row.era), "
                "              n.description = CASE WHEN size(coalesce(n.description, '')) < size(coalesce(row.description, '')) "
                "                      THEN row.description ELSE coalesce(n.description, '') END, "
                "              n.location = coalesce(n.location, CASE WHEN row.location = '' "
                "                                     THEN null ELSE row.location END), "
                "              n.art_type = coalesce(n.art_type, CASE WHEN row.art_type = '' "
                "                                     THEN null ELSE row.art_type END)",
                rows=[{"name": e["name"], "era": e["era"], "book": book,
                       "description": e.get("description", ""),
                       "location": e.get("location", ""),
                       "art_type": e.get("art_type", "")} for e in rows])
            entity_count += len(rows)

            tx.run(
                "UNWIND $rows AS row "
                "MATCH (c:Chunk {chunk_id: $chunk_id}) "
                f"MATCH (e:{label} {{name: row.name}}) "
                "MERGE (c)-[:MENTIONS]->(e)",
                rows=[{"name": e["name"]} for e in rows], chunk_id=chunk_id)

        # 关系按 (起点label, 终点label, 关系类型) 分组后批量写入
        type_of = {}
        for entity in result.entities:
            type_of.setdefault(entity["name"], entity["type"])
        groups: Dict[Tuple[str, str, str], List[Dict]] = {}
        for rel in result.relationships:
            source_type = type_of.get(rel["source"])
            target_type = type_of.get(rel["target"])
            if not source_type or not target_type:
                continue
            snippet = (rel.get("evidence")
                       or self.extract_snippet(chunk["text"], rel["source"], rel["target"]))
            groups.setdefault((source_type, target_type, rel["type"]), []).append(
                {"source": rel["source"], "target": rel["target"], "snippet": snippet})

        rel_count = 0
        for (source_type, target_type, rtype), rows in groups.items():
            tx.run(
                "UNWIND $rows AS row "
                f"MATCH (a:{source_type} {{name: row.source}}) "
                f"MATCH (b:{target_type} {{name: row.target}}) "
                f"MERGE (a)-[r:{rtype}]->(b) "
                "ON CREATE SET r.chunk_ids = [$chunk_id], r.snippets = [row.snippet], "
                "              r.versions = [$version], r.confidence = 'extracted', "
                "              r.chunk_id = $chunk_id, r.books = [$book], r.eras = [$era] "
                "ON MATCH SET r.chunk_ids = CASE WHEN $chunk_id IN coalesce(r.chunk_ids, []) "
                "                      THEN coalesce(r.chunk_ids, []) ELSE coalesce(r.chunk_ids, []) + $chunk_id END, "
                "              r.snippets = CASE WHEN row.snippet IN coalesce(r.snippets, []) "
                "                      THEN coalesce(r.snippets, []) ELSE coalesce(r.snippets, []) + row.snippet END, "
                "              r.books = CASE WHEN $book IN coalesce(r.books, []) "
                "                      THEN coalesce(r.books, []) ELSE coalesce(r.books, []) + $book END, "
                "              r.eras = CASE WHEN $era IN coalesce(r.eras, []) "
                "                      THEN coalesce(r.eras, []) ELSE coalesce(r.eras, []) + $era END, "
                "              r.versions = CASE WHEN $version IN coalesce(r.versions, []) "
                "                      THEN coalesce(r.versions, []) ELSE coalesce(r.versions, []) + $version END, "
                "              r.chunk_id = coalesce(r.chunk_id, $chunk_id)",
                rows=rows, chunk_id=chunk_id, version=PROMPT_VERSION,
                book=book, era=era)
            rel_count += len(rows)
        return {"entities": entity_count, "relationships": rel_count}

    # ---------- 主流程 ----------

    def _handle_chunk(self, chunk: Dict, *, dry_run: bool,
                      store: "CheckpointStore", raw_log: Optional[Path],
                      lock) -> Dict[str, Any]:
        """处理单个块（抽取 + 可选入库 + 断点）。供串行/并发两种模式复用。"""
        result = self.extract_chunk(chunk)
        entry = {"status": result.status, "entities": len(result.entities),
                 "relationships": len(result.relationships),
                 "rejected": len(result.rejected), "chunk_id": chunk["chunk_id"],
                 "error": result.error}
        if raw_log:
            with lock:
                with raw_log.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(result.to_log_record(chunk["chunk_id"]),
                                            ensure_ascii=False) + chr(10))
        if result.status in (STATUS_RETRYABLE, STATUS_FATAL):
            if not dry_run:
                with lock:
                    store.mark_failed(chunk["chunk_id"], result.status, result.error)
            return entry
        if dry_run:
            with lock:
                print(f"--- chunk {chunk['chunk_id']} ({chunk.get('chapter','')}) "
                      f"status={result.status} 实体={len(result.entities)} "
                      f"关系={len(result.relationships)} ---")
                print(json.dumps({"entities": result.entities,
                                  "relationships": result.relationships,
                                  "rejected": result.rejected[:5]},
                                 ensure_ascii=False, indent=1))
            return entry
        try:
            written = self.write_result(chunk, result)
            result.written = written
        except Exception as exc:  # 写入失败（含并发死锁重试耗尽）
            entry["status"] = STATUS_RETRYABLE
            entry["error"] = f"write failed: {type(exc).__name__}: {exc}"
            with lock:
                store.mark_failed(chunk["chunk_id"], STATUS_RETRYABLE, entry["error"])
            return entry
        # 事务成功后才记录完成（任务 05）
        with lock:
            store.mark_done(chunk["chunk_id"], chunk.get("content_hash", ""),
                            result.status, written)
        return entry

    def run(self, chunks: List[Dict], limit: Optional[int] = None,
            resume: bool = False, dry_run: bool = False,
            checkpoint: Optional["CheckpointStore"] = None,
            reingest_failed: bool = False,
            workers: int = 1) -> Dict[str, Any]:
        store = checkpoint or CheckpointStore(
            self.checkpoint_path, book=self.book,
            dataset_version=self.dataset_version, source_sha256="")
        if resume:
            store.load_or_raise()
        else:
            store.load()

        todo = list(chunks)
        if resume:
            todo = [c for c in todo
                    if reingest_failed and c["chunk_id"] in store.failed_ids()
                    or not store.is_done(c["chunk_id"], c.get("content_hash", ""))]
        if limit is not None:
            todo = todo[:limit]
        print(f"[build_kg] 待处理 {len(todo)} 块（总 {len(chunks)}，book={self.book or '?'}）")

        if not dry_run:
            schema = self.ensure_schema()
            if schema:
                print(f"[build_kg] 约束/索引就绪，嵌入维度={schema.get('embedding_dim')}")

        stats: Dict[str, Any] = {STATUS_OK: 0, STATUS_EMPTY: 0, STATUS_RETRYABLE: 0,
                                 STATUS_FATAL: 0, "chunks": 0, "entities": 0,
                                 "relationships": 0, "rejected": 0}
        # --dry-run：只调用抽取模型并打印结果，**不写数据库、不写 checkpoint**
        # --save-raw 仍可用于保存试跑的原始响应（属于独立的调试产物）
        raw_log = self._raw_log_path() if self.save_raw else None
        lock = threading.Lock()

        def _accumulate(entry: Dict[str, Any]) -> None:
            with lock:
                stats[entry["status"]] = stats.get(entry["status"], 0) + 1
                stats["chunks"] += 1
                stats["entities"] += entry["entities"]
                stats["relationships"] += entry["relationships"]
                stats["rejected"] += entry["rejected"]

        workers = max(1, int(workers or 1))
        if workers > 1 and len(todo) > 1:
            print(f"[build_kg] 并发模式：{workers} 个 worker")
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(self._handle_chunk, chunk, dry_run=dry_run,
                                       store=store, raw_log=raw_log, lock=lock): chunk
                           for chunk in todo}
                finished = 0
                for future in as_completed(futures):
                    entry = future.result()
                    _accumulate(entry)
                    finished += 1
                    if entry["status"] in (STATUS_RETRYABLE, STATUS_FATAL):
                        print(f"[build_kg] 失败 {entry['chunk_id']}"
                              f"（{entry['status']}）：{(entry['error'] or '')[:120]}")
                    if finished % 20 == 0:
                        print(f"[build_kg] 进度 {finished}/{len(todo)}，"
                              f"实体 {stats['entities']}，关系 {stats['relationships']}")
        else:
            for index, chunk in enumerate(todo):
                entry = self._handle_chunk(chunk, dry_run=dry_run, store=store,
                                           raw_log=raw_log, lock=lock)
                _accumulate(entry)
                if entry["status"] in (STATUS_RETRYABLE, STATUS_FATAL):
                    print(f"[build_kg] 失败 {entry['chunk_id']}"
                          f"（{entry['status']}）：{(entry['error'] or '')[:120]}")
                if (index + 1) % 20 == 0:
                    print(f"[build_kg] 进度 {index + 1}/{len(todo)}，"
                          f"实体 {stats['entities']}，关系 {stats['relationships']}")

        print(f"[build_kg] 完成：{stats}")
        return stats

    def _raw_log_path(self) -> Path:
        directory = DEFAULT_INTERIM / "raw"
        directory.mkdir(parents=True, exist_ok=True)
        return directory / f"extraction_{self.book or 'unknown'}.jsonl"


# ============ Checkpoint（任务 02 / 05） ============

class CheckpointIncompatible(RuntimeError):
    pass


class CheckpointStore:
    """带数据版本与内容指纹的断点文件；写入使用临时文件 + 原子替换。"""

    def __init__(self, path: Path, *, book: str = "", dataset_version: str = "",
                 source_sha256: str = ""):
        self.path = Path(path)
        self.book = book
        self.dataset_version = dataset_version
        self.source_sha256 = source_sha256
        self.completed: Dict[str, str] = {}
        self.failed: Dict[str, Dict[str, Any]] = {}
        self.loaded = False
        self.incompatibility = ""

    def _signature(self) -> Dict[str, Any]:
        return {"format": CHECKPOINT_FORMAT, "book": self.book,
                "dataset_version": self.dataset_version,
                "source_sha256": self.source_sha256}

    def load(self) -> Dict[str, Any]:
        if not self.path.exists():
            self.loaded = True
            return self._signature()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            self.incompatibility = f"断点文件无法解析：{exc}"
            self.loaded = True
            return self._signature()
        if isinstance(data, list):  # 阶段一/二格式：裸 chunk_id 列表
            self.incompatibility = (
                "断点文件是旧格式（只有 chunk_id 列表），不包含数据版本与内容指纹；"
                "切块参数或原文变化后可能跳过新内容。请删除该文件或换用新的 chunks 文件。")
            self.loaded = True
            return self._signature()
        expected = self._signature()
        for key in ("dataset_version", "source_sha256"):
            stored = data.get(key)
            if stored and expected[key] and stored != expected[key]:
                self.incompatibility = (
                    f"断点与当前数据不一致：{key} {stored} != {expected[key]}")
        self.completed = dict(data.get("completed") or {})
        self.failed = dict(data.get("failed") or {})
        self.loaded = True
        return data

    def load_or_raise(self) -> None:
        self.load()
        if self.incompatibility:
            raise CheckpointIncompatible(self.incompatibility)

    def is_done(self, chunk_id: str, content_hash: str = "") -> bool:
        stored = self.completed.get(chunk_id)
        if stored is None:
            return False
        if content_hash and stored and stored != content_hash:
            return False  # 同一 ID 正文已变化，视为未完成
        return True

    def failed_ids(self) -> List[str]:
        return list(self.failed)

    def mark_done(self, chunk_id: str, content_hash: str = "", status: str = STATUS_OK,
                  written: Optional[Dict[str, int]] = None) -> None:
        self.completed[chunk_id] = content_hash
        self.failed.pop(chunk_id, None)
        self.save()

    def mark_failed(self, chunk_id: str, status: str, error: str) -> None:
        self.failed[chunk_id] = {
            "status": status, "error": (error or "")[:500],
            "at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")}
        self.save()

    def save(self) -> None:
        payload = {**self._signature(), "completed": self.completed,
                   "failed": self.failed,
                   "updated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)  # 原子替换，避免半写 JSON


def reparse_records(path: Path, limit: Optional[int] = None) -> Dict[str, Any]:
    """只重新解析已保存的原始响应（任务 05：支持"仅重新解析"，不重新调 LLM）。"""
    stats = {"records": 0, "reparsed": 0, "still_invalid": 0,
             "entities": 0, "relationships": 0, "rejected": 0, "examples": []}
    path = Path(path)
    if not path.exists():
        return {"error": f"文件不存在：{path}"}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            if limit is not None and stats["records"] >= limit:
                break
            stats["records"] += 1
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                stats["still_invalid"] += 1
                continue
            raw = record.get("raw") or ""
            data, error = parse_llm_payload(raw)
            if data is None:
                stats["still_invalid"] += 1
                if len(stats["examples"]) < 5:
                    stats["examples"].append({"chunk_id": record.get("chunk_id"),
                                              "error": error})
                continue
            processed = KGBuilder._postprocess(
                KGBuilder.__new__(KGBuilder), data,
                record.get("era") or "射雕", record.get("book") or "")
            stats["reparsed"] += 1
            stats["entities"] += len(processed["entities"])
            stats["relationships"] += len(processed["relationships"])
            stats["rejected"] += len(processed["rejected"])
    return stats


def checkpoint_path_for(chunks_path: Path) -> Path:
    """chunks_神雕侠侣.json -> kg_checkpoint_神雕侠侣.json（阶段一遗留名保持兼容）。"""
    chunks_path = Path(chunks_path)
    stem = chunks_path.stem
    if stem.startswith("chunks"):
        stem = "kg_checkpoint" + stem[len("chunks"):]
    else:
        stem = stem + "_kg_checkpoint"
    return chunks_path.parent / (stem + ".json")


# ============ LLM 客户端 ============

def get_llm_client() -> OpenAI:
    from core.http_client import build_http_client
    settings = get_settings()
    # 必须带 http_client：默认客户端在本机会因 zstd 压缩响应报 APIConnectionError
    return OpenAI(base_url=settings.llm_endpoint, api_key=settings.llm_token or "EMPTY",
                  timeout=settings.request_timeout, max_retries=0,
                  http_client=build_http_client(settings.request_timeout))


# ============ 命令行入口 ============

def _resolve_targets(args) -> List[Path]:
    if args.chunks:
        return [Path(args.chunks)]
    if args.book:
        return [DEFAULT_INTERIM / f"chunks_{args.book}.json"]
    if args.legacy:
        return [DEFAULT_OUT_PATH]
    files = sorted(DEFAULT_INTERIM.glob("chunks_*.json"))
    if not files:
        raise SystemExit(
            f"未找到 {DEFAULT_INTERIM} 下的 chunks_*.json；请先运行 corpus.py，"
            f"或用 --book/--chunks 显式指定（--legacy 可读取阶段一 chunks.json）")
    return files


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM 抽取 + Neo4j 入库（多书、版本化、事务化）")
    parser.add_argument("--chunks", type=str, default=None, help="chunks 文件路径")
    parser.add_argument("--book", type=str, default=None, help="书名（如 神雕侠侣）")
    parser.add_argument("--legacy", action="store_true", help="显式使用阶段一 chunks.json")
    parser.add_argument("--limit", type=int, default=None, help="只处理前 N 块")
    parser.add_argument("--resume", action="store_true", help="断点续跑（旧格式断点会被拒绝）")
    parser.add_argument("--reingest-failed", action="store_true", help="resume 时重试失败块")
    parser.add_argument("--preview", action="store_true",
                        help="只读 chunks 打印统计，不调 LLM、不写库")
    parser.add_argument("--dry-run", action="store_true",
                        help="调用付费 LLM 抽取但不写库（会消耗 token）")
    parser.add_argument("--save-raw", action="store_true",
                        help="保存每次抽取的原始响应到 data/interim/raw/")
    parser.add_argument("--workers", type=int, default=None,
                        help="并发 worker 数（默认读取 LLM_WORKERS，建议 4~8）")
    parser.add_argument("--era", type=str, default=None, help="era 缺省值（不填按书名推断）")
    parser.add_argument("--reparse", type=str, default=None,
                        help="只重新解析 data/interim/raw 下的 jsonl，不调用 LLM、不写库")
    args = parser.parse_args()

    if args.reparse:
        stats = reparse_records(Path(args.reparse), limit=args.limit)
        print(json.dumps(stats, ensure_ascii=False, indent=1))
        return

    targets = _resolve_targets(args)
    llm = None
    embedder = None
    driver = None

    for chunks_path in targets:
        if not Path(chunks_path).exists():
            raise SystemExit(f"找不到 chunks 文件：{chunks_path}")
        chunks = json.loads(Path(chunks_path).read_text(encoding="utf-8"))
        book = chunks[0].get("book", "") if chunks else Path(chunks_path).stem.replace("chunks_", "")
        era = args.era or (chunks[0].get("era") if chunks else None) or infer_era(book) or "射雕"
        manifest = load_manifest(book) or {}
        chunk_version = chunks[0].get("dataset_version") if chunks else None
        dataset_version = (chunk_version
                           or manifest.get("dataset_version")
                           or "legacy")
        source_sha = (manifest.get("source") or {}).get("sha256", "")
        ckpt_path = checkpoint_path_for(Path(chunks_path))

        print(f"[build_kg] 读入 {len(chunks)} 块（{Path(chunks_path).name}），"
              f"book={book}, era={era}, dataset_version={dataset_version}, "
              f"checkpoint={ckpt_path.name}")
        if dataset_version == "legacy":
            print("[build_kg] 注意：该 chunks 文件没有版本信息也没有 manifest，"
                  "按 legacy 处理；其断点（旧格式）会被拒绝 resume。"
                  "如需重跑请先用 corpus.py 重新切块。")

        store = CheckpointStore(ckpt_path, book=book, dataset_version=dataset_version,
                                source_sha256=source_sha)

        if args.preview:
            store.load()
            print(f"[preview] 已完成 {len(store.completed)}，失败 {len(store.failed)}；"
                  f"字符总数 {sum(len(c['text']) for c in chunks)}")
            if store.incompatibility:
                print(f"[preview] 注意：{store.incompatibility}")
            continue

        if not get_env("LLM_TOKEN"):
            raise SystemExit("缺少 LLM_TOKEN，请先复制 .env.example 为 .env 并填写")
        if llm is None:
            llm = get_llm_client()
        if embedder is None:
            embedder = get_embedder()

        if not args.dry_run and driver is None:
            from ingest.data_loader import create_driver
            driver = create_driver()

        builder = KGBuilder(driver=driver if not args.dry_run else None, llm=llm,
                            embedder=embedder, model=get_settings().llm_model,
                            default_era=era, checkpoint_path=ckpt_path,
                            book=book, dataset_version=dataset_version,
                            save_raw=args.save_raw,
                            disable_thinking=get_settings().llm_disable_thinking)
        try:
            builder.run(chunks, limit=args.limit, resume=args.resume,
                        dry_run=args.dry_run, checkpoint=store,
                        reingest_failed=args.reingest_failed,
                        workers=args.workers or get_settings().llm_workers)
        except CheckpointIncompatible as exc:
            raise SystemExit(f"[build_kg] 拒绝 resume：{exc}") from exc
        finally:
            if not args.dry_run and embedder is not None:
                spec = get_embedder().spec
                update_manifest(
                    book,
                    extraction={"model": get_settings().llm_model,
                                "prompt_version": PROMPT_VERSION},
                    embedding={"fingerprint": spec.fingerprint, "kind": spec.kind,
                               "dimension": spec.dimension})

    if driver is not None:
        driver.close()


if __name__ == "__main__":
    main()
