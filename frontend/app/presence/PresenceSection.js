// PresenceSection.js — Settings ▸ Presence (V2-928): where the person picks and tunes the agent's face. Full screen
// inside Settings (never a card on the desk, never in the widget list). Layout, by the operator's brief:
//   top    — the categories;
//   left   — the faces of the chosen category, by name (a small still of each);
//   centre — the face alone, alive (no talk or gesture test buttons);
//   right  — «Customise» opens the knobs; «Save» wears the result at once. «Restore default» = Porcelain, on.
// A phone stacks the same pieces (styles.css `.pz` media rules). Every change goes through presence/state.js.
import { t } from "../core/i18n.js?v=1";
import { createRig } from "./rig.js?v=1";
import { createFace, lookOf, fit, drawLook } from "./face.js?v=1";
import { CATEGORIES, facesOf, faceById, editableSpec, faceName, catName } from "./catalog-api.js?v=1";
import { CONTROLS, getP, setP } from "./controls.js?v=1";
import { createEffect } from "../core/reactive.js?v=2";
import { lookCamera, setLookCamera, cameraProblem, CAMERA_PROBLEM } from "./look-state.js?v=1";
import { presenceOn, presenceFace, presenceCustom, setPresenceOn, setPresenceFace, saveCustomFace, resetPresence, DEFAULT_FACE } from "./state.js?v=1";

const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
let live = null;   // the one preview on screen: { face, timer }

/** A still of a face for the list (one frame of a resting rig), drawn when the row scrolls into view. */
const stillRig = createRig(() => 0.5).update(16, { visemes: {}, mode: "listening" });
function still(canvas, entry) {
  const W = 40, H = 40, dpr = Math.min(window.devicePixelRatio || 1, 2), look = lookOf(entry), p = fit(W, H, look, 0.36);
  canvas.width = W * dpr; canvas.height = H * dpr;
  const ctx = canvas.getContext("2d"); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  try { drawLook(ctx, look, stillRig, p.cx, p.cy, p.R, W, H); } catch (_) {}
}

export function mountPresence(host, msg = () => {}) {
  if (!host) return;
  if (live) { clearInterval(live.timer); live.fx(); live.face.dispose(); live = null; }
  const current = () => faceById(presenceFace(), presenceCustom()) || faceById(DEFAULT_FACE);
  let cat = current().cat, editing = null, picked = current();

  host.innerHTML = `<div class="pz">
    <footer class="pz-foot">
      <label class="pz-switch"><input type="checkbox" class="pz-on"/><span>${esc(t("presence.physical"))}</span></label>
      <button type="button" class="pz-ghost set-btn set-btn--secondary pz-reset">${esc(t("presence.reset"))}</button>
      <div class="pz-look"><label class="pz-switch"><input type="checkbox" class="pz-cam"/><span>${esc(t("presence.camera"))}</span></label>
        <p class="pz-hint pz-cam-hint"></p></div>
    </footer>
    <div class="pz-cats" role="tablist">${CATEGORIES.map((c) => `<button type="button" role="tab" data-cat="${c.id}">${esc(catName(c.id))}</button>`).join("")}</div>
    <div class="pz-body">
      <aside class="pz-list" aria-label="${esc(t("presence.faces"))}"></aside>
      <section class="pz-stage"><div class="pz-face"></div>
        <div class="pz-name"></div>
        <div class="pz-acts"><button type="button" class="pz-btn set-btn set-btn--secondary pz-custom">${esc(t("presence.customise"))}</button></div>
        <p class="pz-note"></p></section>
      <aside class="pz-edit" hidden><div class="pz-knobs"></div>
        <div class="pz-editfoot"><button type="button" class="pz-ghost set-btn set-btn--secondary pz-cancel">${esc(t("presence.cancel"))}</button><button type="button" class="pz-btn set-btn set-btn--primary pz-save">${esc(t("presence.save"))}</button></div></aside>
    </div>
</div>`;
  const $ = (s) => host.querySelector(s);
  const face = createFace($(".pz-face"), { entry: picked, scale: 0.34 });
  // «Look at me» (T10): the switch and its line follow look-state.js (a refusal turns it back off and says why)
  const fx = createEffect(() => {
    const on = lookCamera(), why = cameraProblem();
    $(".pz-cam").checked = on;
    const hint = $(".pz-cam-hint"); hint.textContent = t(why ? CAMERA_PROBLEM[why] || CAMERA_PROBLEM.unavailable : "presence.camera_hint"); hint.classList.toggle("is-problem", !!why);
  });
  live = { face, fx, timer: setInterval(() => { if (!host.isConnected && live && live.face === face) { clearInterval(live.timer); fx(); face.dispose(); live = null; } }, 1000) };

  const io = new IntersectionObserver((xs) => xs.forEach((x) => { if (x.isIntersecting) { const b = x.target; still(b.querySelector("canvas"), b._entry); io.unobserve(b); } }), { root: $(".pz-list") });
  function paintList() {
    host.querySelectorAll(".pz-cats [data-cat]").forEach((b) => { const on = b.dataset.cat === cat; b.classList.toggle("on", on); b.setAttribute("aria-selected", on); });
    const list = $(".pz-list"), items = facesOf(cat, presenceCustom());
    list.innerHTML = items.length ? "" : `<p class="pz-empty">${esc(t("presence.mine_empty"))}</p>`;
    for (const e of items) {
      const b = document.createElement("button");
      b.type = "button"; b.className = "pz-item" + (e.id === picked.id ? " on" : ""); b.dataset.id = e.id; b._entry = e;
      b.innerHTML = `<canvas width="40" height="40" aria-hidden="true"></canvas><span>${esc(faceName(e))}</span>`;
      b.onclick = () => pick(e);
      list.appendChild(b); io.observe(b);
    }
    const on = list.querySelector(".pz-item.on"); if (on) on.scrollIntoView({ block: "nearest" });
  }
  function paintStage() {
    $(".pz-name").textContent = faceName(picked);
    $(".pz-on").checked = presenceOn();
    $(".pz-note").textContent = editing && picked.classic && picked.classic !== "porcelain" ? t("presence.classic_note") : "";
    host.querySelector(".pz").classList.toggle("is-editing", !!editing);
    $(".pz-edit").hidden = !editing;
  }
  function pick(e) {
    picked = e; editing = null;
    setPresenceFace(e.id);
    face.setEntry(e); msg(t("presence.applied", { name: faceName(e) }));
    host.querySelectorAll(".pz-item").forEach((b) => b.classList.toggle("on", b.dataset.id === e.id));
    paintStage();
  }
  function knobs() {
    const box = $(".pz-knobs"); box.innerHTML = "";
    CONTROLS.forEach(([grp, list], gi) => {
      const d = document.createElement("details"); d.open = gi < 3;
      d.innerHTML = `<summary>${esc(t("presence.grp." + grp))}</summary>`;
      for (const c of list) {
        const row = document.createElement("label"); row.className = "pz-ctl";
        row.innerHTML = `<span>${esc(t("presence.ctl." + c.path))}</span>`;
        const val = getP(editing, c.path); let el;
        if (c.kind === "select") { el = document.createElement("select"); for (const o of c.opts) { const k = "presence.opt." + o, l = t(k); el.add(new Option(l === k ? o : l, o, false, o === val)); } }
        else if (c.kind === "range") { el = document.createElement("input"); Object.assign(el, { type: "range", min: c.min, max: c.max, step: c.step, value: val ?? c.min }); }
        else if (c.kind === "color") { el = document.createElement("input"); el.type = "color"; el.value = /^#[0-9a-f]{6}$/i.test(val || "") ? val : (c.path === "ears.color" ? editing.head.skin : "#888888"); }
        else { el = document.createElement("input"); el.type = "checkbox"; el.checked = !!val; }
        el.oninput = el.onchange = () => { setP(editing, c.path, c.kind === "range" ? +el.value : c.kind === "check" ? el.checked : el.value); face.setEntry({ spec: editing }); };
        row.appendChild(el); d.appendChild(row);
      }
      box.appendChild(d);
    });
  }

  host.querySelectorAll(".pz-cats [data-cat]").forEach((b) => (b.onclick = () => { cat = b.dataset.cat; paintList(); }));
  $(".pz-custom").onclick = () => { editing = editableSpec(picked); knobs(); face.setEntry({ spec: editing }); paintStage(); };
  $(".pz-cancel").onclick = () => { editing = null; face.setEntry(picked); paintStage(); };
  $(".pz-save").onclick = () => {
    saveCustomFace(editing); editing = null; picked = faceById("mine", presenceCustom()); cat = "mine";
    face.setEntry(picked); paintList(); paintStage(); msg(t("presence.saved"));
  };
  $(".pz-on").onchange = (e) => { setPresenceOn(e.target.checked, "settings"); msg(t(e.target.checked ? "presence.shown" : "presence.hidden")); };
  $(".pz-cam").onchange = (e) => setLookCamera(e.target.checked, "settings");
  $(".pz-reset").onclick = () => { resetPresence(); editing = null; picked = faceById(DEFAULT_FACE); cat = picked.cat; face.setEntry(picked); paintList(); paintStage(); msg(t("presence.restored")); };
  paintList(); paintStage();
}
