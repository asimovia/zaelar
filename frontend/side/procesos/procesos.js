// side/procesos/procesos.js — the «Procesos» column (V2-728 · V2-744) as a component: it imports nothing outside this
// folder. mount(host, bridge) → { show, hide, unmount }; the bridge (`services/procesos-bridge.js`) hands it the
// rows and scope, their setters and fetches, reopen/openCard/removeScheduled, entry (V2-822), t, lang, icons, and
// watch(fn)/onLiveChange(fn) → off. `show()` is entering the tab: the live set and the open sub-tab are fetched;
// while shown, a change of the live set refetches the open sub-tab (the one that lost a row, or gained it).
import { SUBTABS, liveView, histView, schedView, taskToChip } from "./model.js";

const el = (tag, cls, text) => Object.assign(document.createElement(tag), { className: cls }, text != null ? { textContent: text } : {});

export function mount(host, b) {
  const bar = el("div", "cw-subtabs"), list = el("div", "cw-tasklist");
  const subs = SUBTABS.map((st) => {
    const btn = bar.appendChild(el("button", "cw-subtab"));
    btn.onclick = () => { b.setScope(st.id); b.fetchScope(st.id); };
    return [st, btn];
  });
  // ⚙ — the engine's own escalations (memory upkeep, relays) are audited, never counted; a manual test sees them here.
  const all = bar.appendChild(el("button", "cw-subtab all", "⚙"));
  all.onclick = () => { b.setShowAll(!b.showAll()); b.fetchScope(b.scope()); };
  host.append(bar, list);     // no hand-filled form (V2-883): a timed job is created by ASKING the agent
  let shown = false, timer = null;

  // KEYED (a refetch landed while he typed an answer and took it): a row keeps its node while its key lives, is
  // painted IN PLACE only when what it says changed, and its process entry — where his answer is typed — is never
  // rebuilt or moved: a node taken out of the page loses its focus, and a new one has no text.
  const kept = new Map(), empty = el("div", "cw-empty");     // row key → { node, sig, entry, ek }
  function paint(key, v, meta, btn, ek = "") {
    const k = kept.get(key) || { node: el("div", "") }, sig = JSON.stringify([v, ek]), r = k.node;
    kept.set(key, k);
    if (k.sig === sig) return r;
    if (k.ek !== ek) { if (k.entry) k.entry.remove(); k.entry = ek ? b.entry(...JSON.parse(ek)) : null; k.ek = ek; }
    if (!r.firstChild) r.append(el("span", "cw-proc-dot"), el("div", "cw-proc-main"));
    const [dot, main] = r.children;
    r.className = "cw-proc-row " + v.cls;
    dot.textContent = v.glyph;
    for (const c of [...main.children]) if (c !== k.entry) c.remove();
    main.prepend(el("div", "cw-proc-goal", v.title), ...(v.note ? [el("div", "cw-proc-note", v.note)] : []), meta);
    if (k.entry && k.entry.parentNode !== main) main.append(k.entry);
    [...r.children].slice(2).forEach((c) => c.remove());
    if (btn) r.appendChild(el("div", "cron-btns")).append(btn);
    k.sig = sig;
    return r;
  }
  const button = (cls, title, onclick) => Object.assign(el("button", "cron-b hb-icbtn" + cls), { title, onclick });
  const live = (key, task) => {
    const v = liveView(task, Date.now(), b.t, b.lang()), meta = el("div", "cw-proc-meta");
    v.meta.forEach((m, i) => meta.append(el("span", "cw-proc-tag" + (i ? "" : " state"), m)));
    return paint(key, v, meta, null, JSON.stringify([task.session || task.id, task.id]));   // V2-822 — its ONE home
  };
  // Reopening is the SERVER's (it rebuilds the sheet if gone and names the card); the panel stays where he put it.
  const hist = (key, e) => {
    const v = histView(e, Date.now(), b.t);
    const btn = v.results && button("", b.t("chat.taskResults"), async () => {
      const r = await b.reopen(String(e.id || ""));
      if (r && r.ok && r.instance) b.openCard(r.instance);
    });
    if (btn) btn.textContent = b.t("chat.taskResults");
    return paint(key, v, el("div", "cw-proc-meta", v.meta), btn);
  };
  const sched = (key, task) => {
    const v = schedView(task, b.t, b.lang());
    const btn = button(" danger", b.t("chat.delete"), async () => { await b.removeScheduled(String(task.id)); b.fetchScope(b.scope()); });
    btn.innerHTML = (b.icons && b.icons.trash) || "✕";
    return paint(key, v, el("div", "cw-proc-meta", v.meta), btn);
  };

  // The row SHAPE follows the scope: a live, a finished and a timed commission answer different questions.
  function render() {
    const scope = b.scope(), rows = (b.rows() || {})[scope] || [], used = new Set();
    for (const [st, btn] of subs) { btn.className = "cw-subtab" + (scope === st.id ? " on" : ""); btn.textContent = b.t(st.label); }
    all.className = "cw-subtab all" + (b.showAll() ? " on" : "");
    all.title = b.t("chat.taskShowAll");
    const spec = SUBTABS.find((x) => x.id === scope);
    empty.textContent = b.t(spec ? spec.empty : "chat.procEmpty");
    const nodes = !rows.length ? [empty] : rows.map((r, i) => {
      const key = scope + ":" + (r.id ?? "#" + i);
      used.add(key);
      return scope === "live" ? live(key, taskToChip(r)) : scope === "done" ? hist(key, r) : sched(key, r);
    });
    for (const [key, k] of kept) if (!used.has(key)) { k.node.remove(); kept.delete(key); }
    // Only what left is taken out, and a row is moved only when its place changed: the others are never touched.
    for (const c of [...list.children]) if (!nodes.includes(c)) c.remove();
    nodes.forEach((n, i) => { if (list.children[i] !== n) list.insertBefore(n, list.children[i] || null); });
  }
  const offs = [b.watch(render), b.onLiveChange(() => { if (shown) b.fetchScope(b.scope()); })];
  render();

  const hide = () => { shown = false; clearInterval(timer); };
  return {
    show() {           // elapsed time ticks by the quarter minute
      hide(); shown = true; b.fetchLive(); b.fetchScope(b.scope());
      timer = setInterval(() => { if (b.scope() === "live") render(); }, 15000);
    },
    hide,
    unmount() { hide(); offs.forEach((off) => off()); bar.remove(); list.remove(); },
  };
}
