// DaemonSetup — the full-screen surface behind the 🖥 icon (V2-575): THE configuration of the local daemon.
//
// It is a SETTINGS screen with an install wizard in front of it, and the two are genuinely different screens:
//
//   SETTINGS     the daemon answers. Five cards, in this order: status (installed, running, version, linked to
//                this computer or to the cloud agent) · folders (with the default one) · browser (Chrome found, or
//                Chromium downloading with its progress) · pairing with the cloud agent · the tunnel (V2-836).
//                Each card reads `/api/daemon/status` and has an "unknown" face for every field it reads.
//   NOT THERE    here is how to start it on this computer. The screen then waits: `services/daemon.js` polls, and
//                the moment the daemon answers this becomes the settings screen on its own — the wizard ENDS there,
//                on the folders card, rather than closing (2026-11-09: it used to vanish on connect; a settings
//                screen that closes itself is not a settings screen).
//   FROM CLOUD   the daemon runs on the user's own computer. The download is offered; with the relay the pairing
//                card links that computer to this cloud agent, and without it the screen says so plainly.
//
// WHY A FULL SCREEN AND NOT A MODAL, copying `LanguageOnboarding.js` rather than `WizardModal.js`: this asks
// somebody to grant access to their documents. A dialog that vanishes when you click slightly off it is the
// wrong instrument for that — half-granted permissions are exactly the state the permission circuit exists to
// avoid. It closes on the ✕ and on Escape, both deliberate gestures.
//
// EVERY REFUSAL IS SHOWN WITH THE DAEMON'S OWN WORDS. `daemon/fs/roots.py` goes to real trouble to say "that
// is your entire home folder — choose the folders you actually want me to work with", and replacing that with
// "could not add folder" would throw away the only part the user can act on.
import { h, raw } from "../core/dom.js?v=2";
import { createMemo, createSignal, untrack } from "../core/reactive.js?v=2";
import * as store from "../core/store.js?v=2";
import * as api from "../services/api.js?v=2";
import * as daemon from "../services/daemon.js?v=3";
import { t } from "../core/i18n.js?v=1";
import { CLOSE_ICON, DESKTOP_ICON } from "../lib/icons.js?v=2";
import { BrowserCard, StatusCard, TunnelCard } from "./daemon/cards.js?v=2";
import { FoldersCard } from "./daemon/folders.js?v=1";
import { PairingCard } from "./daemon/pairing.js?v=1";

// The poll starts with the surface, which is mounted for the whole life of the page (system-surfaces.js) —
// the icon has to be coloured correctly whether or not anybody ever opens this screen.
daemon.start();

const PLATFORM_LABEL = { macos: "macOS", windows: "Windows" };

// How a SELF-HOSTER starts it. Not a download: they already have the daemon — it is a Python package in this
// repository, it has no dependencies at all, and the launcher starts it beside the engine on both platforms.
// These are the repo's own verbs, so they live here rather than in a translation bundle: `./zaelar restart` is
// not a phrase, it is a command, and translating it would break it.
const SOURCE_COMMANDS = {
  macos: "./zaelar restart",
  windows: ".\\zaelar.ps1 restart",
};

export function DaemonSetup() {
  const [problem, setProblem] = createSignal("");
  const [busy, setBusy] = createSignal("");
  const [chosen, setChosen] = createSignal("");      // which platform's instructions are showing
  const [copied, setCopied] = createSignal(false);
  const [connecting, setConnecting] = createSignal(false);
  let pathEl;

  // `navigator.clipboard` needs a secure context, and a local install is served over plain http
  // — so outside localhost the modern API simply is not there. The old `execCommand` path is
  // the fallback, and the button says what happened either way: a copy button that silently does nothing is
  // worse than no button, because the user walks away believing they have the command.
  const copy = async (text) => {
    if (!text) return;
    let ok = false;
    try {
      if (navigator.clipboard && window.isSecureContext) { await navigator.clipboard.writeText(text); ok = true; }
    } catch (_) { ok = false; }
    if (!ok) {
      try {
        const ta = document.createElement("textarea");
        ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
        document.body.appendChild(ta); ta.select();
        ok = document.execCommand("copy");
        document.body.removeChild(ta);
      } catch (_) { ok = false; }
    }
    if (ok) { setCopied(true); setTimeout(() => setCopied(false), 1800); }
    api.uiEvent("daemon:copy_command", { ok });
  };

  const close = () => { store.setDaemonSetupOpen(false); setProblem(""); };

  // Escape closes. Registered once on the window rather than on the overlay, because the overlay does not
  // hold focus when the user has been typing into the path field.
  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && store.daemonSetupOpen()) close();
  });

  const said = (code) => {
    const key = "daemon.err." + (code || "");
    return code && t(key) !== key ? t(key) : (code || "");
  };

  const act = async (fn, path) => {
    if (!path) return;
    setBusy(path); setProblem("");
    const r = await fn(path);
    setBusy("");
    // The engine answers with a stable CODE (`not_installed`, `not_running`…) when it never reached the daemon;
    // a code with a sentence under `daemon.err.<code>` is shown as that sentence. The daemon's own refusal
    // text has no such key and is passed through unchanged (see server/daemon_api.py::_permissions).
    if (!r.ok) setProblem(said(r.message) || t("daemon.err.generic"));
    else if (pathEl) pathEl.value = "";
  };

  // «Conectar»: the engine starts the daemon it carries — no terminal. The manual way stays under the details.
  const doConnect = async () => {
    setConnecting(true); setProblem("");
    const r = await daemon.connect();
    setConnecting(false);
    api.uiEvent("daemon:connect", { ok: !!r.ok });
    if (!r.ok) setProblem(t("daemon.err.start_failed"));
  };

  // The system's own folder dialog, opened on this desktop by the daemon; a cancel says nothing.
  const doPick = async () => {
    setBusy("pick"); setProblem("");
    const r = await daemon.pick(t("daemon.pick.prompt"));
    setBusy("");
    if (!r.ok) setProblem(said(r.message) || t("daemon.err.generic"));
  };

  const platform = () => chosen() || (daemon.status() || {}).platform || "macos";

  // ── the download block, shared by the "not there" and "from cloud" screens ──────────────────────────────
  const downloads = () => {
    const all = daemon.platforms();
    const names = Object.keys(all);
    if (!names.length) return h("p", { class: "dsx-note" }, () => t("daemon.download.unavailable"));
    const current = () => all[platform()] || {};
    return h("div", { class: "dsx-dl" },
      // Which machine, not which file. The tabs pick the platform; the command below is the whole install.
      h("div", { class: "dsx-dl-row" }, ...names.map((name) =>
        h("button", {
          class: () => "dsx-dl-btn" + (platform() === name ? " on" : ""),
          onClick: () => { setChosen(name); api.uiEvent("daemon:platform", { platform: name }); },
        }, PLATFORM_LABEL[name] || name))),
      h("p", { class: "dsx-note" }, () => t("daemon.cmd.lead")),
      h("div", { class: "dsx-cmd-row" },
        h("code", { class: "dsx-cmd" }, () => current().command || ""),
        h("button", { class: "dsx-copy",
          onClick: () => copy(current().command || ""),
        }, () => copied() ? t("daemon.cmd.copied") : t("daemon.cmd.copy"))),
      h("p", { class: "dsx-note" }, () => t("daemon.cmd.why")),
      h("p", { class: "dsx-note" }, () => t("daemon.note.noadmin")),
      // The direct file stays reachable for somebody who would rather look at it first — and it is the path
      // that COSTS a security dialog, because a browser is what marks a download as quarantined. Said here,
      // quietly, instead of being the button everybody presses by default.
      h("details", { class: "dsx-more" },
        h("summary", {}, () => t("daemon.manual.summary")),
        h("p", { class: "dsx-note" }, () => t("daemon.manual.body")),
        h("p", { class: "dsx-note" },
          h("a", { class: "dsx-link", href: () => current().artifact || "#", download: "" },
            () => t("daemon.manual.artifact")), " · ",
          h("a", { class: "dsx-link", href: () => current().installer || "#", download: "" },
            () => t("daemon.manual.installer")), " · ",
          h("a", { class: "dsx-link", href: () => current().checksums || "#" },
            () => t("daemon.note.checksums_link"))),
        h("p", { class: "dsx-note" }, () => t("daemon.manual.arch"))),
    );
  };

  // ── the cards share the screen's plumbing (the busy marker, the refusal line, the copy button) ─────────────────
  const ctx = {
    busy, act, doPick, copy, copied, said, setProblem,
    bindPath: (el) => (pathEl = el),
    typedPath: () => (pathEl && pathEl.value || "").trim(),
  };
  // Built ONCE: each card binds what it reads, so a status change repaints a line, never a whole card — a card
  // rebuilt every 2 s while a browser downloads would wipe the typed path and close any open fold.
  const cards = {
    status: StatusCard(), folders: FoldersCard(ctx), browser: BrowserCard(),
    pair: PairingCard(ctx), tunnel: TunnelCard(),
  };

  // What SHAPE the screen has. A memo, so the body is rebuilt when the shape changes (the daemon starts answering,
  // say) and not on every poll that changes a percentage.
  const mode = createMemo(() => !daemon.status() ? "loading"
    : daemon.isRemote() ? "remote" : daemon.isConnected() ? "settings" : "absent");
  const relayUp = createMemo(() => daemon.relayConnected());
  const hasRelay = createMemo(() => !!daemon.relay());

  // ── the three screens ───────────────────────────────────────────────────────────────────────────────────
  // Built UNTRACKED: everything the screen reads synchronously while it is built would otherwise subscribe it to
  // the status, and the whole screen would be rebuilt on every poll. The bindings inside keep their own effects.
  const screen = () => {
    const s = daemon.status();
    if (!s) return h("p", { class: "dsx-note" }, () => t("daemon.loading"));
    if (s.state === "remote") {
      const getIt = () => h("div", { class: "dsx-card dsx-get", "data-card": "get" },
        h("p", { class: "dsx-lead" }, () => t("daemon.remote.lead")),
        // Said out loud rather than implied, ONLY on an engine without the relay (no `relay` in its status):
        // there, wiring the daemon to the cloud agent does not exist, and a download screen implying it does is
        // how a product earns "it doesn't work".
        () => hasRelay() ? null : h("p", { class: "dsx-warn" }, () => t("daemon.remote.limit")),
        downloads());
      return h("div", { class: "dsx-settings" },
        cards.status,
        // The download stays until this computer is linked: before that it is the next step, after it, noise.
        () => relayUp() ? null : untrack(getIt),
        cards.folders, cards.browser, cards.pair, cards.tunnel);
    }
    // ⚠️ A SELF-HOSTER IS NEVER OFFERED A DOWNLOAD. They cloned the repository; the daemon is already on their
    // disk as a Python package with no dependencies, and the launcher starts it. Handing them an installer for
    // a binary would be telling somebody who owns the source to go and fetch a copy of it — and it would put a
    // second, differently-versioned daemon on the machine, competing for the same port. The download exists
    // for exactly one audience: somebody whose Zaelar runs in the cloud, on a computer that is not theirs.
    if (!s.reachable) {
      return h("div", {},
        h("p", { class: "dsx-intro" }, () => t("daemon.intro")),
        h("p", { class: "dsx-lead" }, () => t("daemon.local.lead")),
        h("button", { class: "dsx-primary", disabled: () => connecting(), onClick: doConnect },
          () => connecting() ? t("daemon.connecting") : t("daemon.connect")),
        // The terminal way, for when the button cannot: folded, because nobody should need it.
        h("details", { class: "dsx-more" },
          h("summary", {}, () => t("daemon.details")),
          h("p", { class: "dsx-note" }, () => t("daemon.local.body")),
          h("div", { class: "dsx-dl-row" }, ...Object.keys(SOURCE_COMMANDS).map((name) =>
            h("button", {
              class: () => "dsx-dl-btn" + (platform() === name ? " on" : ""),
              onClick: () => { setChosen(name); api.uiEvent("daemon:platform", { platform: name }); },
            }, PLATFORM_LABEL[name] || name))),
          h("div", { class: "dsx-cmd-row" },
            h("code", { class: "dsx-cmd" }, () => SOURCE_COMMANDS[platform()] || SOURCE_COMMANDS.macos),
            h("button", { class: "dsx-copy",
              onClick: () => copy(SOURCE_COMMANDS[platform()] || SOURCE_COMMANDS.macos),
            }, () => copied() ? t("daemon.cmd.copied") : t("daemon.cmd.copy"))),
          h("p", { class: "dsx-note" }, () => t("daemon.local.hint"))));
    }
    // SETTINGS: the folders card comes right after the status, which is where the wizard lands on connect.
    return h("div", { class: "dsx-settings" },
      cards.status, cards.folders, cards.browser, cards.pair, cards.tunnel);
  };
  const body = () => { mode(); return untrack(screen); };   // the only subscription is the shape (see `mode`)

  return h("div", { class: () => "ovl dsx-ovl" + (store.daemonSetupOpen() ? " on" : "") },
    h("div", { class: "dsx-box" },
      h("div", { class: "dsx-head" },
        h("span", { class: "dsx-mark" }, raw(DESKTOP_ICON)),
        h("h2", { class: "dsx-title" }, () => t(mode() === "absent" ? "daemon.title" : "daemon.settings.title")),
        h("button", { class: "dsx-icon", title: () => t("daemon.close"), onClick: close }, raw(CLOSE_ICON))),
      // `body` and not `body()`: passed as a FUNCTION it is a reactive child, so the screen becomes the
      // settings one by itself the moment the daemon answers — which is the whole "install it and watch this
      // turn green" step. Called, it would render once and never change again.
      h("div", { class: "dsx-scroll" },
        body,
        () => problem() ? h("p", { class: "dsx-problem" }, problem()) : null,
        h("button", { class: "dsx-link dsx-recheck", onClick: () => daemon.check() }, () => t("daemon.refresh"))),
    ),
  );
}
