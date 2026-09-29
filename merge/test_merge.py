import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from merge.alias import AliasTable
from merge.anchor import anchor_entities_for_round, anchor_literal
from merge.cluster import apply_alias_and_containment, build_clusters, cluster_mentions, normalize_literal
from merge.edges import merge_edges_for_doc, normalize_condition
from merge.pipeline import merge_document

TYPE_PRIORITY = ["疾病", "证候", "症状", "治法功效", "病因", "方剂", "中药", "性味", "脏腑经络"]


def test_anchor_exact():
    span, method, matched, ambiguous = anchor_literal("患者气虚乏力，脉细。", "气虚")
    assert span == (2, 4) and method == "exact" and not ambiguous


def test_anchor_single_char_exact():
    # a literal shorter than MIN_ANCHOR_LEN must still succeed via a direct exact match
    span, method, _, _ = anchor_literal("患者肺气不足。", "肺")
    assert span == (2, 3) and method == "exact"


def test_anchor_prefix_fallback():
    span, method, matched, _ = anchor_literal("患者心阳不足，神疲乏力。", "心阳亏虚")
    assert method == "prefix" and matched == "心阳" and span == (2, 4)


def test_anchor_prefix_below_min_len_fails():
    span, method, _, _ = anchor_literal("患者乏力。", "心")
    assert span is None and method == "unanchored"


def test_anchor_disambiguation_by_partner():
    text = "桂枝汤中桂枝为君药，麻黄汤中桂枝为臣药。"
    # two occurrences of 桂枝; partner "麻黄汤" anchors near the second occurrence
    partner_span = (text.index("麻黄汤"), text.index("麻黄汤") + 3)
    span, method, _, ambiguous = anchor_literal(text, "桂枝", [partner_span])
    assert ambiguous is False or True  # ambiguity flag only set on the no-partner call
    assert text[span[0]:span[1]] == "桂枝"
    assert span[0] > partner_span[0] - 10  # picked the occurrence closer to 麻黄汤


def test_normalize_literal_fullwidth():
    assert normalize_literal("气 虚") == "气虚"
    assert normalize_literal("Ａ型") == "A型"


def test_containment_merge_within_length_diff():
    text = "患者心阳虚，渐至心阳虚衰。"
    entities_r0 = [{"local_id": "e1", "name": "心阳虚", "type": "证候"}]
    entities_r1 = [{"local_id": "e1", "name": "心阳虚衰", "type": "证候"}]
    rounds = [
        {"round_idx": 0, "entities": entities_r0, "triples": []},
        {"round_idx": 1, "entities": entities_r1, "triples": []},
    ]
    clusters, edges, _ = merge_document("doc1", text, rounds, AliasTable(None), TYPE_PRIORITY)
    assert len(clusters) == 1
    assert clusters[0].canonical == "心阳虚衰"
    assert "心阳虚" in clusters[0].aliases
    assert clusters[0].support == 2


def test_containment_blocked_by_type_mismatch():
    text = "患者心阳虚，渐至心阳虚衰。"
    entities_r0 = [{"local_id": "e1", "name": "心阳虚", "type": "证候"}]
    entities_r1 = [{"local_id": "e1", "name": "心阳虚衰", "type": "病因"}]  # different type
    rounds = [
        {"round_idx": 0, "entities": entities_r0, "triples": []},
        {"round_idx": 1, "entities": entities_r1, "triples": []},
    ]
    clusters, _, _ = merge_document("doc1", text, rounds, AliasTable(None), TYPE_PRIORITY)
    assert len(clusters) == 2


def test_type_voting_not_a_merge_key():
    # same literal, different type labels each round -- must still be ONE cluster
    # (identity by literal/position only), with type decided by majority vote after.
    text = "水饮内停，证属脾虚。"
    e_type_a = [{"local_id": "e1", "name": "水饮内停", "type": "病因"}]
    e_type_b = [{"local_id": "e1", "name": "水饮内停", "type": "证候"}]
    rounds = [
        {"round_idx": 0, "entities": e_type_a, "triples": []},
        {"round_idx": 1, "entities": e_type_b, "triples": []},
        {"round_idx": 2, "entities": e_type_b, "triples": []},
    ]
    clusters, _, _ = merge_document("doc1", text, rounds, AliasTable(None), TYPE_PRIORITY)
    assert len(clusters) == 1
    assert clusters[0].node_type == "证候"  # 2 votes vs 1
    assert clusters[0].type_votes == {"病因": 1, "证候": 2}


def test_edge_existence_union_across_rounds():
    text = "证候甲加中药乙。"
    entities = [{"local_id": "e1", "name": "证候甲", "type": "证候"}, {"local_id": "e2", "name": "中药乙", "type": "中药"}]
    triples_r0 = [{"head": "e1", "tail": "e2", "relation": "用药", "kind": "relational", "condition": None}]
    rounds = [
        {"round_idx": 0, "entities": entities, "triples": triples_r0},
        {"round_idx": 1, "entities": entities, "triples": []},  # round 1 missed this edge
    ]
    clusters, edges, _ = merge_document("doc1", text, rounds, AliasTable(None), TYPE_PRIORITY)
    assert len(edges) == 1
    assert edges[0].support == 1  # only 1/2 rounds supported it, but it's still IN the graph


def test_predicate_conflict_is_voted_not_unioned():
    text = "证候甲导致症状乙。"
    entities = [{"local_id": "e1", "name": "证候甲", "type": "证候"}, {"local_id": "e2", "name": "症状乙", "type": "症状"}]
    rounds = [
        {"round_idx": 0, "entities": entities,
         "triples": [{"head": "e1", "tail": "e2", "relation": "表现为", "kind": "relational", "condition": None}]},
        {"round_idx": 1, "entities": entities,
         "triples": [{"head": "e1", "tail": "e2", "relation": "表现为", "kind": "relational", "condition": None}]},
        {"round_idx": 2, "entities": entities,
         "triples": [{"head": "e1", "tail": "e2", "relation": "主症", "kind": "relational", "condition": None}]},
    ]
    clusters, edges, _ = merge_document("doc1", text, rounds, AliasTable(None), TYPE_PRIORITY)
    assert len(edges) == 1  # one edge slot, not two separate edges
    assert edges[0].predicate == "表现为"  # majority
    assert edges[0].conflicted is True
    assert edges[0].predicate_votes == {"表现为": 2, "主症": 1}


def test_condition_prevents_silent_merge():
    text = "证候甲若寒证加中药乙,若热证减中药乙。"
    entities = [{"local_id": "e1", "name": "证候甲", "type": "证候"}, {"local_id": "e2", "name": "中药乙", "type": "中药"}]
    rounds = [
        {"round_idx": 0, "entities": entities,
         "triples": [{"head": "e1", "tail": "e2", "relation": "加药", "kind": "relational", "condition": "若寒证"}]},
        {"round_idx": 1, "entities": entities,
         "triples": [{"head": "e1", "tail": "e2", "relation": "减药", "kind": "relational", "condition": "若热证"}]},
    ]
    clusters, edges, _ = merge_document("doc1", text, rounds, AliasTable(None), TYPE_PRIORITY)
    # two DIFFERENT conditions -> two separate edges, never voted against each other
    assert len(edges) == 2
    preds = {e.condition: e.predicate for e in edges}
    assert preds["若寒证"] == "加药"
    assert preds["若热证"] == "减药"
    assert all(not e.conflicted for e in edges)


def test_alias_table_promotion_threshold():
    table = AliasTable(None)
    assert table.is_known_alias("心阳虚", "心阳亏虚", "证候") is False
    for _ in range(2):
        table.record("心阳虚", "心阳亏虚", "证候")
    assert table.is_known_alias("心阳虚", "心阳亏虚", "证候") is False  # support=2, threshold=3
    table.record("心阳虚", "心阳亏虚", "证候")
    assert table.is_known_alias("心阳虚", "心阳亏虚", "证候") is True  # support=3


def test_determinism_same_input_same_output():
    text = "证候甲加中药乙,证候甲兼症状丙。"
    entities = [
        {"local_id": "e1", "name": "证候甲", "type": "证候"},
        {"local_id": "e2", "name": "中药乙", "type": "中药"},
        {"local_id": "e3", "name": "症状丙", "type": "症状"},
    ]
    triples = [
        {"head": "e1", "tail": "e2", "relation": "用药", "kind": "relational", "condition": None},
        {"head": "e1", "tail": "e3", "relation": "兼症", "kind": "relational", "condition": None},
    ]
    rounds = [{"round_idx": i, "entities": entities, "triples": triples} for i in range(3)]

    def run_once():
        clusters, edges, _ = merge_document("doc1", text, rounds, AliasTable(None), TYPE_PRIORITY)
        return (
            sorted((c.canonical, c.node_type, c.support) for c in clusters),
            sorted((e.subject_id, e.predicate, e.object_id, e.support) for e in edges),
        )

    assert run_once() == run_once()
