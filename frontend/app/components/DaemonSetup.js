// DaemonSetup — the full-screen surface behind the 🖥 icon (V2-575, V2-869): THE configuration of the local daemon.
// Six TABS in the subheader, one topic each, the open one remembered for the session:
//   STATUS (default) one line of what it is, then installed · running · version · linked to — or, for a computer
//          that is not linked, ONE line and the way to Install / Link instead of four "not known" rows.
//   INSTALL from the cloud the one-line command (the manual file folded); on a self-hoster's engine «Connect» and
//          the launcher's commands, never a download; once installed, "installed, version X" and the update hint.
//   FOLDERS · BROWSER · LINK · TUNNEL one card each (`components/daemon/`), each with an "unknown" face.
// The install wizard ENDS on the folders tab when the daemon answers, rather than closing (2026-11-09).
//
// A FULL SCREEN AND NOT A MODAL: it grants access to his documents, and a dialog that vanishes on a stray click
// leaves permissions half-granted. It closes on the ✕ and on Escape, both deliberate gestures.
// EVERY REFUSAL IS SHOWN WITH THE DAEMON'S OWN WORDS: `daemon/fs/roots.py` says "that is your entire home folder —
// choose the folders you actually want", and "could not add folder" would throw away the part he can act on.
import { h, raw } from "../core/dom.js?v=2";
import { createEffect, createMemo, createSignal, untrack } from "../core/reactive.js?v=2";
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
const TABS = ["status", "install", "folders", "browser", "link", "tunnel"];

// The open tab: a module signal survives a close and reopen, sessionStorage a reload (which may throw: then signal only).
const KEY = "zaelar.daemon.tab";
const [tab, setTabRaw] = createSignal((() => { try { const v = sessionStorage.getItem(KEY); return TABS.includes(v) ? v : "status"; } catch (_) { return "status"; } })());
const setTab = (id) => { setTabRaw(id); try { sessionStorage.setItem(KEY, id); } catch (_) { /* signal only */ } };

// How a SELF-HOSTER starts it. Not a download: they already have the daemon — it is a Python package in this
// repository, it has no dependencies at all, and the launcher starts it beside the engine on both platforms.
// These are the repo's own verbs, so they live here rather than in a translation bundle: `./zaelar restart` is
// not a phrase, it is a command, and translating it would break it.
const SOURCE_COMMANDS = { macos: "./zaelar restart", windows: ".\\zaelar.ps1 restart" };

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
  window.addEventListener("keydown", (e) => { if (e.key === "Escape" && store.daemonSetupOpen()) close(); });

  const said = (code) => { const key = "daemon.err." + (code || ""); return code && t(key) !== key ? t(key) : (code || ""); };

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

  // ── the download block, offered only from the cloud (see the install tab) ─────────────────────────────────
  const downloads = () => {
    const all = daemon.platforms();
    const names = Object.keys(all);
    if (!names.length) return h("p", { class: "dsx-note" }, () => t("daemon.download.unavailable"));
    const current = () => all[platform()] || {};
    return h("div", { class: "dsx-dl" },
      platformRow(names),
      h("p", { class: "dsx-note" }, () => t("daemon.cmd.lead")),
      h("div", { class: "dsx-cmd-row" },
        h("code", { class: "dsx-cmd" }, () => current().command || ""),
        copyBtn(() => current().command || "")),
      h("p", { class: "dsx-note" }, () => t("daemon.cmd.why")),
      // The direct file stays reachable, folded: it is the path that COSTS a security dialog, because a browser
      // is what marks a download as quarantined.
      h("details", { class: "dsx-more" },
        h("summary", {}, () => t("daemon.manual.summary")),
        h("p", { class: "dsx-note" }, () => t("daemon.manual.body")),
        h("p", { class: "dsx-note" },
          h("a", { class: "dsx-link", href: () => current().artifact || "#", download: "" },
            () => t("daemon.manual.artifact")), " · ",
          h("a", { class: "dsx-link", href: () => current().installer || "#", download: "" },
            () => t("daemon.manual.installer")), " · ",
          h("a", { class: "dsx-link", href: () => current().checksums || "#" },
            () => t("daemon.note.checksums_link")))),
    );
  };
  function platformRow(names) {
    return h("div", { class: "dsx-dl-row" }, ...names.map((name) =>
      h("button", {
        class: () => "dsx-dl-btn" + (platform() === name ? " on" : ""),
        onClick: () => { setChosen(name); api.uiEvent("daemon:platform", { platform: name }); },
      }, PLATFORM_LABEL[name] || name)));
  }
  function copyBtn(text) {
    return h("button", { class: "dsx-copy", onClick: () => copy(text()) },
      () => copied() ? t("daemon.cmd.copied") : t("daemon.cmd.copy"));
  }

  // ── the cards share the screen's plumbing (the busy marker, the refusal line, the copy button) ─────────────────
  const ctx = {
    busy, act, doPick, copy, copied, said, setProblem,
    bindPath: (el) => (pathEl = el),
    typedPath: () => (pathEl && pathEl.value || "").trim(),
  };

  // What SHAPE the install tab has: rebuilt when that changes (the daemon starts answering, say), never per poll.
  const shape = createMemo(() => { const s = daemon.status(); const r = daemon.relay();
    return !s ? "loading" : s.state === "remote" ? (r && r.paired ? "done" : "remote") : s.reachable ? "done" : "absent"; });
  const hasRelay = createMemo(() => !!daemon.relay());

  // Built UNTRACKED: what it reads while built would otherwise subscribe the tab to every poll.
  const install = () => {
    const s = daemon.status();
    if (!s) return h("p", { class: "dsx-note" }, () => t("daemon.loading"));
    if (shape() === "done") {
      const v = () => { const st = daemon.status() || {}; return (st.state === "remote" ? (daemon.relay() || {}).version : st.version) || ""; };
      return h("div", {},
        h("p", { class: "dsx-lead dsx-installed-line" }, () => v() ? t("daemon.install.done", { v: v() }) : t("daemon.install.done_bare")),
        () => (daemon.status() || {}).outdated
          ? h("p", { class: "dsx-warn" }, () => t("daemon.ok.outdated"), " ",
              h("span", { class: "dsx-mono" }, () => `${daemon.status().version} → ${daemon.status().expected_version}`))
          : null);
    }
    if (s.state === "remote") {
      return h("div", { class: "dsx-get" },
        // Said out loud ONLY on an engine without the relay: there, linking to the cloud agent does not exist.
        () => hasRelay() ? null : h("p", { class: "dsx-warn" }, () => t("daemon.remote.limit")),
        downloads());
    }
    // ⚠️ A SELF-HOSTER IS NEVER OFFERED A DOWNLOAD. They cloned the repository; the daemon is already on their
    // disk as a Python package with no dependencies, and the launcher starts it. An installer would put a second,
    // differently-versioned daemon on the machine, competing for the same port.
    if (!s.reachable) {
      return h("div", {},
        h("p", { class: "dsx-lead" }, () => t("daemon.local.lead")),
        h("button", { class: "dsx-primary", disabled: () => connecting(), onClick: doConnect },
          () => connecting() ? t("daemon.connecting") : t("daemon.connect")),
        // The terminal way, for when the button cannot: folded, because nobody should need it.
        h("details", { class: "dsx-more" },
          h("summary", {}, () => t("daemon.details")),
          h("p", { class: "dsx-note" }, () => t("daemon.local.body")),
          platformRow(Object.keys(SOURCE_COMMANDS)),
          h("div", { class: "dsx-cmd-row" },
            h("code", { class: "dsx-cmd" }, () => SOURCE_COMMANDS[platform()] || SOURCE_COMMANDS.macos),
            copyBtn(() => SOURCE_COMMANDS[platform()] || SOURCE_COMMANDS.macos)),
          h("p", { class: "dsx-note" }, () => t("daemon.local.hint"))));
    }
    return null;
  };

  // Built ONCE: each card binds what it reads, so a status change repaints a line, never a whole card — a card
  // rebuilt every 2 s while a browser downloads would wipe the typed path and close any open fold.
  const panels = {
    status: StatusCard(setTab), folders: FoldersCard(ctx), browser: BrowserCard(),
    link: PairingCard(ctx), tunnel: TunnelCard(),
    install: h("section", { class: "dsx-card", "data-card": "install" }, () => { shape(); return untrack(install); }),
  };

  // The wizard ENDS on the folders tab: the daemon answering while Install is open moves there.
  let was = untrack(shape);
  createEffect(() => { const now = shape(); if (was !== "done" && now === "done" && untrack(tab) === "install") setTab("folders"); was = now; });

  // Arrow keys move along the tab bar (the WAI tabs pattern).
  const onKeydown = (e) => {
    const d = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!d) return;
    const next = TABS[(TABS.indexOf(tab()) + d + TABS.length) % TABS.length];
    setTab(next); e.preventDefault();
    const b = e.currentTarget.querySelector(`[data-tab="${next}"]`); if (b) b.focus();
  };

  return h("div", { class: () => "ovl dsx-ovl" + (store.daemonSetupOpen() ? " on" : "") },
    h("div", { class: "dsx-box" },
      h("div", { class: "dsx-head" },
        h("span", { class: "dsx-mark" }, raw(DESKTOP_ICON)),
        h("h2", { class: "dsx-title" }, () => t("daemon.settings.title")),
        h("button", { class: "dsx-icon", title: () => t("daemon.close"), onClick: close }, raw(CLOSE_ICON))),
      h("nav", { class: "hb-tabs dsx-tabs", role: "tablist", "aria-label": () => t("daemon.settings.title"), onKeydown },
        ...TABS.map((id) => h("button", {
          class: () => "hb-tab" + (tab() === id ? " is-on" : ""), type: "button", role: "tab", "data-tab": id,
          "aria-selected": () => String(tab() === id), tabindex: () => (tab() === id ? "0" : "-1"),
          onClick: () => { setTab(id); api.uiEvent("daemon:tab", { tab: id }); },
        }, () => t("daemon.tab." + id)))),
      // A reactive child: the open tab's prebuilt panel is attached, the others wait detached with their state.
      h("div", { class: "dsx-scroll", role: "tabpanel" },
        () => panels[tab()],
        () => problem() ? h("p", { class: "dsx-problem" }, problem()) : null,
        h("button", { class: "dsx-link dsx-recheck", onClick: () => daemon.check() }, () => t("daemon.refresh"))),
    ),
  );
}
