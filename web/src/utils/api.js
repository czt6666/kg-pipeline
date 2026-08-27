export async function getJSON(url) {
  const r = await fetch(url);
  return r.json();
}

export function hashRoute() {
  const h = window.location.hash;
  if (h.startsWith("#/graph")) return "graph";
  if (h.startsWith("#/debug")) return "debug";
  return "home";
}

export function go(route) { window.location.hash = "#/" + route; }
