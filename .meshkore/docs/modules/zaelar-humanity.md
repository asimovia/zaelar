# Humanity — the face answers you (V2-928 T12)

`frontend/app/presence/humanity/` · tests: `tests/browser/unit/presence/test_the_face_answers_you.py` (node 4.574)

## Purpose

The agent has a face (V2-928). With the camera on, the face already looks at the person (T10, `look.js`). Humanity is
the next layer: the face's **body language**. It notices what he does in front of the camera — a smile, a laugh, a wink,
a tongue out, a yawn, a raised brow, a nod, a shake of the head, arriving and leaving — and answers with gestures of its
own: a wink back, a tongue back, a laugh, a brow flash, a sigh.

It is deliberately **not a mirror**. A mirror is a gadget; an answer is a being. The face sometimes lets a gesture go,
tires of the same gesture repeated, gives a yawn mostly nothing, and answers after a human beat rather than on the next
frame. Like a child you raise a hand to: you cannot know in advance what it will do, but it is clearly paying attention.

## Hard rules

- **On the device only.** Zero model, zero API, zero tokens. No frame, image or number leaves the page. The detectors
  run in the browser; their readings go to the pure modules below and are dropped.
- **Nothing loads while the camera switch is off.** `humanity/` is imported by `LookAtMe.js` only when the camera starts;
  the vendored MediaPipe files are fetched only after the camera stream is up.
- **Talking is not a face.** Speech moves the mouth all the time, so mouth readings are muted while he talks (see
  Perception). The agent's own speech keeps its mouth: while it speaks, answers that use the mouth are swapped.

## Mechanism

```
camera (look-camera.js) ──► picojs boxes ─────────────► look.js (gaze, T10)
        │                 └► Face Landmarker (lazy) ──► boxes for the gaze + {shapes, pose} per face
        ▼
humanity/index.js  createHumanity(face, {speech})
   perceive.js     frames → events            (pure, time passed in)
   temperament.js  event → answer | nothing   (pure, seeded RNG)
   expression.js   answer → rig gestures      (face.gesture(name))
   remark.js       the seam to the conversation (OFF)
```

### The detectors (`landmarker.js`, `look-camera.js`)

- **picojs** (T10) runs at once and keeps the gaze; it only says *where* a face is.
- **MediaPipe Face Landmarker** (`frontend/vendor/mediapipe/`, 0.10.35, Apache-2.0) gives 478 points and **52 blendshape
  scores** per face. From the points it derives a box (so it can also drive the gaze) and a head-pose proxy (nose against
  cheeks for yaw, against forehead–chin for pitch).
  - **Pinned and verified.** The runtime ships gzip-compressed, because the raw WebAssembly is over the public
    repository's 5 MB file limit. The loader inflates it with `DecompressionStream`, checks the SHA-256 of the inflated
    bytes and of the model, then hands the runtime to MediaPipe as a blob URL.
  - **No telemetry.** Version 1.x of the package carries a usage logger that POSTs to a Google endpoint; 0.10.35 has none,
    and a test fails if a vendored file names one.
  - **CPU delegate by default.** Measured 2026-11-17 in headless Chromium on the operator's Mac (busy):
    - ≈10.5 ms per frame with a face and ≈2.2 ms without, at 10 frames a second;
    - steady from the first frame;
    - that is about a tenth of one core on the main thread.

    The GPU delegate compiles its shaders on the first frame: 2.7 s per frame on software GL, blocking the page. It
    stays opt-in.
- **Degrading under load.**
  - The landmarker starts at 10 analysed frames a second. While a frame takes more than 45 % of its slot it steps down
    to 7, then 5.
  - Under that, or after one frame that blocks for more than 250 ms, it is dropped for the rest of the camera session and
    picojs keeps the gaze.
  - `window.__zaelarLook.stats()` shows `mode` (`light` | `mesh`), `delegate`, `meshFps`, `ms` and `fps`.
- A landmarker that cannot load (no `DecompressionStream`, a hash mismatch, a blocked file) leaves picojs following.
  Humanity then sees presence only: arrive and leave.

### Perception (`perceive.js`)

Every event must be **held** for a while: a blink is not a wink, a word is not a yawn. It re-arms only after the face
**lets go**, which means staying under 70 % of the event's threshold for 280 ms. A smile that hovers at the line is ONE
smile.

| event | reading (MediaPipe blendshapes) | held |
|---|---|---|
| smile | mean of `mouthSmileLeft/Right` ≥ 0.5 | 300 ms |
| laugh | smile ≥ 0.6 and `jawOpen` ≥ 0.2 | 300 ms |
| wink (side) | one `eyeBlink*` ≥ 0.38, the other ≤ 0.35 (it squints a little), gap ≥ 0.15 | 120–1400 ms |
| tongue | `tongueOut` ≥ 0.3 | 260 ms |
| yawn | `jawOpen` ≥ 0.58, no smile | 1.1 s |
| surprise («oh!») | `jawOpen` ≥ 0.35 and brows ≥ 0.45 | 320 ms |
| brows | `browInnerUp` or the outer brows ≥ 0.5, mouth closed | 220 ms |
| nod / shake | nod: ≥ 2 pitch swings of 0.04; shake: ≥ 3 yaw swings of 0.09 (looking aside or swaying is never a «no») within 1.6 s | — |
| arrive / leave | a face held 0.7 s after 30 s of absence / gone 4 s | — |

**The talking gate:**
- Mouth events (smile, tongue, yawn, surprise) are muted while he talks, for 0.9 s after, and whenever the jaw moved twice in the last 0.6 s (so the first syllables of speech do not slip through before talking is recognised).
- Talking is **heard** (his mic level, from `PresenceLayer.js`) or **seen**: the jaw's flutter, four or more swings of
  0.07 within 1.5 s. Because it can be seen, a muted mic does not let his talking through.
- A laugh is the one mouth event allowed while he makes sound, because laughing is audible, and only with a big smile.

Known limits:
- MediaPipe's own model card calls `tongueOut` limited, so the tongue may rarely fire.
- The blink names follow the ARKit convention (the person's own eye); the wink side was not checked against a live person.
- Thresholds come from MediaPipe's typical ranges. They were checked on fake streams and one public test portrait, not
  yet on the operator.

### Temperament (`temperament.js`)

- **Engagement** (0..1) rises 0.18 with every perceived event and halves every 45 s.
- **Weighted answers** per event, `null` included («let it go»): the weights *are* the character
  (`ANSWERS` in the file). An engaged face lets less go: the `null` weight is multiplied by `1.6 − engagement`.
- **A first gesture is almost always answered** (2026-11-18, the operator: «it follows me, but it does not feel it reacts to me»): the first of its kind in 20 s has its `null` weight × 0.25 — except yawn, leave, brows and nod, which are not invitations. Letting go is for repeats.
- **Cooldowns:**
  - at least 1.2 s between any two answers;
  - the same answer never twice within 5 s.
- **Tiredness:** the same gesture more than three times within 20 s draws from `{sigh, look, nothing}`.
- **The voice's mouth:** while the agent speaks, laugh, giggle and tongue become a smile or a brow flash, and a yawn
  becomes nothing.
- **A human beat:** each answer waits a random 120–380 ms.
- **Seeded:** product runs draw a random seed per camera session, so the same session is consistent and no two are alike.
  Tests pass a seed (`seeded(n)`, mulberry32) and are deterministic.

### Expression (`expression.js`, `rig.js`)

- Answers map to the rig's gestures. Gestures already there: smile, laugh, wink, surprise, tilt, nod, shake, look, sad.
- New with T12: `winkL`, `tongue`, `giggle`, `yawn`, `sigh`, `brows`.
- Composite answers play more than one gesture: `hello` is a brow flash then a smile, `shy` is a look away then a smile.
- A wink back mirrors his eye three times in four.
- **The tongue** is drawn by `face.js drawTongue` over **every** look, classics and parametric, from the shared mouth
  geometry. A parametric face uses its own `spec.mouth.tongue` colour.

## The seam to the conversation (OFF)

**The future step.** After a sustained stretch of visual play, the agent may *say* something in character, based on his
personality in state — for example «you've been making faces at me for forty seconds». A stretch is exchanges with no
pause over 10 s, lasting a random 20–60 s.

**What exists now:**
- `remark.js` builds the stretch's summary: `{seconds, counts, line}`, for example
  `He has been playing with your face for 40 s: smiling (3), winking (1).` It holds counts and seconds only; never an
  image or a frame's numbers.
- It offers that summary **once** per stretch, then waits at least 10 minutes before the next.

**Why it is off:**
- `createHumanity` calls its `offer` only when the per-device switch `localStorage.hb_presence_humanity = {"talk": true}`
  is set by hand.
- `LookAtMe.js` passes no `offer` at all. Today the summary goes nowhere and costs no token.

**To build it:**
1. Wire `offer` to a screen→engine route carrying only the summary.
2. On the engine side, turn the summary into at most one line through the conversation brain, with his personality and
   the current conversation, and never while he is talking.
3. Expose the switch in Settings.
4. Write the privacy note: a summary is derived behaviour data that leaves the device, so it needs its own consent.

## The future

- **Hands:** a raised hand, a wave, a thumbs-up. `hands.js` is a declared stub, and the temperament already answers
  `hand`. Hand and gesture models are each over the file limit (7.8 and 8.4 MB) and would double the per-frame cost.
- **Native sources:**
  - ARKit face tracking (iOS, TrueDepth) gives the same 52 blendshapes, with a working `tongueOut`, at 60 fps on the
    Neural Engine.
  - ML Kit (Android) gives smile and eye-open probabilities.
  - Both would feed `perceive.js` through the same `{shapes, pose}` shape, the way `head-motion.js` feeds `look.js`.
- **Mood from the conversation:** the temperament could take the agent's own state (thinking, idle, a good or bad
  answer) as a bias on its weights.
- **Never:** recognising who the person is, or naming his emotions. It reads *gestures* («he smiles»), never feelings
  («he is happy»).
