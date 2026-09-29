"""Step 2-3 of merge/: union-find node clustering across all rounds of one document,
then within-cluster type voting.

Layers run in strict precision order (L1 highest); union-find makes "later layers only
touch what's still separate" free -- a later layer's pairwise check against an
already-merged root just extends the same cluster, it never un-merges anything.

node_type is NEVER part of the merge key. Identity (is this the same entity) comes from
literal text + position only; type (what kind of entity is it) is decided by majority
vote *after* clustering is final -- see build_clusters.
"""
from __future__ import annotations

import unicodedata
from collections import Counter, defaultdict

from .types import Mention, NodeCluster

CONTAINMENT_MAX_LEN_DIFF = 2
CONTAINMENT_MIN_SHORT_LEN = 2


class UnionFind:
    def __init__(self, keys):
        self.parent = {k: k for k in keys}

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def normalize_literal(s: str) -> str:
    """L3 normalization: NFKC (full/halfwidth + compatibility forms) + whitespace
    collapse only. Deliberately does NOT strip semantic suffixes like trailing "证" --
    project history (versions.md v3_zhengsuffix) found naive suffix-stripping silently
    merges terms that sometimes need to stay distinct; the more surgical L5 containment
    rule (length-diff <= 2, type-gated) already recovers most of that case safely."""
    s = unicodedata.normalize("NFKC", s or "")
    return "".join(s.split())


def _spans_overlap(a, b) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def _is_containment(a: str, b: str) -> bool:
    if a == b:
        return False  # handled by L3 already; keep this purely for strict containment
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    if len(short) < CONTAINMENT_MIN_SHORT_LEN:
        return False
    if len(long_) - len(short) > CONTAINMENT_MAX_LEN_DIFF:
        return False
    return short in long_


def cluster_mentions(mentions: list[Mention]):
    """Runs L1-L3 (the layers that don't need the global alias table). Returns
    (UnionFind, index_list); caller runs apply_alias_and_containment for L4-L5, then
    build_clusters to materialize NodeCluster objects. Pure function: fixed input order
    -> fixed output (no randomness anywhere in this module)."""
    idx = list(range(len(mentions)))
    uf = UnionFind(idx)

    anchored = [i for i in idx if mentions[i].char_span is not None]

    # L1: identical char_span
    by_span = defaultdict(list)
    for i in anchored:
        by_span[mentions[i].char_span].append(i)
    for group in by_span.values():
        for j in group[1:]:
            uf.union(group[0], j)

    # L2: partial span overlap
    for a in range(len(anchored)):
        for b in range(a + 1, len(anchored)):
            i, j = anchored[a], anchored[b]
            if uf.find(i) == uf.find(j):
                continue
            if _spans_overlap(mentions[i].char_span, mentions[j].char_span):
                uf.union(i, j)

    # L3: normalized literal equality -- the only path to a cluster for mentions that
    # failed anchoring entirely (position-based rules can't touch them).
    by_norm = defaultdict(list)
    for i in idx:
        by_norm[normalize_literal(mentions[i].text)].append(i)
    for group in by_norm.values():
        for j in group[1:]:
            uf.union(group[0], j)

    return uf, idx


def apply_alias_and_containment(uf: UnionFind, mentions: list[Mention], idx: list[int], alias_lookup) -> None:
    """L4 (global alias table hit) then L5 (containment + same type), mutating uf.
    alias_lookup(norm_a, norm_b, entity_type) -> bool."""
    n = len(idx)

    for a in range(n):
        for b in range(a + 1, n):
            i, j = idx[a], idx[b]
            if uf.find(i) == uf.find(j) or mentions[i].entity_type != mentions[j].entity_type:
                continue
            na, nb = normalize_literal(mentions[i].text), normalize_literal(mentions[j].text)
            if alias_lookup(na, nb, mentions[i].entity_type):
                uf.union(i, j)

    for a in range(n):
        for b in range(a + 1, n):
            i, j = idx[a], idx[b]
            if uf.find(i) == uf.find(j) or mentions[i].entity_type != mentions[j].entity_type:
                continue
            if _is_containment(mentions[i].text, mentions[j].text):
                uf.union(i, j)


def build_clusters(mentions: list[Mention], uf: UnionFind, idx: list[int],
                    doc_id: str, type_priority: list[str]):
    """Materializes final NodeCluster objects. Returns (clusters, {mention_index: cluster_id})."""
    groups = defaultdict(list)
    for i in idx:
        groups[uf.find(i)].append(i)

    priority_rank = {t: r for r, t in enumerate(type_priority)}
    clusters, mention_to_cluster = [], {}
    for n, (root, members) in enumerate(sorted(groups.items())):
        cluster_id = f"{doc_id}#c{n}"
        mem_mentions = [mentions[i] for i in members]

        anchored = [m for m in mem_mentions if m.char_span is not None]
        pool = anchored or mem_mentions
        # canonical = longest literal text among anchored members (falls back to longest
        # overall if nothing anchored); ties broken by round order for determinism.
        canonical_m = min(pool, key=lambda m: (-len(m.text), m.round_idx))
        aliases = sorted({m.text for m in mem_mentions if m.text != canonical_m.text})

        type_votes = Counter(m.entity_type for m in mem_mentions)
        top = max(type_votes.values())
        tied = [t for t, c in type_votes.items() if c == top]
        node_type = min(tied, key=lambda t: priority_rank.get(t, len(type_priority)))

        support = len({m.round_idx for m in mem_mentions})

        clusters.append(NodeCluster(
            cluster_id=cluster_id,
            canonical=canonical_m.text,
            aliases=aliases,
            node_type=node_type,
            type_votes=dict(type_votes),
            char_span=canonical_m.char_span,
            support=support,
            provenance=mem_mentions,
            unanchored=canonical_m.char_span is None,
        ))
        for i in members:
            mention_to_cluster[i] = cluster_id

    return clusters, mention_to_cluster
