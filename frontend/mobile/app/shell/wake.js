// wake.js — the wake word, the desktop orb's 🤖 (Orb.js): ON = `smart` (say the name once, keep talking), OFF = `always`.
// Written through the same /api/settings seam; the SSE `orb:attention` event keeps both shells in step. A row of the
// Settings page since V2-876 D-C gave its dock slot to Apps.
import * as store from "../../../app/core/store.js?v=2";
import * as api from "../../../app/services/api.js?v=2";

export const on = () => store.attentionMode() === "smart" || store.attentionMode() === "wakeword";
export function toggle() {
  const prev = store.attentionMode();
  const next = on() ? "always" : "smart";
  store.setAttentionMode(next);
  api.saveSettings({ attention_mode: next }).catch(() => store.setAttentionMode(prev));
  api.uiEvent("mobile:attention", { state: next });
}
