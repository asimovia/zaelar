/*
 * frontend/app/core/preboot.js — the cold-start narration of the ONE loader, for BOTH shells (V2-558, V2-881).
 *
 * WHY IT EXISTS. On a cold-started instance the ES modules take tens of seconds, and before this a person stared at
 * a spinner that said nothing ("El usuario se puede impacientar"). The loader itself is the neurons
 * (`components/BootOverlay.js` + `boot-anim.js`); this classic script runs on the inline `#preboot` — the first
 * ring of those neurons, painted by the HTML — BEFORE any module exists, and BootOverlay later takes over the very
 * same element. One screen, never three (V2-881: it used to be a spinner, then «Starting up zaelar…», then the mesh).
 *
 * THE HONESTY RULE, because this is exactly where a progress UI lies. This engine's own prompt rules forbid
 * inventing a step ("inventar un paso es MENTIR sobre lo único que el operador no puede comprobar"), and a boot
 * screen is the same problem wearing a different hat. So:
 *
 *   · every line is PRESENT PARTICIPLE — "starting the engine", never "engine started". It narrates what this
 *     phase involves; it never claims a step completed, and nothing here ever draws a checkmark.
 *   · the STAGE (`data-stage`, which the neurons grow from) comes from a real signal — here `/healthz` answering —
 *     never from a timer. Only `store.bootReady` completes the growth (BootOverlay).
 *   · past the expected window it stops narrating and starts reporting: the real elapsed seconds, and that this
 *     is longer than usual. An honest "this is slow" keeps more people than a confident fiction.
 *
 * It never FETCHES `/api/i18n/bundle`, and that is deliberate: the bundle needs a session AND the engine to be up,
 * which is the very thing being waited for. That circularity is what made the cold start show raw keys like
 * `boot.encendiendo`. It reads the bundle the last visit cached instead, with an English floor inline.
 *
 * Loaded as a CLASSIC script (not a module) from both shells so there is ONE definition. Its CSS lives in
 * `core/shared-surfaces.css`, a render-blocking stylesheet both shells load in <head>, so the ring paints on the
 * same first frame as before.
 */
(function () {
  "use strict";

  var host = document.getElementById("preboot");
  if (!host) return;

  // THE INSTANCE'S LANGUAGE, never the browser's. `hb_lang` and `hb_i18n_<code>` are the mirror `core/i18n.js`
  // keeps of the engine's active language and its bundle, so a reload speaks what the agent speaks — Chinese
  // included — before a single request. With no mirror yet (the very first visit) it is English.
  // The English floor below must equal `preboot.*` in i18n/genesis/en/ui.json (test_the_boot_speaks_the_instance_language).
  var FLOOR = {
    "preboot.wake.title": "Waking up your agent",
    "preboot.boot.title": "Getting your agent ready",
    "preboot.slow": "This is taking longer than usual · {s}s",
    "preboot.ready": "Ready",
    "preboot.wake.1": "Reaching your machine",
    "preboot.wake.2": "Reserving its CPU and memory",
    "preboot.wake.3": "Mounting your private volume",
    "preboot.wake.4": "Starting the engine",
    "preboot.boot.1": "Loading the interface",
    "preboot.boot.2": "Connecting to the engine",
    "preboot.boot.3": "Opening your session",
    "preboot.boot.4": "Preparing the voice stack",
    "preboot.boot.5": "Loading the card catalogue",
    "preboot.boot.6": "Connecting to the models",
    "preboot.boot.7": "Opening your memory",
    "preboot.boot.8": "Restoring your desktop",
    "preboot.boot.9": "Recovering your conversations",
    "preboot.boot.10": "Checking your energy",
    "preboot.boot.11": "Reviewing your agenda",
    "preboot.boot.12": "Almost there"
  };
  var DICT = {};
  try {
    var code = localStorage.getItem("hb_lang") || "en";
    DICT = JSON.parse(localStorage.getItem("hb_i18n_" + code) || "{}") || {};
  } catch (_) { DICT = {}; }
  function tr(key) { return DICT[key] || FLOOR[key]; }
  function list(prefix, n) { var out = []; for (var i = 1; i <= n; i++) out.push(tr(prefix + i)); return out; }

  // `wake` only appears when the engine is not answering yet — on a warm reload it never shows.
  var PHASES = {
    wake: { title: tr("preboot.wake.title"), steps: list("preboot.wake.", 4) },
    boot: { title: tr("preboot.boot.title"), steps: list("preboot.boot.", 12) },
  };
  var EXPECTED_MS = 35000;   // what a genuinely cold-started instance takes to become usable, as measured
  var STEP_MS = 2200;

  var started = Date.now(), phase = "boot", stepAt = 0, done = false;
  var cap = document.createElement("div");
  cap.className = "pb-cap";
  var title = document.createElement("p");
  title.className = "pb-title";
  var step = document.createElement("p");
  step.className = "pb-step";
  var slow = document.createElement("p");
  slow.className = "pb-slow";
  cap.appendChild(title); cap.appendChild(step); cap.appendChild(slow);
  host.appendChild(cap);
  if (!host.getAttribute("data-stage")) host.setAttribute("data-stage", "0");

  function setStep(text) {
    if (step.textContent === text) return;
    step.classList.add("swap");
    setTimeout(function () { step.textContent = text; step.classList.remove("swap"); }, 280);
  }

  function tick() {
    if (done) return;
    var elapsed = Date.now() - started, p = PHASES[phase];
    title.textContent = p.title;
    if (elapsed - stepAt >= STEP_MS || !step.textContent) {
      stepAt = elapsed;
      // The last line holds instead of looping: cycling back to "loading the interface" after a minute tells
      // the user the thing restarted, which is worse than saying nothing.
      setStep(p.steps[Math.min(Math.floor(elapsed / STEP_MS), p.steps.length - 1)]);
    }
    if (elapsed > EXPECTED_MS) slow.textContent = tr("preboot.slow").replace("{s}", String(Math.round(elapsed / 1000)));
    setTimeout(tick, 250);
  }

  // ── the real signal ──────────────────────────────────────────────────────────────────────────────────────
  // If the engine's liveness probe does not answer promptly we are on an instance that is still coming up, and
  // the narration switches to the wake-up story. `/healthz` is public and says nothing about anyone's data, which
  // is why it can be asked before a session exists (server/pages.py). Its answer is the loader's first step.
  var probe = setTimeout(function () { phase = "wake"; }, 1200);
  try {
    fetch("/healthz", { cache: "no-store" })
      .then(function (r) {
        if (!r.ok) return;
        clearTimeout(probe); phase = "boot";
        if (Number(host.getAttribute("data-stage")) < 1) host.setAttribute("data-stage", "1");
      })
      .catch(function () { phase = "wake"; });
  } catch (_) { /* a probe that cannot run must not stop the narration */ }

  // BootOverlay calls this on `store.bootReady`: the narration stops and says so while the neurons burst.
  window.__zaelarBoot = {
    finish: function () {
      if (done) return;
      done = true;
      setStep(tr("preboot.ready"));
      slow.textContent = "";
    }
  };

  tick();
})();
