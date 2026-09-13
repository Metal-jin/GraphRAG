# 鎺ュ彛绾﹀畾鏂囨。锛圛NTERFACE.md锛?

> 鏈枃浠舵槸鍏ㄧ粍鐨?瀵规帴渚濇嵁"銆備换浣曚汉鍦ㄥ啓浠ｇ爜鍓嶏紝鍏堣杩欓噷銆?
> 鍐呭鐢?A 璐熻矗瀹氫箟銆?*鏀规帴鍙ｅ繀椤诲悓姝ユ敼杩欓噷銆?*

---

## 1. 妫€绱㈡柟娉曠粺涓€鎺ュ彛锛歈AMethod

鎵€鏈夋绱㈡柟娉?**蹇呴』**锛?
1. 缁ф壙 `QAMethod`锛堝畾涔夊湪 `src/core/interfaces.py`锛?
2. 璁剧疆 `name`锛堟柟娉曞敮涓€鍚嶅瓧锛?
3. 瀹炵幇 `ask(question, top_k)` 鏂规硶
4. 鐢?`@register(name)` 娉ㄥ唽锛堣 `src/core/registry.py`锛?

**褰撳墠宸叉敞鍐岀殑 5 涓柟娉?*锛?

| 鏂规硶鍚?| 绫诲瀷 | 璇存槑 |
|---|---|---|
| `vector` | 鍩虹嚎 | 绾悜閲忔绱?|
| `library_graphrag` | 鍩虹嚎 | 璋冨簱鍥炬绱?|
| `master_chain` | 棰嗗煙绛栫暐 | 甯堝緬閾炬绱?|
| `sect_agg` | 棰嗗煙绛栫暐 | 闂ㄦ淳鑱氬悎妫€绱?|
| `art_lineage` | 棰嗗煙绛栫暐 | 姝﹀姛浼犳壙妫€绱?|
| `person_relation` | 棰嗗煙绛栫暐 | 浜虹墿鍏崇郴妫€绱紙鐖跺瓙/閰嶅伓/缁撴嫓/浠囨晫锛?|

```python
from core.registry import register
from core.interfaces import QAMethod, Answer

@register("my_method")
class MyMethod(QAMethod):
    name = "my_method"

    def ask(self, question: str, top_k: int = 5) -> Answer:
        # ... 妫€绱?+ 鐢熸垚 ...
        return Answer(answer_text="...", method_name=self.name)
```

## 2. 缁熶竴杩斿洖缁撴瀯锛欰nswer

鎵€鏈夋柟娉曠殑 `ask()` 閮藉繀椤昏繑鍥?`Answer`锛屽瓧娈靛涓嬶細

| 瀛楁 | 绫诲瀷 | 鍚箟 |
|---|---|---|
| `answer_text` | str | 鏈€缁堢瓟妗堟枃鏈?|
| `method_name` | str | 鏂规硶鍚嶏紙鍓嶇鏄剧ず銆佽瘎娴嬭褰曠敤锛?|
| `evidence` | list | 鐢ㄥ埌鐨勮瘉鎹紙鏂囨湰鍧?瀛愬浘/璺緞锛屽墠绔珮浜敤锛?|
| `debug_info` | dict | 璋冭瘯淇℃伅锛堝懡涓簡鍝簺瀹炰綋绛夛級 |
| `raw_context` | str | 鍠傜粰 LLM 鐨勫師濮嬩笂涓嬫枃锛堣瘎娴嬪鐜扮敤锛?|

## 3. 鏁版嵁璇诲彇鎺ュ彛锛歞ata_loader

B 璐熻矗瀹炵幇 `src/ingest/data_loader.py`锛屾彁渚涗互涓嬪嚱鏁帮紝C銆丏 閮介€氳繃瀹冭鏁版嵁锛?

| 鍑芥暟 | 杩斿洖 | 鐢ㄩ€?|
|---|---|---|
| `get_chunks()` | list[dict] | 璇绘墍鏈夋枃鏈潡 |
| `get_graph(era=None)` | dict锛堝惈 nodes銆乪dges锛?| 璇诲疄浣撳叧绯诲浘锛堝彲浼?era 杩囨护鏃朵唬锛?|
| `search_by_vector(question, top_k)` | list[dict] | 鎸夊悜閲忔壘鐩镐技鏂囨湰鍧?|
| `search_by_text(query, top_k)` | list[dict] | 鎸夊叧閿瘝鍏ㄦ枃妫€绱㈡枃鏈潡 |
| `run_query(cypher, params)` | list[dict] | 鎵ц浠绘剰 Cypher锛圖 鐨勯鍩熺瓥鐣ョ敤锛?|

> **鑺傜偣缁撴瀯**锛歚{"id", "name", "type"锛堜汉鐗?闂ㄦ淳/姝﹀姛/鍦扮偣锛? "era", "location"}`
> **杈圭粨鏋?*锛歚{"source", "target", "type"锛圡ASTER_OF/...锛墋`
> **杩斿洖鏍煎紡鐢?B 鍜?C銆丏 绾﹀畾锛孊 涓嶈鑷繁鍩嬪ご鍐欍€?*

---

## 4. 闃舵浜屾柊澧烇細鎰忓浘鍒嗙被鍣紙intent_classifier锛?

鏂囦欢锛歚src/generate/intent_classifier.py`

**浣滅敤**锛氳瘑鍒棶棰樼被鍨嬶紝鑷姩璺敱鍒伴鍩熺瓥鐣ワ紝鐢ㄦ埛鏃犻渶鎵嬪姩閫夋柟娉曘€?

```python
from generate.intent_classifier import classify

intent = classify("閮潠鐨勫笀鐖剁殑甯堢埗鏄皝")
# intent.intent       -> "person"锛堣涔夋剰鍥撅級
# intent.method_name  -> "master_chain"锛堣矾鐢卞埌鐨勬柟娉曪級
# intent.seed_entity  -> "閮潠"锛堣瘑鍒殑璧峰瀹炰綋锛?
# intent.injection    -> "path"锛堟敞鍏ュ舰寮忥級
# intent.reason       -> "鍛戒腑浜虹墿瀹炰綋銆岄儹闈栥€嶄笖鍚笀寰掑叧绯诲叧閿瘝"锛堣В閲婏級
```

**鎰忓浘 鈫?璺敱 鈫?娉ㄥ叆 鏄犲皠鍏崇郴**锛?

| 鎰忓浘锛坕ntent锛?| 璺敱锛坢ethod_name锛?| 娉ㄥ叆褰㈠紡锛坕njection锛?|
|---|---|---|
| `person`锛堜汉鐗╁叧绯伙級 | `master_chain` | `path`锛堝叧绯昏矾寰勶級 |
| `person_relation`锛堢埗瀛?閰嶅伓/缁撴嫓/浠囨晫锛?| `person_relation` | `triples`锛堜笁鍏冪粍锛?|
| `sect`锛堥棬娲捐仛鍚堬級 | `sect_agg` | `subgraph`锛堝瓙鍥炬憳瑕侊級 |
| `art`锛堟鍔熶紶鎵匡級 | `art_lineage` | `path`锛堝叧绯昏矾寰勶級 |
| `general`锛堥€氱敤鍏滃簳/缁煎悎姣旇緝锛?| `vector` | `text`锛堝師鏂囷級 |

---

## 5. 闃舵浜屾柊澧烇細鐭ヨ瘑娉ㄥ叆灞傦紙injection锛?

鏂囦欢锛歚src/generate/injection.py`

**浣滅敤**锛氭妸妫€绱㈠埌鐨勮瘉鎹寜鎰忓浘杞垚鏈€閫傚悎 LLM 鐨勬敞鍏ュ舰寮忋€?

```python
from generate.injection import build_context

context = build_context(method_name, evidence, raw_context)
# master_chain  -> 鍏崇郴璺緞锛?閮潠锛堢0浠ｏ級\n绗?浠ｅ笀鐖讹細娲竷鍏€侀┈閽扳€?
# sect_agg      -> 瀛愬浘鎽樿锛?閮潠锛堜細锛氶檷榫欏崄鍏帉锛塡n榛勮搲锛堜細锛氭墦鐙楁娉曪級"
# art_lineage   -> 鍏崇郴璺緞锛?娲竷鍏?--浼犳壙--> 閮潠"
# vector/鍏朵粬   -> 鍘熸枃锛堢洿鎺ョ敤 raw_context锛?
```

---

## 6. 闃舵浜屾柊澧烇細鍏ㄨ嚜鍔ㄩ棶绛斿叆鍙?ask_auto

鏂囦欢锛歚src/generate/service.py`

**浣滅敤**锛歚鎰忓浘璇嗗埆 鈫?璺敱 鈫?娉ㄥ叆 鈫?鐢熸垚` 鍏ㄨ嚜鍔ㄩ摼璺紝鏄樁娈典簩鐨勬牳蹇冨叆鍙ｃ€?

```python
from src.generate.service import ask_auto

result = ask_auto("涓愬府鏈夊摢浜涚粷瀛?)
```

**杩斿洖瀛楁**锛堝湪鍘?Answer 鍩虹涓婃墿灞曪級锛?

| 瀛楁 | 绫诲瀷 | 鍚箟 |
|---|---|---|
| `answer_text` | str | LLM 鐢熸垚鐨勬渶缁堢瓟妗?|
| `method_name` | str | 瀹為檯璺敱鍒扮殑妫€绱㈡柟娉曞悕 |
| `intent` | str | 璇嗗埆鍑虹殑璇箟鎰忓浘锛坧erson/sect/art/general锛?|
| `seed_entity` | str | 璇嗗埆鐨勮捣濮嬪疄浣擄紙鍙兘涓虹┖锛?|
| `injection` | str | 浣跨敤鐨勬敞鍏ュ舰寮忥紙path/subgraph/text锛?|
| `reason` | str | 鍒嗙被渚濇嵁锛堝彲瑙ｉ噴鎬с€佽皟璇曠敤锛?|
| `evidence` | list | 妫€绱㈠埌鐨勮瘉鎹?|
| `debug_info` | dict | 璋冭瘯淇℃伅 |
| `raw_context` | str | **娉ㄥ叆鍚?*鍠傜粰 LLM 鐨勪笂涓嬫枃锛堟敞鎰忥細涓嶆槸鍘熷 raw_context锛?|

> 鏃х殑 `ask_question(question, method_name, top_k)` 淇濈暀锛屽悜鍚庡吋瀹癸紙鎵嬪姩鎸囧畾鏂规硶锛夈€?

---

## 7. 鏂规硶璋冪敤鏂瑰紡

```python
from core.registry import get_method

# 鏂瑰紡涓€锛氭墜鍔ㄦ寚瀹氭柟娉曪紙闃舵涓€鐢ㄦ硶锛屼繚鐣欙級
method = get_method("master_chain")
answer = method.ask("閮潠鐨勫笀鐖舵槸璋侊紵")

# 鏂瑰紡浜岋細鍏ㄨ嚜鍔紙闃舵浜屾帹鑽愶紝鐢ㄦ埛鏃犻渶閫夋柟娉曪級
from src.generate.service import ask_auto
result = ask_auto("閮潠鐨勫笀鐖舵槸璋侊紵")
```

## 8. 鏂板鏂规硶鐨勬楠?

1. 鍦?`src/methods/` 涓嬫柊寤烘枃浠讹紝瀹炵幇 `QAMethod`
2. 鐢?`@register(name)` 娉ㄥ唽
3. 鍦?`src/methods/__init__.py` 閲?`import` 璇ユā鍧楋紝瑙﹀彂娉ㄥ唽
4. 鏇存柊鏈枃浠?

## 9. E1 璇勬祴鎺ュ彛

`src/eval/metrics.py` 鎻愪緵 `evaluate_result(question, answer_text, evidence)`锛岃繑鍥?`entity_hit`銆乣path_completeness`銆乣evidence_sufficiency` 鍜?`evidence_count`銆俙src/eval/run_compare.py` 浼氬湪閫愰 `debug_info` 鍙婃姤鍛婁腑淇濈暀杩欎簺鎸囨爣锛屽苟鎸変汉鐗┿€佹鍔熴€侀棬娲俱€佺患鍚堝洓绫绘眹鎬汇€俙src/eval/injection_experiment.py` 鐢ㄧ粺涓€璇勬祴闆嗙绾挎瘮杈?`triples`銆乣path`銆乣subgraph` 涓夌鐭ヨ瘑娉ㄥ叆褰㈠紡銆?
---

## 9. 闃舵浜屾柊澧烇細瀹炰綋瀵归綈绯荤粺锛坋ntity_alignment锛?

鏂囦欢锛歚src/ingest/entity_alignment.py`锛圔 缁存姢锛?

**浣滅敤**锛氭妸鍚屼竴瀹炰綋鐨勫绉嶇О鍛煎綊骞跺埌鍚屼竴鑺傜偣 + 寤虹珛璺ㄤ功琛€缂橈紙DESCENDANT_OF锛夈€?

**涓夊眰瀵归綈鏈哄埗**锛?

| 灞?| 鏈哄埗 | 瑙﹀彂 | 钀藉簱锛?|
|---|---|---|---|
| 鈶?瑙勫垯灞?`RuleNormalizer` | 绉拌皳鍚庣紑鍓ョ锛?娲府涓?鈫?娲?锛? 濮撴皬褰掍竴锛?璇歌憶姘?鈫?璇歌憶"锛?| 鑷姩 | 鏄?|
| 鈶?璇嶅吀灞?`AliasDictionary` | 浜哄伐鍒悕璇嶅吀锛坄data/processed/alias_dict.json`锛?| 鑷姩 | 鏄?|
| 鈶?鐩镐技搴﹀眰 `SimilarityAligner` | rapidfuzz + pypinyin 鍙岃矾鎵撳垎 | 鑷姩 | **鍚︼紙浠?CSV 鍊欓€夛級** |

**瀹夊叏璁捐**锛氱浉浼煎害灞傚湪"鍚屽涓嶅悓浜?涓婃湁澶╃劧缂洪櫡锛堝"閮含"vs"閮潠"锛夛紝鏁呴粯璁ゅ彧鐢熸垚鍊欓€?CSV锛涗汉宸ュ鏍稿悗鍔犲叆璇嶅吀灞傛墠鑳借惤搴撱€?

**CLI 鐢ㄦ硶**锛?

```powershell
$env:PYTHONPATH='D:\hu\GraphRAG\src'
& "D:\.conda\envs\hu\python.exe" src/ingest/entity_alignment.py --dry-run          # 棰勮
& "D:\.conda\envs\hu\python.exe" src/ingest/entity_alignment.py --apply           # 钀藉簱锛堣瘝鍏?瑙勫垯锛?
& "D:\.conda\envs\hu\python.exe" src/ingest/entity_alignment.py --apply --include-similarity  # 鍚浉浼煎害
& "D:\.conda\envs\hu\python.exe" src/ingest/entity_alignment.py --descendants-only # 鍙窇 DESCENDANT_OF
& "D:\.conda\envs\hu\python.exe" src/ingest/entity_alignment.py --labels 浜虹墿      # 鍙榻愪汉鐗?label
```

鍊欓€?CSV 璺緞锛歚data/interim/alignment_candidates.csv`

---

## 10. 闃舵浜屾柊澧炲叧绯荤被鍨嬶細`DESCENDANT_OF`

**浣滅敤**锛氳法涔﹁缂橈紙D 缁?榛勮～濂冲瓙鈫掓潹杩?绫婚棶棰樼敤锛夈€?

**鐢熸垚鏂瑰紡**锛欱 鐨?`entity_alignment.py` 鍚庡鐞嗘壂鎻忓疄浣?description 瀛楁涓殑 "X涔嬪悗/涔嬪コ/涔嬪瓙/鍚庝汉"妯″紡 + 澶у閿氬畾锛岃緭鍑哄€欓€変笁鍏冪粍 (ancestor, descendant, kind)锛屽箓绛夎惤搴撱€?

**鏌ヨ绀轰緥**锛?

```python
from src.ingest.data_loader import run_query

# 娌?DESCENDANT_OF 閾捐矾杩芥函浠绘剰鍚庝汉
run_query("""
    MATCH (ancestor:浜虹墿 {name: $a})<-[:DESCENDANT_OF*1..5]-(d:浜虹墿)
    RETURN d.name AS descendant
""", {"a": "鏉ㄨ繃"})
```
