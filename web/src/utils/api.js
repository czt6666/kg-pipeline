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
  const data = await r.json();
  // Long-running endpoints (agent chat) send 200 headers before the work finishes, so
  // a failure arrives as a 200 body with only an `error` field.
  if (data && typeof data === "object" && data.error && Object.keys(data).every(k => k === "error" || k === "status")) {
    throw new Error(data.error);
  }
  return data;
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
