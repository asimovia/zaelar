# talking-avatar (vendored)

- Upstream: https://github.com/InterviewFlowAI/talking-avatar (npm `@interviewflowai/talking-avatar`), MIT — see `LICENSE`
  in this folder, kept verbatim. The MIT licence covers these files only; the rest of the engine is under its own licence.
- What is used: the audio → viseme model (`visemeModel.js`, `viseme-model.bin`), its streaming detector and resampler, and
  the JALI-style coarticulation that turns the viseme timeline into mouth weights.
- Local changes are marked `ZAELAR CHANGE` in `TalkingAvatar.js`:
  - the model is served from this folder (nothing is fetched from a CDN);
  - the renderer is injected (the engine draws its own non-human faces, upstream's 3D human head is not used);
  - `observeStream()` only LISTENS to a stream the page already plays — it never plays audio itself;
  - `unlock()` resumes the audio context from a user gesture.
- Used by `frontend/app/presence/` (V2-928).
