# The Local Daemon (`daemon/`)

A small resident process on the user's OWN computer for the two things an engine without his desktop cannot do: read
the folders he grants, and open a real browser window on his screen for a sign-in or a challenge only a person passes.
It is additive: an engine with no daemon behaves exactly as before. Not the shared MeshKore daemon.

Standalone on purpose: the daemon imports nothing from the engine and the engine never imports the daemon (both
directions are guarded by tests). Its dependency set is the standard library, plus Playwright only when a browser
window is wanted. Initiative: V2-575.

## Architecture

```
 engine on the same computer ──loopback HTTP + token──▶ daemon (127.0.0.1:45817)
 engine elsewhere ──HTTPS──▶ relay ◀──WSS, dialled OUT by the daemon── daemon
```

| Folder | What it is |
|---|---|
| `daemon/security/` | WHETHER — the never-served names, the HTTP admission decision (token, Host, no browser origin), throttling. |
| `daemon/fs/` | WHAT — the permission circuit every file operation goes through (list · read · search), read-only. |
| `daemon/http/` | The loopback surface: route table (`routes.py`), handler, life cycle. |
| `daemon/browser/` | The ONE headed sign-in window on a persistent profile. |
| `daemon/relay/` | The OUTBOUND link (P3): config, a stdlib WebSocket client, the link, command dispatch, pairing, session export. |
| `daemon/packaging/` | The single-file builds and the one-line installers. |

State lives under one directory, `config/daemon/` in a source tree or the platform's user-data directory when
installed: `daemon.json` (port, API token, folder allowlist), `audit.jsonl`, `browser/profile/`, and `relay.json`.

## The permission circuit

A fresh install reads nothing: the folder allowlist starts EMPTY and the setup screen proposes Documents. Every file
operation resolves the path, checks it against the allowlist and the never-served names, opens it without following
a symlink, and writes an audit line (allowed or refused). A refusal names the boundary (`code`, a sentence, the
folders that ARE available). The threat model is `.meshkore/docs/security/zaelar-daemon-security.md`.

## The browser window

`/browser/open {task, url, profile?}` opens ONE headed window (a second task's window closes the first);
`/browser/state` answers the page URL and HOW MANY cookies appeared since the window opened — never a name or a
value; `/browser/close`. `browser.auth` is declared only when Playwright and a Chromium are really there. A local engine
may name ITS profile directory so the session lands where its own browser reads it. On the engine,
`nucleo/browser_window.reach()` decides where a window goes — `here` (a graphical server), `daemon` (a connected
daemon declaring `browser.auth`), or nowhere (the process blocks and says why) — and a request from the PHONE never
gets a window: the one it would open is on a computer he is not looking at.

## The relay — a seam

If a relay URL is configured and the daemon has been paired, the daemon dials OUT; otherwise nothing of this runs.

- **URL**: `ZAELAR_DAEMON_RELAY_URL`, else `relay.json`'s `url`, else `build_defaults.json` (`{"relay_url"}`) next to
  the program. https/wss only, except a relay on this machine (tests). The URL is not a secret.
- **Credential**: opaque, stored in `relay.json` (0600, separate from `daemon.json` so forgetting one never touches the
  allowlist). Pairing: `POST <url>/daemon/pair {code, device:{platform, version, hostname_hash}}` →
  `{credential, account_hint, relay_url}`. Doors: `python -m daemon.relay pair CODE` and, in process,
  `daemon.relay.pair.pair_and_connect(code)`.
- **Link**: `WSS <url>/daemon/relay` with `Authorization: Bearer <credential>`; reconnect with jittered exponential
  backoff 1 s → 60 s; a relay silent for 75 s is gone.

### Frames (JSON text, one object per message)

| Direction | Frame | Notes |
|---|---|---|
| daemon → relay | `{"t":"hello","v":1,"caps":[…],"version":…,"platform":"macos\|windows\|linux"}` | always the first frame |
| relay → daemon | `{"t":"welcome","account":"<opaque>","server_time":"<iso>"}` | connected |
| relay → daemon | `{"t":"command","id":…,"op":…,"args":{…},"deadline_ms":…}` | one `result` per command |
| daemon → relay | `{"t":"result","id":…,"ok":true,"data":{…}}` / `{"t":"result","id":…,"ok":false,"error":{"code","message"}}` | |
| daemon → relay | `{"t":"event","name":"browser.state","data":{open, signed_in, url, new_cookies}}` | when his window opens, closes or he signs in |
| relay → daemon | `{"t":"ping"}` → daemon answers `{"t":"pong"}` | |
| relay → daemon | `{"t":"bye","reason":"revoked\|replaced\|shutdown"}` | `revoked`: forget the credential and stop · `replaced`: stop, keep it · else reconnect |

### Operations (the loopback handlers, one boundary for both transports)

| op | args | data |
|---|---|---|
| `files.list` | `{path, limit?}` | as `/files/list` |
| `files.read` | `{path, max_bytes?}` | as `/files/read` (text, size, truncated) |
| `files.search` | `{query, under?}` | as `/files/search` |
| `browser.open` | `{url, task_id}` | `{opened, launching}` — answers within 5 s; the caller polls `browser.state` |
| `browser.state` | `{task_id?}` | `{open, url, new_cookies, signed_in}` |
| `browser.close` | `{task_id?}` | `{closed}` |
| `browser.export_session` | `{site}` | `{domain, storage_state}` |
| `daemon.status` | `{}` | `{version, caps, roots_count, browser:{open}}` |

What a REMOTE caller may not do is enforced in `daemon/relay/dispatch.py`, before the handler: `profile` is dropped
from `browser.open` (the window opens on the daemon's own profile); an unknown op is `unknown_op`; `deadline_ms` is
honoured (clamped to 120 s; `deadline_exceeded`); a result over 20 MB is `result_too_large`; at most 4 commands run at
once (`busy`). Every relayed operation is audited with `caller: relay`.

`login_link.py` asks `GET <url>/daemon/login-link` (bearer) for a one-time `{url, expires_at}` to open the agent
signed in; a relay without it answers 404 and the plain address is used.

## Session export

After he signs in on the daemon's window, an engine elsewhere cannot read that profile, so it asks
`browser.export_session {site}` and imports the result into its own browser context (cookies with `add_cookies`,
localStorage through an init script that fills only keys the page does not have; kept in process memory and
re-applied when the context relaunches). Bounded three ways: the registrable domain of `site` (the last two labels, or
three under a short second level of a two-letter country code; IPs and bare suffixes refused), the daemon's OWN profile
(a window open on any other profile is refused; no other browser is ever read), and 2 MB. The audit line is
«session exported for <domain>» with counts. The engine re-filters to the domain on import.

## The engine's two transports

`widgets/navegador/owner_login/daemon_link.py` (loopback: reads `daemon.json`, probes `/health`, opens the window on
the engine's own profile) and `widgets/navegador/owner_login/relay_link.py` (when `CONTROL_PLANE_URL` is set on a
hosted engine: `POST /daemon/command`, `GET /daemon/presence`, `GET /daemon/credentials`, `POST /daemon/pairing-code`,
with the engine's own `X-Service-Token`). Both register with `browser_window.daemon_connected(caps, opener)` and
withdraw only their own link. The relayed sign-in: open → two signed-in reads of `browser.state` → export → import →
close → the same `_auth_done` a local window ends with; presence is re-read every 30 s while it waits.

`/api/daemon/status` carries `relay: {paired, connected, caps, version, platform, since}` (all-false without a relay);
`POST /api/daemon/pair` returns `{code, expires_at}` on a hosted engine, `relay_not_available` on one with no relay,
and `paired, mode: loopback` over loopback.

## Limits

20 MB per result, 2 MB per exported session, 1 MB per incoming message, `deadline_ms` ≤ 120 000, 4 concurrent
commands, backoff 1 → 60 s. Not done here: the task's browsing itself running on the daemon (only the sign-in and the
session cross), push of events to the engine (it polls), an egress tunnel.

## Testing

| Node | What |
|---|---|
| 7.34 · 7.35 · 7.36 · 7.37 · 7.38 | permission circuit, browser isolation, hostile local process, boot |
| 7.97 · 4.414 | the sign-in window, loopback |
| 7.98 | the engine proxy answers only this computer |
| 7.104 | the relay link: hello, ping, bye, backoff, `profile` stripped, unknown op, deadline, size cap, pairing |
| 7.105 | session export: one domain, own profile, 2 MB, counts-only audit |
| 7.106 | hosted pairing code and `status.relay` |
| 4.420 | end to end: engine → in-process relay → the real daemon link → import; presence; the phone |

The relay in tests is a real WebSocket server on an ephemeral loopback port
(`tests/infrastructure/unit/daemon/fake_relay.py`). No real relay is exercised by this repository.
