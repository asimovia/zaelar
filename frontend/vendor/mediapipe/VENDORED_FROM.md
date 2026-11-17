# MediaPipe Tasks Vision (vendored)

- Upstream: npm `@mediapipe/tasks-vision@0.10.35` (2026-04-27), tarball integrity
  `sha512-HOvadwVRE6JC+45nyYhmnywnr5h/J8KZvOeUNVOG9q/0875pZgItznFB9bRTvLc264YSJqiZ1NsIpCStJw/egg==`, Apache-2.0
  (`LICENSE` in this folder, from `google-ai-edge/mediapipe` at tag `v0.10.35`, kept verbatim). The model
  `face_landmarker.task` is Google's float16 bundle (`storage.googleapis.com/mediapipe-models/face_landmarker/
  face_landmarker/float16/1/face_landmarker.task`: face detector + 478-point mesh + the 52-blendshape model), Apache-2.0.
  The Apache licence covers these files only; the rest of the engine is under its own licence.
- What it is: an on-device face landmarker that returns, per frame, the face's 478 points and 52 expression
  coefficients (smile, blink per eye, jaw open, brows, tongue…). It runs in the page (WebAssembly, CPU or WebGL); no
  image or number leaves the device.
- Why this version (checked 2026-11-17): it has **no telemetry**. From 1.0 the bundle carries a logger that POSTs usage
  to a Google endpoint every minute; 0.10.35, the last 0.10 release, has no network code of its own (it fetches only the
  paths it is given). The
  test `tests/browser/unit/presence/test_the_face_answers_you.py` fails if a vendored file names a logging endpoint.
- Files and SHA-256 (checked by the loader, `frontend/app/presence/humanity/landmarker.js`, before anything runs):
  - `vision_bundle.mjs` — 55d7ab624fbb70dcc5adc4ae6d7ea9cfcb569139d3dbfbf2b1deafcb966bc0fe (upstream, unchanged)
  - `vision_wasm_internal.js` — e7fd9858e8e8f221d9b96eddc11f8e077f263e0b7bbd79d3cbe882b134274f8c (upstream `wasm/`, unchanged)
  - `vision_wasm_internal.wasm.gz` — the upstream `wasm/vision_wasm_internal.wasm` (SIMD build, 11,153,617 bytes,
    6a5c64584c2ab61c763b6e204afbdbc7ce1caf7f5216187322bca8df94f646bc) compressed with `gzip -9 -n`
    (6b6902aa01bbf06cc523ddc403cbbe5199e61b75487598f306c1fd919183913e). **The only local change**: the raw binary is
    over the public repository's 5 MB file limit, so it ships compressed and the loader inflates it in the browser
    (`DecompressionStream`) and checks the hash of the INFLATED bytes against the upstream one above.
  - `face_landmarker.task` — 64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff (unchanged)
- Not vendored: the no-SIMD and ES-module variants of the runtime (every browser that runs the engine has WASM SIMD),
  and the hand / gesture models (8.4 and 7.8 MB, over the file limit — `humanity/hands.js` is a declared stub).
- Used by `frontend/app/presence/humanity/` (V2-928 T12, «the face answers you»), loaded lazily: only while the camera
  switch is on and the camera is running.
