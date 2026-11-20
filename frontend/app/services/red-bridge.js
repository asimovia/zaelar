// red-bridge.js — the ONE file that wires the Network column (`frontend/side/red/`, V2-866) to the app, and the keeper
// of the read it draws: GET /api/a2a/network. A 404 is A2A OFF (its routes are absent): `on()` is false, the shell
// draws no tab and the column no body. The chat's consent cards (components/A2AView.js) answer through here too.
import { mount, cardView as card } from "../../side/red/red.js";
import { isOn } from "../../side/red/model.js";
import * as store from "../core/store.js?v=2";
import { t } from "../core/i18n.js?v=1";
import { createEffect, createSignal, untrack } from "../core/reactive.js?v=2";

const [net, setNet] = createSignal(null);       // the last answer; null = off or unknown
export const on = () => isOn(net());
const post = (url, body) => fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
/** Re-read the network. A2A off with the Network tab saved as open → back to the chat. */
export async function refresh() {
  try { const r = await fetch("/api/a2a/network"); setNet(r.ok ? await r.json() : null); } catch (_) { setNet(null); }
  if (!on() && store.chatTab() === "red") store.setChatTab("chat");
}
/** His Yes / No on a consent card: one POST, the engine runs the accept / decline / connect / never. */
const answer = (id, yes) => post("/api/a2a/cards/" + encodeURIComponent(id), { yes }).then((r) => r.ok, () => false).finally(refresh);
// Stop sharing = the contacts widget's `a2a_revoke`.
const revoke = (contactId, item) => post("/widgets/contactos/action", { action: "a2a_revoke", payload: { contactId, item } }).catch(() => {}).finally(refresh);
const bridge = { t, network: net, watch: (fn) => createEffect(fn), refresh, answer, revoke };
/** A consent card for the chat's own rows (components/A2AView.js): the column's card, answered the same way. */
export const cardView = (c, cls = "cw-msg") => card(c, cls, bridge);
/** `visible()` — a reactive «is the column on screen»: showing it re-reads. Mounting asks once whether A2A is on. */
export function mountRed(host, { visible }) {
  const col = mount(host, bridge);
  createEffect(() => { const v = !!visible(); untrack(() => (v ? col.show() : col.hide())); });
  refresh();
  return col;
}
