# Zaelar surfaces — one engine, one shell per form factor, the device's hands as thin wrappers

> Mechanism map (2026-11-10). What runs where, which folder owns it, and what is particular to each surface. The
> product side (stores, listings, pricing) is not here. Pair: V2-124 (phone shell), V2-575/V2-869 (daemon),
> V2-870 (native companion), V2-792 (one agent, many screens).

## The rule

The ENGINE is one. The UI is **one shell per FORM FACTOR**, never one per platform or per store:

| Form factor | Shell | Route | Folder |
|---|---|---|---|
| Large screen (laptop, desktop, large tablet in a browser) | the desktop web app: the canvas of cards, the top bar, the orb | `/` | `frontend/app/` |
| Phone (any phone browser, the installed PWA, and INSIDE the native app) | the phone shell: one card at a time, the dock with the orb in the centre, sheets | `/m` | `frontend/mobile/` |

Everything a platform adds — a real browser window, files, a tunnel, push, haptics, the audio session, sensors,
share, Siri — is a **thin wrapper** that lends the shell the device's hands through a seam, and the shell stays
byte-identical for everyone. A wrapper never carries screens of its own (a sign-in page or an offline page at most).

## The folders

```
engine/
├─ frontend/app/        the desktop web app (`/`)                       — any large screen, in a browser
├─ frontend/mobile/     the phone shell (`/m`) + PWA manifest + SW       — phone browser · installed PWA · native app
├─ mobile-app/          the native companion (Capacitor): ONE project, platform folders, no second UI
│   ├─ ios/             iPhone (first) · iPad (same target, device family 1,2 — see "tablets")
│   ├─ android/         phone · Android tablet                           — added with `npx cap add android`, not yet
│   ├─ www/             the app's own glue (`in-app.js`, the offline/retry page) — NEVER a copy of the shell
│   └─ scripts/         sync, simulator, device, archive, upload
├─ daemon/              the desktop app: tray + sign-in window + folders + tunnel + auto-update (macOS, Windows; Linux .pyz)
└─ server/pages.py      serves `/` and `/m`; server/ingress.py admits the shells without a session
```

## The surfaces, one by one

| Surface | What opens it | Shell | Voice | Push / notices | Hands beyond the browser | State |
|---|---|---|---|---|---|---|
| **Desktop browser** (Mac/Windows/Linux) | `my-origin/` or the local engine | `/` | WebRTC in the tab | Web Push + the notice ledger | none (the tab) | shipped |
| **Desktop + daemon** (macOS, Windows) | the tray icon opens the agent signed-in | `/` | same | same | real browser window for sign-ins, read-only folders, egress tunnel, auto-update | shipped (V2-869); signed installers pending |
| **Phone browser** (Safari, Chrome…) | `my-origin/m` | `/m` | WebRTC in the tab, foreground only | Web Push only where the platform allows (Android; iOS only as an installed PWA) | none | shipped (V2-124) |
| **Installed PWA** (Add to Home Screen) | the home-screen icon | `/m` | same | iOS: Web Push once installed | none | shipped |
| **Native companion · iPhone** | the App Store app | `/m` loaded from the engine's origin in a WKWebView | WebRTC inside the WebView, foreground (v1); background voice later (V2-870 §6) | native push later (V2-870 §2) | audio session, haptics, native keyboard, sensors door (`ctx.device()`), share/Siri later | in progress (V2-870 §9) |
| **Native companion · Android** | the Play app, same project | `/m` in the Android WebView | same | FCM later | same plugins | not started |
| **Tablets** | see below | — | — | — | — | decision pending |

### Tablets (iPad, Android tablets, Windows tablets)

A tablet is a large screen with touch. Today it gets the **desktop web app in its browser** (`/`), which is
responsive down to tablet widths, and on Windows the daemon too. Nothing tablet-specific exists, and three facts
decide what should:

1. The phone shell is one card at a time; on an iPad that wastes the screen. The desktop app's canvas is the right
   shape for a tablet, so a native tablet app would wrap `/`, not `/m` — the first surface where the wrapper would
   carry the OTHER shell. The seam that makes that cheap is a per-screen choice of shell at load, by viewport class
   (phone → `/m`, else `/`), which does not exist yet: a phone opening `/` today gets the desktop app.
2. The iOS companion can ship **iPhone-only** first (`TARGETED_DEVICE_FAMILY = 1`) and add iPad later in the same
   target; the App Store then asks for iPad screenshots and the review runs the app on an iPad.
3. Windows tablets are PCs: the desktop app in a browser plus the daemon, no store app (a Microsoft Store listing of
   the daemon is a later distribution question, not a surface).

Pending decisions (private roadmap): iPad in the iOS 1.x line and with which shell; the phone→`/m` choice at load.

## What is particular to each version — the seams

| Seam | Where | Who uses it |
|---|---|---|
| `html.in-app` + `data-platform` at document start | `mobile-app/www/in-app.js` → shell CSS | native companion only |
| `window.Capacitor.isNativePlatform()` | `frontend/app/services/push.js installed()` and friends | hides «add to Home Screen», picks native plugins |
| `ctx.device()` — location, motion, heading; failures as values | `frontend/app/services/device.js` | widgets on any screen; native plugin inside the app, Web API elsewhere |
| `origin_dev` / screens registry | `frontend/app/services/screens.js` (V2-792) | the brain knows which screen asked |
| `POST /api/push/device` with `kind: web|apns|fcm` | `server/notices_api.py` (V2-796, V2-870 §2) | Web Push today; native push later |
| `/api/daemon/*` + the relay | `server/daemon_api.py`, `daemon/` | desktop only; `browser_window.reach()` blocks `phone` |
| The voice lock: one live voice session per engine | `server/livekit_api.py` | every surface; the loser drops to chat + observer |

## Not a surface

A watch, a car screen or a smart speaker would be a new form factor with a new shell; nothing here anticipates them.
