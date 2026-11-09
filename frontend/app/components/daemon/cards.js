// The STATUS, BROWSER and TUNNEL cards of the daemon's settings screen (V2-575).
//
// Each card reads `GET /api/daemon/status` through `services/daemon.js` and has an UNKNOWN face for every field it
// reads: an older daemon, an engine without the relay, or a status that has not arrived yet must draw "not known"
// — never throw, and never a confident wrong answer such as "no browser" when the daemon simply did not say.
import { h } from "../../core/dom.js?v=2";
import { createEffect, createSignal } from "../../core/reactive.js?v=2";
import * as daemon from "../../services/daemon.js?v=3";
import { t } from "../../core/i18n.js?v=1";

const say = (line) => t(line.key, line.vars || undefined);

// A yes/no/unknown field: `true`, `false`, or anything else → unknown.
const tri = (v) => (v === true ? t("daemon.status.yes") : v === false ? t("daemon.status.no") : t("daemon.status.unknown"));

function row(labelKey, value, cls) {
  return h("div", { class: "dsx-kv" + (cls ? " " + cls : "") },
    h("span", { class: "dsx-k" }, () => t(labelKey)),
    h("span", { class: "dsx-v" }, value));
}

// ── 1 · STATUS: is it installed, running, which version, and who it is linked to ──────────────────────────────
export function StatusCard() {
  const st = () => daemon.status() || {};
  return h("section", { class: "dsx-card dsx-status", "data-card": "status" },
    h("p", { class: "dsx-lead" }, () => t("daemon.status.what")),
    // From a cloud engine "installed" and "running" are about the CONTAINER, which has no daemon: what is known
    // there is the relay, so those two rows read from it instead of saying "no" about a computer it cannot see.
    row("daemon.status.installed", () => {
      const s = st(); const r = daemon.relay();
      // Paired proves it is installed; unpaired proves nothing about his computer, so it stays "not known".
      return s.state === "remote" ? tri(r && r.paired ? true : undefined) : tri(s.installed);
    }, "dsx-installed"),
    row("daemon.status.running", () => {
      const s = st(); const r = daemon.relay();
      return s.state === "remote" ? tri(r && r.connected ? true : r && r.paired ? false : undefined) : tri(s.running);
    }, "dsx-running"),
    row("daemon.status.version", () => {
      const s = st(); const r = daemon.relay();
      return (s.state === "remote" ? (r && r.version) : s.version) || t("daemon.status.unknown");
    }, "dsx-version"),
    row("daemon.status.link", () => say(daemon.linkLine()), "dsx-link-state"),
    () => st().outdated
      ? h("p", { class: "dsx-warn" }, () => t("daemon.ok.outdated"), " ",
          h("span", { class: "dsx-mono" }, () => `${st().version} → ${st().expected_version}`))
      : null,
  );
}

// ── 3 · BROWSER: which browser the sign-in window uses, and the window itself ─────────────────────────────────
export function BrowserCard() {
  const progress = () => {
    const b = daemon.browser();
    if (!b || b.state !== "downloading") return null;
    const pct = daemon.downloadPercent(b);
    return h("div", { class: "dsx-progress" + (pct == null ? " is-indeterminate" : ""), role: "progressbar",
                      "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": pct == null ? null : String(pct) },
      h("div", { class: "dsx-progress-bar", style: { width: pct == null ? "35%" : pct + "%" } }));
  };
  // "Only Google Chrome is supported for now", said when it explains something: the daemon found a browser it
  // will not use (`unsupported_browsers`), or reports the state `unsupported`.
  const onlyChrome = () => {
    const s = daemon.status() || {};
    const found = Array.isArray(s.unsupported_browsers) ? s.unsupported_browsers.filter(Boolean).map(String) : [];
    const b = daemon.browser();
    if (found.length) return h("p", { class: "dsx-note dsx-only-chrome" },
      () => t("daemon.browser.only_chrome_found", { names: found.join(", ") }));
    if (b && b.state === "unsupported") return h("p", { class: "dsx-note dsx-only-chrome" }, () => t("daemon.browser.only_chrome"));
    return null;
  };
  // The sign-in window opens by itself when a site asks him to sign in (V2-575 P2). This engine has no route to
  // open or close it on demand, so the two buttons are drawn DISABLED with the reason as their tooltip, rather
  // than omitted (the window exists) or live (a button that does nothing is worse than a disabled one).
  const windowTip = () => t("daemon.browser.window_tip");
  return h("section", { class: "dsx-card dsx-browser", "data-card": "browser" },
    h("h3", { class: "dsx-h3" }, () => t("daemon.browser.title")),
    h("p", { class: () => "dsx-browser-state" + (daemon.browser() ? "" : " dsx-unknown") }, () => say(daemon.browserLine())),
    progress,
    onlyChrome,
    // The MEASURED capability (P2): whether a window can open on this screen right now.
    () => daemon.isConnected()
      ? h("p", { class: "dsx-note dsx-cap" }, () => ((daemon.status() || {}).capabilities || []).includes("browser.auth")
          ? t("daemon.cap.browser_on") : t("daemon.cap.browser_off"))
      : null,
    h("div", { class: "dsx-dl-row dsx-window" },
      h("button", { class: "dsx-btn dsx-window-open", disabled: true, title: windowTip }, () => t("daemon.browser.open")),
      h("button", { class: "dsx-mini dsx-window-close", disabled: true, title: windowTip }, () => t("daemon.browser.close"))),
  );
}

// ── 5 · TUNNEL (V2-836): may the cloud agent browse through his computer? ────────────────────────────────────
// The switch lives in the DAEMON, on his computer, and only something on his computer flips it. So:
//   · an engine on the same computer (`local`) shows a live switch: OFF → the consent text is shown again with
//     «I understand, turn it on», and only that button switches it on (`consent: true`); ON → OFF at once;
//   · an engine away from his computer (`remote`) shows the state but cannot flip it, and says where it is flipped:
//     the Zaelar icon on his computer;
//   · a daemon that cannot carry it (older, or not connected) draws the switch disabled and says why.
// The asking step survives a repaint of the status (module signal), so a poll never eats his half-made decision.
const [tunnelAsking, setTunnelAsking] = createSignal(false);
const [tunnelBusy, setTunnelBusy] = createSignal(false);

function tunnelLine() {
  const e = daemon.egress();
  if (!e) return { key: "daemon.tunnel.unknown", vars: null };
  if (!e.capable) return { key: "daemon.tunnel.not_capable", vars: null };
  if (!e.enabled) return { key: "daemon.tunnel.off", vars: null };
  if (e.connected) return { key: "daemon.tunnel.carrying", vars: { n: Number(e.hosts_last_hour) || 0 } };
  return { key: "daemon.tunnel.waiting", vars: null };
}

export function TunnelCard() {
  const e = () => daemon.egress();
  const on = () => !!(e() && e().enabled);
  const live = () => !daemon.isRemote() && !!(e() && e().capable) && !tunnelBusy();
  const flip = async (ev) => {
    ev.preventDefault();                        // the box shows the DAEMON's state, never its own click
    if (!live()) return;
    if (!on()) { setTunnelAsking(true); return; }
    setTunnelBusy(true);
    try { await daemon.setEgress(false); } finally { setTunnelBusy(false); setTunnelAsking(false); }
  };
  const confirm = async () => {
    setTunnelBusy(true);
    try { await daemon.setEgress(true); } finally { setTunnelBusy(false); setTunnelAsking(false); }
  };
  return h("section", { class: "dsx-card dsx-tunnel", "data-card": "tunnel" },
    h("h3", { class: "dsx-h3" }, () => t("daemon.tunnel.title")),
    h("p", { class: "dsx-note dsx-consent" }, () => t("daemon.tunnel.consent")),
    h("label", { class: () => "dsx-toggle" + (live() ? "" : " is-disabled") },
      h("input", { type: "checkbox", class: "dsx-switch", role: "switch", disabled: () => !live(),
                   "aria-checked": () => (on() ? "true" : "false"), onClick: flip,
                   ref: (el) => createEffect(() => { el.checked = on(); }) }),
      h("span", {}, () => t("daemon.tunnel.switch"))),
    () => (tunnelAsking() && live() && !on())
      ? h("div", { class: "dsx-tunnel-ask" },
          h("button", { class: "dsx-primary dsx-tunnel-confirm", disabled: tunnelBusy, onClick: confirm },
            () => t("daemon.tunnel.confirm")),
          " ",
          h("button", { class: "dsx-btn dsx-tunnel-cancel", onClick: () => setTunnelAsking(false) },
            () => t("daemon.tunnel.cancel")))
      : null,
    h("p", { class: () => "dsx-note dsx-tunnel-state" + (e() ? "" : " dsx-unknown") }, () => say(tunnelLine())),
    () => daemon.isRemote() && e() && e().capable
      ? h("p", { class: "dsx-note dsx-tunnel-where" }, () => t("daemon.tunnel.on_computer"))
      : null,
  );
}
