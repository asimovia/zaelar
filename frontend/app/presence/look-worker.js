// look-worker.js — the camera's detectors, OFF the page's main thread (V2-928, 2026-11-18: the landmarker's 10–60 ms a
// frame on the main thread delayed the live caption by up to half a second). A module Web Worker: the page sends one
// frame at a time as a transferred ImageBitmap; this runs picojs (light: where a face is) or, once it has loaded, the
// MediaPipe Face Landmarker (mesh: where, plus the 52 expression scores and a head pose) and answers with the same
// readings look-camera.js used to compute in the page. Nothing leaves the device: no image or number goes past the page.
//
// Messages in:  {type: "init"}                      → loads picojs
//               {type: "mesh"}                      → loads the landmarker (sent once the page listens for its answer)
//               {type: "frame", bitmap, t, w, mesh} → one frame (the bitmap is closed here); `mesh: false` = light only
//               {type: "light"}                     → the page dropped the landmarker (too slow): free it
// Messages out: {type: "mode", mode, why?}          → "mesh" once the landmarker runs, "light" if it cannot
//               {type: "faces", t, ms, dets, faces} → per frame; `faces` null on the light detector
import { createDetector } from "./look-camera.js?v=1";
import { loadLandmarker, readResult } from "./humanity/landmarker.js?v=1";

let detect = null, lm = null, last = 0, canvas = null, ctx = null;

function light(bitmap, W) {
  const H = Math.round((W * bitmap.height) / bitmap.width);
  if (!canvas || canvas.width !== W || canvas.height !== H) {
    canvas = new OffscreenCanvas(W, H);
    ctx = canvas.getContext("2d", { willReadFrequently: true });
  }
  ctx.drawImage(bitmap, 0, 0, W, H);
  return { dets: detect(ctx.getImageData(0, 0, W, H).data, W, H), faces: null };
}

self.onmessage = async ({ data }) => {
  if (data.type === "init") {
    try { detect = await createDetector(); } catch (e) { self.postMessage({ type: "error", why: String(e && e.message || e) }); return; }
    self.postMessage({ type: "ready" });
    return;
  }
  if (data.type === "mesh") {
    loadLandmarker({ delegate: "CPU" })
      .then((l) => { lm = l; self.postMessage({ type: "mode", mode: "mesh", why: l.delegate }); })
      .catch((e) => self.postMessage({ type: "mode", mode: "light", why: "failed: " + (e && e.message ? e.message : e) }));
    return;
  }
  if (data.type === "light") { lm = null; return; }
  if (data.type !== "frame") return;
  const { bitmap, t } = data, t0 = performance.now();
  let out, used = "light";
  try {
    if (lm && data.mesh) {
      const ts = Math.max(last + 1, Math.round(t)); last = ts;
      out = readResult(lm.detectForVideo(bitmap, ts), bitmap.width, bitmap.height); used = "mesh";
    } else out = light(bitmap, data.w);
  } catch (e) {
    out = { dets: [], faces: null, error: String(e && e.message || e) };
  }
  try { bitmap.close(); } catch (_) {}
  self.postMessage({ type: "faces", t, ms: performance.now() - t0, used, ...out });
};
