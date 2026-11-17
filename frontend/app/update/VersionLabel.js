// ============================================================================
// update/VersionLabel.js — the build number a person can read, ONE element for both shells (node 4.568).
//
// The desktop mounts it from `UpdateSurface.js` as `#hb-upd-ver`, bottom-right just above the bottom system bar,
// over the desk's background; the phone shell mounts it as the last line of its ☰ page, at 14px. Both read the SAME
// `watch.js` signals, so the number climbs live in a tab left open for days, with no second poll.
//
// Quiet on purpose: small muted type (`--hb-muted-2`, light grey on the dark themes and the muted ink on the light
// ones), no box, no control look. The tooltip carries `short` (build + commit) and the deployment; a click or a tap
// asks the engine again and toggles `short` inline, because a phone has no hover to show a tooltip.
import { h } from "../core/dom.js?v=2";
import { createSignal } from "../core/reactive.js?v=2";
import { t } from "../core/i18n.js?v=1";
import { build, info, check, startUpdateWatch } from "./watch.js?v=1";

function injectStyles() {
  if (document.getElementById("hb-ver-css")) return;
  const s = document.createElement("style");
  s.id = "hb-ver-css";
  s.textContent = `
  .hb-ver{font:500 11px/1.2 var(--sans,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif);
    letter-spacing:.02em;color:var(--hb-muted-2,#99A2AE);opacity:.72;cursor:default;user-select:none;
    -webkit-user-select:none;white-space:nowrap}
  .hb-ver:empty{display:none}
  .hb-ver:hover{opacity:1}
  /* Desktop: over the desk's background, under every card (the card stage is z-index 12), and clear of a chat
     wall docked on the right (--chatdock-r is 0 when nothing is docked). It lives in the 16px gap between the bar
     and the feedback launcher (.fw-wrap, bottom: wrail-h + 16px), so line-height 1 and 3px off the bar. */
  #hb-upd-ver{position:fixed;right:calc(var(--chatdock-r,0px) + 14px);bottom:calc(var(--wrail-h,58px) + 3px);
    z-index:11;line-height:1}
  /* Phone: the foot of the ☰ page, centred under the last row, at a size he can read without squinting (operator,
     2026-11-17: the 11px badge was too small on the phone). */
  .zm-ver{display:block;text-align:center;padding:18px 16px 22px;font-size:14px;opacity:.9}
  `;
  document.head.appendChild(s);
}

export function VersionLabel({ id = null, cls = "" } = {}) {
  injectStyles();
  startUpdateWatch();
  const [detail, setDetail] = createSignal(false);
  return h("span", {
    id,
    class: ("hb-ver " + cls).trim(),
    title: () => {
      const s = info() || {};
      return t("update.version_title", { short: s.short || "?", deploy: s.deploy || "?" });
    },
    onClick: () => { setDetail(!detail()); check(); },
  }, () => {
    const n = build();
    const s = info() || {};
    const base = n > 0 ? "v" + n : (s.version ? "v" + s.version : "");
    return base && detail() && s.short ? base + " · " + s.short : base;
  });
}
