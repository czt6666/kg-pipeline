"""Stage 0: build resources/schemas/docred.yaml from official DocRED labels.

Reads data/raw/docred/{rel_info.json,train_annotated.json} and produces:
  - resources/schemas/docred.yaml           (per DESIGN.md 1.4)
  - resources/schemas/docred_domain_range_stats.json  (audit trail for domain/range coverage)

Entity types and relation names/pids are taken verbatim from the official files.
domain/range are computed as the (head_type, tail_type) pairs that cumulatively
cover >= COVERAGE_THRESHOLD of that relation's labeled instances in train_annotated.
kind is derived from range: intrinsic if range subset of {TIME, NUM}, else relational
(this codifies the rule stated in DESIGN.md 1.1 rather than a manual pass).
"""
import json
import yaml
from collections import Counter, defaultdict
from pathlib import Path

RAW_DIR = Path("data/raw/docred")
SCHEMA_DIR = Path("resources/schemas")
COVERAGE_THRESHOLD = 0.95
LITERAL_TYPES = {"TIME", "NUM"}


def main():
    rel_info = json.loads((RAW_DIR / "rel_info.json").read_text())
    docs = json.loads((RAW_DIR / "train_annotated.json").read_text())
    descriptions = json.loads((RAW_DIR / "wikidata_property_descriptions.json").read_text())

    entity_types = set()
    pair_counts = defaultdict(Counter)  # pid -> Counter[(head_type, tail_type)]
    rel_total = Counter()

    for doc in docs:
        vertex_set = doc["vertexSet"]
        for vs in vertex_set:
            for m in vs:
                entity_types.add(m["type"])
        # each vertex can have multiple mentions with possibly different-cased
        # but same type per DocRED convention; take the first mention's type
        vtype = [vs[0]["type"] for vs in vertex_set]
        for label in doc["labels"]:
            pid = label["r"]
            h, t = label["h"], label["t"]
            ht, tt = vtype[h], vtype[t]
            pair_counts[pid][(ht, tt)] += 1
            rel_total[pid] += 1

    entity_types = sorted(entity_types)
    assert entity_types == ["LOC", "MISC", "NUM", "ORG", "PER", "TIME"], entity_types

    relations = []
    stats_audit = {}
    for pid, name in rel_info.items():
        counts = pair_counts.get(pid)
        total = rel_total.get(pid, 0)
        if not counts or total == 0:
            # relation never appears in train_annotated (possible for a few rare P-ids)
            domain, range_ = [], []
            covered_pairs = []
            coverage_achieved = 0.0
        else:
            ranked = counts.most_common()
            cum = 0
            covered_pairs = []
            for pair, c in ranked:
                covered_pairs.append({"head_type": pair[0], "tail_type": pair[1], "count": c})
                cum += c
                if cum / total >= COVERAGE_THRESHOLD:
                    break
            domain = sorted({p["head_type"] for p in covered_pairs})
            range_ = sorted({p["tail_type"] for p in covered_pairs})
            coverage_achieved = cum / total

        kind = "intrinsic" if range_ and set(range_).issubset(LITERAL_TYPES) else "relational"

        relations.append(
            {
                "name": name,
                "pid": pid,
                "kind": kind,
                "domain": domain,
                "range": range_,
                "description": descriptions[pid],
            }
        )
        stats_audit[pid] = {
            "name": name,
            "total_instances": total,
            "coverage_achieved": round(coverage_achieved, 4),
            "covered_pairs": covered_pairs,
        }

    # keep schema.yaml relation order stable (sorted by pid numeric part) for prompt/prefix-cache stability
    relations.sort(key=lambda r: int(r["pid"][1:]))

    schema = {
        "dataset": "docred",
        "entity_types": entity_types,
        "relations": relations,
    }

    SCHEMA_DIR.mkdir(exist_ok=True)
    with open(SCHEMA_DIR / "docred.yaml", "w", encoding="utf-8") as f:
        yaml.dump(schema, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

    with open(SCHEMA_DIR / "docred_domain_range_stats.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "coverage_threshold": COVERAGE_THRESHOLD,
                "literal_types": sorted(LITERAL_TYPES),
                "per_relation": stats_audit,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    n_intrinsic = sum(1 for r in relations if r["kind"] == "intrinsic")
    n_relational = len(relations) - n_intrinsic
    print(f"entity_types: {entity_types}")
    print(f"relations: {len(relations)} total, {n_intrinsic} intrinsic, {n_relational} relational")
    print(f"relations with zero train instances: {sum(1 for pid in rel_info if rel_total.get(pid, 0) == 0)}")


if __name__ == "__main__":
    main()
