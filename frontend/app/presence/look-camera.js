// look-camera.js — «look at me» (V2-928 T10), the CAMERA: the front camera, read a dozen times a second, and an on-device
// face detector that says where the faces are — the light one (vendored picojs, frontend/vendor/picojs/) at once, and,
// when the face answers you (T12), the vendored MediaPipe Face Landmarker once it has loaded, which also reads his
// expression (humanity/). Both run in a Web Worker (look-worker.js): the page only hands it one frame at a time. Nothing leaves the page: no frame, no box, no number is sent to the engine, a model or any
// server — the readings go straight to look.js and humanity/, and the frame is overwritten by the next one. The camera
// runs only between start() and stop(); the caller (LookAtMe.js) stops it when the switch is off, the face is off or
// hidden, or the tab is hidden.
import pico from "../../vendor/picojs/pico.js";

const CASCADE = new URL("../../vendor/picojs/facefinder.bin", import.meta.url).href;
let _classify = null;
async function classifier() {
  if (!_classify) {
    const r = await fetch(CASCADE);
    if (!r.ok) throw Object.assign(new Error("cascade " + r.status), { code: "unavailable" });
    _classify = pico.unpack_cascade(new Int8Array(await r.arrayBuffer()));
  }
  return _classify;
}

const MEMORY = 4, IOU = 0.2, MIN_Q = 36;   // detections merged over the last 4 frames; a cluster's summed score floor
// The landmarker's pace: it starts at 10 analysed frames a second and steps down while one frame takes more than this
// share of its slot (15 %: it runs in the worker, but a core it holds is a core the page and the voice do not get);
// under the last step it is dropped and picojs keeps the gaze (humanity/ then sees presence only). While he or the
// agent talks the camera runs at SLOW_FPS: enough to follow him, and his mouth is not read then.
const MESH_FPS = [10, 7, 5], MESH_BUDGET = 0.15, MESH_STALL_MS = 250, SLOW_FPS = 4;

/** A detector over RGBA frames: `detect(rgba, w, h)` → `[{x, y, size, q, ar}]` (centre and side over the frame, 0..1; ar = height over width). */
export async function createDetector() {
  const classify = await classifier();
  const memory = pico.instantiate_detection_memory(MEMORY);
  let gray = null;
  return function detect(rgba, w, h) {
    if (!gray || gray.length !== w * h) gray = new Uint8Array(w * h);
    for (let i = 0, j = 0; i < gray.length; i++, j += 4) gray[i] = (2 * rgba[j] + 7 * rgba[j + 1] + rgba[j + 2]) / 10;
    const params = { shiftfactor: 0.1, minsize: Math.max(16, Math.round(w * 0.08)), maxsize: Math.round(Math.min(w, h) * 0.95), scalefactor: 1.1 };
    let dets = pico.run_cascade({ pixels: gray, nrows: h, ncols: w, ldim: w }, classify, params);
    dets = pico.cluster_detections(memory(dets), IOU);
    return dets.filter((d) => d[3] > MIN_Q).map(([r, c, s, q]) => ({ x: c / w, y: r / h, size: s / w, q, ar: h / w }));
  };
}

/** Why a camera could not start, as a value the switch can say: denied · nocamera · unsupported · unavailable. */
export function cameraError(e) {
  const n = (e && (e.code || e.name)) || "";
  if (n === "unsupported") return "unsupported";
  if (/NotAllowed|Security|denied/i.test(n)) return "denied";
  if (/NotFound|Overconstrained|NotReadable|devices/i.test(n)) return "nocamera";
  return "unavailable";
}

/** Can the detectors run in a module Web Worker on this page (frames as transferred ImageBitmaps)? */
function workerCapable() {
  return typeof Worker === "function" && typeof OffscreenCanvas === "function" && typeof createImageBitmap === "function";
}

/** The worker, ready to take frames — or null when it cannot start (then the page runs the light detector itself). */
function startWorker() {
  if (!workerCapable()) return Promise.resolve(null);
  return new Promise((resolve) => {
    let w;
    try { w = new Worker(new URL("./look-worker.js?v=1", import.meta.url), { type: "module" }); } catch (_) { resolve(null); return; }
    const fail = () => { try { w.terminate(); } catch (_) {} resolve(null); };
    const t = setTimeout(fail, 8000);
    w.onerror = () => { clearTimeout(t); fail(); };
    w.onmessage = ({ data }) => {
      if (data.type === "ready") { clearTimeout(t); resolve(w); }
      else if (data.type === "error") { clearTimeout(t); fail(); }
    };
    w.postMessage({ type: "init" });
  });
}

/**
 * Start the camera and the detectors. `onFaces(dets, t, faces)` runs per analysed frame: `dets` the face boxes (gaze),
 * `faces` the landmarker's reading (`[{size, shapes, pose}]`, humanity/) once it runs, else null.
 * The detectors run in a Web Worker (look-worker.js), never on the page's main thread; `mesh` asks the worker to load
 * the Face Landmarker too, and until it is ready, if it fails, or if this device is too slow for it, picojs keeps the
 * gaze. Without workers the page runs picojs itself (light only). `onMode(mode, why)`: "light" | "mesh".
 * Resolves to `{stop(), stats(), setPace(slow)}` — `setPace(true)` while he or the agent is talking: a few frames a
 * second are enough to follow, and the mouth is not read then anyway. Stats: `{fps, ms, w, h, mode, delegate, meshFps,
 * worker}`. Rejects with an error whose `cameraError()` names the reason. The stream is stopped on every failure path.
 */
export async function startCamera({ onFaces, mesh = false, onMode = null, fps = 12, width = 240 } = {}) {
  const md = globalThis.navigator && navigator.mediaDevices;
  if (!md || !md.getUserMedia) throw Object.assign(new Error("no camera API (an insecure page?)"), { code: "unsupported" });
  const worker = await startWorker();
  const detect = worker ? null : await createDetector();
  let stream;
  try {
    // 640×480 ideal: picojs reads a 240-px copy anyway, and the landmarker needs a face bigger than a thumbnail
    stream = await md.getUserMedia({ audio: false,
      video: { facingMode: "user", width: { ideal: 640 }, height: { ideal: 480 }, frameRate: { ideal: 15, max: 30 } } });
  } catch (e) { if (worker) worker.terminate(); throw e; }
  let stopped = false, timer = 0, frames = 0, seen = 0, since = performance.now(), rate = 0, ms = 0, W = width, H = 0;
  let meshFps = MESH_FPS[0], meshSeen = 0, mode = "light", delegate = "", busy = false, slow = false;
  const stop = () => {
    if (stopped) return; stopped = true; clearTimeout(timer);
    for (const tr of stream.getTracks()) { try { tr.stop(); } catch (_) {} }
    video.srcObject = null;
    if (worker) worker.terminate();
  };
  const video = document.createElement("video");
  video.muted = true; video.playsInline = true; video.setAttribute("playsinline", ""); video.srcObject = stream;
  try { await video.play(); } catch (e) { stop(); throw e; }
  const canvas = worker ? null : document.createElement("canvas");
  const ctx = canvas ? canvas.getContext("2d", { willReadFrequently: true }) : null;
  const toLight = (why) => {
    if (mode === "mesh" && worker) worker.postMessage({ type: "light" });
    mode = "light"; ms = 0; seen = 0;
    try { onMode && onMode("light", why); } catch (_) {}
  };
  const tick = (t1, dets, faces) => {
    frames++;
    if (t1 - since >= 1000) { rate = frames * 1000 / (t1 - since); frames = 0; since = t1; }
    try { onFaces && onFaces(dets, t1, faces); } catch (_) {}
  };
  const judge = (took, used) => {
    ms = ms ? ms * 0.8 + took * 0.2 : took;
    if (used === "mesh") {
      // the landmarker on a busy or slow device: fewer frames first, then back to the light detector for good;
      // one frame that took far too long (after the first two, which carry the warm-up) drops it at once
      if (++meshSeen > 2 && took > MESH_STALL_MS) toLight("stall");
      else if (meshSeen > 15 && ms > MESH_BUDGET * 1000 / meshFps) {
        const i = MESH_FPS.indexOf(meshFps);
        if (i < MESH_FPS.length - 1) { meshFps = MESH_FPS[i + 1]; meshSeen = 0; } else toLight("slow");
      }
    } else if (++seen > 10 && ms > 600 / fps && W > 160) W = 160;   // a slow device: a smaller frame, never under 160
  };

  if (worker) worker.onmessage = ({ data }) => {
    if (stopped) return;
    if (data.type === "mode") {
      if (data.mode === "mesh") { mode = "mesh"; delegate = data.why || ""; ms = 0; meshSeen = 0; try { onMode && onMode("mesh", delegate); } catch (_) {} }
      else toLight(data.why);
    } else if (data.type === "faces") {
      busy = false;
      if (data.error && data.used === "mesh") toLight("error");
      judge(data.ms, data.used);
      tick(performance.now(), data.dets || [], data.faces || null);
    }
  };

  if (worker && mesh) worker.postMessage({ type: "mesh" });     // now that the page listens for its «mode»

  function frame() {
    if (stopped) return;
    const t0 = performance.now();
    if (video.readyState >= 2 && video.videoWidth) {
      H = Math.round(W * video.videoHeight / video.videoWidth);
      if (worker) {
        if (!busy) {             // one frame in flight at a time: a slow worker is skipped, never queued
          busy = true;
          const m = mode === "mesh", opts = m ? {} : { resizeWidth: W, resizeHeight: H, resizeQuality: "low" };
          createImageBitmap(video, opts).then((bitmap) => {
            if (stopped) { bitmap.close(); return; }
            worker.postMessage({ type: "frame", bitmap, t: performance.now(), w: W, mesh: m }, [bitmap]);
          }).catch(() => { busy = false; });
        }
      } else {
        if (canvas.width !== W || canvas.height !== H) { canvas.width = W; canvas.height = H; }
        ctx.drawImage(video, 0, 0, W, H);
        const dets = detect(ctx.getImageData(0, 0, W, H).data, W, H), t1 = performance.now();
        judge(t1 - t0, "light");
        tick(t1, dets, null);
      }
    }
    const every = 1000 / (slow ? SLOW_FPS : mode === "mesh" ? meshFps : fps);
    timer = setTimeout(frame, Math.max(0, every - (performance.now() - t0)));
  }
  frame();
  return { stop, setPace(s) { slow = !!s; },
    stats: () => ({ fps: Math.round(rate * 10) / 10, ms: Math.round(ms * 10) / 10, w: W, h: H, mode, delegate,
      meshFps: mode === "mesh" ? meshFps : 0, worker: !!worker, slow }) };
}
