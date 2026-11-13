# gym — notes

- 2026-11-13 V2-900: created by porting the gym area of an earlier single-user PWA so it works the same inside
  the agent: program choice, my gym (equipment + free-text preferences + age), a VERSIONED plan, today's day from the
  rotation, preview, the GUIDED session (block timer, sets with weight/reps/RIR, rests, beeps, undo/skip/end early/
  finish/abort), alternatives, the calendar, a session's summary (E1/E1.1), an exercise's history, the manual log and the
  muscle-recovery map (the original app's `muscle-state.js` 1:1, `muscles.py`). Not on main until V2-902 (phase I).
- Decisions:
  - The live session lives in data.py (`live`), not in the card: every screen shows the same block and the voice can
    drive it. The timer is an END TIME (`ends_at`, server ms; the card corrects its clock with `now`); any screen reports
    `timer_done` against the cursor it saw and it counts once.
  - `screens: shared`, NO `runtime`: the session reflects data, it produces no sound or picture that competes for the
    speaker (the beeps are 0.2 s cues), and stopping the agent must not end his workout — he ends it. With the agent
    stopped the card does not beep (`ctx.running === false`).
  - ONE screen drives (`claim`): where he tapped Start, or the phone app / a phone browser; a desktop that did not start
    it only reflects (a «Drive from this screen» button takes over). Only that screen reads the strap
    (`ctx.device().activity({sensors:["heart_rate"]})`, never Web Bluetooth), beeps and holds the wake lock
    (`navigator.wakeLock`, released when the card goes away or the session ends). Heart rate reaches data.py every 5 s:
    the rest is extended +30 s once if the heart is > 130 bpm when it ends (the original app's rule), and avg/max are kept on the
    session. The zone is shown only when an age is set (a zone from a guessed age is a reading we do not have).
  - Every model call goes through `coach.ask()` (prompts in `prompts.json`, generalised: no persona, no program name, no
    personal weights). Today it answers `model_unavailable` and the deterministic path works: the program's rotation
    instead of the trainer's plan, the app's own alternatives list, and `log_workout` / `edit_session` with the
    STRUCTURE filled by the agent itself (the agent is already a model — the sentence path only needs the seam for the
    card's own text boxes).
  - Alternatives: the original app's static `EX_ALTERNATIVES` (defined there but unused — it only asked the LLM) is now the first
    source; the model only when the list is exhausted. An alternative keeps its own key (its weights stay its own) and
    `muscle_key` = the program exercise, so the recovery map credits the right muscles.
  - Versioned plan: choosing a program writes a version (reason + full snapshot); a session runs on the SNAPSHOT and
    records its version; the same program again keeps the progress; another opens a new version.
  - Program content is data in EN + ES (`programs/*.json`, `exercises.json`, `alternatives.json`); the original app's personal
    targets (kcal, supplements, target weights) were dropped. Pictures are vendored (`img/`, Unlicense, ~335 KB) and
    copied once into the app's data dir, the only place the engine serves an app's files from.
  - Destructive taps are two-tap inline (no `confirm()` dialog); by voice `abort`/`delete_*` are `confirm: true`.
  - Dates are the person's local dates (the original app used UTC dates).
- Known limits: the calendar shows gym sessions only (rides are the Cycling app's; the hub gathers both in V2-902);
  `set_done` is not `repeatable` (it writes a row) — whether two «done» in a row survive the anti-drag guard is to
  measure live; the heart-rate push re-renders every screen every 5 s while a strap sends; the native app's wake lock
  and beeps with the screen locked are not measured.
