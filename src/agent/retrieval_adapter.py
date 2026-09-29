"""Retrieval adapter: turns a schema-validated RetrievalRequest into calls on the existing
hybrid retrieval module (retrieval.pipeline.hybrid_search) and normalises the output into
Evidence. This is the *only* place the agent touches retrieval -- the loop never imports
hybrid_search directly, so the whole retrieval backend is swappable (tests use
FakeRetrievalAdapter; a future vector/rerank backend just needs the same `.retrieve()`).

The agent's `path` doesn't drive graph traversal (graph_patterns.py already fixes typed,
directional chains per seed type); it *prioritises* which of the resolved entity's returned
facts surface first, so a "treatment" query and a "differential" query on the same entity
foreground different facts even though retrieval returns the same superset.
"""
from __future__ import annotations

from .actions import Evidence, EvidenceFact, RetrievalQuery, RetrievalRequest
from .schema_spec import SchemaSpec


class RetrievalAdapter:
    def __init__(self, dataset: str, merge: str, schema: SchemaSpec, top_k: int = 10):
        self.dataset = dataset
        self.merge = merge
        self.schema = schema
        self.top_k = top_k

    def validate(self, request: RetrievalRequest) -> list[str]:
        """Returns a list of human-readable errors (empty == valid). The loop shows these
        back to the request-building stage for one repair attempt before giving up."""
        errors = []
        if not request.queries:
            errors.append("检索请求没有任何 query")
        for i, q in enumerate(request.queries):
            if not q.term or not q.term.strip():
                errors.append(f"query[{i}] 缺少 term")
            if q.seed_type is not None and not self.schema.is_entity_type(q.seed_type):
                errors.append(f"query[{i}] seed_type='{q.seed_type}' 不是合法实体类型")
            seed = q.seed_type or self._infer_seed_type(q.path)
            ok, errs = self.schema.validate_path(seed or "疾病", q.path)
            if not ok:
                errors.extend(f"query[{i}] {e}" for e in errs)
        return errors

    def _infer_seed_type(self, path: list[str]) -> str | None:
        """When seed_type is omitted, pick a type from the first relation's domain so
        validate_path still has something concrete to check against."""
        if not path:
            return None
        spec = self.schema.relations.get(path[0])
        if spec and spec["domain"]:
            return spec["domain"][0]
        return None

    def retrieve(self, request: RetrievalRequest) -> list[Evidence]:
        # Imported lazily so tests / the schema layer don't pull in faiss + the embedding
        # client just to construct an adapter.
        from retrieval.pipeline import hybrid_search

        out = []
        for q in request.queries:
            result = hybrid_search(self.dataset, self.merge, q.term,
                                   top_k=request.top_k or self.top_k, expand=True)
            out.append(self._to_evidence(q, result))
        return out

    def _to_evidence(self, q: RetrievalQuery, result: dict) -> Evidence:
        resolved = result.get("resolved")
        candidates = [c.get("name", "") for c in result.get("candidates", [])]
        if not resolved:
            return Evidence(query=q.term, found=False, candidates=candidates[:5],
                            note="未找到匹配实体")
        seed = resolved.get("seed", {})
        note = ""
        if q.seed_type and seed.get("type") and seed["type"] != q.seed_type:
            # Not fatal -- the caller (judge stage) decides whether the mismatch matters --
            # but surfaced so it can, e.g., pick a different candidate or re-ask.
            note = f"命中实体类型为「{seed.get('type')}」，与预期「{q.seed_type}」不符"
        facts = self._rank_facts(resolved.get("facts", []), q.path)
        return Evidence(
            query=q.term,
            found=True,
            resolved_entity={"entity_id": seed.get("entity_id"), "name": seed.get("name"),
                             "type": seed.get("type")},
            candidates=[c for c in candidates if c != seed.get("name")][:5],
            facts=facts,
            # Always None now: pipeline.expand_entity no longer runs the LLM summary call
            # inline (see pipeline.py's async-summary docstring) -- the agent already
            # composes its reply from `facts` directly, so this just carries the field
            # through for schema/serialization compatibility rather than being dropped.
            summary=resolved.get("summary"),
            note=note,
        )

    def _rank_facts(self, raw_facts: list[dict], path: list[str]) -> list[EvidenceFact]:
        """Facts whose hop relations overlap the requested `path` float to the top; profile
        facts (the entity card, no hops) come next; everything else after. Order-stable
        within each bucket so output is deterministic."""
        want = set(path)
        primary, profile, other = [], [], []
        for f in raw_facts:
            rels = [h["relation"] for h in f.get("hops", [])]
            ef = EvidenceFact(sentence=f["sentence"], source=f.get("source", ""), relations=rels)
            if want and want & set(rels):
                primary.append(ef)
            elif f.get("source") == "profile":
                profile.append(ef)
            else:
                other.append(ef)
        return primary + profile + other


class FakeRetrievalAdapter(RetrievalAdapter):
    """Test double: returns pre-seeded Evidence keyed by query term, no network/graph.
    Reuses the real `validate()` so schema-validation behaviour is exercised in tests."""

    def __init__(self, schema: SchemaSpec, evidence_by_term: dict[str, Evidence]):
        super().__init__("TCM", "fake", schema)
        self._evidence = evidence_by_term
        self.requests: list[RetrievalRequest] = []

    def retrieve(self, request: RetrievalRequest) -> list[Evidence]:
        self.requests.append(request)
        out = []
        for q in request.queries:
            out.append(self._evidence.get(q.term, Evidence(query=q.term, found=False,
                                                            note="fake: no evidence seeded")))
        return out
