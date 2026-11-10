# mobile-app — the native companion (V2-870)

A Capacitor 7 iOS app that is **one full-screen WKWebView showing the engine's own `/m` shell**
(`frontend/mobile/`, V2-124). There is no second mobile UI: the shell's bar (orb in the centre) is the whole UI.
Android will live in this same project later (`npx cap add android`); it is not added yet.

- App id: `com.zaelar.app` (fixed forever — changing it breaks updates and deep links). Name: Zaelar.
- Minimum iOS: 16. Dependencies: Swift Package Manager (`ios/App/CapApp-SPM`), no CocoaPods.

## What is native and what is not

| Native (Swift / project settings) | Web (the engine's `/m` shell, unchanged) |
|---|---|
| `AVAudioSession` `playAndRecord` + `voiceChat`, speaker by default, Bluetooth allowed; set at launch and again on foreground (`AppDelegate.swift`) | Everything you see and touch: dock, orb, deck, sheets, chat |
| Permission sentences for microphone and camera (EN + ES `InfoPlist.strings`); iOS asks on the first `getUserMedia`, never at launch | Voice v1: the LiveKit WebRTC client inside the WebView, foreground only |
| Light status bar over a dark background; portrait on iPhone | Safe-area layout (`viewport-fit=cover` + `env(safe-area-inset-*)`) |
| A bundled page (`www/index.html`) shown only when the origin cannot be loaded, with a retry button | Sign-in, session, i18n strings — all served by the engine |

Capacitor's own WebView setup already provides what in-WebView voice needs: inline media playback, no user gesture
required for playback, the WebView's scroll bounce turned off. `capacitor.config.ts` adds `contentInset: never`,
the dark background, and `limitsNavigationsToAppBoundDomains: false`.

## Which engine it opens

The WebView loads `<origin>/m` directly. The shell calls **relative** `/api/...` URLs and imports modules shared
with the desktop app, so loading it from the engine's own origin keeps everything working with no change to
`frontend/mobile/`. Bundling a copy of the shell inside the app is deferred: a bundled copy would be a second
origin with no API behind it, and needs an API-base seam in the shell first (V2-870 §1).

The origin is a **build-time** setting, read by `cap sync` from the environment:

```bash
npm install
ZAELAR_ORIGIN=http://localhost:43917 npm run sync   # the default when unset: a self-hosted engine on this Mac
ZAELAR_ORIGIN=https://engine.example.org npm run sync
```

- A plain `http://` origin turns on `server.cleartext` (local/LAN engines); an `https://` origin does not.
- If the origin's sign-in page lives on another host, list it so the WebView follows it in-page instead of handing
  it to Safari: `ZAELAR_ALLOW_NAVIGATION="auth.example.org" ZAELAR_ORIGIN=... npm run sync`.
- Switching servers at runtime («my server» inside the app) is a follow-up; today it means a re-sync and rebuild.

## Run in the simulator against a local engine

Needs full Xcode (Command Line Tools alone have no `simctl`) with an iOS simulator runtime, and Node ≥ 20.

```bash
cd mobile-app
npm install
npm run sync        # ZAELAR_ORIGIN defaults to http://localhost:43917
npm run ios:run     # pick a simulator; or: npx cap run ios --target <udid>
```

The simulator shares the Mac's network, so `localhost:43917` is the engine running on the Mac. A self-hosted engine
treats the simulator's WebView like any other local browser: the shell mints its UI cookie on the first `GET /m`.

`npm run ios:open` opens the project in Xcode (signing, a real device, the debugger). Without the Capacitor CLI:

```bash
xcodebuild -project ios/App/App.xcodeproj -scheme App -sdk iphonesimulator \
  -destination 'generic/platform=iOS Simulator' -derivedDataPath ios/DerivedData build
xcrun simctl install booted ios/DerivedData/Build/Products/Debug-iphonesimulator/App.app
xcrun simctl launch booted com.zaelar.app
```

## A real iPhone and a local engine

A phone cannot reach the Mac's `localhost`. Use the Mac's LAN address (`ZAELAR_ORIGIN=http://192.168.x.y:43917`)
and make sure the engine listens on that interface; iOS asks once for local-network access.

## Session

The WKWebView keeps the origin's cookies in the app's persistent data store, so a session cookie with an expiry
survives killing and relaunching the app. A cookie without an expiry (a per-boot or browser-session cookie) does
not: on relaunch the shell obtains a new one the way a fresh browser tab would. The app adds no login screen of its
own; whatever the origin does for an unauthenticated `/m` (a redirect to its sign-in page) happens in-page.

## Not here yet

Background voice, native push, the share target, deep links and App Intents (V2-870 §2–§6), runtime server
switching, app icons and launch artwork, Android.

## Generated (not tracked)

`node_modules/`, `package-lock.json` (`package.json` pins exact versions instead), `www/origin.js` (written by `capacitor.config.ts` at sync), `ios/App/App/public/`,
`ios/App/App/capacitor.config.json`, `ios/App/App/config.xml`, `ios/capacitor-cordova-ios-plugins/`, build
outputs and `DerivedData/`.
