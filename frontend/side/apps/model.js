// side/apps/model.js — the catalogue's rows by who built them (no DOM, no imports). A FORKED shipped widget is in BOTH
// scopes on purpose: pale under System (the native one no longer runs) and under Custom as the one he opens.
export const SCOPES = [{ id: "system", label: "chat.appsSystem", empty: "chat.appsSystemEmpty" },
                       { id: "custom", label: "chat.appsCustom", empty: "chat.appsCustomEmpty" }];
export const scopeOf = (id) => SCOPES.find((s) => s.id === id) || SCOPES[0];
export const widgetsOf = (reg) => (Array.isArray(reg) ? reg : []).filter((w) => w && w.surface === "user");
const byName = (a, b) => String(a.name || a.id).localeCompare(String(b.name || b.id));
export const tilesOf = (rows, scope) => { const mine = scopeOf(scope).id === "custom";
  return rows.filter((w) => (mine ? w.origin !== "builtin" : w.origin === "builtin" || w.forked)).sort(byName)
    .map((w) => ({ w, customized: !mine && !!w.forked, forkOf: mine && !!w.forked })); };
