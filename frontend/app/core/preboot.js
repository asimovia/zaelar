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
    "preboot.boot.5": "Loading the catalogue",
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

  // ── THE DRAWING, ON ITS OWN THREAD, FROM THE FIRST BYTE ─────────────────────────────────────────────────────────
  // The brain used to start when the module graph had loaded (BootOverlay), seconds later, and on the page's own
  // thread, so it stuttered exactly while the page was busy loading the agent. Here it starts NOW, in a worker, on a
  // canvas handed over to it: it moves at its own pace whatever the page does. BootOverlay finds this controller and
  // drives it (stages, finish); where a browser has no OffscreenCanvas or module workers, nothing is set and
  // BootOverlay draws on the page as before.
  (function () {
    try {
      var c = document.createElement("canvas");
      if (!window.Worker || !c.transferControlToOffscreen) return;
      c.className = "boot-canvas";
      host.insertBefore(c, host.firstChild);
      var rgb = function (name, fb) {
        var v = "";
        try { v = (getComputedStyle(document.documentElement).getPropertyValue(name) || "").trim(); } catch (_) {}
        var m = /^#([0-9a-f]{6})$/i.exec(v || fb) || /^#([0-9a-f]{6})$/i.exec(fb);
        return [0, 2, 4].map(function (i) { return parseInt(m[1].slice(i, i + 2), 16); });
      };
      var size = function () {
        var r = host.getBoundingClientRect();
        return { w: r.width, h: r.height, dpr: Math.min(window.devicePixelRatio || 1, 2) };
      };
      var w = new Worker("/static/app/core/boot-worker.js?v=1", { type: "module" });
      var shown = 0, onDone = null, dead = false;
      var fail = function () {                 // the worker could not run: the page draws it instead (BootOverlay)
        if (dead) return;
        dead = true;
        try { w.terminate(); } catch (_) {}
        try { c.remove(); } catch (_) {}
        host.classList.remove("anim");
        delete window.__zaelarBootAnim;
      };
      w.onerror = fail;
      w.onmessage = function (e) {
        var m = e.data || {};
        if (m.t === "p") {                                               // it draws: the HTML ring steps aside
          shown = m.p; host.classList.add("anim");
          var api = window.__zaelarBootAnim;
          if (api && api.onProgress) api.onProgress(m.p);
        }
        else if (m.t === "done" && onDone) { var f = onDone; onDone = null; f(); }
      };
      var off = c.transferControlToOffscreen();
      w.postMessage({ t: "start", canvas: off, size: size(),
                      reduced: !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches),
                      colors: { accent: rgb("--hb-accent", "#3D6FE0"), accent2: rgb("--hb-accent2", "#8B5CF6"), bg: rgb("--hb-bg", "#0d1622") } }, [off]);
      var onResize = function () { if (!dead) w.postMessage({ t: "size", size: size() }); };
      window.addEventListener("resize", onResize);
      window.__zaelarBootAnim = {
        setStage: function (n) { if (!dead) w.postMessage({ t: "stage", n: n }); },
        finish: function (cb) {
          if (dead) { if (cb) cb(); return; }
          onDone = cb; w.postMessage({ t: "finish" });
          setTimeout(function () { if (onDone) { var f = onDone; onDone = null; f(); } }, 700);   // never waits on a worker that went quiet
        },
        shown: function () { return shown; },
        onProgress: null,
        destroy: function () { dead = true; window.removeEventListener("resize", onResize); try { w.postMessage({ t: "destroy" }); } catch (_) {} },
      };
    } catch (_) { /* no worker, no handover: BootOverlay draws on the page */ }
  })();

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
