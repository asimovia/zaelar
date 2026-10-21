/*
 * frontend/app/core/preboot.js — the boot narration, for BOTH shells (V2-558).
 *
 * WHY IT EXISTS. The splash was a spinning ring and one fixed sentence, "Starting up zaelar…", held until
 * `main.js` finished loading. On a cold account Machine that is tens of seconds, and the operator measured the
 * result on his own first run: over a minute of a spinner that says nothing, on the very first impression the
 * product ever makes. "El usuario se puede impacientar" — and an unattended spinner is indistinguishable from a
 * hang, so the reasonable thing for a person to do is close the tab.
 *
 * THE HONESTY RULE, because this is exactly where a progress UI lies. This engine's own prompt rules forbid
 * inventing a step ("inventar un paso es MENTIR sobre lo único que el operador no puede comprobar"), and a boot
 * screen is the same problem wearing a different hat. So:
 *
 *   · every line is PRESENT PARTICIPLE — "starting the engine", never "engine started". It narrates what this
 *     phase involves; it never claims a step completed, and nothing here ever draws a checkmark.
 *   · the PHASE comes from a real signal (`/healthz`, and `main.js` announcing itself), not from a timer.
 *   · the ring is elapsed-vs-expected and CANNOT reach 100% on its own — it eases toward 92% and stops there.
 *     A bar that sits full while nothing happens is the most-told lie in software.
 *   · past the expected window it stops narrating and starts reporting: the real elapsed seconds, and that this
 *     is longer than usual. An honest "this is slow" keeps more people than a confident fiction.
 *
 * It never FETCHES `/api/i18n/bundle`, and that is deliberate: the bundle needs a session AND the engine to be up,
 * which is the very thing being waited for. That circularity is what made the cold start show raw keys like
 * `boot.encendiendo` (INI-024's known blemish). It reads the bundle the last visit cached instead, with an
 * English floor inline.
 *
 * Loaded as a CLASSIC script (not a module) from both shells so there is ONE definition. Safe because by the
 * time this runs the engine has already served the HTML from the same origin — a Machine that has not woken at
 * all never gets this far; that case is the edge's own recovery page (web/functions/_middleware.js).
 */
(function () {
  "use strict";

  var host = document.getElementById("preboot");
  if (!host) return;

  // THE INSTANCE'S LANGUAGE, never the browser's. `hb_lang` and `hb_i18n_<code>` are the mirror `core/i18n.js`
  // keeps of the engine's active language and its bundle, so a reload speaks what the agent speaks — Chinese
  // included — before a single request. It used to read `navigator.language`: an English instance in a Spanish
  // browser booted in Spanish. With no mirror yet (the very first visit) it is English, the product's default.
  // The English floor below must equal `preboot.*` in i18n/bundles/en.json (test_the_boot_speaks_the_instance_language).
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

  // The phases, in the order a boot actually goes through them. `wake` only appears when the engine is not
  // answering yet — on a warm reload it never shows, which is why the warm path stays quiet and quick.
  var PHASES = {
    wake: { title: tr("preboot.wake.title"), steps: list("preboot.wake.", 4) },
    boot: { title: tr("preboot.boot.title"), steps: list("preboot.boot.", 12) },
  };

  // ~35 s is what a genuinely cold Machine takes to become usable, measured on this deployment. The ring is
  // shaped around that, not around a guess, and it does NOT finish when the clock does — see EASE below.
  var EXPECTED_MS = 35000;
  var STEP_MS = 2200;
  var CAP = 0.92;

  var started = Date.now();
  var phase = "boot";
  var stepAt = 0;
  var done = false;

  // ── the ring: an OUTER progress arc around the spinner that is already there (operator ask) ──────────────
  var R = 34, C = 2 * Math.PI * R;
  var wrap = document.createElement("div");
  wrap.className = "pb-wrap";
  wrap.innerHTML =
    '<svg class="pb-arc" viewBox="0 0 80 80" aria-hidden="true">' +
    '<circle cx="40" cy="40" r="' + R + '" class="pb-track"/>' +
    '<circle cx="40" cy="40" r="' + R + '" class="pb-fill" stroke-dasharray="' + C + '" stroke-dashoffset="' + C + '"/>' +
    "</svg>";

  var style = document.createElement("style");
  style.textContent =
    "#preboot .pb-wrap{position:relative;width:80px;height:80px;display:flex;align-items:center;justify-content:center}" +
    "#preboot .pb-arc{position:absolute;inset:0;width:80px;height:80px;transform:rotate(-90deg)}" +
    "#preboot .pb-arc circle{fill:none;stroke-width:3;stroke-linecap:round}" +
    "#preboot .pb-track{stroke:rgba(230,232,238,.12)}" +
    "#preboot .pb-fill{stroke:#10b981;transition:stroke-dashoffset .6s cubic-bezier(.22,.61,.36,1)}" +
    "#preboot .ring{width:46px;height:46px}" +
    "#preboot .pb-title{font-weight:650;opacity:.95;margin:0}" +
    /* The step line is the only thing that moves every couple of seconds, so it gets the fade — a label that
       swaps abruptly reads as a glitch, and on a slow boot the user sees this happen fifteen times. */
    "#preboot .pb-step{opacity:.62;font-size:13.5px;margin:0;transition:opacity .28s;min-height:1.3em;text-align:center;padding:0 24px}" +
    "#preboot .pb-step.swap{opacity:0}" +
    "#preboot .pb-slow{opacity:.5;font-size:12px;margin:0}" +
    "@media (prefers-reduced-motion: reduce){#preboot .ring{animation:none}#preboot .pb-fill{transition:none}}";
  document.head.appendChild(style);

  var oldRing = host.querySelector(".ring");
  var lbl = host.querySelector(".lbl");
  if (oldRing) { wrap.appendChild(oldRing); host.insertBefore(wrap, lbl || null); }

  var title = document.createElement("p");
  title.className = "pb-title";
  var step = document.createElement("p");
  step.className = "pb-step";
  var slow = document.createElement("p");
  slow.className = "pb-slow";
  if (lbl) { lbl.replaceWith(title); } else { host.appendChild(title); }
  host.appendChild(step);
  host.appendChild(slow);

  var arc = wrap.querySelector(".pb-fill");
  function paintRing(p) { if (arc) arc.setAttribute("stroke-dashoffset", String(C * (1 - p))); }

  function setStep(text) {
    if (step.textContent === text) return;
    step.classList.add("swap");
    setTimeout(function () { step.textContent = text; step.classList.remove("swap"); }, 280);
  }

  function tick() {
    if (done) return;
    var elapsed = Date.now() - started;
    var p = PHASES[phase];
    title.textContent = p.title;

    // EASE: asymptotic, so it slows as it goes and never arrives by itself. Only `finish()` closes it.
    var eased = 1 - Math.exp(-elapsed / (EXPECTED_MS / 2.2));
    paintRing(Math.min(CAP, eased * CAP));

    if (elapsed - stepAt >= STEP_MS) {
      stepAt = elapsed;
      var i = Math.floor(elapsed / STEP_MS);
      // The last line holds instead of looping: cycling back to "loading the interface" after a minute tells
      // the user the thing restarted, which is worse than saying nothing.
      setStep(p.steps[Math.min(i, p.steps.length - 1)]);
    }

    if (elapsed > EXPECTED_MS) {
      var s = Math.round(elapsed / 1000);
      slow.textContent = tr("preboot.slow").replace("{s}", String(s));
    }
    setTimeout(tick, 250);
  }

  // ── the real signal ──────────────────────────────────────────────────────────────────────────────────────
  // If the engine's liveness probe does not answer promptly we are on a Machine that is still coming up, and
  // the narration switches to the wake-up story the operator asked for. `/healthz` is public and says nothing
  // about anyone's data, which is why it can be asked before a session exists (server/pages.py).
  var probe = setTimeout(function () { phase = "wake"; }, 1200);
  try {
    fetch("/healthz", { cache: "no-store" })
      .then(function (r) { if (r.ok) { clearTimeout(probe); phase = "boot"; } })
      .catch(function () { phase = "wake"; });
  } catch (_) { /* a probe that cannot run must not stop the narration */ }

  // `main.js` calls this the moment the app is up; it is also what removes the splash, so the ring completing
  // is the LAST thing seen rather than a claim made on its behalf.
  window.__zaelarPrebootDone = function () {
    if (done) return;
    done = true;
    paintRing(1);
    setStep(tr("preboot.ready"));
    slow.textContent = "";
  };

  tick();
})();
