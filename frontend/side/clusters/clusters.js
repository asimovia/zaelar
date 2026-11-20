// side/clusters/clusters.js — the «Clusters» column (V2-086) as a component of its own: the networks there are credentials for,
// whether we are inside, who is there, how much was said, and the CONNECT gate; no conversation (clusters have their own monitor).
// It imports nothing: mount(host, { clusters(), confirm(), t(key, vars), watch(fn) → stop, refresh(), connect(name), disconnect(name),
// resolve(ok) }) → { show(), hide(), unmount() }; `watch` runs fn now and again when what it read changes. cluster_id is not a secret
// (it travels in the invitation); the token never reaches the client. THE GATE: no socket opens without his explicit «yes» on it.
const el = (tag, cls, ...kids) => { const e = document.createElement(tag); e.className = cls; e.append(...kids.filter((k) => k != null)); return e; };
const btn = (cls, label, onclick, title) => Object.assign(el("button", cls, label), { onclick }, title ? { title: label } : {});
export function rowView(c, t) {
  const on = Array.isArray(c.online) ? c.online : [];
  const peers = on.length ? t(on.length > 1 ? "chat.clusterPeers" : "chat.clusterPeer", { n: on.length, list: on.join(", ") }) : t("chat.clusterNobody");
  return { name: String(c.name || ""), connected: !!c.connected, isPublic: !!c.public, id: c.cluster_id || "", meta: t(c.connected
    ? "chat.connected" : "chat.disconnected") + (c.handle ? t("chat.clusterAs", { handle: c.handle }) : "") + peers + t("chat.clusterMsgs", { n: c.msgs || 0 }) };
}
export const gateView = (confirm, t) => (confirm ? { question: confirm.question || t("chat.clusterConfirmQ") } : null);
export function mount(host, b) {
  const t = b.t, list = el("div", "cl-list");
  const row = (r) => el("div", "cl-row", el("div", "cl-main",
      el("div", "cl-name", el("span", "cl-dot" + (r.connected ? " on" : "")), r.name, r.isPublic ? el("span", "cl-badge", t("chat.public")) : null),
      el("div", "cl-meta", r.meta), r.id ? el("div", "cl-id", r.id) : null),
    el("div", "cl-btns", r.connected ? btn("cl-b", t("chat.disconnectBtn"), () => b.disconnect(r.name), true)
                                     : btn("cl-b on", t("chat.connectBtn"), () => b.connect(r.name), true)));
  let gate = null;
  host.classList.add("side-clusters"); host.append(list);
  const stop = b.watch(() => {
    const g = gateView(b.confirm(), t), rows = b.clusters() || []; if (gate) gate.remove();
    gate = g && host.insertBefore(el("div", "cl-confirm", el("div", "cl-q", g.question), el("div", "cl-cbtns",   // resolve(true): this button only
      btn("cl-b on", t("chat.yesConnect"), () => b.resolve(true)), btn("cl-b", t("chat.no"), () => b.resolve(false)))), list);
    list.replaceChildren(...(rows.length ? rows.map((c) => row(rowView(c, t))) : [el("div", "cw-empty", t("chat.clustersEmpty"))]));
  });
  return { show: () => b.refresh(), hide: () => {},   // show asks for the list, later changes come through `watch`; nothing to pause
           unmount() { stop(); host.replaceChildren(); host.classList.remove("side-clusters"); } };
}
