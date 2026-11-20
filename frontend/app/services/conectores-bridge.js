// conectores-bridge.js — the ONE file that wires the Connectors column (`frontend/side/conectores/`) to the app: its
// two reads (the registry's descriptors with their state, Google grouped as one row, and the catalog's wishlist), «I
// want it» as a countable feedback line, the words, and when it is shown. Both shells mount it here — the desktop's
// side panel and the phone's ☰ → Connectors page — so they can never disagree about what is connected.
import { mount } from "../../side/conectores/conectores.js";
import * as api from "./api.js?v=2";
import * as feedbackApi from "./feedback-api.js?v=1";
import { t } from "../core/i18n.js?v=1";
import { createEffect, untrack } from "../core/reactive.js?v=2";
import { groupGoogle } from "../components/ConnectorWizard.js?v=7";

/** `visible()` — a reactive «is the column on screen»: showing it re-reads. `manage(id)` — the credential surface. */
export function mountConectores(host, { visible, manage }) {
  const col = mount(host, { t, manage, watch: (fn) => createEffect(fn),
    async load() {
      const [live, wish] = await Promise.all([api.getConnectors(), api.getConnectorCatalog()]);
      return { live: groupGoogle((live && live.connectors) || []), wish: (wish && wish.catalog) || [] };
    },
    // A request the receiving side can COUNT: the manifest id as a fixed, machine-written prefix, never his words.
    want: (m) => feedbackApi.sendFeedback({ message: `[conector:${m.id}] Lo quiero: ${m.label}` }) });
  createEffect(() => { const v = !!visible(); untrack(() => (v ? col.show() : col.hide())); });
  return col;
}
