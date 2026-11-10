// in-app.js — the app's own glue, injected by the native shell at document start into every page the WebView loads
// (iOS: MainViewController.swift, as a WKUserScript). It is part of the APP, not of the engine's shell: it works with
// whatever engine version the app opens, and a browser never runs it.
//
//   · marks the page: <html class="in-app" data-platform="ios">, so CSS (the shell's and the website's) can adapt
//     without sniffing user agents and without waiting for a script of its own;
//   · a light haptic tick when a control of the shell's dock, the orb or a send button is pressed.
(function () {
  var root = document.documentElement;
  root.classList.add('in-app');
  root.setAttribute('data-platform', (window.Capacitor && window.Capacitor.getPlatform && window.Capacitor.getPlatform()) || 'ios');

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
})();
