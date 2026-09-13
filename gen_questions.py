# -*- coding: utf-8 -*-
"""生成阶段二三本书评测集：射雕(54) + 神雕(8+补) + 倚天(12+补)，目标 100 题。"""
import json

# 读射雕 54 题（E1 阶段二做的分类评测集）
shediao = json.loads(open('src/eval/questions.json', encoding='utf-8').read())
shediao_qs = shediao['questions'] if isinstance(shediao, dict) else shediao

# 读完整集，抽神雕、倚天题
full = json.loads(open('src/eval/questions_full.json', encoding='utf-8').read())
full_qs = full['questions'] if isinstance(full, dict) else full
shen_yd = [q for q in full_qs if q.get('source_hint') in ('神雕侠侣', '倚天屠龙记')]

# 补充题：神雕 10 题 + 倚天 12 题（基于核心人物关系，答案准确、实体核心）
# 字段：question, category, relation, hop, difficulty, answer_entities, acceptable_answers, source_hint
extra = [
    # ---- 神雕侠侣 补充 ----
    ("郭靖的小女儿是谁？", "亲属", "女儿", 1, "easy", ["郭襄"], ["郭襄"], "神雕侠侣"),
    ("郭靖的大女儿是谁？", "亲属", "女儿", 1, "easy", ["郭芙"], ["郭芙"], "神雕侠侣"),
    ("郭芙的父亲是谁？", "亲属", "父亲", 1, "easy", ["郭靖"], ["郭靖"], "神雕侠侣"),
    ("郭襄的母亲是谁？", "亲属", "母亲", 1, "easy", ["黄蓉"], ["黄蓉"], "神雕侠侣"),
    ("郭芙的母亲是谁？", "亲属", "母亲", 1, "easy", ["黄蓉"], ["黄蓉"], "神雕侠侣"),
    ("杨过的师父是谁？", "师徒", "师父", 1, "easy", ["小龙女"], ["小龙女"], "神雕侠侣"),
    ("小龙女属于哪个门派？", "门派", "所属门派", 1, "easy", ["古墓派"], ["古墓派"], "神雕侠侣"),
    ("杨过的义父欧阳锋的绰号是什么？", "多跳属性", "义父的绰号", 2, "medium", ["西毒"], ["西毒"], "神雕侠侣"),
    ("郭靖的岳父是谁？", "多跳亲属", "岳父", 2, "medium", ["黄药师"], ["黄药师", "东邪"], "神雕侠侣"),
    ("杨过的妻子小龙女属于哪个门派？", "多跳门派", "妻子的门派", 2, "medium", ["古墓派"], ["古墓派"], "神雕侠侣"),
    # ---- 倚天屠龙记 补充 ----
    ("张无忌成为哪个教派的教主？", "门派", "所属门派", 1, "easy", ["明教"], ["明教"], "倚天屠龙记"),
    ("谢逊的师父是谁？", "师徒", "师父", 1, "medium", ["成昆"], ["成昆"], "倚天屠龙记"),
    ("杨逍属于哪个教派？", "门派", "所属门派", 1, "easy", ["明教"], ["明教"], "倚天屠龙记"),
    ("灭绝师太属于哪个门派？", "门派", "所属门派", 1, "easy", ["峨眉派"], ["峨眉派"], "倚天屠龙记"),
    ("张翠山属于哪个门派？", "门派", "所属门派", 1, "easy", ["武当派"], ["武当派"], "倚天屠龙记"),
    ("张无忌的母亲殷素素的丈夫是谁？", "亲属", "丈夫", 1, "easy", ["张翠山"], ["张翠山"], "倚天屠龙记"),
    ("明教的金毛狮王是谁？", "门派", "成员", 1, "easy", ["谢逊"], ["谢逊"], "倚天屠龙记"),
    ("张无忌的父亲张翠山的师父是谁？", "多跳师徒", "父亲的师父", 2, "medium", ["张三丰"], ["张三丰"], "倚天屠龙记"),
    ("张无忌的义父谢逊的师父是谁？", "多跳师徒", "义父的师父", 2, "medium", ["成昆"], ["成昆"], "倚天屠龙记"),
    ("周芷若的师父灭绝师太属于哪个门派？", "多跳门派", "师父的门派", 2, "medium", ["峨眉派"], ["峨眉派"], "倚天屠龙记"),
    ("张三丰的徒弟张翠山是谁的父亲？", "多跳亲属", "徒弟的父亲", 2, "medium", ["张无忌"], ["张无忌"], "倚天屠龙记"),
    ("谢逊的师父成昆的绰号是什么？", "多跳属性", "师父的绰号", 2, "hard", ["混元霹雳手"], ["混元霹雳手"], "倚天屠龙记"),
    ("杨过的师父小龙女的丈夫是谁？", "多跳婚姻", "师父的丈夫", 2, "medium", ["杨过"], ["杨过"], "神雕侠侣"),
    ("郭靖的岳父黄药师的女儿是谁？", "多跳亲属", "岳父的女儿", 2, "medium", ["黄蓉"], ["黄蓉"], "神雕侠侣"),
    ("张无忌的父亲张翠山的师父张三丰创立了什么门派？", "多跳门派", "师父创立的门派", 2, "medium", ["武当派"], ["武当派"], "倚天屠龙记"),
    ("张无忌的义父谢逊的师父成昆的绰号是什么？", "多跳属性", "义父师父的绰号", 2, "hard", ["混元霹雳手"], ["混元霹雳手"], "倚天屠龙记"),
]

# 合并 + 重新编号
merged = list(shediao_qs) + list(shen_yd)
for item in extra:
    merged.append({
        "question": item[0], "category": item[1], "relation": item[2],
        "hop": item[3], "difficulty": item[4],
        "answer_entities": item[5], "acceptable_answers": item[6],
        "source_hint": item[7],
    })

# 重新编号 q001..qNNN
for i, q in enumerate(merged):
    q['id'] = f"q{i+1:03d}"

out = {
    "dataset_name": "金庸三部曲知识图谱多跳问答评测集（阶段二）",
    "version": "3.0",
    "language": "zh-CN",
    "description": f"阶段二评测集：{len(merged)} 题，覆盖射雕/神雕/倚天三本书。射雕题来自 E1 分类评测集，神雕/倚天题来自完整集并补充核心关系题。",
    "scoring_hint": "程序使用 acceptable_answers 做实体命中判断；answer_entities 是规范名称。",
    "questions": merged,
}
open('src/eval/questions_stage2.json', 'w', encoding='utf-8').write(
    json.dumps(out, ensure_ascii=False, indent=1))
print("生成完成，共", len(merged), "题")
from collections import Counter
c = Counter(q.get('source_hint','?') for q in merged)
for b, n in sorted(c.items(), key=lambda x:-x[1]):
    print(f"  {b}: {n} 题")
