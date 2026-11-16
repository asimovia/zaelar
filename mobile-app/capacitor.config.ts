/**
 * The companion is ONE full-screen WKWebView showing the engine's own `/m` shell, loaded from the engine's origin.
 *
 * Why the origin and not a bundled copy: the shell fetches RELATIVE `/api/...` URLs and imports modules shared with
 * the desktop app, so a copy inside the app would be a second origin with no API behind it. Packaging the shell
 * (V2-870 §1) needs an API-base seam first; until then the WebView simply opens the engine.
 *
 * The origin is chosen at BUILD time (this file is read by `cap sync`, which writes `ios/App/App/capacitor.config.json`
 * and `android/app/src/main/assets/capacitor.config.json`):
 *
 *   ZAELAR_ORIGIN=http://localhost:43917 npx cap sync ios     # default: a self-hosted engine on this Mac
 *   ZAELAR_ORIGIN=https://engine.example.org npx cap sync ios # any other origin
 *
 * Optional: ZAELAR_ALLOW_NAVIGATION="auth.example.org,*.example.org" — extra hosts the WebView may navigate to
 * in-page (e.g. a sign-in page on another host). Any host not listed opens in the system browser instead. The
 * origin's own host is always allowed — every path of it, not only `/m`.
 */
import type { CapacitorConfig } from '@capacitor/cli';
import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const origin = (process.env.ZAELAR_ORIGIN || 'http://localhost:43917').replace(/\/+$/, '');
const url = new URL(origin);
const cleartext = url.protocol === 'http:'; // only a plain-http engine (local/LAN) needs it
// The engine's own host always comes first. `server.url` points at `/m`, and iOS counts as "the app" only URLs that
// start with it: without this entry any other path of the same engine (a sign-in page, a redirect to `/`) would leave
// the app for Safari. Android already keeps the whole host in-app, so the entry changes nothing there.
const allowNavigation = [
  url.host,
  ...(process.env.ZAELAR_ALLOW_NAVIGATION || '')
    .split(',')
    .map((h) => h.trim())
    .filter((h) => h && h !== url.host),
];

// The bundled page (www/index.html) is only shown when the origin cannot be loaded; it needs to know where to retry.
writeFileSync(join(__dirname, 'www', 'origin.js'), `window.ZAELAR_ORIGIN = ${JSON.stringify(origin)};\n`);

const { version } = JSON.parse(readFileSync(join(__dirname, 'package.json'), 'utf8'));

const config: CapacitorConfig = {
  appId: 'com.zaelar.app', // fixed forever: changing it breaks updates and deep links
  appName: 'Zaelar',
  webDir: 'www',
  backgroundColor: '#0a0f16',
  server: {
    url: `${origin}/m`,
    cleartext,
    errorPath: 'index.html',
    allowNavigation,
  },
  ios: {
    contentInset: 'never', // the shell draws under the bars itself (viewport-fit=cover + safe-area insets)
    scrollEnabled: true, // the shell's own scrollers need it; Capacitor already turns the WebView bounce off
    limitsNavigationsToAppBoundDomains: false,
    backgroundColor: '#0a0f16',
    // A hint, never a credential: lets the engine tell the app from a browser (admission stays the session).
    appendUserAgent: `ZaelarApp/${version} (ios)`,
  },
  android: {
    backgroundColor: '#0a0f16',
    // Same hint as iOS: the engine can tell the app from a browser (admission stays the session).
    appendUserAgent: `ZaelarApp/${version} (android)`,
    // WebView debugging (chrome://inspect) follows the build type: on for debug builds, off for the store build.
    // The insets (system bars, cutout, keyboard) are the app's own job: MainActivity.java.
    adjustMarginsForEdgeToEdge: 'disable',
  },
  plugins: {
    // Android: Back is MainActivity's (history, then to the background); the plugin's handler would stop at the start.
    App: { disableBackButtonHandler: true },
    // iOS: the WebView shrinks above the keyboard (no document scroll under the status bar); dark keys; the form
    // accessory bar (‹ › ✓) is hidden by the plugin's default. Android ignores these: MainActivity does the same.
    Keyboard: { resize: 'native', style: 'DARK' },
  },
};

export default config;
