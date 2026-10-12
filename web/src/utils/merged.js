// A dataset can hold several independently-merged graphs (data/graph/{dataset}/merged*/,
// see services/kg_server.py graph listing) -- e.g. TCM has one per source book. `merge`
// defaults to "merged" for the single-graph case (docred/genwiki), so plain dataset name
// is still enough there; only the "merged_X" case needs a friendlier label than "TCM" x3.
const BOOK_LABELS = {
  neike: "中医内科学",
  jichu: "中医基础理论",
  zhenduan: "中医诊断学",
};

export function mergeKey(m) {
  return `${m.dataset}::${m.merge || "merged"}`;
}

export function mergeLabel(m) {
  const merge = m.merge || "merged";
  if (merge === "merged") {
    // still disambiguate a lone non-default split name (e.g. a trial run) rather than
    // showing a bare dataset name that collides with other merges of the same dataset
    if (m.splits?.length === 1 && m.splits[0] !== m.dataset) return `${m.dataset} · ${m.splits[0]}`;
    return m.dataset;
  }
  const suffix = merge.replace(/^merged_/, "");
  return `${m.dataset} · ${BOOK_LABELS[suffix] || suffix}`;
}
