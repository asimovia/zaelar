// The FOLDERS card of the daemon's settings screen (V2-575): which folders Zaelar may read on this computer.
//
// The only destructive control here is "stop reading this folder", which is the safe direction. The first granted
// folder is the DEFAULT one — the folder a request that names no folder looks in — and with nothing granted yet
// the suggested Documents folder carries that mark instead, so the person sees where a first grant will land.
//
// The card is a function of the status, redrawn when it changes; the free-text path field is the one thing a
// redraw would wipe, so it lives OUTSIDE the reactive part and the poll never clears what is half-typed.
import { h } from "../../core/dom.js?v=2";
import { createMemo } from "../../core/reactive.js?v=2";
import * as daemon from "../../services/daemon.js?v=3";
import { t } from "../../core/i18n.js?v=1";

// The candidate a fresh install suggests as its default: the one the daemon calls Documents, by path or label.
function suggestedDefault(candidates) {
  return candidates.find((c) => /(^|[\\/])(documents|documentos)$/i.test(String(c.path || "").replace(/[\\/]+$/, "")))
    || candidates.find((c) => /^(documents|documentos)$/i.test(String(c.label || "")))
    || null;
}

// `ctx` is the screen's shared plumbing: `busy()`, `act(fn, path)`, `doPick()` and `bindPath(el)`.
export function FoldersCard(ctx) {
  const list = () => {
    const s = daemon.status() || {};
    // From a cloud engine the paths are his desktop's business and never arrive: said, not drawn as "none".
    if (s.state === "remote") return h("p", { class: "dsx-note dsx-unknown" }, () => t("daemon.folders.remote"));
    const roots = s.roots || [];
    const candidates = (s.candidates || []).filter((c) => !c.allowed);
    const suggested = roots.length ? null : suggestedDefault(candidates);
    return h("div", {},
      roots.length
        ? h("ul", { class: "dsx-list" }, ...roots.map((path, i) =>
            h("li", { class: "dsx-item" + (i === 0 ? " is-default" : "") },
              h("span", { class: "dsx-path" }, path),
              i === 0 ? h("span", { class: "dsx-tag dsx-default" }, () => t("daemon.folders.default")) : null,
              h("button", {
                class: "dsx-mini", disabled: () => ctx.busy() === path,
                onClick: () => ctx.act(daemon.revoke, path),
              }, () => t("daemon.folders.revoke")))))
        : h("p", { class: "dsx-empty" }, () => t("daemon.folders.none")),
      candidates.length
        ? h("div", { class: "dsx-cands" },
            h("p", { class: "dsx-note" }, () => t("daemon.folders.suggested")),
            h("div", { class: "dsx-dl-row" }, ...candidates.map((c) =>
              h("button", {
                class: "dsx-chip" + (c === suggested ? " is-default" : ""),
                title: c === suggested ? t("daemon.folders.default_suggested") : null,
                disabled: () => ctx.busy() === c.path,
                onClick: () => ctx.act(daemon.grant, c.path),
              }, "+ " + (c.label || c.path),
                 c === suggested ? h("span", { class: "dsx-tag dsx-default" }, () => t("daemon.folders.default")) : null))))
        : null,
    );
  };
  const local = createMemo(() => !daemon.isRemote());
  return h("section", { class: "dsx-card dsx-folders", "data-card": "folders" },
    h("p", { class: "dsx-note dsx-body" }, () => t("daemon.folders.body")),
    () => local()
      ? h("button", { class: "dsx-primary", disabled: () => ctx.busy() === "pick", onClick: ctx.doPick },
          () => t("daemon.folders.pick"))
      : null,
    list,
    // Outside the reactive list on purpose (see the header): only its visibility follows the status.
    h("div", { class: "dsx-add", style: { display: () => (local() ? "" : "none") } },
      h("input", { class: "dsx-input", type: "text", ref: ctx.bindPath,
                   placeholder: () => t("daemon.folders.placeholder") }),
      h("button", { class: "dsx-btn", onClick: () => ctx.act(daemon.grant, ctx.typedPath()) },
        () => t("daemon.folders.add"))),
  );
}
