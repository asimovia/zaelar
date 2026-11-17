# picojs (vendored)

- Upstream: https://github.com/nenadmarkus/picojs at `afffa50ec4134a47005f2cbf8112eaa69f65f37e` (`pico.js`, MIT — its
  header and readme) and the face cascade `facefinder` (kept as `facefinder.bin`) from https://github.com/nenadmarkus/pico at
  `7d550c78b2c31a4e1dfc5bcdfe9da013297b5cc8` (`rnt/cascades/facefinder`, MIT — `LICENSE` in this folder, kept
  verbatim). The MIT licence covers these files only; the rest of the engine is under its own licence.
- SHA-256 of the upstream files: `pico.js` 785b981cc79e5fa3f7557dc3fa7773629d7529994d7627de41b77d8687649309 (before the
  changes below), `facefinder` d8014993e7298c7b1865d1f8b855d6dbf4ec5c808bf879e2091ab6837abf90cd (unchanged).
- What it is: a pixel-intensity-comparison face detector (Markuš et al.) — ~200 lines of plain JavaScript and a 234 KB
  cascade. No WASM, no GPU, no model server: it runs in the page on a small grey frame, so no image leaves the device.
- Why this one: the lightest detector that holds 10–15 fps on a phone. MediaPipe's face detector was measured too:
  its WASM runtime is 9.5–13.5 MB per file, over the public repository's 5 MB file limit.
- Local changes are marked `ZAELAR CHANGE` in `pico.js`: an ES module with a default export (upstream assigns a
  global), and `let i` in `instantiate_detection_memory` (upstream leaks a global, an error in strict mode).
- Used by `frontend/app/presence/look-camera.js` (V2-928 T10, «look at me»).
