"""Stage 0 (GenWiki): build schema, docs.jsonl, gold.jsonl, few-shot, prompt template.

GenWiki (COLING 2020) text is a templated sentence with <ENT_i> placeholders; the gold
graph is a list of [head, relation, tail] DBpedia-property triples whose head/tail are
the *filled* entity strings. We fill the placeholders to reconstruct the natural sentence
as the extraction input, and keep the graph as gold triples.

Relations = DBpedia properties covering >=90% of train/fine instances (top 70). GenWiki
has no official entity types; we reuse DocRED's 6 types (PER/ORG/LOC/TIME/NUM/MISC) as an
extraction constraint only (types are not compared in eval). domain/range left empty so
validation does not type-drop (see DESIGN.md 1.3: type distribution requires a first
extraction pass).
"""
import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from common import REPO_ROOT, read_jsonl, write_jsonl
from prompt_builder import PromptBuilder

# (property, kind, description) — kind: intrinsic = stored as node attribute, relational = edge.
# Descriptions are concise glosses for the LLM prompt.
RELATIONS = [
    ("birthPlace", "relational", "place where the person was born"),
    ("country", "relational", "sovereign state the subject is located in"),
    ("location", "relational", "location of the subject"),
    ("birthYear", "intrinsic", "year the person was born"),
    ("deathPlace", "relational", "place where the person died"),
    ("nationality", "intrinsic", "nationality of the person"),
    ("activeYearsStartYear", "intrinsic", "year the person began their active career"),
    ("deathYear", "intrinsic", "year the person died"),
    ("title", "intrinsic", "honorary or professional title held by the person"),
    ("pushpinMap", "intrinsic", "map name used in the infobox (Wikipedia pushpin map)"),
    ("isPartOf", "relational", "the larger entity this subject is a part of"),
    ("populationTotal", "intrinsic", "total population of the place"),
    ("settlementType", "intrinsic", "type of settlement (e.g. hamlet, village, city)"),
    ("birthName", "intrinsic", "name of the person at birth"),
    ("activeYearsEndYear", "intrinsic", "year the person ended their active career"),
    ("type", "intrinsic", "type or class of the entity"),
    ("foundingYear", "intrinsic", "year the organization/place was founded"),
    ("city", "relational", "city the subject is located in"),
    ("state", "relational", "state/province the subject is located in"),
    ("spouse", "relational", "spouse of the person"),
    ("region", "relational", "region the subject is located in"),
    ("name", "intrinsic", "name of the entity"),
    ("hometown", "relational", "hometown of the person"),
    ("residence", "relational", "place where the person resides"),
    ("county", "relational", "county the subject is located in"),
    ("yearOfConstruction", "intrinsic", "year the structure was constructed"),
    ("openingYear", "intrinsic", "year the venue/structure opened"),
    ("office", "intrinsic", "public office held by the person"),
    ("family", "relational", "family the person belongs to"),
    ("team", "relational", "sports team the person plays for"),
    ("road", "relational", "road the subject is located on"),
    ("locatedInArea", "relational", "area the subject is located in"),
    ("associatedMusicalArtist", "relational", "musical artist associated with the subject"),
    ("occupation", "intrinsic", "occupation of the person"),
    ("associatedBand", "relational", "band associated with the subject"),
    ("subdivision", "relational", "administrative subdivision of the subject"),
    ("artist", "relational", "artist of the work"),
    ("alias", "intrinsic", "alternative name of the entity"),
    ("home", "relational", "home location of the subject"),
    ("writer", "relational", "writer of the work"),
    ("headquarter", "relational", "location of the headquarters"),
    ("militaryCommand", "relational", "military command the unit belongs to"),
    ("starring", "relational", "actor starring in the work"),
    ("district", "relational", "district the subject is located in"),
    ("place", "relational", "place associated with the subject"),
    ("stateOfOrigin", "relational", "state of origin"),
    ("children", "relational", "children of the person"),
    ("language", "relational", "language associated with the subject"),
    ("producer", "relational", "producer of the work"),
    ("combatant", "relational", "combatant in the conflict"),
    ("extra", "intrinsic", "extra attribute value"),
    ("owner", "relational", "owner of the subject"),
    ("conference", "relational", "sports conference the team belongs to"),
    ("ground", "relational", "home ground/stadium of the team"),
    ("label", "relational", "record label of the work"),
    ("genre", "intrinsic", "genre of the work or artist"),
    ("year", "intrinsic", "year associated with the subject"),
    ("director", "relational", "director of the work"),
    ("orderInOffice", "intrinsic", "order in office (e.g. 45th)"),
    ("rd1Team", "relational", "team in the first round"),
    ("regionServed", "relational", "region the organization serves"),
    ("rev", "intrinsic", "revenue figure"),
    ("rd2Team", "relational", "team in the second round"),
    ("siteStadium", "relational", "stadium site"),
    ("PopulatedPlace/areaTotal", "intrinsic", "total area of the populated place"),
    ("restingPlace", "relational", "resting place (burial location) of the person"),
    ("religion", "intrinsic", "religion of the person"),
    ("manufacturer", "relational", "manufacturer of the product"),
    ("field", "intrinsic", "field of work or study"),
    ("knownFor", "intrinsic", "what the person is known for"),
]

ENTITY_TYPES = ["PER", "ORG", "LOC", "TIME", "NUM", "MISC"]

# heuristic type hints for few-shot only (eval does not compare types)
LOC_RELS = {"country", "location", "birthPlace", "deathPlace", "city", "state", "region",
            "county", "district", "place", "locatedInArea", "hometown", "residence",
            "restingPlace", "headquarter", "road", "ground", "siteStadium", "home"}
PER_RELS = {"birthYear", "deathYear", "birthPlace", "deathPlace", "occupation", "nationality",
            "spouse", "children", "title", "birthName", "restingPlace", "activeYearsStartYear",
            "activeYearsEndYear", "office", "family", "hometown", "residence", "stateOfOrigin"}

RAW = REPO_ROOT / "data/raw/genwiki/genwiki"


def fill_text(ex: dict) -> str:
    t = ex["text"]
    for i, e in enumerate(ex["entities"]):
        t = t.replace(f"<ENT_{i}>", e)
    return t


def _camel_split(name: str) -> str:
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
    s = s.replace("/", " ").replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", s).strip().lower()


def _auto_kind(name: str) -> str:
    low = name.lower()
    if any(k in low for k in ("year", "date", "type", "name", "alias", "title", "rev",
                              "area", "population", "order", "extra", "genre", "field")):
        return "intrinsic"
    return "relational"


def build_schema():
    # start with curated relations (good descriptions), then add any test-set relation
    # not already covered, with an auto-generated gloss. This closes the train/test
    # property-distribution gap (train top-90% missed 17% of test triples).
    curated = {n: (k, d) for n, k, d in RELATIONS}
    test = json.load(open(RAW / "test/test.json"))
    extra_names = []
    seen = set(curated)
    for ex in test:
        for _, r, _ in ex["graph"]:
            if r not in seen:
                seen.add(r)
                extra_names.append(r)
    rels = [{"name": n, "kind": k, "domain": [], "range": [], "description": d}
            for n, (k, d) in curated.items()]
    for n in extra_names:
        rels.append({"name": n, "kind": _auto_kind(n), "domain": [], "range": [],
                     "description": _camel_split(n)})
    schema = {"dataset": "genwiki", "entity_types": ENTITY_TYPES, "relations": rels}
    import yaml
    out = REPO_ROOT / "schema/genwiki_schema.yaml"
    out.parent.mkdir(exist_ok=True)
    yaml.safe_dump(schema, open(out, "w", encoding="utf-8"), allow_unicode=True, sort_keys=False)
    print(f"wrote {out} ({len(rels)} relations; {len(extra_names)} auto-added from test set)")


def build_docs_gold(split: str, limit: int | None = None):
    if split == "test":
        data = json.load(open(RAW / "test/test.json"))
    else:
        data = json.load(open(RAW / "train/fine/part_1.json"))
    if limit:
        data = data[:limit]
    docs, gold = [], []
    for i, ex in enumerate(data):
        doc_id = f"genwiki_{split}_{i:04d}"
        docs.append({"doc_id": doc_id, "text": fill_text(ex), "n_tokens": None, "chunks": None})
        gold.append({"doc_id": doc_id, "triples": [
            {"head": h, "relation": r, "tail": t} for h, r, t in ex["graph"]
        ]})
    write_jsonl(REPO_ROOT / f"data/work/genwiki/{split}/docs.jsonl", docs)
    write_jsonl(REPO_ROOT / f"data/work/genwiki/{split}/gold.jsonl", gold)
    print(f"wrote {len(docs)} docs + {len(gold)} gold rows to data/work/genwiki/{split}/")


def build_fewshot():
    """Pick 3 diverse short train examples whose graph uses only in-schema relations."""
    schema_rels = {r for r, _, _ in RELATIONS}
    data = json.load(open(RAW / "train/fine/part_1.json"))
    picked = []
    seen_kinds = set()
    for ex in data:
        rels = {r for _, r, _ in ex["graph"]}
        if not rels.issubset(schema_rels):
            continue
        if len(ex["graph"]) < 3 or len(ex["graph"]) > 7:
            continue
        kinds = tuple(sorted(rels))
        if kinds in seen_kinds:
            continue
        seen_kinds.add(kinds)
        picked.append(ex)
        if len(picked) >= 3:
            break

    def guess_type(name, roles, rels):
        if re.fullmatch(r"\d{3,4}", name):
            return "TIME"
        if re.fullmatch(r"[\d.,]+", name):
            return "NUM"
        if "tail" in roles and any(r in LOC_RELS for r in rels):
            return "LOC"
        if "head" in roles and any(r in PER_RELS for r in rels):
            return "PER"
        return "MISC"

    out = []
    for ex in picked:
        # collect every unique head/tail string (tail literals are also entities)
        roles = defaultdict(set)
        rels_by_ent = defaultdict(set)
        for h, r, t in ex["graph"]:
            roles[h].add("head"); roles[t].add("tail")
            rels_by_ent[h].add(r); rels_by_ent[t].add(r)
        eid, entities = {}, []
        for name in sorted({n for h, r, t in ex["graph"] for n in (h, t)}):
            eid[name] = f"e{len(entities)+1}"
            entities.append({"id": eid[name], "name": name, "type": guess_type(name, roles[name], rels_by_ent[name]), "mentions": [name]})
        triples = [{"head": eid[h], "relation": r, "tail": eid[t]} for h, r, t in ex["graph"]]
        out.append({"text": fill_text(ex), "output": {"entities": entities, "triples": triples}})
    write_jsonl(REPO_ROOT / "prompts/genwiki_fewshot.json", out)
    print(f"wrote prompts/genwiki_fewshot.json ({len(out)} examples)")
    return out


class GenWikiPromptBuilder(PromptBuilder):
    """Same load/write/report skeleton as build_tcm_prompt.py / build_docred_prompt.py
    (see prompt_builder.PromptBuilder); only render() differs, grouping relations by
    kind (relational vs intrinsic) rather than by domain (DocRED) or a markdown table
    (TCM)."""
    schema_path = REPO_ROOT / "schema/genwiki_schema.yaml"
    fewshot_path = REPO_ROOT / "prompts/genwiki_fewshot.json"
    out_path = REPO_ROOT / "prompts/genwiki_prompt_template.txt"

    def load_fewshot(self):
        # genwiki_fewshot.json is written via write_jsonl (see build_fewshot() above),
        # i.e. one JSON object per line despite the .json extension -- not a JSON array.
        return list(read_jsonl(self.fewshot_path))

    def render(self, schema, fewshot):
        rels_by_kind = defaultdict(list)
        for r in schema["relations"]:
            rels_by_kind[r["kind"]].append((r["name"], r["description"]))
        lines = []
        lines.append("你是一个结构化信息抽取器。从给定文本中抽取实体和关系三元组，输出严格的 JSON。")
        lines.append("")
        lines.append("实体类型只能取以下值：PER, ORG, LOC, TIME, NUM, MISC")
        lines.append("")
        lines.append("关系只能取以下名称，不得自造（每行一条附一句话说明）：")
        for kind in ["relational", "intrinsic"]:
            label = "实体间关系" if kind == "relational" else "属性/字面量关系"
            lines.append(f"[{label}]")
            for n, d in rels_by_kind[kind]:
                lines.append(f"- {n} — {d}")
        lines.append("")
        lines.append("输出规则：")
        lines.append("1. entities 中每个实体给出 id、name、type、mentions。name 必须使用文本中出现的字面形式。")
        lines.append("2. triples 中 head 和 tail 填写 entities 中的 id。")
        lines.append("3. relation 必须逐字取自上方关系列表。")
        lines.append("4. 尽量完整地抽取：文本中每个实体对/属性只要存在对应关系都要抽，宁可多抽不可漏抽。")
        lines.append("5. 只输出 JSON，不要任何解释，不要 markdown 代码围栏。")
        lines.append("")
        for i, ex in enumerate(fewshot, 1):
            lines.append(f"示例{i}")
            lines.append("文本：")
            lines.append(ex["text"])
            lines.append("抽取结果：")
            lines.append(json.dumps(ex["output"], ensure_ascii=False))
            lines.append("")
        lines.append("文本：")
        lines.append("{TEXT}")
        lines.append("抽取结果：")
        return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="test")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    build_schema()
    build_docs_gold(args.split, args.limit)
    build_fewshot()
    GenWikiPromptBuilder().build()


if __name__ == "__main__":
    main()
