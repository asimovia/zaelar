// landmarker.js — the vendored MediaPipe Face Landmarker (frontend/vendor/mediapipe/), loaded LAZILY and verified.
// Nothing here runs until the camera switch is on and the camera is live: `loadLandmarker()` is the first and only
// door, called by look-camera.js after its stream started. The runtime ships gzip-compressed (the raw WebAssembly is over
// the public repository's file limit), so it is inflated in the page and its bytes are checked against the upstream
// SHA-256 before it is compiled; the model is checked the same way. A mismatch, a browser without DecompressionStream
// or WebCrypto, or a slow start → the promise rejects and the camera keeps the light detector (picojs) for the gaze.
// The frames go into the landmarker in the page and its numbers go to perceive.js — no image or number is sent.

const BASE = new URL("../../../vendor/mediapipe/", import.meta.url).href;
export const PINS = {
  wasm: "6a5c64584c2ab61c763b6e204afbdbc7ce1caf7f5216187322bca8df94f646bc",    // inflated vision_wasm_internal.wasm
  model: "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff",   // face_landmarker.task
};

async function bytes(name, gz = false) {
  const r = await fetch(BASE + name);
  if (!r.ok) throw new Error(name + " " + r.status);
  if (!gz) return new Uint8Array(await r.arrayBuffer());
  return new Uint8Array(await new Response(r.body.pipeThrough(new DecompressionStream("gzip"))).arrayBuffer());
}
async function checked(buf, pin, what) {
  const d = new Uint8Array(await crypto.subtle.digest("SHA-256", buf));
  const hex = Array.from(d, (b) => b.toString(16).padStart(2, "0")).join("");
  if (hex !== pin) throw new Error(what + " does not match its pinned hash");
  return buf;
}

let _p = null;
/**
 * → the FaceLandmarker (VIDEO mode, blendshapes on), loaded once per page. `delegate`: "CPU" (default) | "GPU".
 * CPU by default, measured 2026-11-17: ≈10 ms a frame with a face (≈2 ms without) at 10 frames a second, steady from the
 * first frame. The GPU path compiles its shaders on the first frame — seconds without a real GPU (a headless browser,
 * a busy or old machine), with the page blocked — and competes with the face's own canvas, for a few ms at best.
 */
export function loadLandmarker({ delegate } = {}) {
  if (_p) return _p;
  _p = (async () => {
    if (typeof DecompressionStream !== "function" || !(globalThis.crypto && crypto.subtle)) throw new Error("no inflate / no hash here");
    const [vision, wasm, model] = await Promise.all([
      import(BASE + "vision_bundle.mjs"),
      bytes("vision_wasm_internal.wasm.gz", true).then((b) => checked(b, PINS.wasm, "the runtime")),
      bytes("face_landmarker.task").then((b) => checked(b, PINS.model, "the model")),
    ]);
    const wasmUrl = URL.createObjectURL(new Blob([wasm], { type: "application/wasm" }));
    const fileset = { wasmLoaderPath: BASE + "vision_wasm_internal.js", wasmBinaryPath: wasmUrl };
    const make = (d) => vision.FaceLandmarker.createFromOptions(fileset, {
      baseOptions: { modelAssetBuffer: model, delegate: d }, runningMode: "VIDEO", numFaces: 2,
      outputFaceBlendshapes: true, outputFacialTransformationMatrixes: false,
      minFaceDetectionConfidence: 0.5, minFacePresenceConfidence: 0.5, minTrackingConfidence: 0.5,
    });
    const want = delegate || "CPU";
    try { return Object.assign(await make(want), { delegate: want }); }
    catch (e) { if (want === "CPU") throw e; return Object.assign(await make("CPU"), { delegate: "CPU" }); }
  })();
  _p.catch(() => { _p = null; });          // a failed load may be tried again by the next camera start
  return _p;
}

/** One landmarker result → `{dets, faces}`: dets in look-camera's shape (gaze), faces with blendshapes + a head pose. */
export function readResult(res, w, h) {
  const out = { dets: [], faces: [] };
  const lms = (res && res.faceLandmarks) || [];
  lms.forEach((pts, i) => {
    let x0 = 1, x1 = 0, y0 = 1, y1 = 0;
    for (const p of pts) { if (p.x < x0) x0 = p.x; if (p.x > x1) x1 = p.x; if (p.y < y0) y0 = p.y; if (p.y > y1) y1 = p.y; }
    // the mesh spans cheek to cheek, a little narrower than picojs's box: scaled so look.js's distance reads the same
    out.dets.push({ x: (x0 + x1) / 2, y: (y0 + y1) / 2, size: (x1 - x0) * 1.12, q: 100, ar: h / w });
    const shapes = {};
    const cats = res.faceBlendshapes && res.faceBlendshapes[i] && res.faceBlendshapes[i].categories;
    if (cats) for (const c of cats) shapes[c.categoryName] = c.score;
    // head pose, as proxies in face widths: the nose tip against the cheeks (yaw) and between forehead and chin (pitch)
    const nose = pts[1], l = pts[234], r = pts[454], top = pts[10], chin = pts[152];
    const pose = nose && l && r && top && chin ? {
      yaw: (nose.x - (l.x + r.x) / 2) / Math.max(1e-3, Math.abs(r.x - l.x)),
      pitch: (nose.y - (top.y + chin.y) / 2) / Math.max(1e-3, Math.abs(chin.y - top.y)),
    } : null;
    out.faces.push({ shapes, pose, size: x1 - x0 });
  });
  return out;
}
