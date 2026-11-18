// face.js — ONE canvas that draws a face from the shared rig (V2-928). Two uses:
//  * the BACKGROUND face of the desk: `lipSync: true` wraps the canvas in the vendored lip-sync core, which only
//    LISTENS to the agent's audio stream (`observe`) — the page keeps playing it, so the voice is never doubled;
//  * a PREVIEW (Settings, catalogue cells): no audio at all, the rig still breathes, blinks and lives.
// The face never paints a background of its own: it sits on whatever the desk or the panel already paints.
import { createRig, geometry } from "./rig.js?v=1";
import { drawAvatar, shapeOf, isTall } from "./creator.js?v=1";
import { STYLES } from "./classics.js?v=1";

/** The look an entry asks for: a classic id or a parametric spec (see catalog-api.js). */
export function lookOf(entry) {
  if (entry && entry.spec) return { spec: entry.spec, shape: shapeOf(entry.spec) };
  const style = STYLES.find((s) => s.id === (entry && entry.classic)) || STYLES[0];
  return { style };
}

/** Where the head goes in a W×H box: centred, a share of the short side, room left for tall ears or horns. */
export function fit(W, H, look, k = 0.3) {
  let R = Math.min(W, H) * k, cy = H / 2;
  if (look.spec) {
    const tall = isTall(look.spec);
    R *= (tall ? 0.76 : 0.88) / Math.max(1, look.spec.head.h);
    if (tall) cy += R * 0.22;
  }
  return { cx: W / 2, cy, R };
}

/** Draw one frame of `look` with rig numbers `r`. */
export function drawLook(ctx, look, r, cx, cy, R, W, H) {
  const G = look.spec ? geometry(r, cx, cy, R, look.shape) : geometry(r, cx, cy, R);
  if (look.spec) drawAvatar(ctx, G, look.spec);
  else look.style.draw(ctx, G, W, H);
  if (r.tongue > 0.02) drawTongue(ctx, G, look.spec && look.spec.mouth && look.spec.mouth.tongue);
}

/** The tongue (T12, «the face answers you»): drawn over EVERY look from the shared mouth, so any face can stick it out. */
export function drawTongue(ctx, G, color) {
  const k = G.r.tongue, m = G.mouth(), base = m.my - m.h * 0.55, w = Math.max(0.07, m.mw * 0.42), len = 0.05 + 0.14 * k;
  const pts = [];
  for (let i = 0; i <= 16; i++) { const a = (Math.PI * i) / 16; pts.push(G.P([-Math.cos(a) * w, base - Math.sin(a) * len], 0.06)); }
  ctx.save();
  ctx.beginPath(); pts.forEach((p, i) => (i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y))); ctx.closePath();
  ctx.fillStyle = color || "#e0607a"; ctx.fill();
  ctx.lineWidth = Math.max(1, G.R * 0.012); ctx.strokeStyle = "rgba(90,20,40,0.5)"; ctx.stroke();
  const a = G.P([0, base], 0.06), b = G.P([0, base - len * 0.55], 0.06);
  ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
  ctx.restore();
}

export function createFace(host, opts = {}) {
  const rig = createRig();
  let look = lookOf(opts.entry), mood = "listening", hearing = false, speakingHint = false, alpha = 1, scale = opts.scale || 0.3;
  let avatar = null, getFrame = () => ({ visemes: {}, mode: mood }), lookSource = null;

  function createRenderer(el, frameOf) {
    getFrame = frameOf;
    const canvas = document.createElement("canvas");
    canvas.className = opts.className || "";
    canvas.setAttribute("aria-hidden", "true");
    Object.assign(canvas.style, { position: "absolute", inset: "0", width: "100%", height: "100%", display: "block", pointerEvents: "none" });
    el.appendChild(canvas);
    const ctx = canvas.getContext("2d");
    let W = 0, H = 0, dpr = 1, raf = 0, last = performance.now(), paused = false;
    const resize = () => {
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      W = el.clientWidth; H = el.clientHeight;
      canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    };
    const ro = new ResizeObserver(resize); ro.observe(el); resize();
    function tick(now) {
      const dt = Math.min(now - last, 50); last = now;
      const f = getFrame();
      if (lookSource) { try { rig.setLook(lookSource(now)); } catch (_) {} }   // «look at me» pulls on this frame
      const r = rig.update(dt, { ...f, mode: f.mode === "speaking" || speakingHint && !avatar ? "speaking" : f.mode, hearing });
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, W, H);
      if (W > 4 && H > 4 && alpha > 0.01) {
        const p = fit(W, H, look, scale);
        ctx.save(); ctx.globalAlpha = alpha;
        drawLook(ctx, look, r, p.cx, p.cy, p.R, W, H);
        ctx.restore();
      }
      raf = paused ? 0 : requestAnimationFrame(tick);
    }
    raf = requestAnimationFrame(tick);
    return {
      ready: Promise.resolve(), canvas,
      setPaused(p) { if (p === paused) return; paused = p; cancelAnimationFrame(raf); if (!p) { last = performance.now(); raf = requestAnimationFrame(tick); } },
      dispose() { cancelAnimationFrame(raf); ro.disconnect(); canvas.remove(); },
    };
  }

  let view;
  if (opts.lipSync) {
    // Loaded only for the live face: the model (≈1 MB) is fetched once and cached by the browser.
    const ready = import("../../vendor/talking-avatar/TalkingAvatar.js").then(({ TalkingAvatar }) => {
      if (disposed) return;
      avatar = new TalkingAvatar({ container: host, createRenderer, onError: (e) => console.warn("[presence]", e && e.message ? e.message : e) });
      view = avatar.view;
      if (pendingStream) avatar.observeStream(pendingStream).catch(() => {});
    });
    ready.catch(() => { view = createRenderer(host, getFrame); });
  } else view = createRenderer(host, getFrame);

  let disposed = false, pendingStream = null;
  const onVis = () => view && view.setPaused(document.hidden);
  document.addEventListener("visibilitychange", onVis);

  return {
    /** Lip sync from the agent's audio stream (observe only). */
    observe(stream) { pendingStream = stream; if (avatar && stream) avatar.observeStream(stream).catch(() => {}); },
    detach() { pendingStream = null; if (avatar) avatar.detachStream(); },
    unlock() { return avatar ? avatar.unlock() : Promise.resolve(); },
    setEntry(entry) { look = lookOf(entry); },
    /** mood: idle | listening | thinking; hearing: the person is talking; speaking: the agent's voice is on. */
    setState({ mood: m, hearing: h, speaking: s } = {}) {
      if (m && m !== mood) { mood = m; rig.setMood(m); if (avatar) avatar.setStatus(m === "thinking" ? "thinking" : "listening"); }
      if (h !== undefined) hearing = !!h;
      if (s !== undefined) speakingHint = !!s;
    },
    gesture: (g) => rig.gesture(g),
    /** «Look at me» (T10): `{x, y, w}` from look.js, or null when nobody is followed. */
    setLook: (target) => rig.setLook(target),
    /** …or a function the face asks on each of its own frames (`now` → target or null): no extra timer. */
    setLookSource(fn) { lookSource = typeof fn === "function" ? fn : null; if (!lookSource) rig.setLook(null); },
    setAlpha(a) { alpha = a; },
    setScale(k) { scale = k; },
    setPaused(p) { if (view) view.setPaused(p || document.hidden); },
    dispose() { disposed = true; document.removeEventListener("visibilitychange", onVis); if (avatar) avatar.dispose(); else if (view) view.dispose(); },
  };
}
