// boot-worker.js — the ONE loader's animation, on its own thread (operator, 2026-11-16).
//
// The page that shows the loader is loading the whole agent: every module, the voice stack, the first requests. A
// canvas animated on that thread stops whenever the thread is busy, which is exactly while the loader is on screen.
// Here the same animation (`components/boot-anim.js`) draws on an OffscreenCanvas the page handed over
// (`core/preboot.js`), on this worker's own frame clock: it moves at its own pace whatever the page is doing.
//
// Messages in:  {t:"start", canvas, size:{w,h,dpr}, colors, reduced} · {t:"size", size} · {t:"stage", n} ·
//               {t:"finish"} · {t:"destroy"}
// Messages out: {t:"p", p} (the share grown, 0..1) · {t:"done"} (the growth completed after `finish`)
import { startBootAnim } from "../components/boot-anim.js?v=6";

let ctrl = null, size = { w: 0, h: 0, dpr: 1 }, resized = null;
const raf = typeof self.requestAnimationFrame === "function"
  ? (fn) => self.requestAnimationFrame(fn)
  : (fn) => setTimeout(() => fn(performance.now()), 16);            // a worker without a frame clock: ~60 a second
const caf = typeof self.cancelAnimationFrame === "function" ? (id) => self.cancelAnimationFrame(id) : (id) => clearTimeout(id);

self.onmessage = (e) => {
  const m = e.data || {};
  if (m.t === "start" && !ctrl) {
    size = m.size;
    ctrl = startBootAnim(m.canvas, {
      onProgress: (p) => self.postMessage({ t: "p", p }),
      env: { reduced: !!m.reduced, colors: m.colors, size: () => size,
             onResize: (fn) => { resized = fn; return () => { resized = null; }; }, raf, caf },
    });
  } else if (m.t === "size") { size = m.size; if (resized) resized(); }
  else if (m.t === "stage" && ctrl) ctrl.setStage(m.n);
  else if (m.t === "finish" && ctrl) ctrl.finish(() => self.postMessage({ t: "done" }));
  else if (m.t === "destroy") { if (ctrl) ctrl.destroy(); ctrl = null; self.close(); }
};
