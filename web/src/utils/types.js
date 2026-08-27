const TYPE_COLORS = { PER:"#4f46e5", ORG:"#059669", LOC:"#d97706", NUM:"#0891b2", TIME:"#7c3aed", MISC:"#64748b" };
const TYPE_LABELS = { PER:"人物", ORG:"组织", LOC:"地点", NUM:"数字", TIME:"时间", MISC:"其他" };
// Not every dataset's entity types are in TYPE_COLORS above (e.g. TCM uses 症状/中药/
// 证候/... instead of PER/ORG/LOC), so those all fell back to the same grey MISC color.
// Assign a real, stable color to whatever type strings actually show up.
const TYPE_PALETTE = ["#4f46e5","#059669","#d97706","#0891b2","#7c3aed","#dc2626","#db2777","#65a30d","#0d9488","#ea580c","#a16207","#0369a1","#be185d","#4d7c0f"];
const typeColorCache = new Map(Object.entries(TYPE_COLORS));

export function colorForType(t) {
  if (!t) return TYPE_COLORS.MISC;
  if (!typeColorCache.has(t)) typeColorCache.set(t, TYPE_PALETTE[typeColorCache.size % TYPE_PALETTE.length]);
  return typeColorCache.get(t);
}

export function labelForType(t) { return t ? (TYPE_LABELS[t] || t) : ""; }
