// The PAIRING card of the daemon's settings screen (V2-575 P3): link the daemon on his computer to a cloud agent.
//
// Three faces, all decided by what the engine answers rather than by guessing what kind of engine this is:
//   · over LOOPBACK (an engine on the same computer) there is nothing to pair — the engine reads the daemon's own
//     token from the same disk — so the card says "already linked" and offers no code;
//   · on a HOSTED engine with the relay, "Get a code" asks `POST /api/daemon/pair` for a one-time code and shows
//     it big, with its countdown and where to type it (the menu-bar icon, or the command line in a fold);
//   · on an engine WITHOUT the relay (`relay_not_available`, or a status with no `relay` field) the card is not
//     drawn at all: a pairing step that can never complete is worse than none.
//
// The answer lives in `store.daemonPair` and not here: the card is redrawn with the status, and a code the person
// is in the middle of typing into another window must survive that.
import { h } from "../../core/dom.js?v=2";
import { createEffect, createMemo, createSignal } from "../../core/reactive.js?v=2";
import * as store from "../../core/store.js?v=2";
import * as api from "../../services/api.js?v=2";
import * as daemon from "../../services/daemon.js?v=3";
import { t } from "../../core/i18n.js?v=1";

// mm:ss, or h:mm:ss for a code that lives longer than an hour.
function clock(ms) {
  const s = Math.max(0, Math.ceil(ms / 1000));
  const hh = Math.floor(s / 3600), mm = Math.floor((s % 3600) / 60), ss = s % 60;
  const p = (n) => String(n).padStart(2, "0");
  return hh ? `${hh}:${p(mm)}:${p(ss)}` : `${mm}:${p(ss)}`;
}

export function PairingCard(ctx) {
  const [now, setNow] = createSignal(Date.now());
  const [asking, setAsking] = createSignal(false);
  let tick = null;

  // The countdown ticks only while there is a live code AND the screen is open; it stops at zero by itself.
  createEffect(() => {
    const p = store.daemonPair();
    const live = !!(p && p.code && p.expiresAt && store.daemonSetupOpen());
    if (tick) { clearInterval(tick); tick = null; }
    if (!live) return;
    setNow(Date.now());
    tick = setInterval(() => {
      setNow(Date.now());
      if (Date.now() >= p.expiresAt && tick) { clearInterval(tick); tick = null; }
    }, 1000);
  });

  const getCode = async () => {
    setAsking(true); ctx.setProblem("");
    const r = await daemon.pair();
    setAsking(false);
    api.uiEvent("daemon:pair", { ok: !!r.ok, loopback: !!r.loopback, unavailable: !!r.unavailable });
    if (r.unavailable) { store.setDaemonPair({ unavailable: true }); return; }
    if (r.loopback) { store.setDaemonPair({ loopback: true }); return; }
    if (!r.ok) { ctx.setProblem(ctx.said(r.error) || t("daemon.pair.failed")); return; }
    store.setDaemonPair({ code: r.code, expiresAt: r.expiresAt });
  };

  // MEMOS, not plain functions: the status changes every 2 s while a browser downloads, and a card rebuilt on each
  // of those would close the fold the person just opened. A memo only moves when its answer does.
  const hidden = createMemo(() => {
    const p = store.daemonPair();
    if (p && p.unavailable) return true;
    return daemon.isRemote() && !daemon.relay();
  });
  const loopback = createMemo(() => !daemon.isRemote() || !!(store.daemonPair() || {}).loopback);
  const left = () => { const p = store.daemonPair(); return p && p.code && p.expiresAt ? p.expiresAt - now() : null; };
  const expired = createMemo(() => { const l = left(); return l != null && l <= 0; });

  // Rebuilt only when the code itself changes; the countdown is a text binding inside it, ticking on its own.
  const codeBlock = () => {
    const p = store.daemonPair();
    if (!p || !p.code) return null;
    const cli = `zaelar-daemon pair ${p.code}`;
    return h("div", { class: () => "dsx-pair" + (expired() ? " is-expired" : "") },
      h("div", { class: "dsx-pair-code", "aria-label": () => t("daemon.pair.code_label") }, p.code),
      h("p", { class: "dsx-note dsx-pair-left" }, () => {
        const l = left();
        return l == null ? "" : l <= 0 ? t("daemon.pair.expired") : t("daemon.pair.expires_in", { left: clock(l) });
      }),
      () => expired() ? null : h("p", { class: "dsx-note dsx-pair-how" }, () => t("daemon.pair.how")),
      () => expired() ? null : h("details", { class: "dsx-more" },
        h("summary", {}, () => t("daemon.pair.cli_summary")),
        h("div", { class: "dsx-cmd-row" },
          h("code", { class: "dsx-cmd dsx-pair-cli" }, cli),
          h("button", { class: "dsx-copy", onClick: () => ctx.copy(cli) },
            () => ctx.copied() ? t("daemon.cmd.copied") : t("daemon.cmd.copy")))));
  };

  return h("div", { class: "dsx-pair-slot" }, () => hidden() ? null :
    h("section", { class: "dsx-card dsx-pairing", "data-card": "pair" },
      h("h3", { class: "dsx-h3" }, () => t("daemon.pair.title")),
      () => loopback()
        ? h("p", { class: "dsx-note dsx-pair-linked" }, () => t("daemon.pair.loopback"))
        : h("div", {},
            h("p", { class: "dsx-note" }, () => daemon.relayConnected()
              ? t(daemon.linkLine().key, daemon.linkLine().vars || undefined) : t("daemon.pair.body")),
            h("button", { class: "dsx-primary dsx-pair-get", disabled: asking, onClick: getCode },
              () => asking() ? t("daemon.pair.asking")
                : (store.daemonPair() || {}).code ? t("daemon.pair.again") : t("daemon.pair.get")),
            codeBlock)));
}
