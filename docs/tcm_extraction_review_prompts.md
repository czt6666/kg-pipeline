# TCM 抽取结果审阅 Prompt 集（一篇文档一条独立 prompt）


---

## tcm_neike_trial_0000

```
## 抽取规则

### 实体类型

- 疾病：病名。例：感冒、消渴、胸痹、太阳病。
- 证候：对一组症状的病理概括，通常以"证"结尾或可补"证"字；疾病"辨证论治"下的分型标题一律为证候。例：风寒束表证、脾虚湿盛证。
- 症状：患者可感或医生可察的单一临床表现，含舌象、脉象。例：恶寒、口苦、苔白腻、脉浮紧。
- 治法功效：治疗原则或方药作用。证候后的"治法"与方药后的"功效"共用此类型，由关系名区分角色。例：辛温解表、健脾化湿、宣肺平喘。
- 方剂：例：麻黄汤、参苓白术散。
- 中药：例：麻黄、桂枝、炙甘草。
- 性味：每个性或味单独一个实体。例：辛、温、苦、寒。
- 脏腑经络：例：肺、脾、肾、足太阳膀胱经。

### 关系

| relation | 头类型 | 尾类型 | 含义 | 常见文本线索 |
|---|---|---|---|---|
| 分型 | 疾病 | 证候 | 疾病分型为证候 | 辨证论治下的分型标题 |
| 表现为 | 证候 | 症状 | 证候表现为症状 | "症状：""临床表现：""症见" |
| 治法 | 证候 | 治法功效 | 证候的治法 | "治法：""治宜""当以……法" |
| 方用 | 证候 | 方剂 | 证候所用方剂 | "方药：""代表方：""某方主之" |
| 病位 | 证候 | 脏腑经络 | 证候的病位 | "病位在""病在""病位主要在" |
| 组成 | 方剂 | 中药 | 方剂由中药组成 | "组成：""常用药：""方中……" |
| 功效 | 方剂 或 中药 | 治法功效 | 方剂或中药的功效 | "功效：""功能：""本方……""某药……以……" |
| 性味 | 中药 | 性味 | 中药的性味 | "性味：""味辛，性温" |
| 归经 | 中药 | 脏腑经络 | 中药归经 | "归经：""入肺经" |
| 主治 | 中药 | 症状 / 疾病 / 证候 | 中药主治 | "主治：""治……""用于……" |

只抽取正文明确写出的内容，不因已有医学知识补全；症状按顿号/逗号拆成独立短语；证机概要/病机等描述性语句不作为实体。

原文：
所属疾病：反胃


反胃是指以饮食入胃，宿食不化，经过良久，由胃反出为主症的病证。东汉•张仲景《金匮要略》称为“胃反”。北宋《太平圣惠方•第四十七卷》称为“反胃”。西医学中的幽门梗阻、胃癌等，可参照本节辨证论治。

临床特征是朝食暮吐，暮食朝吐。病因多由饮食不当，饥饱无常，或嗜食生冷，损及脾阳，或忧愁思虑，有伤脾胃，中焦阳气不振，寒从内生，而致脾胃虚寒，病情缠绵，终致脾胃衰败，胃中无火，不能腐熟水谷，饮食入胃，停留不化，逆而向上，尽吐而出。《景岳全书•反胃》指出：“或以酷饮无度，伤于酒湿，或以纵食生冷，败其真阳，或因七情忧郁，竭其中气。总之，无非内伤之甚，致损伤胃气而然。”

治疗原则在于温中健脾，降逆和胃。若反复呕吐，津气并虚，加益气养阴之品；日久不愈，加温补肾阳之法。兼气滞痰结者，治当行气化痰；兼阳虚停饮者，治当通阳化饮；而瘀结成毒者，治当散结解毒。

脾胃虚寒临床表现：食后脘腹胀满，朝食暮吐，暮食朝吐，宿谷不化，吐后则舒，神疲乏力，面色清白，手足不温，大便溏少，舌质淡，苔白腻，脉细缓无力。

证机概要：脾胃阳虚，宿食不化，停滞胃中，胃气上逆。

治法：温中健脾，和胃降逆。

代表方：丁香透膈汤。

常用药：人参、白术、炙甘草健脾益气；丁香、半夏、木香、香附温中和胃降逆；砂仁、白豆蔻、神曲、麦芽醒脾化食。

若胃虚气逆，呕吐甚者，加旋覆花、代赭石；吐甚而气阴耗伤者，去丁香、砂仁、白豆蔻，加沙参、麦冬；阳虚停饮，胸膈不利者，加桂枝、附子、生姜等。胃气大虚者，用大半夏汤加味；气滞痰结，心下痞硬，暖气者，用旋覆代赭汤加减。


抽取结果：
entities:
{"local_id": "e1", "name": "反胃", "type": "疾病", "mentions": ["反胃", "胃反"]}
{"local_id": "e2", "name": "脾胃虚寒", "type": "证候", "mentions": ["脾胃虚寒"]}
{"local_id": "e3", "name": "食后脘腹胀满", "type": "症状", "mentions": ["食后脘腹胀满"]}
{"local_id": "e4", "name": "朝食暮吐", "type": "症状", "mentions": ["朝食暮吐"]}
{"local_id": "e5", "name": "暮食朝吐", "type": "症状", "mentions": ["暮食朝吐"]}
{"local_id": "e6", "name": "宿谷不化", "type": "症状", "mentions": ["宿谷不化"]}
{"local_id": "e7", "name": "吐后则舒", "type": "症状", "mentions": ["吐后则舒"]}
{"local_id": "e8", "name": "神疲乏力", "type": "症状", "mentions": ["神疲乏力"]}
{"local_id": "e9", "name": "面色清白", "type": "症状", "mentions": ["面色清白"]}
{"local_id": "e10", "name": "手足不温", "type": "症状", "mentions": ["手足不温"]}
{"local_id": "e11", "name": "大便溏少", "type": "症状", "mentions": ["大便溏少"]}
{"local_id": "e12", "name": "舌质淡", "type": "症状", "mentions": ["舌质淡"]}
{"local_id": "e13", "name": "苔白腻", "type": "症状", "mentions": ["苔白腻"]}
{"local_id": "e14", "name": "脉细缓无力", "type": "症状", "mentions": ["脉细缓无力"]}
{"local_id": "e15", "name": "温中健脾", "type": "治法功效", "mentions": ["温中健脾"]}
{"local_id": "e16", "name": "和胃降逆", "type": "治法功效", "mentions": ["和胃降逆", "降逆和胃"]}
{"local_id": "e17", "name": "丁香透膈汤", "type": "方剂", "mentions": ["丁香透膈汤"]}
{"local_id": "e18", "name": "人参", "type": "中药", "mentions": ["人参"]}
{"local_id": "e19", "name": "白术", "type": "中药", "mentions": ["白术"]}
{"local_id": "e20", "name": "炙甘草", "type": "中药", "mentions": ["炙甘草"]}
{"local_id": "e21", "name": "丁香", "type": "中药", "mentions": ["丁香"]}
{"local_id": "e22", "name": "半夏", "type": "中药", "mentions": ["半夏"]}
{"local_id": "e23", "name": "木香", "type": "中药", "mentions": ["木香"]}
{"local_id": "e24", "name": "香附", "type": "中药", "mentions": ["香附"]}
{"local_id": "e25", "name": "砂仁", "type": "中药", "mentions": ["砂仁"]}
{"local_id": "e26", "name": "白豆蔻", "type": "中药", "mentions": ["白豆蔻"]}
{"local_id": "e27", "name": "神曲", "type": "中药", "mentions": ["神曲"]}
{"local_id": "e28", "name": "麦芽", "type": "中药", "mentions": ["麦芽"]}
{"local_id": "e29", "name": "健脾益气", "type": "治法功效", "mentions": ["健脾益气"]}
{"local_id": "e30", "name": "温中和胃降逆", "type": "治法功效", "mentions": ["温中和胃降逆"]}
{"local_id": "e31", "name": "醒脾化食", "type": "治法功效", "mentions": ["醒脾化食"]}
triples:
{"head": "e1", "relation": "分型", "tail": "e2", "pid": null, "kind": "relational", "flipped": false}
{"head": "e2", "relation": "表现为", "tail": "e3", "pid": null, "kind": "relational", "flipped": false}
{"head": "e2", "relation": "表现为", "tail": "e4", "pid": null, "kind": "relational", "flipped": false}
{"head": "e2", "relation": "表现为", "tail": "e5", "pid": null, "kind": "relational", "flipped": false}
{"head": "e2", "relation": "表现为", "tail": "e6", "pid": null, "kind": "relational", "flipped": false}
{"head": "e2", "relation": "表现为", "tail": "e7", "pid": null, "kind": "relational", "flipped": false}
{"head": "e2", "relation": "表现为", "tail": "e8", "pid": null, "kind": "relational", "flipped": false}
{"head": "e2", "relation": "表现为", "tail": "e9", "pid": null, "kind": "relational", "flipped": false}
{"head": "e2", "relation": "表现为", "tail": "e10", "pid": null, "kind": "relational", "flipped": false}
{"head": "e2", "relation": "表现为", "tail": "e11", "pid": null, "kind": "relational", "flipped": false}
{"head": "e2", "relation": "表现为", "tail": "e12", "pid": null, "kind": "relational", "flipped": false}
{"head": "e2", "relation": "表现为", "tail": "e13", "pid": null, "kind": "relational", "flipped": false}
{"head": "e2", "relation": "表现为", "tail": "e14", "pid": null, "kind": "relational", "flipped": false}
{"head": "e2", "relation": "治法", "tail": "e15", "pid": null, "kind": "relational", "flipped": false}
{"head": "e2", "relation": "治法", "tail": "e16", "pid": null, "kind": "relational", "flipped": false}
{"head": "e2", "relation": "方用", "tail": "e17", "pid": null, "kind": "relational", "flipped": false}
{"head": "e17", "relation": "组成", "tail": "e18", "pid": null, "kind": "relational", "flipped": false}
{"head": "e17", "relation": "组成", "tail": "e19", "pid": null, "kind": "relational", "flipped": false}
{"head": "e17", "relation": "组成", "tail": "e20", "pid": null, "kind": "relational", "flipped": false}
{"head": "e17", "relation": "组成", "tail": "e21", "pid": null, "kind": "relational", "flipped": false}
{"head": "e17", "relation": "组成", "tail": "e22", "pid": null, "kind": "relational", "flipped": false}
{"head": "e17", "relation": "组成", "tail": "e23", "pid": null, "kind": "relational", "flipped": false}
{"head": "e17", "relation": "组成", "tail": "e24", "pid": null, "kind": "relational", "flipped": false}
{"head": "e17", "relation": "组成", "tail": "e25", "pid": null, "kind": "relational", "flipped": false}
{"head": "e17", "relation": "组成", "tail": "e26", "pid": null, "kind": "relational", "flipped": false}
{"head": "e17", "relation": "组成", "tail": "e27", "pid": null, "kind": "relational", "flipped": false}
{"head": "e17", "relation": "组成", "tail": "e28", "pid": null, "kind": "relational", "flipped": false}
{"head": "e18", "relation": "功效", "tail": "e29", "pid": null, "kind": "relational", "flipped": false}
{"head": "e19", "relation": "功效", "tail": "e29", "pid": null, "kind": "relational", "flipped": false}
{"head": "e20", "relation": "功效", "tail": "e29", "pid": null, "kind": "relational", "flipped": false}
{"head": "e21", "relation": "功效", "tail": "e30", "pid": null, "kind": "relational", "flipped": false}
{"head": "e22", "relation": "功效", "tail": "e30", "pid": null, "kind": "relational", "flipped": false}
{"head": "e23", "relation": "功效", "tail": "e30", "pid": null, "kind": "relational", "flipped": false}
{"head": "e24", "relation": "功效", "tail": "e30", "pid": null, "kind": "relational", "flipped": false}
{"head": "e25", "relation": "功效", "tail": "e31", "pid": null, "kind": "relational", "flipped": false}
{"head": "e26", "relation": "功效", "tail": "e31", "pid": null, "kind": "relational", "flipped": false}
{"head": "e27", "relation": "功效", "tail": "e31", "pid": null, "kind": "relational", "flipped": false}
{"head": "e28", "relation": "功效", "tail": "e31", "pid": null, "kind": "relational", "flipped": false}

我现在在做中医知识图谱的抽取。规则、原文、结果在上面。你来评判一下有没有多抽（不该抽的抽了）、少抽（该抽的漏了）、抽错（实体归错类、关系头尾/方向错、三元组语义错），并指出原文哪一句对应哪个问题。
```


---

## tcm_neike_trial_0001

```
## 抽取规则

### 实体类型

- 疾病：病名。例：感冒、消渴、胸痹、太阳病。
- 证候：对一组症状的病理概括，通常以"证"结尾或可补"证"字；疾病"辨证论治"下的分型标题一律为证候。例：风寒束表证、脾虚湿盛证。
- 症状：患者可感或医生可察的单一临床表现，含舌象、脉象。例：恶寒、口苦、苔白腻、脉浮紧。
- 治法功效：治疗原则或方药作用。证候后的"治法"与方药后的"功效"共用此类型，由关系名区分角色。例：辛温解表、健脾化湿、宣肺平喘。
- 方剂：例：麻黄汤、参苓白术散。
- 中药：例：麻黄、桂枝、炙甘草。
- 性味：每个性或味单独一个实体。例：辛、温、苦、寒。
- 脏腑经络：例：肺、脾、肾、足太阳膀胱经。

### 关系

| relation | 头类型 | 尾类型 | 含义 | 常见文本线索 |
|---|---|---|---|---|
| 分型 | 疾病 | 证候 | 疾病分型为证候 | 辨证论治下的分型标题 |
| 表现为 | 证候 | 症状 | 证候表现为症状 | "症状：""临床表现：""症见" |
| 治法 | 证候 | 治法功效 | 证候的治法 | "治法：""治宜""当以……法" |
| 方用 | 证候 | 方剂 | 证候所用方剂 | "方药：""代表方：""某方主之" |
| 病位 | 证候 | 脏腑经络 | 证候的病位 | "病位在""病在""病位主要在" |
| 组成 | 方剂 | 中药 | 方剂由中药组成 | "组成：""常用药：""方中……" |
| 功效 | 方剂 或 中药 | 治法功效 | 方剂或中药的功效 | "功效：""功能：""本方……""某药……以……" |
| 性味 | 中药 | 性味 | 中药的性味 | "性味：""味辛，性温" |
| 归经 | 中药 | 脏腑经络 | 中药归经 | "归经：""入肺经" |
| 主治 | 中药 | 症状 / 疾病 / 证候 | 中药主治 | "主治：""治……""用于……" |

只抽取正文明确写出的内容，不因已有医学知识补全；症状按顿号/逗号拆成独立短语；证机概要/病机等描述性语句不作为实体。

原文：
所属疾病：呃逆

呃逆是指气逆上冲，喉间呃呃连声，声短而频，不能自止为主症的疾病。西医学中的单纯性膈肌痉挛，以及胃炎、胃肠神经官能症与胸腹手术等引起的膈肌痉挛，可参照本节辨证论治。

呃逆俗称“打嗝”，古称“哕”，又称“哕逆”。《黄帝内经》首先提出其病位在胃，并与感受寒气及胃失和降有关。如《素问•宣明五气》曰：“胃为气逆，为哕。”《灵枢•口问》日：“谷人于胃，胃气上注于肺，今有故寒气与新谷气，俱还入于胃，新故相乱，真邪相攻，气并相逆，复出于胃，故为哕。”并认识到呃逆也为病危征兆，如《素问 •宝命全形论》日：“病深者，其声哕。”《灵枢 •杂病》载有三种简易疗法：“哕，以草刺鼻，嚏，嚏而已；无息而疾迎引之，立已；大惊之，亦可已。”

东汉 •张仲景《金匮要略•呕吐哕下利病脉证治》中将呃逆分为三种：一为实证，即“哕而腹满，视其前后，知何部不利，利之即愈”；二为寒证，即“干呕哕，若手足厥者，橘皮汤主之”；三为虚热证，即“哕逆者，橘皮竹茹汤主之”。此为后世分寒热虚实辨治奠定了基础。

唐•王焘《外台秘要》曰：“伏热在胃，令人胸满，胸满则气逆，气逆则哕。”宋•陈无择《三因极一病证方论•哕逆论证》曰：“大率胃实即噫，胃虚则哕，此由胃中虚，膈上热，故哕。”

指出呃逆与膈相关。元•朱丹溪首先使用“呃逆”病名，但尚与咳逆混称。

明•张景岳正式确立了呃逆病名，澄清了有关混乱的称谓。如《景岳全书•呃逆》云：“哕者，呃逆也，非咳逆也；咳逆者，咳嗽之甚者也，非呃逆也；干呕者，无物之吐，即呕也，非哕也；噫者，饱食之息，即暖气也，非咳逆也。”清•李用粹《证治汇补 •呃逆》谓：“治当降气化痰和胃为主，随其所感而用药。气逆者，疏导之；食停者，消化之；痰滞者，涌吐之；热郁者，清下之；血瘀者，破导之；若汗吐下后，服凉药过多者，当温补；阴火上冲者，当平补；虚而夹热者，当凉补。”对本病治疗提出了系统法则，至今仍有重要价值。

抽取结果：
entities:
{"local_id": "e1", "name": "呃逆", "type": "疾病", "mentions": ["呃逆"]}
{"local_id": "e2", "name": "气逆上冲", "type": "症状", "mentions": ["气逆上冲"]}
{"local_id": "e3", "name": "喉间呃呃连声", "type": "症状", "mentions": ["喉间呃呃连声"]}
{"local_id": "e4", "name": "声短而频", "type": "症状", "mentions": ["声短而频"]}
{"local_id": "e5", "name": "不能自止", "type": "症状", "mentions": ["不能自止"]}
{"local_id": "e6", "name": "胃", "type": "脏腑经络", "mentions": ["胃"]}
{"local_id": "e7", "name": "肺", "type": "脏腑经络", "mentions": ["肺"]}
{"local_id": "e8", "name": "实证", "type": "证候", "mentions": ["实证"]}
{"local_id": "e9", "name": "腹满", "type": "症状", "mentions": ["腹满"]}
{"local_id": "e10", "name": "寒证", "type": "证候", "mentions": ["寒证"]}
{"local_id": "e11", "name": "干呕哕", "type": "症状", "mentions": ["干呕哕"]}
{"local_id": "e12", "name": "手足厥", "type": "症状", "mentions": ["手足厥"]}
{"local_id": "e13", "name": "橘皮汤", "type": "方剂", "mentions": ["橘皮汤"]}
{"local_id": "e14", "name": "虚热证", "type": "证候", "mentions": ["虚热证"]}
{"local_id": "e15", "name": "哕逆", "type": "症状", "mentions": ["哕逆"]}
{"local_id": "e16", "name": "橘皮竹茹汤", "type": "方剂", "mentions": ["橘皮竹茹汤"]}
{"local_id": "e17", "name": "胸满", "type": "症状", "mentions": ["胸满"]}
{"local_id": "e18", "name": "膈", "type": "脏腑经络", "mentions": ["膈"]}
{"local_id": "e19", "name": "降气化痰和胃", "type": "治法功效", "mentions": ["降气化痰和胃"]}
{"local_id": "e20", "name": "疏导", "type": "治法功效", "mentions": ["疏导"]}
{"local_id": "e21", "name": "消化", "type": "治法功效", "mentions": ["消化"]}
{"local_id": "e22", "name": "涌吐", "type": "治法功效", "mentions": ["涌吐"]}
{"local_id": "e23", "name": "清下", "type": "治法功效", "mentions": ["清下"]}
{"local_id": "e24", "name": "破导", "type": "治法功效", "mentions": ["破导"]}
{"local_id": "e25", "name": "温补", "type": "治法功效", "mentions": ["温补"]}
{"local_id": "e26", "name": "平补", "type": "治法功效", "mentions": ["平补"]}
{"local_id": "e27", "name": "凉补", "type": "治法功效", "mentions": ["凉补"]}
triples:
{"head": "e1", "relation": "分型", "tail": "e8", "pid": null, "kind": "relational", "flipped": false}
{"head": "e8", "relation": "表现为", "tail": "e9", "pid": null, "kind": "relational", "flipped": false}
{"head": "e1", "relation": "分型", "tail": "e10", "pid": null, "kind": "relational", "flipped": false}
{"head": "e10", "relation": "表现为", "tail": "e11", "pid": null, "kind": "relational", "flipped": false}
{"head": "e10", "relation": "表现为", "tail": "e12", "pid": null, "kind": "relational", "flipped": false}
{"head": "e10", "relation": "方用", "tail": "e13", "pid": null, "kind": "relational", "flipped": false}
{"head": "e1", "relation": "分型", "tail": "e14", "pid": null, "kind": "relational", "flipped": false}
{"head": "e14", "relation": "表现为", "tail": "e15", "pid": null, "kind": "relational", "flipped": false}
{"head": "e14", "relation": "方用", "tail": "e16", "pid": null, "kind": "relational", "flipped": false}

我现在在做中医知识图谱的抽取。规则、原文、结果在上面。你来评判一下有没有多抽（不该抽的抽了）、少抽（该抽的漏了）、抽错（实体归错类、关系头尾/方向错、三元组语义错），并指出原文哪一句对应哪个问题。
```


---

## tcm_neike_trial_0002

```
## 抽取规则

### 实体类型

- 疾病：病名。例：感冒、消渴、胸痹、太阳病。
- 证候：对一组症状的病理概括，通常以"证"结尾或可补"证"字；疾病"辨证论治"下的分型标题一律为证候。例：风寒束表证、脾虚湿盛证。
- 症状：患者可感或医生可察的单一临床表现，含舌象、脉象。例：恶寒、口苦、苔白腻、脉浮紧。
- 治法功效：治疗原则或方药作用。证候后的"治法"与方药后的"功效"共用此类型，由关系名区分角色。例：辛温解表、健脾化湿、宣肺平喘。
- 方剂：例：麻黄汤、参苓白术散。
- 中药：例：麻黄、桂枝、炙甘草。
- 性味：每个性或味单独一个实体。例：辛、温、苦、寒。
- 脏腑经络：例：肺、脾、肾、足太阳膀胱经。

### 关系

| relation | 头类型 | 尾类型 | 含义 | 常见文本线索 |
|---|---|---|---|---|
| 分型 | 疾病 | 证候 | 疾病分型为证候 | 辨证论治下的分型标题 |
| 表现为 | 证候 | 症状 | 证候表现为症状 | "症状：""临床表现：""症见" |
| 治法 | 证候 | 治法功效 | 证候的治法 | "治法：""治宜""当以……法" |
| 方用 | 证候 | 方剂 | 证候所用方剂 | "方药：""代表方：""某方主之" |
| 病位 | 证候 | 脏腑经络 | 证候的病位 | "病位在""病在""病位主要在" |
| 组成 | 方剂 | 中药 | 方剂由中药组成 | "组成：""常用药：""方中……" |
| 功效 | 方剂 或 中药 | 治法功效 | 方剂或中药的功效 | "功效：""功能：""本方……""某药……以……" |
| 性味 | 中药 | 性味 | 中药的性味 | "性味：""味辛，性温" |
| 归经 | 中药 | 脏腑经络 | 中药归经 | "归经：""入肺经" |
| 主治 | 中药 | 症状 / 疾病 / 证候 | 中药主治 | "主治：""治……""用于……" |

只抽取正文明确写出的内容，不因已有医学知识补全；症状按顿号/逗号拆成独立短语；证机概要/病机等描述性语句不作为实体。

原文：
所属疾病：呃逆

呃逆的发生多由寒邪犯胃、饮食不当、情志不遂、体虚久病等，导致胃失和降，胃气上逆动膈而发病。

抽取结果：
entities:
{"local_id": "e1", "name": "呃逆", "type": "疾病", "mentions": ["呃逆"]}
triples:


我现在在做中医知识图谱的抽取。规则、原文、结果在上面。你来评判一下有没有多抽（不该抽的抽了）、少抽（该抽的漏了）、抽错（实体归错类、关系头尾/方向错、三元组语义错），并指出原文哪一句对应哪个问题。
```


---

## tcm_neike_trial_0003

```
## 抽取规则

### 实体类型

- 疾病：病名。例：感冒、消渴、胸痹、太阳病。
- 证候：对一组症状的病理概括，通常以"证"结尾或可补"证"字；疾病"辨证论治"下的分型标题一律为证候。例：风寒束表证、脾虚湿盛证。
- 症状：患者可感或医生可察的单一临床表现，含舌象、脉象。例：恶寒、口苦、苔白腻、脉浮紧。
- 治法功效：治疗原则或方药作用。证候后的"治法"与方药后的"功效"共用此类型，由关系名区分角色。例：辛温解表、健脾化湿、宣肺平喘。
- 方剂：例：麻黄汤、参苓白术散。
- 中药：例：麻黄、桂枝、炙甘草。
- 性味：每个性或味单独一个实体。例：辛、温、苦、寒。
- 脏腑经络：例：肺、脾、肾、足太阳膀胱经。

### 关系

| relation | 头类型 | 尾类型 | 含义 | 常见文本线索 |
|---|---|---|---|---|
| 分型 | 疾病 | 证候 | 疾病分型为证候 | 辨证论治下的分型标题 |
| 表现为 | 证候 | 症状 | 证候表现为症状 | "症状：""临床表现：""症见" |
| 治法 | 证候 | 治法功效 | 证候的治法 | "治法：""治宜""当以……法" |
| 方用 | 证候 | 方剂 | 证候所用方剂 | "方药：""代表方：""某方主之" |
| 病位 | 证候 | 脏腑经络 | 证候的病位 | "病位在""病在""病位主要在" |
| 组成 | 方剂 | 中药 | 方剂由中药组成 | "组成：""常用药：""方中……" |
| 功效 | 方剂 或 中药 | 治法功效 | 方剂或中药的功效 | "功效：""功能：""本方……""某药……以……" |
| 性味 | 中药 | 性味 | 中药的性味 | "性味：""味辛，性温" |
| 归经 | 中药 | 脏腑经络 | 中药归经 | "归经：""入肺经" |
| 主治 | 中药 | 症状 / 疾病 / 证候 | 中药主治 | "主治：""治……""用于……" |

只抽取正文明确写出的内容，不因已有医学知识补全；症状按顿号/逗号拆成独立短语；证机概要/病机等描述性语句不作为实体。

原文：
所属疾病：呃逆

1.寒邪犯胃 外感寒凉之邪，内客脾胃，寒遏中阳，胃气失和，寒气上逆动膈，导致呃逆之证。

2.饮食不当 过食生冷，或过用寒凉药物，寒气客胃，循经犯膈，膈间不利，胃气不降，肺失宣肃，气逆上冲咽喉而呃；过食辛热厚味，滥用温补之剂，燥热内盛，腑气不行，气逆动膈，上冲为呃。《景岳全书•呃逆》曰：“皆其胃中有火，所以上冲为呃。”或进食太快太饱，致气不顺行，气逆动膈，发生呃逆。

3. 情志不遂 逆气动膈，或气郁化火，灼津成痰，痰火蕴胃，或肝郁克脾，或忧思伤脾，运化失职，滋生痰浊，或素有痰饮内停，复因恼怒气逆，逆气夹痰浊上逆动膈，发为呃逆。《古今医统大全•咳逆》曰：“凡有忍气郁结积怒之人，并不得行其志者，多有咳逆之证。”

4.体虚久病 素体不足，年高体弱，或大病久病，正气未复，或吐下太过，虚损误攻，均可损伤中气，或胃阴耗伤，胃失和降，发生呃逆。甚则病深及肾，肾气失于摄纳，独气上乘，上逆动膈，发生呕逆。大病久病出现呃逆，多提示预后不良。《证治汇补•呃逆》曰：“伤寒及滞下后，老人、虚人、妇人产后多有呃症者，皆病深之候也。若额上出汗，连声不绝者危。”

抽取结果：
entities:
{"local_id": "e1", "name": "呃逆", "type": "疾病", "mentions": ["呃逆"]}
{"local_id": "e2", "name": "寒邪犯胃", "type": "证候", "mentions": ["寒邪犯胃"]}
{"local_id": "e3", "name": "饮食不当", "type": "证候", "mentions": ["饮食不当"]}
{"local_id": "e4", "name": "情志不遂", "type": "证候", "mentions": ["情志不遂"]}
{"local_id": "e5", "name": "体虚久病", "type": "证候", "mentions": ["体虚久病"]}
{"local_id": "e6", "name": "胃气失和", "type": "症状", "mentions": ["胃气失和"]}
{"local_id": "e7", "name": "寒气上逆动膈", "type": "症状", "mentions": ["寒气上逆动膈"]}
{"local_id": "e8", "name": "胃气不降", "type": "症状", "mentions": ["胃气不降"]}
{"local_id": "e9", "name": "肺失宣肃", "type": "症状", "mentions": ["肺失宣肃"]}
{"local_id": "e10", "name": "气逆上冲咽喉", "type": "症状", "mentions": ["气逆上冲咽喉"]}
{"local_id": "e11", "name": "燥热内盛", "type": "症状", "mentions": ["燥热内盛"]}
{"local_id": "e12", "name": "腑气不行", "type": "症状", "mentions": ["腑气不行"]}
{"local_id": "e13", "name": "气逆动膈", "type": "症状", "mentions": ["气逆动膈"]}
{"local_id": "e14", "name": "气不顺行", "type": "症状", "mentions": ["气不顺行"]}
{"local_id": "e15", "name": "逆气动膈", "type": "症状", "mentions": ["逆气动膈"]}
{"local_id": "e16", "name": "气郁化火", "type": "症状", "mentions": ["气郁化火"]}
{"local_id": "e17", "name": "灼津成痰", "type": "症状", "mentions": ["灼津成痰"]}
{"local_id": "e18", "name": "痰火蕴胃", "type": "症状", "mentions": ["痰火蕴胃"]}
{"local_id": "e19", "name": "肝郁克脾", "type": "症状", "mentions": ["肝郁克脾"]}
{"local_id": "e20", "name": "忧思伤脾", "type": "症状", "mentions": ["忧思伤脾"]}
{"local_id": "e21", "name": "运化失职", "type": "症状", "mentions": ["运化失职"]}
{"local_id": "e22", "name": "滋生痰浊", "type": "症状", "mentions": ["滋生痰浊"]}
{"local_id": "e23", "name": "痰饮内停", "type": "症状", "mentions": ["痰饮内停"]}
{"local_id": "e24", "name": "恼怒气逆", "type": "症状", "mentions": ["恼怒气逆"]}
{"local_id": "e25", "name": "逆气夹痰浊上逆动膈", "type": "症状", "mentions": ["逆气夹痰浊上逆动膈"]}
{"local_id": "e26", "name": "损伤中气", "type": "症状", "mentions": ["损伤中气"]}
{"local_id": "e27", "name": "胃阴耗伤", "type": "症状", "mentions": ["胃阴耗伤"]}
{"local_id": "e28", "name": "胃失和降", "type": "症状", "mentions": ["胃失和降"]}
{"local_id": "e29", "name": "病深及肾", "type": "症状", "mentions": ["病深及肾"]}
{"local_id": "e30", "name": "肾气失于摄纳", "type": "症状", "mentions": ["肾气失于摄纳"]}
{"local_id": "e31", "name": "独气上乘", "type": "症状", "mentions": ["独气上乘"]}
{"local_id": "e32", "name": "上逆动膈", "type": "症状", "mentions": ["上逆动膈"]}
{"local_id": "e33", "name": "脾胃", "type": "脏腑经络", "mentions": ["脾胃"]}
{"local_id": "e34", "name": "胃", "type": "脏腑经络", "mentions": ["胃"]}
{"local_id": "e35", "name": "膈", "type": "脏腑经络", "mentions": ["膈"]}
{"local_id": "e36", "name": "肺", "type": "脏腑经络", "mentions": ["肺"]}
{"local_id": "e37", "name": "肝", "type": "脏腑经络", "mentions": ["肝"]}
{"local_id": "e38", "name": "脾", "type": "脏腑经络", "mentions": ["脾"]}
{"local_id": "e39", "name": "肾", "type": "脏腑经络", "mentions": ["肾"]}
triples:
{"head": "e1", "relation": "分型", "tail": "e2", "pid": null, "kind": "relational", "flipped": false}
{"head": "e1", "relation": "分型", "tail": "e3", "pid": null, "kind": "relational", "flipped": false}
{"head": "e1", "relation": "分型", "tail": "e4", "pid": null, "kind": "relational", "flipped": false}
{"head": "e1", "relation": "分型", "tail": "e5", "pid": null, "kind": "relational", "flipped": false}
{"head": "e2", "relation": "表现为", "tail": "e6", "pid": null, "kind": "relational", "flipped": false}
{"head": "e2", "relation": "表现为", "tail": "e7", "pid": null, "kind": "relational", "flipped": false}
{"head": "e3", "relation": "表现为", "tail": "e8", "pid": null, "kind": "relational", "flipped": false}
{"head": "e3", "relation": "表现为", "tail": "e9", "pid": null, "kind": "relational", "flipped": false}
{"head": "e3", "relation": "表现为", "tail": "e10", "pid": null, "kind": "relational", "flipped": false}
{"head": "e3", "relation": "表现为", "tail": "e11", "pid": null, "kind": "relational", "flipped": false}
{"head": "e3", "relation": "表现为", "tail": "e12", "pid": null, "kind": "relational", "flipped": false}
{"head": "e3", "relation": "表现为", "tail": "e13", "pid": null, "kind": "relational", "flipped": false}
{"head": "e3", "relation": "表现为", "tail": "e14", "pid": null, "kind": "relational", "flipped": false}
{"head": "e3", "relation": "表现为", "tail": "e15", "pid": null, "kind": "relational", "flipped": false}
{"head": "e4", "relation": "表现为", "tail": "e15", "pid": null, "kind": "relational", "flipped": false}
{"head": "e4", "relation": "表现为", "tail": "e16", "pid": null, "kind": "relational", "flipped": false}
{"head": "e4", "relation": "表现为", "tail": "e17", "pid": null, "kind": "relational", "flipped": false}
{"head": "e4", "relation": "表现为", "tail": "e18", "pid": null, "kind": "relational", "flipped": false}
{"head": "e4", "relation": "表现为", "tail": "e19", "pid": null, "kind": "relational", "flipped": false}
{"head": "e4", "relation": "表现为", "tail": "e20", "pid": null, "kind": "relational", "flipped": false}
{"head": "e4", "relation": "表现为", "tail": "e21", "pid": null, "kind": "relational", "flipped": false}
{"head": "e4", "relation": "表现为", "tail": "e22", "pid": null, "kind": "relational", "flipped": false}
{"head": "e4", "relation": "表现为", "tail": "e23", "pid": null, "kind": "relational", "flipped": false}
{"head": "e4", "relation": "表现为", "tail": "e24", "pid": null, "kind": "relational", "flipped": false}
{"head": "e4", "relation": "表现为", "tail": "e25", "pid": null, "kind": "relational", "flipped": false}
{"head": "e5", "relation": "表现为", "tail": "e26", "pid": null, "kind": "relational", "flipped": false}
{"head": "e5", "relation": "表现为", "tail": "e27", "pid": null, "kind": "relational", "flipped": false}
{"head": "e5", "relation": "表现为", "tail": "e28", "pid": null, "kind": "relational", "flipped": false}
{"head": "e5", "relation": "表现为", "tail": "e29", "pid": null, "kind": "relational", "flipped": false}
{"head": "e5", "relation": "表现为", "tail": "e30", "pid": null, "kind": "relational", "flipped": false}
{"head": "e5", "relation": "表现为", "tail": "e31", "pid": null, "kind": "relational", "flipped": false}
{"head": "e5", "relation": "表现为", "tail": "e32", "pid": null, "kind": "relational", "flipped": false}
{"head": "e2", "relation": "病位", "tail": "e33", "pid": null, "kind": "relational", "flipped": false}
{"head": "e2", "relation": "病位", "tail": "e34", "pid": null, "kind": "relational", "flipped": false}
{"head": "e3", "relation": "病位", "tail": "e34", "pid": null, "kind": "relational", "flipped": false}
{"head": "e3", "relation": "病位", "tail": "e36", "pid": null, "kind": "relational", "flipped": false}
{"head": "e4", "relation": "病位", "tail": "e34", "pid": null, "kind": "relational", "flipped": false}
{"head": "e4", "relation": "病位", "tail": "e37", "pid": null, "kind": "relational", "flipped": false}
{"head": "e4", "relation": "病位", "tail": "e38", "pid": null, "kind": "relational", "flipped": false}
{"head": "e5", "relation": "病位", "tail": "e34", "pid": null, "kind": "relational", "flipped": false}
{"head": "e5", "relation": "病位", "tail": "e39", "pid": null, "kind": "relational", "flipped": false}

我现在在做中医知识图谱的抽取。规则、原文、结果在上面。你来评判一下有没有多抽（不该抽的抽了）、少抽（该抽的漏了）、抽错（实体归错类、关系头尾/方向错、三元组语义错），并指出原文哪一句对应哪个问题。
```


---

## tcm_neike_trial_0004

```
## 抽取规则

### 实体类型

- 疾病：病名。例：感冒、消渴、胸痹、太阳病。
- 证候：对一组症状的病理概括，通常以"证"结尾或可补"证"字；疾病"辨证论治"下的分型标题一律为证候。例：风寒束表证、脾虚湿盛证。
- 症状：患者可感或医生可察的单一临床表现，含舌象、脉象。例：恶寒、口苦、苔白腻、脉浮紧。
- 治法功效：治疗原则或方药作用。证候后的"治法"与方药后的"功效"共用此类型，由关系名区分角色。例：辛温解表、健脾化湿、宣肺平喘。
- 方剂：例：麻黄汤、参苓白术散。
- 中药：例：麻黄、桂枝、炙甘草。
- 性味：每个性或味单独一个实体。例：辛、温、苦、寒。
- 脏腑经络：例：肺、脾、肾、足太阳膀胱经。

### 关系

| relation | 头类型 | 尾类型 | 含义 | 常见文本线索 |
|---|---|---|---|---|
| 分型 | 疾病 | 证候 | 疾病分型为证候 | 辨证论治下的分型标题 |
| 表现为 | 证候 | 症状 | 证候表现为症状 | "症状：""临床表现：""症见" |
| 治法 | 证候 | 治法功效 | 证候的治法 | "治法：""治宜""当以……法" |
| 方用 | 证候 | 方剂 | 证候所用方剂 | "方药：""代表方：""某方主之" |
| 病位 | 证候 | 脏腑经络 | 证候的病位 | "病位在""病在""病位主要在" |
| 组成 | 方剂 | 中药 | 方剂由中药组成 | "组成：""常用药：""方中……" |
| 功效 | 方剂 或 中药 | 治法功效 | 方剂或中药的功效 | "功效：""功能：""本方……""某药……以……" |
| 性味 | 中药 | 性味 | 中药的性味 | "性味：""味辛，性温" |
| 归经 | 中药 | 脏腑经络 | 中药归经 | "归经：""入肺经" |
| 主治 | 中药 | 症状 / 疾病 / 证候 | 中药主治 | "主治：""治……""用于……" |

只抽取正文明确写出的内容，不因已有医学知识补全；症状按顿号/逗号拆成独立短语；证机概要/病机等描述性语句不作为实体。

原文：
所属疾病：呃逆

呃逆的基本病机是胃失和降，膈间气机不利，气逆动膈。凡见胃失和降，气逆于上，循手太阴之脉上动于膈，膈间之气不利，气逆上冲咽喉，致喉间呃呃连声，不能自止者，均可见有呃逆。

病位在膈，病变脏腑关键在胃，且常与肺、肾、肝、脾有关。胃居膈下，其气以降为顺，胃与膈有经脉相连属；肺处膈上，其主肃降，手太阴肺之经脉还循胃口，上膈，属肺。肺之宣肃影响胃气和降，且膈居肺胃之间，诸多病因影响肺胃时，使胃失和降，膈间气机不利，逆气上冲于喉间，致呃逆发作。肺之肃降与胃之和降，还有赖于肾的摄纳，若肾元亏虚，肾失摄纳，逆气上冲，夹胃气上逆动膈，亦可致呃。胃之和降，还需肝之条达，脾之健运，如肝失疏泄，横逆犯胃，胃失和降，气逆动膈，或脾失健运，痰饮食浊内停，胃气被遏，气逆动膈，均成呃逆。

病理性质有虚实之分。实证多为胃寒、胃热、气滞、痰阻，胃失和降；虚证常因脾胃阳虚或胃阴不足等正虚气逆所致，更有虚实夹杂并见者。呃逆的病机转化决定于病邪性质和正气强弱。

寒邪为病者，主要是寒邪与阳气抗争，阳气不衰则寒邪易于疏散；反之，胃中寒冷，损伤阳气，久可致脾胃虚寒之证。热邪为病者，如胃中积热或肝郁日久化火，易于损阴耗液而转化力胃阴亏虚。气郁、食滞、痰饮为病者，皆能伤及脾胃，转化为脾胃虚弱证。亦有气郁日久渐致血瘀，而兼夹血瘀而致胃中气机不畅，胃气上逆者。

抽取结果：
entities:
{"local_id": "e1", "name": "呃逆", "type": "疾病", "mentions": ["呃逆"]}
{"local_id": "e2", "name": "胃失和降", "type": "证候", "mentions": ["胃失和降"]}
{"local_id": "e3", "name": "气逆上冲", "type": "症状", "mentions": ["气逆上冲"]}
{"local_id": "e4", "name": "喉间呃呃连声", "type": "症状", "mentions": ["喉间呃呃连声"]}
{"local_id": "e5", "name": "不能自止", "type": "症状", "mentions": ["不能自止"]}
{"local_id": "e6", "name": "膈", "type": "脏腑经络", "mentions": ["膈"]}
{"local_id": "e7", "name": "胃", "type": "脏腑经络", "mentions": ["胃"]}
{"local_id": "e8", "name": "肺", "type": "脏腑经络", "mentions": ["肺"]}
{"local_id": "e9", "name": "肾", "type": "脏腑经络", "mentions": ["肾"]}
{"local_id": "e10", "name": "肝", "type": "脏腑经络", "mentions": ["肝"]}
{"local_id": "e11", "name": "脾", "type": "脏腑经络", "mentions": ["脾"]}
{"local_id": "e12", "name": "胃寒", "type": "证候", "mentions": ["胃寒"]}
{"local_id": "e13", "name": "胃热", "type": "证候", "mentions": ["胃热"]}
{"local_id": "e14", "name": "气滞", "type": "证候", "mentions": ["气滞"]}
{"local_id": "e15", "name": "痰阻", "type": "证候", "mentions": ["痰阻"]}
{"local_id": "e16", "name": "脾胃阳虚", "type": "证候", "mentions": ["脾胃阳虚"]}
{"local_id": "e17", "name": "胃阴不足", "type": "证候", "mentions": ["胃阴不足"]}
{"local_id": "e18", "name": "脾胃虚寒", "type": "证候", "mentions": ["脾胃虚寒"]}
{"local_id": "e19", "name": "胃阴亏虚", "type": "证候", "mentions": ["胃阴亏虚"]}
{"local_id": "e20", "name": "脾胃虚弱", "type": "证候", "mentions": ["脾胃虚弱"]}
{"local_id": "e21", "name": "血瘀", "type": "证候", "mentions": ["血瘀"]}
triples:
{"head": "e1", "relation": "分型", "tail": "e2", "pid": null, "kind": "relational", "flipped": false}
{"head": "e2", "relation": "表现为", "tail": "e3", "pid": null, "kind": "relational", "flipped": false}
{"head": "e2", "relation": "表现为", "tail": "e4", "pid": null, "kind": "relational", "flipped": false}
{"head": "e2", "relation": "表现为", "tail": "e5", "pid": null, "kind": "relational", "flipped": false}
{"head": "e2", "relation": "病位", "tail": "e6", "pid": null, "kind": "relational", "flipped": false}
{"head": "e2", "relation": "病位", "tail": "e7", "pid": null, "kind": "relational", "flipped": false}
{"head": "e2", "relation": "病位", "tail": "e8", "pid": null, "kind": "relational", "flipped": false}
{"head": "e2", "relation": "病位", "tail": "e9", "pid": null, "kind": "relational", "flipped": false}
{"head": "e2", "relation": "病位", "tail": "e10", "pid": null, "kind": "relational", "flipped": false}
{"head": "e2", "relation": "病位", "tail": "e11", "pid": null, "kind": "relational", "flipped": false}
{"head": "e1", "relation": "分型", "tail": "e12", "pid": null, "kind": "relational", "flipped": false}
{"head": "e1", "relation": "分型", "tail": "e13", "pid": null, "kind": "relational", "flipped": false}
{"head": "e1", "relation": "分型", "tail": "e14", "pid": null, "kind": "relational", "flipped": false}
{"head": "e1", "relation": "分型", "tail": "e15", "pid": null, "kind": "relational", "flipped": false}
{"head": "e1", "relation": "分型", "tail": "e16", "pid": null, "kind": "relational", "flipped": false}
{"head": "e1", "relation": "分型", "tail": "e17", "pid": null, "kind": "relational", "flipped": false}
{"head": "e1", "relation": "分型", "tail": "e18", "pid": null, "kind": "relational", "flipped": false}
{"head": "e1", "relation": "分型", "tail": "e19", "pid": null, "kind": "relational", "flipped": false}
{"head": "e1", "relation": "分型", "tail": "e20", "pid": null, "kind": "relational", "flipped": false}
{"head": "e1", "relation": "分型", "tail": "e21", "pid": null, "kind": "relational", "flipped": false}

我现在在做中医知识图谱的抽取。规则、原文、结果在上面。你来评判一下有没有多抽（不该抽的抽了）、少抽（该抽的漏了）、抽错（实体归错类、关系头尾/方向错、三元组语义错），并指出原文哪一句对应哪个问题。
```


---

## tcm_neike_trial_0005

```
## 抽取规则

### 实体类型

- 疾病：病名。例：感冒、消渴、胸痹、太阳病。
- 证候：对一组症状的病理概括，通常以"证"结尾或可补"证"字；疾病"辨证论治"下的分型标题一律为证候。例：风寒束表证、脾虚湿盛证。
- 症状：患者可感或医生可察的单一临床表现，含舌象、脉象。例：恶寒、口苦、苔白腻、脉浮紧。
- 治法功效：治疗原则或方药作用。证候后的"治法"与方药后的"功效"共用此类型，由关系名区分角色。例：辛温解表、健脾化湿、宣肺平喘。
- 方剂：例：麻黄汤、参苓白术散。
- 中药：例：麻黄、桂枝、炙甘草。
- 性味：每个性或味单独一个实体。例：辛、温、苦、寒。
- 脏腑经络：例：肺、脾、肾、足太阳膀胱经。

### 关系

| relation | 头类型 | 尾类型 | 含义 | 常见文本线索 |
|---|---|---|---|---|
| 分型 | 疾病 | 证候 | 疾病分型为证候 | 辨证论治下的分型标题 |
| 表现为 | 证候 | 症状 | 证候表现为症状 | "症状：""临床表现：""症见" |
| 治法 | 证候 | 治法功效 | 证候的治法 | "治法：""治宜""当以……法" |
| 方用 | 证候 | 方剂 | 证候所用方剂 | "方药：""代表方：""某方主之" |
| 病位 | 证候 | 脏腑经络 | 证候的病位 | "病位在""病在""病位主要在" |
| 组成 | 方剂 | 中药 | 方剂由中药组成 | "组成：""常用药：""方中……" |
| 功效 | 方剂 或 中药 | 治法功效 | 方剂或中药的功效 | "功效：""功能：""本方……""某药……以……" |
| 性味 | 中药 | 性味 | 中药的性味 | "性味：""味辛，性温" |
| 归经 | 中药 | 脏腑经络 | 中药归经 | "归经：""入肺经" |
| 主治 | 中药 | 症状 / 疾病 / 证候 | 中药主治 | "主治：""治……""用于……" |

只抽取正文明确写出的内容，不因已有医学知识补全；症状按顿号/逗号拆成独立短语；证机概要/病机等描述性语句不作为实体。

原文：
所属疾病：呃逆

1.呃逆以气逆上冲，喉间呃呃连声，声短而频，不能自止为主症。其呃声或高或低，或疏或

密，间歇不定。

2. 常伴有胸膈痞闷、胃脘不适，或情绪不定。

3.多有饮食不当、情志不遂、感受冷凉、胸腹手术等诱发因素，或有体虚久病病史。

上消化道X线、胃镜检查及肝肾功能、彩超、CT、MRI 等检查有助于本病诊断。

抽取结果：
entities:
{"local_id": "e1", "name": "呃逆", "type": "疾病", "mentions": ["呃逆"]}
{"local_id": "e2", "name": "气逆上冲", "type": "症状", "mentions": ["气逆上冲"]}
{"local_id": "e3", "name": "喉间呃呃连声", "type": "症状", "mentions": ["喉间呃呃连声"]}
{"local_id": "e4", "name": "声短而频", "type": "症状", "mentions": ["声短而频"]}
{"local_id": "e5", "name": "不能自止", "type": "症状", "mentions": ["不能自止"]}
{"local_id": "e6", "name": "胸膈痞闷", "type": "症状", "mentions": ["胸膈痞闷"]}
{"local_id": "e7", "name": "胃脘不适", "type": "症状", "mentions": ["胃脘不适"]}
{"local_id": "e8", "name": "情绪不定", "type": "症状", "mentions": ["情绪不定"]}
triples:


我现在在做中医知识图谱的抽取。规则、原文、结果在上面。你来评判一下有没有多抽（不该抽的抽了）、少抽（该抽的漏了）、抽错（实体归错类、关系头尾/方向错、三元组语义错），并指出原文哪一句对应哪个问题。
```


---

## tcm_neike_trial_0006

```
## 抽取规则

### 实体类型

- 疾病：病名。例：感冒、消渴、胸痹、太阳病。
- 证候：对一组症状的病理概括，通常以"证"结尾或可补"证"字；疾病"辨证论治"下的分型标题一律为证候。例：风寒束表证、脾虚湿盛证。
- 症状：患者可感或医生可察的单一临床表现，含舌象、脉象。例：恶寒、口苦、苔白腻、脉浮紧。
- 治法功效：治疗原则或方药作用。证候后的"治法"与方药后的"功效"共用此类型，由关系名区分角色。例：辛温解表、健脾化湿、宣肺平喘。
- 方剂：例：麻黄汤、参苓白术散。
- 中药：例：麻黄、桂枝、炙甘草。
- 性味：每个性或味单独一个实体。例：辛、温、苦、寒。
- 脏腑经络：例：肺、脾、肾、足太阳膀胱经。

### 关系

| relation | 头类型 | 尾类型 | 含义 | 常见文本线索 |
|---|---|---|---|---|
| 分型 | 疾病 | 证候 | 疾病分型为证候 | 辨证论治下的分型标题 |
| 表现为 | 证候 | 症状 | 证候表现为症状 | "症状：""临床表现：""症见" |
| 治法 | 证候 | 治法功效 | 证候的治法 | "治法：""治宜""当以……法" |
| 方用 | 证候 | 方剂 | 证候所用方剂 | "方药：""代表方：""某方主之" |
| 病位 | 证候 | 脏腑经络 | 证候的病位 | "病位在""病在""病位主要在" |
| 组成 | 方剂 | 中药 | 方剂由中药组成 | "组成：""常用药：""方中……" |
| 功效 | 方剂 或 中药 | 治法功效 | 方剂或中药的功效 | "功效：""功能：""本方……""某药……以……" |
| 性味 | 中药 | 性味 | 中药的性味 | "性味：""味辛，性温" |
| 归经 | 中药 | 脏腑经络 | 中药归经 | "归经：""入肺经" |
| 主治 | 中药 | 症状 / 疾病 / 证候 | 中药主治 | "主治：""治……""用于……" |

只抽取正文明确写出的内容，不因已有医学知识补全；症状按顿号/逗号拆成独立短语；证机概要/病机等描述性语句不作为实体。

原文：
所属疾病：呃逆

干呕、暖气 三者同属胃气上逆的表现。呃逆为胃气上逆动膈，气从膈间上逆，气冲喉间，呃呃连声，声短而频，不能自止。干呕乃胃气上逆，发出呕吐之声，属于有声无物的呕吐。暖气乃胃气阻郁，气逆于上，冲咽而出，发出沉缓的暖气声，常伴酸腐气味，食后多发，故张景岳称之为“饱食之息”。在预后方面，干呕与嗳气只是脾胃疾病的症状，与疾病预后无明显关系。而呃逆若出现于危重病人，常为临终先兆。

抽取结果：
entities:
{"local_id": "e1", "name": "呃逆", "type": "疾病", "mentions": ["呃逆"]}
{"local_id": "e2", "name": "干呕", "type": "症状", "mentions": ["干呕"]}
{"local_id": "e3", "name": "嗳气", "type": "症状", "mentions": ["暖气", "嗳气"]}
{"local_id": "e4", "name": "胃气上逆", "type": "证候", "mentions": ["胃气上逆"]}
{"local_id": "e5", "name": "胃", "type": "脏腑经络", "mentions": ["胃"]}
{"local_id": "e6", "name": "膈", "type": "脏腑经络", "mentions": ["膈"]}
{"local_id": "e7", "name": "喉间", "type": "脏腑经络", "mentions": ["喉间"]}
{"local_id": "e8", "name": "呃呃连声", "type": "症状", "mentions": ["呃呃连声"]}
{"local_id": "e9", "name": "声短而频", "type": "症状", "mentions": ["声短而频"]}
{"local_id": "e10", "name": "不能自止", "type": "症状", "mentions": ["不能自止"]}
{"local_id": "e11", "name": "呕吐之声", "type": "症状", "mentions": ["呕吐之声"]}
{"local_id": "e12", "name": "有声无物", "type": "症状", "mentions": ["有声无物"]}
{"local_id": "e13", "name": "胃气阻郁", "type": "证候", "mentions": ["胃气阻郁"]}
{"local_id": "e14", "name": "气逆于上", "type": "证候", "mentions": ["气逆于上"]}
{"local_id": "e15", "name": "冲咽而出", "type": "症状", "mentions": ["冲咽而出"]}
{"local_id": "e16", "name": "沉缓的嗳气声", "type": "症状", "mentions": ["沉缓的暖气声"]}
{"local_id": "e17", "name": "酸腐气味", "type": "症状", "mentions": ["酸腐气味"]}
{"local_id": "e18", "name": "食后多发", "type": "症状", "mentions": ["食后多发"]}
{"local_id": "e19", "name": "饱食之息", "type": "症状", "mentions": ["饱食之息"]}
{"local_id": "e20", "name": "脾胃", "type": "脏腑经络", "mentions": ["脾胃"]}
{"local_id": "e21", "name": "临终先兆", "type": "症状", "mentions": ["临终先兆"]}
triples:
{"head": "e4", "relation": "表现为", "tail": "e2", "pid": null, "kind": "relational", "flipped": false}
{"head": "e4", "relation": "表现为", "tail": "e3", "pid": null, "kind": "relational", "flipped": false}
{"head": "e4", "relation": "病位", "tail": "e5", "pid": null, "kind": "relational", "flipped": false}
{"head": "e13", "relation": "表现为", "tail": "e15", "pid": null, "kind": "relational", "flipped": false}
{"head": "e13", "relation": "表现为", "tail": "e16", "pid": null, "kind": "relational", "flipped": false}
{"head": "e13", "relation": "表现为", "tail": "e17", "pid": null, "kind": "relational", "flipped": false}
{"head": "e13", "relation": "表现为", "tail": "e18", "pid": null, "kind": "relational", "flipped": false}

我现在在做中医知识图谱的抽取。规则、原文、结果在上面。你来评判一下有没有多抽（不该抽的抽了）、少抽（该抽的漏了）、抽错（实体归错类、关系头尾/方向错、三元组语义错），并指出原文哪一句对应哪个问题。
```


---

## tcm_neike_trial_0007

```
## 抽取规则

### 实体类型

- 疾病：病名。例：感冒、消渴、胸痹、太阳病。
- 证候：对一组症状的病理概括，通常以"证"结尾或可补"证"字；疾病"辨证论治"下的分型标题一律为证候。例：风寒束表证、脾虚湿盛证。
- 症状：患者可感或医生可察的单一临床表现，含舌象、脉象。例：恶寒、口苦、苔白腻、脉浮紧。
- 治法功效：治疗原则或方药作用。证候后的"治法"与方药后的"功效"共用此类型，由关系名区分角色。例：辛温解表、健脾化湿、宣肺平喘。
- 方剂：例：麻黄汤、参苓白术散。
- 中药：例：麻黄、桂枝、炙甘草。
- 性味：每个性或味单独一个实体。例：辛、温、苦、寒。
- 脏腑经络：例：肺、脾、肾、足太阳膀胱经。

### 关系

| relation | 头类型 | 尾类型 | 含义 | 常见文本线索 |
|---|---|---|---|---|
| 分型 | 疾病 | 证候 | 疾病分型为证候 | 辨证论治下的分型标题 |
| 表现为 | 证候 | 症状 | 证候表现为症状 | "症状：""临床表现：""症见" |
| 治法 | 证候 | 治法功效 | 证候的治法 | "治法：""治宜""当以……法" |
| 方用 | 证候 | 方剂 | 证候所用方剂 | "方药：""代表方：""某方主之" |
| 病位 | 证候 | 脏腑经络 | 证候的病位 | "病位在""病在""病位主要在" |
| 组成 | 方剂 | 中药 | 方剂由中药组成 | "组成：""常用药：""方中……" |
| 功效 | 方剂 或 中药 | 治法功效 | 方剂或中药的功效 | "功效：""功能：""本方……""某药……以……" |
| 性味 | 中药 | 性味 | 中药的性味 | "性味：""味辛，性温" |
| 归经 | 中药 | 脏腑经络 | 中药归经 | "归经：""入肺经" |
| 主治 | 中药 | 症状 / 疾病 / 证候 | 中药主治 | "主治：""治……""用于……" |

只抽取正文明确写出的内容，不因已有医学知识补全；症状按顿号/逗号拆成独立短语；证机概要/病机等描述性语句不作为实体。

原文：
所属疾病：呃逆

1.辨虚实 呃逆有虚实之分。实证多为寒凝、火郁、气滞、痰阻等致胃失和降而产生，其呃声响亮有力，连续发作；虚证每由胃阴耗损或脾胃亏虚等使正虚气逆引起，其呃声时晰时续，气怯乏力。

2.辨寒热寒证因寒邪犯胃，胃失和降，上逆动膈，呃声沉缓有力，遇寒凉更甚；热证属燥

热伤胃，阳明腑气不顺，胃气上逆，呃声高响且短，气涌而出。

抽取结果：
entities:
{"local_id": "e1", "name": "呃逆", "type": "疾病", "mentions": ["呃逆"]}
{"local_id": "e2", "name": "实证", "type": "证候", "mentions": ["实证"]}
{"local_id": "e3", "name": "虚证", "type": "证候", "mentions": ["虚证"]}
{"local_id": "e4", "name": "寒证", "type": "证候", "mentions": ["寒证"]}
{"local_id": "e5", "name": "热证", "type": "证候", "mentions": ["热证"]}
{"local_id": "e6", "name": "呃声响亮有力", "type": "症状", "mentions": ["呃声响亮有力"]}
{"local_id": "e7", "name": "连续发作", "type": "症状", "mentions": ["连续发作"]}
{"local_id": "e8", "name": "呃声时晰时续", "type": "症状", "mentions": ["呃声时晰时续"]}
{"local_id": "e9", "name": "气怯乏力", "type": "症状", "mentions": ["气怯乏力"]}
{"local_id": "e10", "name": "呃声沉缓有力", "type": "症状", "mentions": ["呃声沉缓有力"]}
{"local_id": "e11", "name": "遇寒凉更甚", "type": "症状", "mentions": ["遇寒凉更甚"]}
{"local_id": "e12", "name": "呃声高响且短", "type": "症状", "mentions": ["呃声高响且短"]}
{"local_id": "e13", "name": "气涌而出", "type": "症状", "mentions": ["气涌而出"]}
triples:
{"head": "e1", "relation": "分型", "tail": "e2", "pid": null, "kind": "relational", "flipped": false}
{"head": "e1", "relation": "分型", "tail": "e3", "pid": null, "kind": "relational", "flipped": false}
{"head": "e1", "relation": "分型", "tail": "e4", "pid": null, "kind": "relational", "flipped": false}
{"head": "e1", "relation": "分型", "tail": "e5", "pid": null, "kind": "relational", "flipped": false}
{"head": "e2", "relation": "表现为", "tail": "e6", "pid": null, "kind": "relational", "flipped": false}
{"head": "e2", "relation": "表现为", "tail": "e7", "pid": null, "kind": "relational", "flipped": false}
{"head": "e3", "relation": "表现为", "tail": "e8", "pid": null, "kind": "relational", "flipped": false}
{"head": "e3", "relation": "表现为", "tail": "e9", "pid": null, "kind": "relational", "flipped": false}
{"head": "e4", "relation": "表现为", "tail": "e10", "pid": null, "kind": "relational", "flipped": false}
{"head": "e4", "relation": "表现为", "tail": "e11", "pid": null, "kind": "relational", "flipped": false}
{"head": "e5", "relation": "表现为", "tail": "e12", "pid": null, "kind": "relational", "flipped": false}
{"head": "e5", "relation": "表现为", "tail": "e13", "pid": null, "kind": "relational", "flipped": false}

我现在在做中医知识图谱的抽取。规则、原文、结果在上面。你来评判一下有没有多抽（不该抽的抽了）、少抽（该抽的漏了）、抽错（实体归错类、关系头尾/方向错、三元组语义错），并指出原文哪一句对应哪个问题。
```


---

## tcm_neike_trial_0008

```
## 抽取规则

### 实体类型

- 疾病：病名。例：感冒、消渴、胸痹、太阳病。
- 证候：对一组症状的病理概括，通常以"证"结尾或可补"证"字；疾病"辨证论治"下的分型标题一律为证候。例：风寒束表证、脾虚湿盛证。
- 症状：患者可感或医生可察的单一临床表现，含舌象、脉象。例：恶寒、口苦、苔白腻、脉浮紧。
- 治法功效：治疗原则或方药作用。证候后的"治法"与方药后的"功效"共用此类型，由关系名区分角色。例：辛温解表、健脾化湿、宣肺平喘。
- 方剂：例：麻黄汤、参苓白术散。
- 中药：例：麻黄、桂枝、炙甘草。
- 性味：每个性或味单独一个实体。例：辛、温、苦、寒。
- 脏腑经络：例：肺、脾、肾、足太阳膀胱经。

### 关系

| relation | 头类型 | 尾类型 | 含义 | 常见文本线索 |
|---|---|---|---|---|
| 分型 | 疾病 | 证候 | 疾病分型为证候 | 辨证论治下的分型标题 |
| 表现为 | 证候 | 症状 | 证候表现为症状 | "症状：""临床表现：""症见" |
| 治法 | 证候 | 治法功效 | 证候的治法 | "治法：""治宜""当以……法" |
| 方用 | 证候 | 方剂 | 证候所用方剂 | "方药：""代表方：""某方主之" |
| 病位 | 证候 | 脏腑经络 | 证候的病位 | "病位在""病在""病位主要在" |
| 组成 | 方剂 | 中药 | 方剂由中药组成 | "组成：""常用药：""方中……" |
| 功效 | 方剂 或 中药 | 治法功效 | 方剂或中药的功效 | "功效：""功能：""本方……""某药……以……" |
| 性味 | 中药 | 性味 | 中药的性味 | "性味：""味辛，性温" |
| 归经 | 中药 | 脏腑经络 | 中药归经 | "归经：""入肺经" |
| 主治 | 中药 | 症状 / 疾病 / 证候 | 中药主治 | "主治：""治……""用于……" |

只抽取正文明确写出的内容，不因已有医学知识补全；症状按顿号/逗号拆成独立短语；证机概要/病机等描述性语句不作为实体。

原文：
所属疾病：呃逆

呃逆的治疗以理气和胃、降逆止呃为基本治法。治疗要分清寒、热、虚、实，分别施以祛寒、清热、补虚、泻实之法。同时可辅以降逆止呃之品，以利膈间之气。对于重危病证中出现的呃逆，可予补益元气，急救胃气，或施益气、救阴、温阳等法，以固其本。

抽取结果：
entities:
{"local_id": "e1", "name": "呃逆", "type": "疾病", "mentions": ["呃逆"]}
{"local_id": "e2", "name": "理气和胃", "type": "治法功效", "mentions": ["理气和胃"]}
{"local_id": "e3", "name": "降逆止呃", "type": "治法功效", "mentions": ["降逆止呃"]}
{"local_id": "e4", "name": "祛寒", "type": "治法功效", "mentions": ["祛寒"]}
{"local_id": "e5", "name": "清热", "type": "治法功效", "mentions": ["清热"]}
{"local_id": "e6", "name": "补虚", "type": "治法功效", "mentions": ["补虚"]}
{"local_id": "e7", "name": "泻实", "type": "治法功效", "mentions": ["泻实"]}
{"local_id": "e8", "name": "补益元气", "type": "治法功效", "mentions": ["补益元气"]}
{"local_id": "e9", "name": "急救胃气", "type": "治法功效", "mentions": ["急救胃气"]}
{"local_id": "e10", "name": "益气", "type": "治法功效", "mentions": ["益气"]}
{"local_id": "e11", "name": "救阴", "type": "治法功效", "mentions": ["救阴"]}
{"local_id": "e12", "name": "温阳", "type": "治法功效", "mentions": ["温阳"]}
triples:


我现在在做中医知识图谱的抽取。规则、原文、结果在上面。你来评判一下有没有多抽（不该抽的抽了）、少抽（该抽的漏了）、抽错（实体归错类、关系头尾/方向错、三元组语义错），并指出原文哪一句对应哪个问题。
```


---

## tcm_neike_trial_0009

```
## 抽取规则

### 实体类型

- 疾病：病名。例：感冒、消渴、胸痹、太阳病。
- 证候：对一组症状的病理概括，通常以"证"结尾或可补"证"字；疾病"辨证论治"下的分型标题一律为证候。例：风寒束表证、脾虚湿盛证。
- 症状：患者可感或医生可察的单一临床表现，含舌象、脉象。例：恶寒、口苦、苔白腻、脉浮紧。
- 治法功效：治疗原则或方药作用。证候后的"治法"与方药后的"功效"共用此类型，由关系名区分角色。例：辛温解表、健脾化湿、宣肺平喘。
- 方剂：例：麻黄汤、参苓白术散。
- 中药：例：麻黄、桂枝、炙甘草。
- 性味：每个性或味单独一个实体。例：辛、温、苦、寒。
- 脏腑经络：例：肺、脾、肾、足太阳膀胱经。

### 关系

| relation | 头类型 | 尾类型 | 含义 | 常见文本线索 |
|---|---|---|---|---|
| 分型 | 疾病 | 证候 | 疾病分型为证候 | 辨证论治下的分型标题 |
| 表现为 | 证候 | 症状 | 证候表现为症状 | "症状：""临床表现：""症见" |
| 治法 | 证候 | 治法功效 | 证候的治法 | "治法：""治宜""当以……法" |
| 方用 | 证候 | 方剂 | 证候所用方剂 | "方药：""代表方：""某方主之" |
| 病位 | 证候 | 脏腑经络 | 证候的病位 | "病位在""病在""病位主要在" |
| 组成 | 方剂 | 中药 | 方剂由中药组成 | "组成：""常用药：""方中……" |
| 功效 | 方剂 或 中药 | 治法功效 | 方剂或中药的功效 | "功效：""功能：""本方……""某药……以……" |
| 性味 | 中药 | 性味 | 中药的性味 | "性味：""味辛，性温" |
| 归经 | 中药 | 脏腑经络 | 中药归经 | "归经：""入肺经" |
| 主治 | 中药 | 症状 / 疾病 / 证候 | 中药主治 | "主治：""治……""用于……" |

只抽取正文明确写出的内容，不因已有医学知识补全；症状按顿号/逗号拆成独立短语；证机概要/病机等描述性语句不作为实体。

原文：
所属疾病：呃逆

1. 胃中寒冷

临床表现：呃声沉而有力，胃脘部及膈间不舒，得热则减，遇寒则甚，进食减少，喜食热饮，口淡不渴，舌质淡，苔白，脉迟缓。

证机概要：寒蓄中焦，气机不利，胃气上逆。

治法：温中散寒，降逆止呃。

代表方：丁香散。

常用药：丁香、柿蒂降逆止呃；高良姜、干姜、荜茇温中散寒；香附、陈皮理气和胃。

若寒气较重者，加吴茱萸、肉桂、乌药；寒凝气滞，脘腹痞满者，加枳壳、厚朴、香附、陈皮；寒凝食滞，脘闷暖腐者，加炒菜菔子、半夏、槟榔；有表寒之邪者，加紫苏、荆芥、防风、生姜。

抽取结果：
entities:
{"local_id": "e1", "name": "呃逆", "type": "疾病", "mentions": ["呃逆"]}
{"local_id": "e2", "name": "胃中寒冷", "type": "证候", "mentions": ["胃中寒冷"]}
{"local_id": "e3", "name": "呃声沉而有力", "type": "症状", "mentions": ["呃声沉而有力"]}
{"local_id": "e4", "name": "胃脘部及膈间不舒", "type": "症状", "mentions": ["胃脘部及膈间不舒"]}
{"local_id": "e5", "name": "得热则减", "type": "症状", "mentions": ["得热则减"]}
{"local_id": "e6", "name": "遇寒则甚", "type": "症状", "mentions": ["遇寒则甚"]}
{"local_id": "e7", "name": "进食减少", "type": "症状", "mentions": ["进食减少"]}
{"local_id": "e8", "name": "喜食热饮", "type": "症状", "mentions": ["喜食热饮"]}
{"local_id": "e9", "name": "口淡不渴", "type": "症状", "mentions": ["口淡不渴"]}
{"local_id": "e10", "name": "舌质淡", "type": "症状", "mentions": ["舌质淡"]}
{"local_id": "e11", "name": "苔白", "type": "症状", "mentions": ["苔白"]}
{"local_id": "e12", "name": "脉迟缓", "type": "症状", "mentions": ["脉迟缓"]}
{"local_id": "e13", "name": "温中散寒", "type": "治法功效", "mentions": ["温中散寒"]}
{"local_id": "e14", "name": "降逆止呃", "type": "治法功效", "mentions": ["降逆止呃"]}
{"local_id": "e15", "name": "丁香散", "type": "方剂", "mentions": ["丁香散"]}
{"local_id": "e16", "name": "丁香", "type": "中药", "mentions": ["丁香"]}
{"local_id": "e17", "name": "柿蒂", "type": "中药", "mentions": ["柿蒂"]}
{"local_id": "e18", "name": "高良姜", "type": "中药", "mentions": ["高良姜"]}
{"local_id": "e19", "name": "干姜", "type": "中药", "mentions": ["干姜"]}
{"local_id": "e20", "name": "荜茇", "type": "中药", "mentions": ["荜茇"]}
{"local_id": "e21", "name": "香附", "type": "中药", "mentions": ["香附"]}
{"local_id": "e22", "name": "陈皮", "type": "中药", "mentions": ["陈皮"]}
{"local_id": "e23", "name": "理气和胃", "type": "治法功效", "mentions": ["理气和胃"]}
triples:
{"head": "e1", "relation": "分型", "tail": "e2", "pid": null, "kind": "relational", "flipped": false}
{"head": "e2", "relation": "表现为", "tail": "e3", "pid": null, "kind": "relational", "flipped": false}
{"head": "e2", "relation": "表现为", "tail": "e4", "pid": null, "kind": "relational", "flipped": false}
{"head": "e2", "relation": "表现为", "tail": "e5", "pid": null, "kind": "relational", "flipped": false}
{"head": "e2", "relation": "表现为", "tail": "e6", "pid": null, "kind": "relational", "flipped": false}
{"head": "e2", "relation": "表现为", "tail": "e7", "pid": null, "kind": "relational", "flipped": false}
{"head": "e2", "relation": "表现为", "tail": "e8", "pid": null, "kind": "relational", "flipped": false}
{"head": "e2", "relation": "表现为", "tail": "e9", "pid": null, "kind": "relational", "flipped": false}
{"head": "e2", "relation": "表现为", "tail": "e10", "pid": null, "kind": "relational", "flipped": false}
{"head": "e2", "relation": "表现为", "tail": "e11", "pid": null, "kind": "relational", "flipped": false}
{"head": "e2", "relation": "表现为", "tail": "e12", "pid": null, "kind": "relational", "flipped": false}
{"head": "e2", "relation": "治法", "tail": "e13", "pid": null, "kind": "relational", "flipped": false}
{"head": "e2", "relation": "治法", "tail": "e14", "pid": null, "kind": "relational", "flipped": false}
{"head": "e2", "relation": "方用", "tail": "e15", "pid": null, "kind": "relational", "flipped": false}
{"head": "e15", "relation": "组成", "tail": "e16", "pid": null, "kind": "relational", "flipped": false}
{"head": "e15", "relation": "组成", "tail": "e17", "pid": null, "kind": "relational", "flipped": false}
{"head": "e15", "relation": "组成", "tail": "e18", "pid": null, "kind": "relational", "flipped": false}
{"head": "e15", "relation": "组成", "tail": "e19", "pid": null, "kind": "relational", "flipped": false}
{"head": "e15", "relation": "组成", "tail": "e20", "pid": null, "kind": "relational", "flipped": false}
{"head": "e15", "relation": "组成", "tail": "e21", "pid": null, "kind": "relational", "flipped": false}
{"head": "e15", "relation": "组成", "tail": "e22", "pid": null, "kind": "relational", "flipped": false}
{"head": "e16", "relation": "功效", "tail": "e14", "pid": null, "kind": "relational", "flipped": false}
{"head": "e17", "relation": "功效", "tail": "e14", "pid": null, "kind": "relational", "flipped": false}
{"head": "e18", "relation": "功效", "tail": "e13", "pid": null, "kind": "relational", "flipped": false}
{"head": "e19", "relation": "功效", "tail": "e13", "pid": null, "kind": "relational", "flipped": false}
{"head": "e20", "relation": "功效", "tail": "e13", "pid": null, "kind": "relational", "flipped": false}
{"head": "e21", "relation": "功效", "tail": "e23", "pid": null, "kind": "relational", "flipped": false}
{"head": "e22", "relation": "功效", "tail": "e23", "pid": null, "kind": "relational", "flipped": false}

我现在在做中医知识图谱的抽取。规则、原文、结果在上面。你来评判一下有没有多抽（不该抽的抽了）、少抽（该抽的漏了）、抽错（实体归错类、关系头尾/方向错、三元组语义错），并指出原文哪一句对应哪个问题。
```
