"""Schema guardrail for the TCM diagnosis agent.

The agent must never invent entity types or relations, and every Retrieval Request's
`path` must be walkable on the *real* KG schema (schema/tcm_schema.yaml -- the single
source of truth). This module loads that schema and offers:

  - the legal vocabulary (entity types + relations with domain/range),
  - `validate_path(seed_type, path)` -- checks a requested relation chain is type-consistent
    and connected, in either edge orientation (retrieval walks both, see
    retrieval/graph_patterns.py), returning precise rejection reasons for debugging,
  - `vocabulary_block()` -- a compact human/LLM-readable rendering of the vocabulary +
    canonical clinical paths, injected verbatim into the retrieval-request prompt so the
    model is told exactly what it may emit (kept in sync with the schema, never hand-listed).

Nothing here talks to the graph data; it only knows the schema. The retrieval adapter
(retrieval_adapter.py) is what actually executes a validated request against a merged graph.
"""
from __future__ import annotations

import functools
from pathlib import Path

import yaml

from common import REPO_ROOT, load_config

# Canonical clinical paths the product cares about, expressed purely in schema relation
# names. Used both as prompt examples and as safe fallbacks when the model asks to retrieve
# an entity but omits/garbles the path. Each must pass validate_path from its stated seed
# type -- test_agent_loop.py asserts this so the two never drift apart.
CANONICAL_PATHS = {
    "疾病→证候": ("疾病", ["分型"]),
    "疾病→证候→症状": ("疾病", ["分型", "表现为"]),
    "疾病→证候→治法": ("疾病", ["分型", "治法"]),
    "疾病→证候→方剂": ("疾病", ["分型", "方用"]),
    "疾病→证候→方剂→中药": ("疾病", ["分型", "方用", "组成"]),
    "疾病→病因": ("疾病", ["病因"]),
    "证候→治法": ("证候", ["治法"]),
    "证候→方剂": ("证候", ["方用"]),
    "证候→中药": ("证候", ["用药"]),
    "症状→证候": ("症状", ["表现为"]),
    "方剂→中药": ("方剂", ["组成"]),
    "中药→功效": ("中药", ["功效"]),
    "中药→归经": ("中药", ["归经"]),
    "中药→主治": ("中药", ["主治"]),
}


class SchemaSpec:
    def __init__(self, schema: dict):
        raw_types = schema.get("entity_types", [])
        # entity_types entries are either a bare string or a {name, prompt_line} object
        # (see stage2_validate.load_schema) -- normalise to names.
        self.entity_types = [t["name"] if isinstance(t, dict) else t for t in raw_types]
        self._type_set = set(self.entity_types)
        self.relations = {}
        for r in schema.get("relations", []):
            self.relations[r["name"]] = {
                "kind": r.get("kind", "relational"),
                "domain": list(r.get("domain", [])),
                "range": list(r.get("range", [])),
                "description": r.get("description", ""),
            }

    # ---- vocabulary checks ----

    def is_entity_type(self, t: str) -> bool:
        return t in self._type_set

    def is_relation(self, r: str) -> bool:
        return r in self.relations

    def validate_path(self, seed_type: str, path: list[str]) -> tuple[bool, list[str]]:
        """Walk `path` from `seed_type`, allowing each relation to be traversed forward
        (frontier is head, land on range) or backward (frontier is tail, land on domain).
        Returns (ok, errors). A path is legal iff every relation exists and connects to the
        running frontier of possible types in at least one orientation. `intrinsic`
        relations (e.g. 性味) live on a node's attributes, not as edges, so they may only
        appear as the final hop and are treated as a terminal attribute lookup."""
        errors: list[str] = []
        if not self.is_entity_type(seed_type):
            errors.append(f"未知实体类型 seed_type='{seed_type}'（合法类型：{'、'.join(self.entity_types)}）")
            return False, errors
        if not path:
            return True, errors  # bare entity lookup (profile only) is always fine

        frontier = {seed_type}
        for i, rel in enumerate(path):
            spec = self.relations.get(rel)
            if spec is None:
                errors.append(f"第{i+1}跳关系 '{rel}' 不在 schema 中")
                return False, errors
            if spec["kind"] == "intrinsic" and i != len(path) - 1:
                errors.append(f"第{i+1}跳 '{rel}' 是 intrinsic 属性，只能作为路径最后一跳")
                return False, errors
            dom, rng = set(spec["domain"]), set(spec["range"])
            forward = bool(frontier & dom)
            backward = bool(frontier & rng)
            if not (forward or backward):
                errors.append(
                    f"第{i+1}跳 '{rel}' 无法从类型 {{{','.join(sorted(frontier))}}} 出发："
                    f"domain={spec['domain']} range={spec['range']}"
                )
                return False, errors
            nxt = set()
            if forward:
                nxt |= rng
            if backward:
                nxt |= dom
            frontier = nxt
        return True, errors

    # ---- prompt material ----

    def vocabulary_block(self) -> str:
        lines = ["【实体类型】", "、".join(self.entity_types), "", "【关系（domain → range）】"]
        for name, spec in self.relations.items():
            tag = "属性" if spec["kind"] == "intrinsic" else "边"
            lines.append(
                f"- {name}（{tag}）：{'/'.join(spec['domain'])} → {'/'.join(spec['range'])}"
            )
        lines.append("")
        lines.append("【常用检索路径（用关系名表达，可正向或反向走）】")
        for label, (seed, path) in CANONICAL_PATHS.items():
            lines.append(f"- {label}：seed_type={seed}，path={path}")
        return "\n".join(lines)


@functools.lru_cache(maxsize=None)
def load_schema_spec(dataset: str = "TCM") -> SchemaSpec:
    cfg = load_config()
    rel = cfg["datasets"][dataset]["schema_path"]
    schema = yaml.safe_load((REPO_ROOT / rel).read_text())
    return SchemaSpec(schema)
