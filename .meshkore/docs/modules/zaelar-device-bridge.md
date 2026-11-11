# Device bridge — the phone as a sensor (V2-890)

The device's sensors reach the engine through **one door**, `frontend/app/services/device.js`, which apps receive as
`ctx.device()` on every host (desktop `widgets/desktop.js`, phone `mobile/app/shell/Deck.js`). Behind the door:

| Where the shell runs | What answers | Background |
|---|---|---|
| Native app (iOS today, Android later) | `ZaelarDevice`, the app's own Capacitor plugin (`mobile-app/ios/App/App/DevicePlugin.swift`), plus the stock Geolocation plugin for one-off reads | yes — an activity keeps reading with the screen locked |
| Any browser (desktop, phone, PWA) | the Web APIs (`navigator.geolocation`, `DeviceMotionEvent`, `DeviceOrientationEvent`) | no — foreground only |

## The door (`ctx.device()`)

| Call | Returns |
|---|---|
| `capabilities()` | `["location","motion","heading"]` present on this screen (sync, V2-870 P2) |
| `details()` | `{platform, form, background_sessions, sensors: {name: {available, permission, …}}, os_version?, app_build?}` |
| `location({precise})` / `watchLocation(onFix)` | one fix / follow while on screen |
| `motion(onReading)` / `heading(onDeg)` | raw accelerometer + gyro / compass, `{stop}` |
| `activity({sensors, label, kind}, onSample)` | `{stop, background}`; `sensors` ⊂ `location · heart_rate · motion_activity · altitude` |
| `heartRateStraps(seconds)` | `{straps:[{id,name}], pick(id)}` |

Every failure is a value (`{error: "denied"|"unavailable"|"unsupported"|"timeout"}`), never a throw.

## The native plugin (`ZaelarDevice`)

- `capabilities()` — hardware present and permission state per sensor, read from CoreLocation, CoreBluetooth,
  CoreMotion and `UIDevice` (`form`: phone/tablet).
- `startSession({sensors, background, activity, label})` / `stopSession()` / `getSession()` — one session at a time.
  Samples go into a native ring buffer (20 000) with a sequence number; while the app is active each is also sent as
  a `sample` event. `drain({after})` returns the samples after a sequence number and forgets the confirmed ones, so
  the door hands every sample over exactly once when the screen comes back.
- **Location**: `allowsBackgroundLocationUpdates` only inside a session, `showsBackgroundLocationIndicator = true`,
  When-In-Use authorization only (never Always); `activityType` fitness or automotive.
- **Heart rate**: the Bluetooth Heart Rate Service (GATT `0x180D`, measurement `0x2A37`; 8/16-bit value, RR intervals
  in ms when sent). Straps and watches in "broadcast heart rate" mode expose it. The chosen strap is remembered;
  a dropped strap is reconnected during the session; CoreBluetooth state restoration keeps it across a relaunch.
  ANT+ has no radio on iPhone and is not supported. No HealthKit.
- **Motion activity** (`CMMotionActivityManager`: walking/running/cycling/driving/stationary + confidence) and
  **altitude** (`CMAltimeter`: relative metres, pressure).
- Info.plist: `NSBluetoothAlwaysUsageDescription`, `NSMotionUsageDescription`, `UIBackgroundModes` =
  `location`, `bluetooth-central` (guarded by `tests/infrastructure/unit/test_the_ios_app_carries_its_store_manifests.py`).

## One contract, every device and platform

The door is the contract; each platform only implements the plugin behind it. What stays the same everywhere:

- **Plugin name and methods**: `ZaelarDevice` with `capabilities · startSession · stopSession · getSession · drain ·
  scanHeartRate · forgetHeartRate`, and the events `sample · session · permission · heart_rate_strap`.
- **Sensor names and sample shapes** (`location`, `heart_rate`, `motion_activity`, `altitude`, …) — a new sensor is
  added to the door, the table in `widgets/AGENTS.md` and every platform's plugin in the same change.
- **`details()`** answers `platform` (`ios` · `android` · `web`) and `form` (`phone` · `tablet` · `desktop`); an app
  adapts to what is `available`, never to a platform name.

| Platform | Plugin | State |
|---|---|---|
| iPhone | `mobile-app/ios/App/App/DevicePlugin.swift` | built (F0) |
| iPad | same Swift target, device family `1,2` (`form: "tablet"`; Wi-Fi iPads report approximate location, some lack a barometer — `available` says so) | the plugin is ready; the target is still iPhone-only (`TARGETED_DEVICE_FAMILY = 1`) |
| Android phone / tablet | `mobile-app/android/` (`npx cap add android`), a Kotlin `DevicePlugin` with the same `jsName`: Fused Location + a foreground service with its notification (Android's equivalent of the blue indicator), BLE GATT `0x180D`, Activity Recognition, the pressure sensor | not started |
| Browser (desktop, phone, PWA) | the Web APIs inside `services/device.js` | foreground location, motion, heading |

## Rules

1. **A generated app never calls a native API.** Only the shell's own code talks to the plugin; the validation gate
   (`widgets/validator_js.py`) refuses `Capacitor`, `navigator.geolocation` and `navigator.bluetooth` in a
   `widget.js`. An app gets values through `ctx.device`.
2. **Nothing starts by itself.** A session starts from the person's tap or request and stops with `stop()`.
3. **Read, never assume.** The generator contract (`widgets/generator.py` `_CONTRACT`, detail in `widgets/AGENTS.md`
   «The screen's sensors») tells the coding agent to call `details()` first and use only what is `available` on the
   screen that renders the app — the same app opens on a desktop, a phone browser and the native app.
4. Storage is the app's: a track the app keeps goes through `ctx.action` into its `data.py`.

## Not built yet

Camera, native push, Live Activity / lock-screen display, background voice, Android build, the engine-side
`activity` app that drives a session by voice, and a per-screen capability line for the voice brain (V2-870 P2b).

Tests: `tests/browser/unit/mobile/test_an_activity_keeps_reading_with_the_screen_locked.py` (node 4.491),
`test_the_screen_is_a_sensor.py` (4.438), the store-manifest guard (4.439).
