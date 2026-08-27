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

    seen_triples = set()
    valid_triples = []
    for t in raw_triples:
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
        if kind == "intrinsic" and tail_type not in LITERAL_TYPES:
            warn("intrinsic_nonliteral", {"triple": t, "tail_type": tail_type})
        if kind == "relational" and tail_type in LITERAL_TYPES:
            warn("relational_literal", {"triple": t, "tail_type": tail_type})

        key = (head, rel_def["name"], tail)
        if key in seen_triples:
            warn("duplicate", {"triple": t})
            continue
        seen_triples.add(key)

        valid_triples.append(
            {"head": head, "relation": rel_def["name"], "tail": tail, "pid": rel_def.get("pid"),
             "kind": kind, "flipped": flipped}
        )

    return {"doc_id": doc_id, "entities": list(valid_entities.values()), "triples": valid_triples}


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

    valid_rows, warnings_rows, mentions_rows = [], [], []
    n_ok = n_failed = 0
    for raw in read_jsonl(wd / "extraction_raw.jsonl"):
        doc_id = raw["doc_id"]
        if raw["parse_status"] == "failed" or raw["parsed"] is None:
            n_failed += 1
            continue
        n_ok += 1
        valid_doc = validate_doc(doc_id, raw["parsed"], entity_types, rel_by_norm_name, warnings_rows)
        valid_rows.append(valid_doc)
        text = docs_by_id[doc_id]["text"]
        align_mentions(doc_id, text, valid_doc["entities"], mentions_rows)

    write_jsonl(wd / "extraction_valid.jsonl", valid_rows)
    write_jsonl(wd / "warnings.jsonl", warnings_rows)
    write_jsonl(wd / "mentions.jsonl", mentions_rows)

    rule_counts = defaultdict(int)
    for w in warnings_rows:
        rule_counts[w["rule"]] += 1
    align_counts = defaultdict(int)
    for m in mentions_rows:
        align_counts[m["align_method"]] += 1

    print(f"docs: ok={n_ok} failed={n_failed}")
    print(f"entities: {sum(len(v['entities']) for v in valid_rows)}, "
          f"triples: {sum(len(v['triples']) for v in valid_rows)}")
    print(f"warnings: {dict(rule_counts)}")
    print(f"alignment: {dict(align_counts)}")


if __name__ == "__main__":
    main()
