"""Step 1 of merge/: locate each entity literal's character span in the source chunk
text. Pure, deterministic, no network access.

Algorithm (fixed order, first hit wins):
  1. exact match: source_text.find(literal)
  2. longest matchable prefix: truncate from the right one character at a time until a
     substring is found (a hit shorter than MIN_ANCHOR_LEN does not count -- that floor
     only applies to this truncated-prefix fallback, not to an exact match on the
     original literal, so legitimate short entities like "肺"/"脾" still anchor on step 1)
  3. failure: char_span=None, anchor_method="unanchored"

When a literal occurs more than once in the text, the occurrence nearest to a "partner"
span (the other endpoint of the same triple) is picked -- see anchor_entities_for_round.
"""
from __future__ import annotations

from collections import defaultdict

MIN_ANCHOR_LEN = 2


def _find_all(haystack: str, needle: str) -> list[int]:
    if not needle:
        return []
    out, start = [], 0
    while True:
        i = haystack.find(needle, start)
        if i == -1:
            return out
        out.append(i)
        start = i + 1


def _nearest(positions: list[int], length: int, partner_spans: list[tuple[int, int]]) -> tuple[int, int]:
    if len(positions) == 1 or not partner_spans:
        p = positions[0]
        return (p, p + length)
    centers = [(a + b) / 2 for a, b in partner_spans]

    def dist(p):
        mid = p + length / 2
        return min(abs(mid - c) for c in centers)

    best = min(positions, key=dist)
    return (best, best + length)


def anchor_literal(text: str, literal: str, partner_spans: list[tuple[int, int]] | None = None):
    """Returns (char_span|None, anchor_method, matched_text, ambiguous: bool)."""
    partner_spans = partner_spans or []
    if not literal:
        return None, "unanchored", literal, False

    positions = _find_all(text, literal)
    if positions:
        return _nearest(positions, len(literal), partner_spans), "exact", literal, len(positions) > 1

    candidate = literal[:-1]
    while len(candidate) >= MIN_ANCHOR_LEN:
        positions = _find_all(text, candidate)
        if positions:
            return _nearest(positions, len(candidate), partner_spans), "prefix", candidate, len(positions) > 1
        candidate = candidate[:-1]

    return None, "unanchored", literal, False


def anchor_entities_for_round(text: str, entities: list[dict], triples: list[dict]) -> dict:
    """entities: [{local_id, name, type}], triples: [{head, tail, ...}] (local_id refs,
    same round). Returns {local_id: {"span": (a,b)|None, "method": str, "matched": str}}.

    Two passes: pass 1 anchors every literal with no partner info (an ambiguous one gets
    its first occurrence as a placeholder). Pass 2 re-resolves the ones flagged
    ambiguous using whatever partner spans pass 1 produced. This is a documented,
    deterministic two-pass approximation, not a global fixed point -- if a literal's
    partner is itself still ambiguous after pass 1, its placeholder span is used as-is.
    """
    partners = defaultdict(set)
    for t in triples:
        h, tl = t.get("head"), t.get("tail")
        if h and tl:
            partners[h].add(tl)
            partners[tl].add(h)

    prelim = {}
    for e in entities:
        span, method, matched, ambiguous = anchor_literal(text, e["name"])
        prelim[e["local_id"]] = {"span": span, "method": method, "matched": matched, "ambiguous": ambiguous}

    final = {}
    for e in entities:
        lid = e["local_id"]
        p = prelim[lid]
        if p["ambiguous"]:
            partner_spans = [prelim[pid]["span"] for pid in partners.get(lid, ())
                              if prelim.get(pid, {}).get("span")]
            if partner_spans:
                span, method, matched, _ = anchor_literal(text, e["name"], partner_spans)
                p = {"span": span, "method": method, "matched": matched}
        final[lid] = {"span": p["span"], "method": p["method"], "matched": p["matched"]}
    return final
