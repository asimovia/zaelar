// in-app.js — the app's own glue, injected by the native shell at document start into the main frame of every page
// the WebView loads (iOS: MainViewController.swift, as a WKUserScript; Android: InAppPlugin.java, as a document-start
// script). It is part of the APP, not of the engine's
// shell: it works with whatever engine version the app opens, and a browser never runs it.
//
// It acts ONLY on the engine's origin (`ZAELAR_APP_ORIGIN`, the configured server's origin, passed in by the native
// side). Any other page the WebView follows in-page — a sign-in host listed in ZAELAR_ALLOW_NAVIGATION — is left
// exactly as its owner wrote it.
//
//   · marks the page: <html class="in-app" data-platform="ios|android">, so the shell's CSS can adapt without sniffing user
//     agents and without waiting for a script of its own;
//   · hides the shell's top banner (`.zm-banner`): its offers — «add to Home Screen», «turn on browser
//     notifications» — belong to a browser tab, never to the installed app, whatever engine version serves the shell;
//   · a light haptic tick when a control of the shell's dock, the orb or a send button is pressed;
//   · `window.ZaelarNative.headMotion` (V2-928 T10): the head's attitude from headphones that report it, so the agent's
//     face can look at the person — `available()` → Promise<boolean>, `start(cb)` → Promise<boolean> with
//     `cb({yaw, pitch, t})` (radians, epoch ms), `stop()` → Promise. iOS only (CMHeadphoneMotionManager, through the
//     device plugin); Android has no such API, so there `available()` is false and `start()` does nothing. The values
//     stay on the phone: the page reads them and never sends them anywhere.
//   · `window.ZaelarNative.audio`: the voice's audio as the phone sees it, iOS and Android (`ZaelarAudio` plugin) —
//     `available()` → Promise<boolean>; `route()` → Promise<{output, name, speakerForced} | null>, output one of
//     speaker · earpiece · bluetooth · headphones · usb · airplay · car · other · none; `setSpeaker(on)` →
//     Promise<route | null> (on: the loudspeaker even when the system would use the earpiece; off: the system's
//     choice again); `onRouteChange(cb)` and `onInterruption(cb)` → Promise<unsubscribe>, cb gets the route with a
//     `reason`, or `{phase: began|ended|reset, shouldResume?, reason?, t}` (a call, Siri, another app). It never sets
//     a LEVEL: the agent's voice level is the page's own (a Web Audio gain on iOS, the element's volume elsewhere),
//     and the system volume is the person's.
(function () {
  if (typeof ZAELAR_APP_ORIGIN !== 'string' || location.origin !== ZAELAR_APP_ORIGIN) return;
  var root = document.documentElement;
  root.classList.add('in-app');
  // The native side may pass its platform (Android does: its script runs before Capacitor's bridge exists); iOS's
  // wrapper passes only the origin, and the bridge is already there.
  var platform = typeof ZAELAR_APP_PLATFORM === 'string' ? ZAELAR_APP_PLATFORM
    : (window.Capacitor && window.Capacitor.getPlatform && window.Capacitor.getPlatform()) || 'ios';
  root.setAttribute('data-platform', platform);

  var style = document.createElement('style');
  style.textContent = 'html.in-app .zm-banner{display:none!important}';
  root.appendChild(style);   // <head> does not exist yet at document start; a <style> under <html> still applies

  var TICK = '.zm-dock button, .zm-orb-btn, .zm-pwr, .zm-send, .zm-sheet-x';
  var haptics = null;
  function tick() {
    try {
      var cap = window.Capacitor;
      if (!cap) return;
      haptics = haptics || (cap.Plugins && cap.Plugins.Haptics) || (cap.registerPlugin && cap.registerPlugin('Haptics'));
      if (haptics) haptics.impact({ style: 'LIGHT' });
    } catch (_) { /* a missing plugin never breaks a tap */ }
  }
  document.addEventListener('pointerdown', function (e) {
    var t = e.target;
    if (t && t.closest && t.closest(TICK)) tick();
  }, { capture: true, passive: true });

  var native = window.ZaelarNative = window.ZaelarNative || {};
  native.headMotion = (function () {
    var listener = null;
    function plugin() {
      if (platform !== 'ios') return null;
      try {
        var cap = window.Capacitor;
        return cap && ((cap.Plugins && cap.Plugins.ZaelarDevice) || (cap.registerPlugin && cap.registerPlugin('ZaelarDevice')));
      } catch (_) { return null; }
    }
    function drop() {
      var l = listener;
      listener = null;
      return Promise.resolve(l && l.then ? l : null).then(function (h) { if (h && h.remove) return h.remove(); });
    }
    function stop() {
      var p = plugin();
      return drop().then(function () { if (p) return p.stopHeadMotion(); }).catch(function () {});
    }
    return {
      available: function () {
        var p = plugin();
        if (!p) return Promise.resolve(false);
        return p.headMotionAvailable().then(function (r) { return !!(r && r.available); }, function () { return false; });
      },
      start: function (cb) {
        var p = plugin();
        if (!p || typeof cb !== 'function') return Promise.resolve(false);
        return drop().then(function () {
          listener = Promise.resolve(p.addListener('headMotion', function (s) {
            if (s && typeof s.yaw === 'number') cb({ yaw: s.yaw, pitch: s.pitch, t: s.t });
          }));
          return listener;
        }).then(function () { return p.startHeadMotion(); })
          .then(function () { return true; }, function () { return stop().then(function () { return false; }); });
      },
      stop: stop,
    };
  })();

  native.audio = (function () {
    function plugin() {
      try {
        var cap = window.Capacitor;
        return cap && ((cap.Plugins && cap.Plugins.ZaelarAudio) || (cap.registerPlugin && cap.registerPlugin('ZaelarAudio')));
      } catch (_) { return null; }
    }
    function call(name, arg) {
      var p = plugin();
      if (!p || typeof p[name] !== 'function') return Promise.resolve(null);
      return Promise.resolve(p[name](arg)).catch(function () { return null; });
    }
    function listen(event, cb) {
      var p = plugin();
      if (!p || typeof cb !== 'function') return Promise.resolve(function () {});
      return Promise.resolve(p.addListener(event, function (d) { try { cb(d || {}); } catch (_) {} }))
        .then(function (h) { return function () { if (h && h.remove) h.remove(); }; }, function () { return function () {}; });
    }
    return {
      available: function () { return call('available').then(function (r) { return !!(r && r.available); }); },
      route: function () { return call('route'); },
      setSpeaker: function (on) { return call('setSpeaker', { on: on !== false }); },
      onRouteChange: function (cb) { return listen('audioRoute', cb); },
      onInterruption: function (cb) { return listen('audioInterruption', cb); },
    };
  })();
})();
