"""Formats graph_pattern_search results (profile + ranked pattern facts) into readable
Chinese text -- the final "topK facts -> text a human can read" step of the hybrid
pipeline. Templated per relation rather than LLM-generated: deterministic, free, fast
enough to run inline with retrieval, and easy to unit-test/eval against fixed strings.
"""
from __future__ import annotations

RELATION_TEMPLATES = {
    "分型": "{head}分型为{tail}",
    "表现为": "{head}表现为{tail}",
    "主症": "{head}的主症为{tail}",
    "兼症": "{head}常兼见{tail}",
    "治法": "{head}治法为{tail}",
    "方用": "{head}方用{tail}",
    "用药": "{head}常用药：{tail}",
    "病位": "{head}病位在{tail}",
    "病因": "{head}病因为{tail}",
    "鉴别": "{head}与{tail}当鉴别",
    "别名": "{head}又称{tail}",
    "组成": "{head}由{tail}组成",
    "功效": "{head}功效为{tail}",
    "归经": "{head}归经{tail}",
    "主治": "{head}主治{tail}",
    "加药": "{head}若{condition}，加{tail}",
    "减药": "{head}若{condition}，去{tail}",
    "加方": "{head}若{condition}，加用{tail}",
    "换方": "{head}若{condition}，改用{tail}",
    "变证": "{head}若病情发展为{tail}",
}


def _condition_text(condition):
    if isinstance(condition, dict):
        return condition.get("raw") or ""
    return condition or ""


def render_hop(hop, name_of):
    template = RELATION_TEMPLATES.get(hop["relation"], "{head} {relation} {tail}")
    return template.format(
        head=name_of(hop["head"]), tail=name_of(hop["tail"]), relation=hop["relation"],
        condition=_condition_text(hop.get("condition")),
    )


def render_path(hops, name_of):
    """Multi-hop paths are joined as a sequence of full per-hop sentences rather than one
    grammatically-fused sentence (e.g. "感冒分型为风寒束表证；风寒束表证治法为辛温解表")
    -- a bit more repetitive than hand-written prose, but correct for every relation
    combination without a second per-hop "continuation" phrasing table to maintain."""
    return "；".join(render_hop(h, name_of) for h in hops)


CONDITION_RELATIONS = {"加药", "减药", "加方", "换方"}


def render_profile(seed_id, seed_name, profile, name_of, max_per_relation=8):
    """One line per relation the seed participates in (outgoing values joined with "、",
    not one line per edge) -- keeps the profile compact. When a relation has more than
    max_per_relation targets (a "hub" node, e.g. a symptom shared across dozens of
    syndromes), the line is suffixed with "等N项" rather than silently dropping the rest --
    see present_result's docstring on why hiding the count was confusing (完整知识图谱 shows
    every neighbor individually, so 检索's compact one-line-per-relation view needs to at
    least say "there are more" instead of looking like a shorter, less-complete answer).

    Exception: 加药/减药/加方/换方 can carry a different `condition` per edge, so grouping
    them into one joined line would silently drop it (caught by inspecting a real 随证加减
    node: grouped rendering produced "脾胃虚寒证若，去砂仁" with the "若{condition}，" slot
    empty because the group-line template hardcoded condition=""). Those get one line per
    edge instead, via render_hop, so each keeps its own condition text.
    """
    lines = []
    for attr, values in (profile.get("attributes") or {}).items():
        if values:
            lines.append(f"{seed_name}{attr}：{'、'.join(values)}")

    for relation, tails in profile.get("out", {}).items():
        if relation in CONDITION_RELATIONS:
            for t in tails[:max_per_relation]:
                hop = {"head": seed_id, "relation": relation, "tail": t["entity_id"], "condition": t.get("condition")}
                lines.append(render_hop(hop, name_of))
            continue
        names = [name_of(t["entity_id"]) for t in tails[:max_per_relation]]
        extra = f"等{len(tails)}项" if len(tails) > max_per_relation else None
        template = RELATION_TEMPLATES.get(relation, "{head} {relation} {tail}")
        line = template.format(head=seed_name, tail="、".join(names), relation=relation, condition="")
        lines.append(f"{line}（{extra}）" if extra else line)

    for relation, heads in profile.get("in", {}).items():
        if relation in CONDITION_RELATIONS:
            for h in heads[:max_per_relation]:
                hop = {"head": h["entity_id"], "relation": relation, "tail": seed_id, "condition": h.get("condition")}
                lines.append(render_hop(hop, name_of))
            continue
        names = [name_of(h["entity_id"]) for h in heads[:max_per_relation]]
        extra = f"等{len(heads)}项" if len(heads) > max_per_relation else None
        # seed sits on the tail side here; there's no reverse-direction template per
        # relation, so this is phrased generically rather than doubling every entry in
        # RELATION_TEMPLATES for a direction that's only used in this one spot.
        line = f"{'、'.join(names)}的{relation}为{seed_name}"
        lines.append(f"{line}（{extra}）" if extra else line)
    return lines


def present_result(seed, profile, ranked_patterns, nodes, top_k=10):
    """seed={entity_id,name,type}; profile/ranked_patterns come straight out of
    graph_patterns.graph_pattern_search + fusion.rank_facts; nodes = entity_id -> node
    dict, for resolving names of entities touched by pattern hops (not just the seed).

    Returns {"text": "...", "facts": [{"source", "sentence", "hops"?}]}. Profile facts are
    never truncated (they're already compact -- one line per relation, not per edge); topK
    only bounds how many *pattern* facts get appended after them.
    """
    def name_of(entity_id):
        return nodes.get(entity_id, {}).get("name", entity_id)

    profile_facts = [
        {"source": "profile", "sentence": line}
        for line in render_profile(seed["entity_id"], seed["name"], profile, name_of)
    ]
    pattern_facts = [
        {"source": p["pattern_id"], "sentence": render_path(p["hops"], name_of), "hops": p["hops"]}
        for p in ranked_patterns
    ]

    facts = profile_facts + pattern_facts[:top_k]
    text = f"『{seed['name']}』（{seed['type']}）\n" + "\n".join(f"- {f['sentence']}" for f in facts)
    return {"text": text, "facts": facts}
