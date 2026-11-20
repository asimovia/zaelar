// side/conectores/model.js — the Connectors column's order and grouping. No DOM, no imports. Families in the order he
// expects them; anything not listed sorts after, alphabetically. A test walks the live descriptors() against this
// array (a family missing here files his calendar under Infraestructura, silently).
export const CONN_FAMILY_ORDER = ["google", "mensajeria", "musica", "fotos", "archivos", "video", "agenda", "contactos", "infra"];
const rank = (f) => { const i = CONN_FAMILY_ORDER.indexOf(f); return i < 0 ? 99 : i; };
/** Rows → [[family, rows]], families in CONN_FAMILY_ORDER, unknown ones after, alphabetically; a row with no family is infra. */
export function byFamily(rows) {
  const fams = new Map();
  for (const r of rows || []) { const f = r.family || "infra"; if (!fams.has(f)) fams.set(f, []); fams.get(f).push(r); }
  return [...fams.keys()].sort((a, b) => rank(a) - rank(b) || a.localeCompare(b)).map((f) => [f, fams.get(f)]);
}
/** A live row's state: Google is one row with a consent per service, on when any service is. */
export function liveState(c) {
  const n = c.services ? c.services.filter((x) => x.connected).length : 0;
  return c.services ? { on: n > 0, n, total: c.services.length } : { on: !!c.connected };
}
