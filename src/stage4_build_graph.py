"""Stage 4: build nodes.jsonl / edges.jsonl / graph.graphml from extraction_valid +
alignment_map + mentions (DESIGN.md 6, entity_id-level graph).

Canonical name/aliases per entity_id are re-derived here (not persisted separately by
stage 3) since alignment_map.jsonl + extraction_valid.jsonl already contain everything
needed: group local_ids sharing an entity_id, take the longest surface name as canonical.

Intrinsic triples become node attributes (attributes[relation] = [tail_entity_name,...]);
relational triples become MultiDiGraph edges. A final entity_id-level identical-triple
dedup pass runs after local_id -> entity_id remapping, since two distinct local_ids can
map to the same merged entity_id and thereby collide (DESIGN.md 5).
"""
import argparse
from collections import defaultdict

import networkx as nx

from core.common import read_jsonl, work_dir, write_jsonl


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="docred")
    ap.add_argument("--split", default="dev")
    args = ap.parse_args()

    wd = work_dir(args.dataset, args.split)

    valid_docs = {d["doc_id"]: d for d in read_jsonl(wd / "extraction_valid.jsonl")}

    # doc_id -> local_id -> entity_id
    local_to_entity = defaultdict(dict)
    for row in read_jsonl(wd / "alignment_map.jsonl"):
        local_to_entity[row["doc_id"]][row["local_id"]] = row["entity_id"]

    # doc_id -> local_id -> [mention_id,...]  (insertion order preserved)
    local_to_mentions = defaultdict(lambda: defaultdict(list))
    for row in read_jsonl(wd / "mentions.jsonl"):
        local_to_mentions[row["doc_id"]][row["local_id"]].append(row["mention_id"])

    # entity_id -> node accumulator
    nodes = {}  # entity_id -> {entity_id, doc_id, name, type, aliases:set, attributes:defaultdict(list), mention_ids:list}
    edges = []
    seen_edge_keys = set()
    # entities folded into another node's attributes via an intrinsic triple, and never
    # otherwise a relational head/tail anywhere in the split -- these get no edges and
    # would show up as always-isolated nodes purely because their info moved to an
    # attribute string, so they're dropped from node_rows at the end (DESIGN.md /
    # CLAUDE.md "kind: intrinsic 挂成头实体 attributes 里的字符串，性味本身不作为图节点").
    intrinsic_tail_entities = set()
    relational_participant_entities = set()

    for doc_id, doc in valid_docs.items():
        entity_by_local = {e["local_id"]: e for e in doc["entities"]}
        entity_ids_this_doc = local_to_entity[doc_id]

        # group local_ids by entity_id to compute canonical name/aliases
        groups = defaultdict(list)
        for local_id, entity_id in entity_ids_this_doc.items():
            groups[entity_id].append(local_id)

        for entity_id, local_ids in groups.items():
            members = [entity_by_local[lid] for lid in local_ids if lid in entity_by_local]
            if not members:
                continue
            canonical = max(members, key=lambda e: len(e["name"]))
            aliases = sorted({m["name"] for m in members if m["name"] != canonical["name"]})
            mention_ids = []
            for lid in local_ids:
                mention_ids.extend(local_to_mentions[doc_id].get(lid, []))
            nodes[entity_id] = {
                "entity_id": entity_id,
                "doc_id": doc_id,
                "name": canonical["name"],
                "type": canonical["type"],
                "aliases": aliases,
                "attributes": defaultdict(list),
                "mention_ids": mention_ids,
            }

        for t in doc["triples"]:
            head_entity = entity_ids_this_doc.get(t["head"])
            tail_entity = entity_ids_this_doc.get(t["tail"])
            if head_entity is None or tail_entity is None or head_entity not in nodes:
                continue

            if t["kind"] == "intrinsic":
                tail_name = nodes.get(tail_entity, {}).get("name") or entity_by_local.get(t["tail"], {}).get("name")
                if tail_name and tail_name not in nodes[head_entity]["attributes"][t["relation"]]:
                    nodes[head_entity]["attributes"][t["relation"]].append(tail_name)
                intrinsic_tail_entities.add(tail_entity)
            else:
                relational_participant_entities.add(head_entity)
                relational_participant_entities.add(tail_entity)
                # condition is part of the identity for 加药/减药/加方/换方/变证: the same
                # (head, relation, tail) can legitimately recur under different 随证加减
                # trigger conditions in one doc (e.g. two different symptom clauses both
                # add the same herb), and collapsing those would silently drop a condition.
                key = (doc_id, head_entity, t["relation"], tail_entity, t.get("condition"))
                if key in seen_edge_keys:
                    continue
                seen_edge_keys.add(key)
                edges.append(
                    {
                        "edge_id": f"{doc_id}#e{len(edges)}",
                        "doc_id": doc_id,
                        "head": head_entity,
                        "relation": t["relation"],
                        "pid": t["pid"],
                        "tail": tail_entity,
                        "condition": t.get("condition"),
                        "provenance": {
                            "head_mention_ids": local_to_mentions[doc_id].get(t["head"], []),
                            "tail_mention_ids": local_to_mentions[doc_id].get(t["tail"], []),
                        },
                    }
                )

    folded_only = intrinsic_tail_entities - relational_participant_entities

    node_rows = []
    for n in nodes.values():
        if n["entity_id"] in folded_only:
            continue
        node_rows.append(
            {
                "entity_id": n["entity_id"],
                "doc_id": n["doc_id"],
                "name": n["name"],
                "type": n["type"],
                "aliases": n["aliases"],
                "attributes": dict(n["attributes"]),
                "mention_ids": n["mention_ids"],
            }
        )

    write_jsonl(wd / "nodes.jsonl", node_rows)
    write_jsonl(wd / "edges.jsonl", edges)

    g = nx.MultiDiGraph()
    for n in node_rows:
        g.add_node(
            n["entity_id"],
            name=n["name"],
            type=n["type"],
            aliases=",".join(n["aliases"]),
            attributes=str(n["attributes"]),
        )
    for e in edges:
        condition = e.get("condition")
        # condition is a plain string as of v4_pro; older v4 splits stored {"raw": ...}.
        condition_raw = (condition.get("raw") if isinstance(condition, dict) else condition) or ""
        g.add_edge(
            e["head"], e["tail"], relation=e["relation"], pid=e["pid"] or "",
            edge_id=e["edge_id"], condition=condition_raw,
        )
    nx.write_graphml(g, wd / "graph.graphml")

    print(f"nodes: {len(node_rows)}, edges: {len(edges)}")
    print(f"graph.graphml written to {wd/'graph.graphml'}")


if __name__ == "__main__":
    main()
