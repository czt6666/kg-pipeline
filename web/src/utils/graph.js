export function buildAdjacency(edges) {
  const adj = new Map();
  const push = (k, e) => { if (!adj.has(k)) adj.set(k, []); adj.get(k).push(e); };
  for (const e of edges) { push(e.head, e); push(e.tail, e); }
  return adj;
}

export function egoSubgraph(adjacency, focusId, hops, budget) {
  const visited = new Set([focusId]);
  const edgeMap = new Map();
  let frontier = [focusId];
  for (let h = 0; h < hops && frontier.length; h++) {
    const next = [];
    for (const u of frontier) {
      for (const e of (adjacency.get(u) || [])) {
        edgeMap.set(e.head + "|" + e.relation + "|" + e.tail, e);
        const other = e.head === u ? e.tail : e.head;
        if (!visited.has(other) && visited.size < budget) { visited.add(other); next.push(other); }
      }
    }
    frontier = next;
  }
  const edges = [...edgeMap.values()].filter(e => visited.has(e.head) && visited.has(e.tail));
  return { nodeIds: visited, edges };
}
