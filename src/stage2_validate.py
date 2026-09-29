"""Stage 2: validate extraction_raw.jsonl against schema, align mentions to source text.

Implements DESIGN.md section 3 (validation rules, in order) and 2.6 (source alignment).
Reads extraction_raw.jsonl + docs.jsonl + schema; writes extraction_valid.jsonl,
warnings.jsonl, mentions.jsonl.
"""
import argparse
import difflib
import re
import unicodedata
from collections import defaultdict

import yaml

from common import read_jsonl, work_dir, write_jsonl

LITERAL_TYPES = {"TIME", "NUM"}

# v4/v4_pro: 加药/减药/加方/换方 must carry a condition (v4_pro emits a plain string;
# v4 emitted a {"raw":..., "refs":[...]} dict -- see condition_text() below).
CONDITION_RELATIONS = {"加药", "减药", "加方", "换方"}

# v4/v4_pro 二: these bare deficiency terms are 证候, not 症状, even though they look like
# short symptom words -- the model sometimes mistypes them, so enforce it in code too.
BARE_SYNDROME_NAMES = {"阳虚", "阴虚", "气虚", "血虚", "气阴两虚", "脾阳不振", "脾虚气陷"}

# v4/v4_pro 二: 治法功效 containing these characters is a 方义说明 (in-formula rationale
# referring to another herb/effect), not a standalone effect entity -- e.g. "防地黄之滋腻".
FANGYI_CHARS = set("之合以防")


def condition_text(raw_condition):
    """Normalizes a raw `condition` value to a plain string or None. v4_pro emits a plain
    string directly. v4 emitted {"raw": ..., "refs": [...]} -- refs pointed at entities
    minted solely to be pointed at (e.g. "阴虚火旺"/"胃火上炎" parsed out of a 若……者
    clause), which then sat in the graph with no other edges; v4_pro dropped refs and
    stopped extracting those entities altogether, so this only needs the raw text now.
    Dict form is still accepted here for backward compat with already-extracted v4 splits.
    """
    if isinstance(raw_condition, str):
        return raw_condition.strip() or None
    if isinstance(raw_condition, dict):
        return (raw_condition.get("raw") or "").strip() or None
    return None


def normalize_entities(doc_id, valid_entities, warnings_out):
    """v4/v4_pro: fix up 证候/症状 typing that the model gets wrong often enough to be
    worth enforcing in code rather than trusting the prompt alone (see CLAUDE.md/versions.md
    history on 证 suffix compliance)."""
    def warn(rule, payload):
        warnings_out.append({"doc_id": doc_id, "stage": "validate", "rule": rule, "payload": payload})

    for ent in valid_entities.values():
        if ent["type"] not in ("症状", "证候"):
            continue

        if ent["type"] == "症状" and ent["name"] in BARE_SYNDROME_NAMES:
            warn("retyped_symptom_to_syndrome", {"local_id": ent["local_id"], "name": ent["name"]})
            ent["type"] = "证候"

        if ent["type"] == "证候" and not ent["name"].endswith("证"):
            fixed = ent["name"] + "证"
            warn("zheng_suffix_added", {"local_id": ent["local_id"], "from": ent["name"], "to": fixed})
            ent["name"] = fixed


def drop_fangyi_entities(doc_id, valid_entities, valid_triples, warnings_out):
    """v4: 治法功效 entities that are really in-formula rationale phrases (含"之合以防")
    aren't real effect nodes -- drop them and any triple (功效 or otherwise) touching them."""
    def warn(rule, payload):
        warnings_out.append({"doc_id": doc_id, "stage": "validate", "rule": rule, "payload": payload})

    drop_ids = {
        local_id for local_id, ent in valid_entities.items()
        if ent["type"] == "治法功效" and any(ch in ent["name"] for ch in FANGYI_CHARS)
    }
    if not drop_ids:
        return valid_triples

    for local_id in drop_ids:
        warn("fangyi_entity_dropped", {"entity": valid_entities[local_id]})
        del valid_entities[local_id]

    kept_triples = []
    for tr in valid_triples:
        if tr["head"] in drop_ids or tr["tail"] in drop_ids:
            warn("fangyi_triple_dropped", {"triple": tr})
            continue
        kept_triples.append(tr)
    return kept_triples


def normalize_relation_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def load_schema(path):
    schema = yaml.safe_load(open(path, encoding="utf-8"))
    # entity_types is a flat list of name strings for docred/genwiki, but a list of
    # {name, prompt_line} objects for TCM (which needs per-type prompt text) -- accept both.
    entity_types = {e["name"] if isinstance(e, dict) else e for e in schema["entity_types"]}
    rel_by_norm_name = {}
    for r in schema["relations"]:
        rel_by_norm_name[normalize_relation_name(r["name"])] = r
    return entity_types, rel_by_norm_name


def validate_doc(doc_id, parsed, entity_types, rel_by_norm_name, warnings_out):
    def warn(rule, payload):
        warnings_out.append({"doc_id": doc_id, "stage": "validate", "rule": rule, "payload": payload})

    raw_entities = parsed.get("entities", [])
    raw_triples = parsed.get("triples", [])

    valid_entities = {}
    for e in raw_entities:
        if not isinstance(e, dict):
            warn("malformed_entity", {"entity": e})
            continue
        local_id = e.get("id")
        etype = e.get("type")
        if local_id is None or etype not in entity_types:
            warn("unknown_type", {"entity": e})
            continue
        valid_entities[local_id] = {
            "local_id": local_id,
            "name": e.get("name", ""),
            "type": etype,
            "mentions": e.get("mentions") or [e.get("name", "")],
        }

    normalize_entities(doc_id, valid_entities, warnings_out)

    seen_triples = set()
    valid_triples = []
    for t in raw_triples:
        if not isinstance(t, dict):
            warn("malformed_triple", {"triple": t})
            continue
        head, tail = t.get("head"), t.get("tail")
        if head not in valid_entities or tail not in valid_entities:
            warn("dangling_ref", {"triple": t})
            continue

        norm_rel = normalize_relation_name(t.get("relation", ""))
        rel_def = rel_by_norm_name.get(norm_rel)
        if rel_def is None:
            warn("unknown_relation", {"triple": t})
            continue

        head_type = valid_entities[head]["type"]
        tail_type = valid_entities[tail]["type"]
        domain, range_ = set(rel_def["domain"]), set(rel_def["range"])
        flipped = False

        def satisfies(ht, tt):
            return (not domain or ht in domain) and (not range_ or tt in range_)

        if satisfies(head_type, tail_type):
            pass
        elif satisfies(tail_type, head_type):
            head, tail = tail, head
            head_type, tail_type = tail_type, head_type
            flipped = True
            warn("flipped", {"triple": t})
        else:
            warn("type_violation", {"triple": t, "head_type": head_type, "tail_type": tail_type})
            continue

        kind = rel_def["kind"]
        if kind == "intrinsic" and tail_type not in LITERAL_TYPES and tail_type not in range_:
            warn("intrinsic_nonliteral", {"triple": t, "tail_type": tail_type})
        if kind == "relational" and tail_type in LITERAL_TYPES:
            warn("relational_literal", {"triple": t, "tail_type": tail_type})

        # v4/v4_pro: 加药/减药/加方/换方 must carry a condition; every other relation must not.
        raw_condition = t.get("condition")
        rel_name = rel_def["name"]
        if rel_name in CONDITION_RELATIONS:
            condition = condition_text(raw_condition)
            if condition is None:
                warn("missing_condition", {"triple": t})
                continue
        elif raw_condition:
            warn("unexpected_condition", {"triple": t})
            continue
        else:
            condition = None

        key = (head, rel_def["name"], tail)
        if key in seen_triples:
            warn("duplicate", {"triple": t})
            continue
        seen_triples.add(key)

        valid_triples.append(
            {"head": head, "relation": rel_def["name"], "tail": tail, "pid": rel_def.get("pid"),
             "kind": kind, "flipped": flipped, "condition": condition}
        )

    valid_triples = drop_fangyi_entities(doc_id, valid_entities, valid_triples, warnings_out)

    return {"doc_id": doc_id, "entities": list(valid_entities.values()), "triples": valid_triples}, valid_entities


def validate_modifiers(doc_id, raw_modifiers, valid_entities, warnings_out):
    """v2_pro only: 随证加减 (conditional add/remove of herbs), kept out of the main
    triple graph since they're conditional, not asserted facts. head/condition_symptoms/
    add/remove reference local_ids from the same doc's entities; dangling ones are dropped
    (with a warning) rather than dropping the whole modifier row.
    """
    def warn(rule, payload):
        warnings_out.append({"doc_id": doc_id, "stage": "validate", "rule": rule, "payload": payload})

    valid_modifiers = []
    for m in raw_modifiers:
        if not isinstance(m, dict):
            warn("malformed_modifier", {"modifier": m})
            continue
        head = m.get("head")
        if head not in valid_entities:
            warn("modifier_dangling_head", {"modifier": m})
            continue

        def filter_ids(ids, rule):
            kept = [i for i in ids or [] if i in valid_entities]
            if len(kept) != len(ids or []):
                warn(rule, {"modifier": m})
            return kept

        valid_modifiers.append({
            "local_id": m.get("id"),
            "head": head,
            "condition": m.get("condition", ""),
            "condition_symptoms": filter_ids(m.get("condition_symptoms"), "modifier_dangling_condition_symptom"),
            "add": filter_ids(m.get("add"), "modifier_dangling_add"),
            "remove": filter_ids(m.get("remove"), "modifier_dangling_remove"),
        })
    return valid_modifiers


def normalize_surface(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = s.strip()
    s = re.sub(r"\s+", " ", s)
    return s


def align_mentions(doc_id, text, entities, mentions_out):
    """Exact substring match first (occurrences consumed in text order across all
    mentions requesting the same surface string); difflib longest-match-block fallback;
    otherwise align_method=none. Mutates mentions_out (list) and returns
    local_id -> [mention_id,...] map for stage 4 provenance.
    """
    occurrence_cursor = defaultdict(int)  # surface -> next unused occurrence index
    occurrence_positions = {}  # surface -> [start,...] all occurrences in text

    def positions_for(surface):
        if surface not in occurrence_positions:
            positions = [m.start() for m in re.finditer(re.escape(surface), text)]
            occurrence_positions[surface] = positions
        return occurrence_positions[surface]

    local_id_to_mention_ids = defaultdict(list)
    idx = 0
    for e in entities:
        for surface in e["mentions"]:
            mention_id = f"{doc_id}#m{idx}"
            idx += 1
            positions = positions_for(surface)
            cursor = occurrence_cursor[surface]
            if cursor < len(positions):
                start = positions[cursor]
                occurrence_cursor[surface] += 1
                mentions_out.append(
                    {"mention_id": mention_id, "doc_id": doc_id, "local_id": e["local_id"],
                     "surface": surface, "char_start": start, "char_end": start + len(surface),
                     "align_method": "exact"}
                )
            else:
                sm = difflib.SequenceMatcher(None, text, surface, autojunk=False)
                block = sm.find_longest_match(0, len(text), 0, len(surface))
                if block.size > 0:
                    mentions_out.append(
                        {"mention_id": mention_id, "doc_id": doc_id, "local_id": e["local_id"],
                         "surface": surface, "char_start": block.a, "char_end": block.a + block.size,
                         "align_method": "fuzzy"}
                    )
                else:
                    mentions_out.append(
                        {"mention_id": mention_id, "doc_id": doc_id, "local_id": e["local_id"],
                         "surface": surface, "char_start": None, "char_end": None,
                         "align_method": "none"}
                    )
            local_id_to_mention_ids[e["local_id"]].append(mention_id)
    return local_id_to_mention_ids


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="docred")
    ap.add_argument("--split", default="dev")
    args = ap.parse_args()

    wd = work_dir(args.dataset, args.split)
    entity_types, rel_by_norm_name = load_schema(f"schema/{args.dataset}_schema.yaml")
    docs_by_id = {d["doc_id"]: d for d in read_jsonl(wd / "docs.jsonl")}

    valid_rows, warnings_rows, mentions_rows, modifiers_rows = [], [], [], []
    n_ok = n_failed = 0
    for raw in read_jsonl(wd / "extraction_raw.jsonl"):
        doc_id = raw["doc_id"]
        if raw["parse_status"] == "failed" or raw["parsed"] is None:
            n_failed += 1
            continue
        if not isinstance(raw["parsed"], dict):
            # Model occasionally emits a bare top-level JSON array instead of the
            # expected {"entities": [...], "triples": [...]} object -- treat like a
            # parse failure (no entities/triples) instead of crashing the whole
            # stage. Rare enough that the other rounds cover the doc in 3round merge.
            warnings_rows.append({"doc_id": doc_id, "stage": "validate", "rule": "malformed_doc",
                                  "payload": {"parsed_type": type(raw["parsed"]).__name__}})
            n_failed += 1
            continue
        n_ok += 1
        valid_doc, valid_entities = validate_doc(doc_id, raw["parsed"], entity_types, rel_by_norm_name, warnings_rows)
        valid_rows.append(valid_doc)
        text = docs_by_id[doc_id]["text"]
        align_mentions(doc_id, text, valid_doc["entities"], mentions_rows)

        raw_modifiers = raw["parsed"].get("modifiers", [])
        valid_modifiers = validate_modifiers(doc_id, raw_modifiers, valid_entities, warnings_rows)
        modifiers_rows.append({"doc_id": doc_id, "modifiers": valid_modifiers})

    write_jsonl(wd / "extraction_valid.jsonl", valid_rows)
    write_jsonl(wd / "warnings.jsonl", warnings_rows)
    write_jsonl(wd / "mentions.jsonl", mentions_rows)
    write_jsonl(wd / "modifiers.jsonl", modifiers_rows)

    rule_counts = defaultdict(int)
    for w in warnings_rows:
        rule_counts[w["rule"]] += 1
    align_counts = defaultdict(int)
    for m in mentions_rows:
        align_counts[m["align_method"]] += 1

    print(f"docs: ok={n_ok} failed={n_failed}")
    print(f"entities: {sum(len(v['entities']) for v in valid_rows)}, "
          f"triples: {sum(len(v['triples']) for v in valid_rows)}, "
          f"modifiers: {sum(len(m['modifiers']) for m in modifiers_rows)}")
    print(f"warnings: {dict(rule_counts)}")
    print(f"alignment: {dict(align_counts)}")


if __name__ == "__main__":
    main()
