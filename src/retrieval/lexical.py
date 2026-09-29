"""Tiered keyword search for the hybrid pipeline.

This assumes the caller is an agent passing a precise TCM term. Exact/near-exact matches
should dominate; fuzzy matching is only a fallback for minor surface variants (e.g.
missing the trailing "证").

Tiers, scored so a lower tier can never outrank a higher one. Exact matches are split by
whether they hit the node's own `name` or merely one of its `aliases`: the alias table is
populated by stage7/merge's promotion heuristic (co-occurring surface forms, support>=3),
which is looser than "this literally is the entity's name" -- e.g. several distinct
diseases in the extracted TCM data ended up with "感冒" itself listed as an alias (虚体感冒/
时行感冒/易患感冒/...), so without this split, searching the common term "感冒" returned six
"equally exact" candidates instead of the one disease actually named that:
  1.0        exact match on `name` (normalized: whitespace/punctuation stripped)
  0.95       "证-variant" of the above (also stripping a trailing "证", e.g. query "阳虚" vs
             node "阳虚证" -- see CLAUDE.md/versions.md on 证-suffix compliance being
             inconsistent in the extracted data, so callers routinely omit it)
  0.92       exact match on an *alias* only (not the node's own name)
  0.88       证-variant match on an alias only
  0.6-0.9    substring match either direction, scored by length ratio (shorter/longer) so
             "石淋" against "石淋证" scores higher than "石淋" against a long unrelated name
             that merely contains it
  0.0-0.5    difflib fallback for typos/minor variants, scaled down so it can never beat a
             genuine substring hit
"""
from __future__ import annotations

import difflib
import re
from pathlib import Path

from .graph_io import load_nodes_edges

_STRIP_RE = re.compile(r"[（）()、，,。\s]")


def _exact_norm(s: str) -> str:
    return _STRIP_RE.sub("", s or "").lower()


def _core_norm(s: str) -> str:
    return _exact_norm(s).rstrip("证")


def _surfaces(n: dict) -> list[str]:
    """(surface, is_primary) pairs -- index 0 is the node's own name, the rest are aliases
    (see module docstring on why that distinction matters for tiering)."""
    return [(n["name"], True)] + [(a, False) for a in (n.get("aliases") or [])]


def _score_one(query: str, q_exact: str, q_core: str, surface: str, is_primary: bool):
    """Returns (score, tier) for a single candidate surface string, or None if no match."""
    s_exact = _exact_norm(surface)
    if not s_exact:
        return None
    if q_exact == s_exact:
        return (1.0, "exact") if is_primary else (0.92, "exact_alias")
    s_core = _core_norm(surface)
    if q_core and s_core and q_core == s_core:
        return (0.95, "exact_zheng_variant") if is_primary else (0.88, "exact_alias_zheng_variant")
    shorter, longer = sorted([q_exact, s_exact], key=len)
    if shorter and shorter in longer:
        ratio = len(shorter) / len(longer)
        return 0.6 + 0.3 * ratio, "substring"
    fuzzy = difflib.SequenceMatcher(None, q_exact, s_exact).ratio()
    if fuzzy > 0.5:
        return fuzzy * 0.5, "fuzzy"
    return None


def lexical_search(wd: Path, term: str, top_k: int = 10):
    """Returns [{entity_id, name, type, score, tier, matched_surface, doc_id?}, ...],
    sorted by score descending, best tier per node only (no double-counting a node that
    matches on both its name and an alias)."""
    nodes, _ = load_nodes_edges(wd)
    q_exact, q_core = _exact_norm(term), _core_norm(term)

    scored = []
    for n in nodes.values():
        best = None
        for surface, is_primary in _surfaces(n):
            hit = _score_one(term, q_exact, q_core, surface, is_primary)
            if hit and (best is None or hit[0] > best[0]):
                best = (hit[0], hit[1], surface)
        if best:
            score, tier, surface = best
            entry = {
                "entity_id": n["entity_id"], "name": n["name"], "type": n["type"],
                "score": score, "tier": tier, "matched_surface": surface,
            }
            if "doc_id" in n:
                entry["doc_id"] = n["doc_id"]
            scored.append(entry)

    scored.sort(key=lambda e: -e["score"])
    return scored[:top_k]
