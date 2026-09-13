# -*- coding: utf-8 -*-
"""关系清洗：删除描述性指称节点 + 绰号重复节点，让师徒链更干净。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from ingest.data_loader import run_query


# 明确是"称呼/指称"的词，正名不含这些词
NOISE_KEYS = [
    "师父", "师傅", "恩师", "师尊", "道士", "道人", "叫化",
    "大侠", "女侠", "侠客", "老前辈", "道长", "真人",
    "爷爷", "大哥", "二哥", "三哥", "姐姐", "妹妹",
]


def main():
    # 1. 删除含称谓的指称节点
    cond = " OR ".join([f"n.name CONTAINS '{k}'" for k in NOISE_KEYS])
    r1 = run_query(f"MATCH (n) WHERE {cond} DETACH DELETE n RETURN count(n) AS c")
    print(f"1) 删除含称谓的指称节点: {r1[0]['c']} 个")

    # 2. 删除「绰号+正名」节点（长名包含另一个≥2字的短名，如 丹阳子马钰 含 马钰）
    r2 = run_query("""
        MATCH (a:人物), (b:人物)
        WHERE a.name <> b.name
          AND a.name CONTAINS b.name
          AND char_length(b.name) >= 2
        DETACH DELETE a
        RETURN count(a) AS c
    """)
    print(f"2) 删除绰号+正名重复节点: {r2[0]['c']} 个")

    # 3. 矛盾关系清理：夫妻/仇敌/结拜的人不可能是师徒，删除这些错误边
    r3 = run_query("""
        MATCH (a)-[r:MASTER_OF]-(b)
        WHERE EXISTS((a)-[:SPOUSE_OF]-(b))
           OR EXISTS((a)-[:ENEMY_OF]-(b))
           OR EXISTS((a)-[:SWORN_BROTHER_OF]-(b))
        DELETE r
        RETURN count(r) AS c
    """)
    print(f"3) 删除矛盾关系（夫妻/仇敌/结拜不该是师徒）: {r3[0]['c']} 条")

    # 4. 验证：郭靖的师父还剩哪些（入边 MASTER_OF）
    rows = run_query(
        "MATCH (p:人物 {name:$n})<-[r:MASTER_OF]-(x) RETURN x.name AS master ORDER BY master",
        {"n": "郭靖"},
    )
    print(f"\n清理后，郭靖的师父还有 {len(rows)} 个：")
    for x in rows:
        print("  ", x["master"])


if __name__ == "__main__":
    main()
