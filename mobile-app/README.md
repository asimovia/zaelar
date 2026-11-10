# mobile-app — the native companion (V2-870)

A Capacitor 7 app that is **one full-screen WebView showing the engine's own `/m` shell** (`frontend/mobile/`,
V2-124). There is no second UI: the shell's bar (orb in the centre) is the whole UI, and this project only lends it
the device's hands. Where it sits among the other surfaces: `.meshkore/docs/architecture/zaelar-surfaces.md`.

```
mobile-app/
├─ ios/       iPhone (first) — iPad later in the same target
├─ android/   Android, added later in this same project with `npx cap add android` — not yet
├─ www/       the app's own glue (`in-app.js`) and the page shown when the engine cannot be reached — never a copy of the shell
└─ scripts/   version, icons, simulator, device, archive, upload
```

iPad: 1.0 ships iPhone-only (`TARGETED_DEVICE_FAMILY = 1`, the only place that says so); iPad joins later in the same
target (device family `1,2`), with the shell it gets (`/m` or the desktop `/`) still to be decided.

- App id: `com.zaelar.app` (fixed forever — changing it breaks updates and deep links). Name: Zaelar.
- Minimum iOS: 16. Dependencies: Swift Package Manager (`ios/App/CapApp-SPM`), no CocoaPods.

## What is native and what is not

| Native (the app) | Web (the engine's `/m` shell) |
|---|---|
| `AVAudioSession` `playAndRecord` + `voiceChat`, speaker by default, Bluetooth allowed; set at launch and on every foreground (`AppDelegate.swift`) | Everything you see and touch: dock, orb, deck, sheets, chat |
| Plugins: Keyboard (`resize: native`, dark keys, no form accessory bar), Haptics, App, Geolocation | Voice v1: the LiveKit WebRTC client inside the WebView, foreground only |
| Permission sentences (EN + ES `InfoPlist.strings`) for microphone and location; iOS asks on first use, never at launch (no camera: nothing uses it) | Safe-area layout (`viewport-fit=cover` + `env(safe-area-inset-*)`) |
| `www/in-app.js`, the app's glue (below); light status bar; portrait on iPhone | Sign-in, session, i18n strings — all served by the engine |
| `www/index.html`, shown only when the origin cannot be loaded, with a retry button | |

Capacitor's own WebView setup already provides what in-WebView voice needs: inline media playback, no user gesture
required for playback, no scroll bounce, and microphone/motion permission granted to the page (the system asks the
user once, for the app). `capacitor.config.ts` adds `contentInset: never`, the dark background and
`limitsNavigationsToAppBoundDomains: false`.

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

## On a real iPhone

```bash
ZAELAR_ORIGIN=https://engine.example.org ZAELAR_ALLOW_NAVIGATION=signin.example.org \
  TEAM=<team id> npm run ios:device          # builds, installs and launches on the connected phone
```

`scripts/ios-device.sh` signs with the team in `TEAM` (Xcode › Settings › Accounts; a free personal team works, its
builds expire after 7 days), builds for `generic/platform=iOS` (so a phone on a newer iOS than this Xcode still
works), installs with `devicectl` on the first paired iPhone (or the device id given) and leaves the opening to the
icon. A free team's app must be trusted once on the phone: Settings › General › VPN & Device Management. If the team cannot register
`com.zaelar.app`, `BUNDLE_ID=com.zaelar.app.dev` overrides it for that build only (build settings on the command
line; the project keeps `com.zaelar.app`).

Voice needs an **https** origin. A phone reaches a self-hosted engine on the Mac only by its LAN address
(`HOST=0.0.0.0 ./zaelar start`, then `ZAELAR_ORIGIN=http://192.168.x.y:43917`), which shows the screen but has no
voice: a plain-http address is not a secure context, so the WebView gives it no microphone, and a local LiveKit
announces itself on the loopback. Use a hosted engine (or an https tunnel to the Mac) for voice.

## Session

The WKWebView keeps the origin's cookies in the app's persistent data store, so a session cookie with an expiry
survives killing and relaunching the app. A cookie without an expiry (a per-boot or browser-session cookie) does
not: on relaunch the shell obtains a new one the way a fresh browser tab would. The app adds no login screen of its
own; whatever the origin does for an unauthenticated `/m` (a redirect to its sign-in page) happens in-page.

## The app's own glue (`www/in-app.js`)

Injected by `MainViewController.swift` at document start into every main-frame page, so it works with any engine
version and never runs in a browser. It acts only on the configured engine's origin (any other page the WebView
follows in-page is left alone). It hides the shell's top banner (its «add to Home Screen» and browser-notification
offers belong to a browser tab, never to the app), marks `<html class="in-app" data-platform="ios">` — CSS (the shell's
and the website's) adapts without sniffing user agents — and gives a light haptic tick on the dock, the orb and send
buttons. Capacitor also injects its bridge into every page, remote origin included, so the shell can ask
`window.Capacitor.isNativePlatform()` (`services/push.js` uses it: no «add to Home Screen» offer inside the app) and
reach plugins as `window.Capacitor.Plugins.<Name>` — never through an npm import, since the shell is served by the
engine, not bundled. The user agent ends in `ZaelarApp/<version> (ios)`: a hint for the engine, never a credential.

## The screen as a sensor

`frontend/app/services/device.js` is one door for location (one fix or a watch), motion and compass: the native
plugin inside the app, the Web API in a browser, every failure a value. Apps (widgets) reach it as
`await ctx.device()` (contract in `widgets/AGENTS.md`). No widget uses it yet: it is the seam the phone's sensor apps
will be built on, not a feature by itself.

## Measured in the simulator

Xcode 26.6, iPhone 17 Pro simulator (iOS 26.5):

- the shell renders with the dock where a native tab bar sits and a light status bar; the chat is a full screen and,
  with the keyboard up, keeps its header and puts the composer on the keys;
- a typed line reaches the engine and the WebView joins the LiveKit room (WebRTC works in WKWebView);
- a sign-in page on another host renders in-page when listed in `ZAELAR_ALLOW_NAVIGATION`;
- location: the system dialog shows the app's sentence and a fix comes back from the plugin.

Not verifiable in the simulator: the microphone, the audio route and haptics — real-device steps.

## What App Review checks inside the app

The shell behaves differently only where `inNativeApp()` (`frontend/app/core/native.js`) is true:

- **No purchase path** (3.1.3(f)): the out-of-Energy notice and the menu's Energy row open the account page without
  `#buy`, in the system browser (a new window leaves the app), and say «your account», never «top up».
- **A yes before the AI services** (5.1.2(i)): `mobile/app/shell/ai-consent.js` + `AiConsentSheet.js` ask before the
  first turn; until the yes the always-on voice does not start and the orb, the mic/speaker hand-off and the chat send
  open the question instead. The answer is the engine's (`config/v2` section `consent`, written through
  `POST /api/config/v2`), so it survives reloads and reinstalls; Settings can withdraw it (which ends the voice here).
- **Account deletion reachable** (5.1.1(v)): the menu's «Delete account» row opens the account page at `#delete` in
  the system browser. The deletion itself is the account service's, not the engine's.
- **What leaves the phone**: a location fix from `ctx.device()` goes only to the app on screen that asked — no widget
  uses it yet and the engine has no route that receives one, so nothing is posted or stored. The engine writes no
  audio: the only recorder is a debugging tap (`mic_raw.wav`) that runs only with `ZAELAR_RECORD_MIC` set; the STT
  config (`ZAELAR_STT`, `ZAELAR_STT_MODEL*`, `ZAELAR_STT_EOT_*`) has no retention or opt-out key, so each STT
  provider's own default retention applies. Transcripts are text and are kept like any conversation.

## Store readiness

| File | What it carries |
|---|---|
| `ios/App/App/Info.plist` | display name, `ITSAppUsesNonExemptEncryption = false` (HTTPS only), `LSApplicationCategoryType` productivity, `UIRequiresFullScreen`, portrait, the microphone and location sentences (no camera: nothing uses it); versions read from build settings. No `UIBackgroundModes` until background voice. |
| `ios/App/App.xcodeproj` | iPhone only for 1.0 (`TARGETED_DEVICE_FAMILY = 1`; iPad later, same target), iOS 16+, `MARKETING_VERSION`/`CURRENT_PROJECT_VERSION` stamped by `scripts/version.sh` |
| `scripts/version.sh` (run by `npm run sync`) | version = `package.json` `version`; build = the engine's `update/BUILD` (`IOS_BUILD=127.1` for a second upload on the same engine build) |
| `ios/App/App/PrivacyInfo.xcprivacy` | no tracking; the store labels' data types (email, name, precise location, contacts, audio, user content, customer support, search history, user id, product interaction, diagnostics), all linked, for app functionality; required-reason API: UserDefaults (CA92.1) (Capacitor's frameworks ship their own manifests) |
| `ios/App/App/App.entitlements.template` | Associated Domains (`applinks:` + `webcredentials:`) for `ZAELAR_APP_LINKS_HOST`, rendered only for a store build; the host must serve `/.well-known/apple-app-site-association` (not built yet). No push entitlement yet. |
| `scripts/icons.py` (`npm run icons`) | `AppIcon.appiconset` (1024 opaque + iOS 18 dark/tinted) and the launch mark, drawn from `frontend/mobile/icons/generate.py`'s geometry; `--source brand.png` swaps in a designed icon |
| `Base.lproj/LaunchScreen.storyboard` | the dark background with the mark centred, no text |
| `scripts/ios-archive.sh` (`npm run ios:archive`) | `xcodebuild archive` (generic iOS, automatic signing, `-allowProvisioningUpdates`, team `APPLE_TEAM_ID`) + `-exportArchive` (app-store-connect) → `build/ipa/App.ipa` |
| `scripts/ios-upload.sh` (`npm run ios:upload`) | `xcodebuild -exportArchive` with `destination: upload`, authenticated by an App Store Connect API key: `ASC_KEY_ID`, `ASC_ISSUER_ID`, `ASC_KEY_P8` (path to the `.p8`) |

Both store scripts refuse to run without their variables and take `--dry-run` (check inputs, print the commands).
A paid Apple Developer team is required: App Store distribution and Associated Domains are not available to a free
personal team.

**Shipping a TestFlight build, in order:**

1. Paid team in Xcode › Settings › Accounts; the app record `com.zaelar.app` created in App Store Connect.
2. An App Store Connect API key (role App Manager) saved outside the repo; its id, issuer id and `.p8` path in
   `ASC_KEY_ID`, `ASC_ISSUER_ID`, `ASC_KEY_P8`.
3. If the engine build did not move since the last upload: `IOS_BUILD=<build>.<n>`.
4. `APPLE_TEAM_ID=… ZAELAR_ORIGIN=https://… ZAELAR_APP_LINKS_HOST=… ZAELAR_ALLOW_NAVIGATION=… npm run ios:archive`
5. `ASC_KEY_ID=… ASC_ISSUER_ID=… ASC_KEY_P8=… APPLE_TEAM_ID=… npm run ios:upload`
6. In App Store Connect: wait for processing, answer the export-compliance question (already answered by the
   Info.plist key), add internal testers.

## Not here yet

Background voice, native push, the share target, deep links and App Intents (V2-870 §2–§6), runtime server
switching, the apple-app-site-association file on the engine host, Android.

## Generated (not tracked)

`node_modules/`, `package-lock.json` (`package.json` pins exact versions instead), `www/origin.js` (written by
`capacitor.config.ts` at sync), `ios/App/App/public/`, `ios/App/App/capacitor.config.json`, `ios/App/App/config.xml`,
`ios/capacitor-cordova-ios-plugins/`, build outputs and `DerivedData/`.
