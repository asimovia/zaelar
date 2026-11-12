// BootOverlay — the ONE loader (V2-881). Both shells.
//
// It used to be the third of three: the inline splash (spinner + narration), then this overlay's own caption
// («Starting up zaelar…»), then the neurons. Now there is one screen from the first byte to «ready»: the HTML paints
// `#preboot` (the first ring of the neurons, turning), `core/preboot.js` narrates the cold start on it before any
// module exists, and this component TAKES OVER THAT SAME ELEMENT — it adds the canvas that grows the mesh, never a
// second overlay — so nothing flashes between them.
//
// The growth is the progress bar (`role=progressbar`, `aria-valuenow`). It grows continuously on its own clock
// (boot-anim.js), never past a ceiling below the whole mesh; a real phase — the stage preboot reached (`data-stage`),
// this module being mounted, `store.bootPhase` (voice, memory, reflex) — may pull it forward. The ONLY thing that
// completes it is `store.bootReady`: then the rest develops within GROW.FINISH_S and the veil lifts.
import { createEffect } from "../core/reactive.js?v=2";
import * as store from "../core/store.js?v=2";
import { startBootAnim, STAGE_READY, BURST_MS } from "./boot-anim.js?v=4";

/** bootPhase → stage. Exported for the test. */
export const PHASE_STAGE = { encendiendo: 2, voz: 3, memoria: 4, reflejo: 5 };

export function BootOverlay() {
  let host = document.getElementById("preboot");
  if (!host) {                       // a page without the inline host still gets the same loader
    host = document.createElement("div");
    host.id = "preboot"; host.className = "boot-ovl";
  }
  host.setAttribute("role", "progressbar");
  host.setAttribute("aria-valuemin", "0");
  host.setAttribute("aria-valuemax", "100");
  const canvas = document.createElement("canvas");
  canvas.className = "boot-canvas";
  host.prepend(canvas);
  const report = (f) => host.setAttribute("aria-valuenow", String(Math.round(f * 100)));

  // Start once the host is laid out (a canvas measured before mount is 0×0).
  requestAnimationFrame(() => {
    const ctrl = startBootAnim(canvas, { onProgress: report });
    host.classList.add("anim");      // the canvas draws the ring now; the HTML one steps aside
    ctrl.setStage(Math.max(2, Number(host.dataset.stage) || 0));
    report(ctrl.shown());
    createEffect(() => {
      const s = PHASE_STAGE[store.bootPhase()];
      if (s) ctrl.setStage(s);
    });
    createEffect(() => {
      if (!store.bootReady()) return;
      try { window.__zaelarBoot && window.__zaelarBoot.finish(); } catch (_) { /* the narration is optional */ }
      ctrl.finish(() => {
        host.classList.add("gone");
        setTimeout(() => { ctrl.destroy(); host.remove(); }, BURST_MS);
      });
      report(1);
      host.dataset.stage = String(STAGE_READY);
    });
  });
  return host;
}
