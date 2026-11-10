// in-app.js — the app's own glue, injected by the native shell at document start into the main frame of every page
// the WebView loads (iOS: MainViewController.swift, as a WKUserScript). It is part of the APP, not of the engine's
// shell: it works with whatever engine version the app opens, and a browser never runs it.
//
// It acts ONLY on the engine's origin (`ZAELAR_APP_ORIGIN`, the configured server's origin, passed in by the native
// side). Any other page the WebView follows in-page — a sign-in host listed in ZAELAR_ALLOW_NAVIGATION — is left
// exactly as its owner wrote it.
//
//   · marks the page: <html class="in-app" data-platform="ios">, so the shell's CSS can adapt without sniffing user
//     agents and without waiting for a script of its own;
//   · hides the shell's top banner (`.zm-banner`): its offers — «add to Home Screen», «turn on browser
//     notifications» — belong to a browser tab, never to the installed app, whatever engine version serves the shell;
//   · a light haptic tick when a control of the shell's dock, the orb or a send button is pressed.
(function () {
  if (typeof ZAELAR_APP_ORIGIN !== 'string' || location.origin !== ZAELAR_APP_ORIGIN) return;
  var root = document.documentElement;
  root.classList.add('in-app');
  root.setAttribute('data-platform', (window.Capacitor && window.Capacitor.getPlatform && window.Capacitor.getPlatform()) || 'ios');

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
})();
