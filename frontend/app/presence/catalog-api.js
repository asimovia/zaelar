// catalog-api.js — every face the person can wear, as one list of entries (V2-928):
//   { id, cat, base, n, classic? , spec? }  — `base` names it (i18n `presence.face.<base>`), `n` its variation.
// Classics are fixed drawings (`c-<style>`); the rest are parametric specs; «mine» is his own customised face.
import { STYLES } from "./classics.js?v=1";
import { CATEGORIES, buildCatalog } from "./catalog.js?v=1";
import { DEFAULT_SPEC, merge } from "./creator.js?v=1";
import { t } from "../core/i18n.js?v=1";

export { CATEGORIES };
let _all = null;
function all() {
  if (_all) return _all;
  const classics = STYLES.map((s) => ({ id: "c-" + s.id, cat: "classic", base: s.id, n: 0, classic: s.id }));
  const gen = buildCatalog(14).map((e) => { const i = e.id.lastIndexOf("-"); return { id: e.id, cat: e.cat, base: e.id.slice(0, i), n: +e.id.slice(i + 1), spec: e.spec }; });
  return (_all = classics.concat(gen));
}

/** The entries of one category («mine» holds his customised face when there is one). */
export function facesOf(cat, custom) {
  if (cat === "mine") return custom ? [mineEntry(custom)] : [];
  return all().filter((e) => e.cat === cat);
}
export const mineEntry = (custom) => ({ id: "mine", cat: "mine", base: "mine", n: 0, spec: merge(DEFAULT_SPEC, custom) });

/** The entry an id names, or null (an id from an older catalogue falls back to the default upstream). */
export function faceById(id, custom) {
  if (id === "mine") return custom ? mineEntry(custom) : null;
  return all().find((e) => e.id === id) || null;
}

/** A spec to start customising from: the face's own, or — for a classic — the parametric twin of Porcelain. */
export function editableSpec(entry) {
  const src = entry && entry.spec ? entry.spec : (faceById("porcelana-0") || {}).spec || DEFAULT_SPEC;
  return JSON.parse(JSON.stringify(src));
}

export const faceName = (e) => !e ? "" : e.id === "mine" ? t("presence.mine_name") : t("presence.face." + e.base) + (e.n ? " " + (e.n + 1) : "");
export const catName = (id) => t("presence.cat." + id);
