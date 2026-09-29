export async function getJSON(url) {
  const r = await fetch(url);
  return r.json();
}

export async function postJSON(url, body) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({ error: `HTTP ${r.status}` }));
    throw new Error(err.error || `HTTP ${r.status}`);
  }
  return r.json();
}

const ROUTES = ["ocr", "preprocess", "debug", "align", "graph", "retrieval", "qa", "benchmark"];

export function hashRoute() {
  const h = window.location.hash;
  for (const r of ROUTES) {
    if (h.startsWith("#/" + r)) return r;
  }
  return "home";
}

export function go(route) { window.location.hash = "#/" + route; }
