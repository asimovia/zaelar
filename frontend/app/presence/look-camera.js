// look-camera.js — «look at me» (V2-928 T10), the CAMERA: the front camera, read a dozen times a second, and an on-device
// face detector that says where the faces are — the light one (vendored picojs, frontend/vendor/picojs/) at once, and,
// when the face answers you (T12), the vendored MediaPipe Face Landmarker once it has loaded, which also reads his
// expression (humanity/). Nothing leaves the page: no frame, no box, no number is sent to the engine, a model or any
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
// share of its slot; under the last step it is dropped and picojs keeps the gaze (humanity/ then sees presence only).
const MESH_FPS = [10, 7, 5], MESH_BUDGET = 0.45, MESH_STALL_MS = 250;

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

/**
 * Start the camera and the detector. `onFaces(dets, t, faces)` runs per analysed frame: `dets` the face boxes (gaze),
 * `faces` the rich reading (`[{size, shapes, pose}]`, humanity/) once a rich detector runs, else null.
 * `rich` (optional): `() => Promise<{detect(video, t) → {dets, faces}, delegate}>` — the Face Landmarker, loaded after
 * the stream is up; until it is ready, if it fails, or if this device is too slow for it, picojs keeps the gaze.
 * `onMode(mode, why)`: "light" | "mesh" as the detector changes. Resolves to `{stop(), stats()}` — stats:
 * `{fps, ms, w, h, mode, delegate}`. Rejects with an error whose `cameraError()` names the reason.
 */
export async function startCamera({ onFaces, rich = null, onMode = null, fps = 12, width = 240 } = {}) {
  const md = globalThis.navigator && navigator.mediaDevices;
  if (!md || !md.getUserMedia) throw Object.assign(new Error("no camera API (an insecure page?)"), { code: "unsupported" });
  const detect = await createDetector();
  // 640×480 ideal: picojs reads a 240-px copy anyway, and the landmarker needs a face bigger than a thumbnail
  const stream = await md.getUserMedia({ audio: false,
    video: { facingMode: "user", width: { ideal: 640 }, height: { ideal: 480 }, frameRate: { ideal: 15, max: 30 } } });
  let stopped = false, timer = 0, frames = 0, seen = 0, since = performance.now(), rate = 0, ms = 0, W = width, H = 0;
  let mesh = null, meshFps = MESH_FPS[0], meshSeen = 0, mode = "light", delegate = "";
  const stop = () => {
    if (stopped) return; stopped = true; clearTimeout(timer);
    for (const tr of stream.getTracks()) { try { tr.stop(); } catch (_) {} }
    video.srcObject = null;
  };
  const video = document.createElement("video");
  video.muted = true; video.playsInline = true; video.setAttribute("playsinline", ""); video.srcObject = stream;
  try { await video.play(); } catch (e) { stop(); throw e; }
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  const toLight = (why) => { mesh = null; mode = "light"; ms = 0; seen = 0; try { onMode && onMode("light", why); } catch (_) {} };
  if (rich) rich().then((m) => {
    if (stopped || !m) return;
    mesh = m; mode = "mesh"; delegate = m.delegate || ""; ms = 0;
    try { onMode && onMode("mesh", delegate); } catch (_) {}
  }).catch((e) => toLight("failed: " + (e && e.message ? e.message : e)));

  function frame() {
    if (stopped) return;
    const t0 = performance.now();
    if (video.readyState >= 2 && video.videoWidth) {
      let dets, faces = null;
      if (mesh) {
        try { ({ dets, faces } = mesh.detect(video, t0)); } catch (e) { toLight("error"); dets = null; }
      }
      if (!dets) {
        H = Math.round(W * video.videoHeight / video.videoWidth);
        if (canvas.width !== W || canvas.height !== H) { canvas.width = W; canvas.height = H; }
        ctx.drawImage(video, 0, 0, W, H);
        dets = detect(ctx.getImageData(0, 0, W, H).data, W, H);
      }
      const t1 = performance.now();
      ms = ms ? ms * 0.8 + (t1 - t0) * 0.2 : t1 - t0;
      if (mesh) {
        // the landmarker on a busy or slow device: fewer frames first, then back to the light detector for good;
        // one frame that blocks the page (after the first two, which carry the warm-up) drops it at once
        if (++meshSeen > 2 && t1 - t0 > MESH_STALL_MS) toLight("stall");
        else if (meshSeen > 15 && ms > MESH_BUDGET * 1000 / meshFps) {
          const i = MESH_FPS.indexOf(meshFps);
          if (i < MESH_FPS.length - 1) { meshFps = MESH_FPS[i + 1]; meshSeen = 0; } else toLight("slow");
        }
      } else if (++seen > 10 && ms > 600 / fps && W > 160) W = 160;
      // a slow device gets a smaller frame rather than a stuttering face (never below 160 px: faces get too small);
      // the first frames are not judged — they carry the JIT's warm-up
      frames++;
      if (t1 - since >= 1000) { rate = frames * 1000 / (t1 - since); frames = 0; since = t1; }
      try { onFaces && onFaces(dets, t1, faces); } catch (_) {}
    }
    const every = 1000 / (mesh ? meshFps : fps);
    timer = setTimeout(frame, Math.max(0, every - (performance.now() - t0)));
  }
  frame();
  return { stop, stats: () => ({ fps: Math.round(rate * 10) / 10, ms: Math.round(ms * 10) / 10, w: W, h: H, mode, delegate,
    meshFps: mesh ? meshFps : 0 }) };
}
