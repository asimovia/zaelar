- 2026-11-13 V2-899: created by porting the nutrition area of the operator's previous single-user PWA, to work the
  same inside the agent. Five screens on one card: Today (balance + capture + meals of the day, ‹ day ›), Weight
  (log, 30-day chart, 30-day quality strip, editable history), Coach (photos of a restaurant menu → what to order),
  Evaluation (the week) and Profile (where the targets come from).
- Kept 1:1 (and pinned by tests): targets = Mifflin-St Jeor × 1.55 × goal factor (gain 1+surplus, lose 1−surplus,
  maintain 1), protein = weight × g/kg, a fixed target wins, ≥3 measured burn days replace the formula; logical day
  starts at 03:00; day light = kcal-weighted mean of the 1-5 scores, only with lunch AND dinner (≥4 green, ≥3 yellow);
  day score 0-100 = protein 35 + variety 40 + kcal balance 25, capped under 600 kcal; goal band ±5 % (≥80 kcal);
  meal lifecycle pending → done | failed with retry, refine (appends his words, re-estimates; a time change alone does
  not) and edit by hand (makes it done); the latest weigh-in is the profile weight; a photo with no food fails.
- Deliberate differences from the source: rounding is JavaScript's half-up (`jround`) — Python's `round` is
  half-to-even and moved scores by one; the variety words are WHOLE words (the source's substring table counted
  «agua» inside «aguacate» as water) and the model's own language-free `components` tags win over words; the
  word table lives in `components.json` (ES + EN), never in Python; `sex` added to the profile (female = −161;
  unknown keeps the source's +5, so an old profile gives the same numbers); the evaluation uses the profile's
  targets and goal (the source hardcoded 3200 kcal and «gain muscle»); the menu coach uses the goal-aware targets
  (the source always applied the surplus); lunch/dinner windows are 12-16 / 19-23 LOCAL (the source counted
  11-15 / 18-22 UTC hours of a Madrid user, i.e. the same thing); delete goes to a bin with `restore` (the source
  deleted for good); no in-card Web Speech mic — dictation is the agent's own voice (`log_meal` with his words);
  no live camera stream (`getUserMedia`) — the file input with `capture="environment"` opens the phone camera.
- The model door: every model call (meal estimate, weekly evaluation, menu coach) goes through `data.estimate()`;
  `MODEL_DOOR` is None until phase I (V2-902 I4), so it answers `estimator_unavailable` and the meal is saved for
  him to fill. The prompts are DATA in `prompts.json`, generalised (no persona, no program or brand names, his
  language as `{lang}`), with the JSON shape each answer must have. Nothing here calls a provider or reads a key.
  The estimate runs inside the action (synchronous); the source ran it in the background and the card polled.
- Photos: `ctx.upload` (manifest `"uploads": true`; multipart to `/widgets/nutrition/upload`, 64 MB cap, a generated
  `up_<hex>_<name>` in `store.data_dir`), shrunk on the screen to ~1600 px over 1.5 MB, then the action names the
  file. Never base64 in state.json or in an action (the action route is a JSON body with no size cap of its own).
  A photo leaves the disk only when its meal falls off the bin (20 rows).
- `screens: shared`; `state` reports screen · day (empty = today) · meal · pending; a voice `show` is adopted once
  per order (`view.n`), never over his own tap. No `background` cycle and no `runtime`: it produces nothing.
- Known limits: "today" in `view_data`/`prompt_digest` is the HOST's local clock (the card uses the screen's);
  the day's burn (TDEE from a watch) has no source until the health ledger exists; the vocabulary of components
  covers ES + EN only; the estimate blocks the action while the model answers (phase I decides background or not).
