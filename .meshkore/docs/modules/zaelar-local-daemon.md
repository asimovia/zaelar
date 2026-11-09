# The Local Daemon (`daemon/`)

A small resident process on the user's OWN computer for the two things an engine without his desktop cannot do: read
the folders he grants, and open a real browser window on his screen for a sign-in or a challenge only a person passes.
It is additive: an engine with no daemon behaves exactly as before. Not the shared MeshKore daemon. When he switches
it on, it can also carry an engine's browsing so sites see his own connection (the egress tunnel, below).

Standalone on purpose: the daemon imports nothing from the engine and the engine never imports the daemon (both
directions are guarded by tests). Its dependency set is the standard library, plus Playwright only when a browser
window is wanted. Initiative: V2-575.

## Architecture

```
 engine on the same computer ──loopback HTTP + token──▶ daemon (127.0.0.1:45817)
 engine elsewhere ──HTTPS──▶ relay ◀──WSS, dialled OUT by the daemon── daemon
 engine elsewhere ◀──WSS /daemon/tunnel, dialled OUT by the daemon (egress)── daemon ──TCP──▶ public sites
```

| Folder | What it is |
|---|---|
| `daemon/security/` | WHETHER — the never-served names, the HTTP admission decision (token, Host, no browser origin), throttling. |
| `daemon/fs/` | WHAT — the permission circuit every file operation goes through (list · read · search), read-only. |
| `daemon/http/` | The loopback surface: route table (`routes.py`), handler, life cycle. |
| `daemon/browser/` | The ONE headed sign-in window on a persistent profile. |
| `daemon/relay/` | The OUTBOUND link (P3): config, a stdlib WebSocket client, the link, command dispatch, pairing, session export. |
| `daemon/egress/` | The egress tunnel (V2-836): its own WebSocket, one TCP stream per `open`, the per-host audit. |
| `daemon/packaging/` | The single-file builds and the one-line installers. |

State lives under one directory, `config/daemon/` in a source tree or the platform's user-data directory when
installed: `daemon.json` (port, API token, folder allowlist, the `egress` switch), `audit.jsonl`, `browser/profile/`, and `relay.json`.

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
| `egress.offer` | `{token, url, expires_at}` | `{accepted, connected}` — refused `egress_disabled` while his switch is off (see «Egress») |

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

## Egress — the engine browses through his computer (V2-836)

A seam: if an engine away from his computer can offer a tunnel AND his daemon is connected with `egress` among its
capabilities, the engine's own Chromium (the navigator's and the search one) and its direct fetches open their TCP
connections from his computer, so sites see his connection instead of a datacenter's. Otherwise nothing of this runs
and the traffic goes out directly, unchanged.

**The switch** is `daemon.json`'s `egress: {enabled, consented_at}` — OFF by default, ON only with a recorded consent
(a file edited to `enabled: true` without `consented_at` reads off). Flipped ONLY on his computer: the tray item
«Outbound tunnel: on/off» (choosing it is the consent; its tooltip says what it means), or the 🖥 screen of an engine on
the same computer (`POST /api/daemon/egress {enabled}` → loopback `POST /egress {enabled, consent}`; ON is asked first
with the consent text and «I understand, turn it on»). `GET /egress` reads it. A relayed command never switches it:
`egress.offer` is refused while it is off, and the loopback route refuses an ON that says it came through the relay.
`hello` declares `egress` only while it is on; flipping it makes the relay link say hello again; switching it OFF
closes the tunnel and every stream at once.

**The offer and the dial.** The engine mints `<instance_id>.<32 random bytes, base64url>` (10 min, kept in memory,
`nucleo/daemon_egress/tokens.py`) and sends `egress.offer {token, url: <ZAELAR_TUNNEL_ORIGIN>/daemon/tunnel,
expires_at}` over the relay. The daemon accepts a `wss://` URL on the same site as its relay (or two loopback ends),
dials it with `Authorization: Bearer <token>`, and redials with backoff only while that offer is fresh; the engine
renews it before half its life is gone. On a hostname shared by several instances, `server/ingress.py` admits
`/daemon/tunnel` without a cookie and replays it (`307 fly-replay: instance=<prefix>`) to the instance the prefix
names; that instance verifies the token in constant time against its own set and closes **4401** on anything else,
which the daemon reads as «do not retry this token». A WebSocket on that hostname is admitted only on that allowlist.

**Frames** on the tunnel (JSON text): engine → daemon `{"t":"open","id","host","port"}`; daemon → engine
`{"t":"ok","id"}` or `{"t":"close","id","error"}`; both ways `{"t":"data","id","b64"}` and `{"t":"close","id"}`;
engine → daemon `{"t":"ping"}` every 25 s → `{"t":"pong"}`. CONNECT semantics: a byte stream to `host:port`; TLS runs
end to end, so the daemon sees host names and byte counts only.

**On the engine**, `nucleo/daemon_egress/forwarder.py` listens on `127.0.0.1:<ephemeral>` and speaks `CONNECT
host:port` (and absolute-form `http://`) to Chromium (`--proxy-server`, added at launch only while a tunnel is up) and
to httpx (`proxy=`). A stream goes through the tunnel while one is up and directly when none is; a stream the daemon
REFUSES is answered `502` and not retried directly. A Chromium launched before the tunnel came up keeps going out
directly until its next launch (the search one relaunches when idle; the navigator waits up to 5 s for a dial already
offered before launching).

**The daemon's rules** (`daemon/security/egress_guard.py`, applied per stream in `daemon/egress/connect.py`): the
switch is re-read; ports 80/443/8080/8443 only; names that only exist inside his network refused before any lookup;
the name resolved on the daemon and EVERY address checked public — loopback, RFC 1918, link-local, ULA, CGNAT,
multicast/reserved, and v4 embedded in mapped/NAT64/6to4 v6 refused, one private answer refuses the name; the socket
connects to a checked address (never to the name again) and the peer is re-checked; a per-site token bucket (120,
refilled 4/s); at most 128 streams. The audit (`daemon/egress/ledger.py`) writes `egress.host` when a host is first
reached in an hour, `egress.summary` (streams, bytes each way) when the hour turns or the tunnel closes, and one
`refused` line per host and reason per hour — never a URL.

**Status**: `/api/daemon/status.egress = {capable, enabled, connected, hosts_last_hour}`. On this computer it is the
daemon's `GET /egress`; away from it, `enabled` is `egress` in his daemon's capabilities, `capable` a connected daemon
recent enough to carry it, `connected` this engine's tunnel.

## Limits

20 MB per result, 2 MB per exported session, 1 MB per incoming message, `deadline_ms` ≤ 120 000, 4 concurrent
commands, backoff 1 → 60 s; tunnel: 128 streams, 32 KB per data frame, a 10-minute token. Not done here: the task's
browsing itself running on the daemon's window (only the sign-in and the session cross), push of events to the engine
(it polls), the tunnel for an engine on the same computer (it has no instance id: its traffic is already his).

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
| 7.121 | egress guard: every private range by resolved address, ports, per-site rate, the switch per stream |
| 7.122 | egress switch: off by default, consent, offer refused while off, `hello`, kill switch mid-session |
| 7.123 | egress end to end: offer → dial → one CONNECT round trip; the token; two streams on one socket |
| 7.124 | `/daemon/tunnel` admission: allowlist, replay by prefix, no cookie, 4401 |
| 7.125 · 4.431 · 4.432 | `status.egress` and the switch route · launch args only with a tunnel · the 🖥 switch asks first |

The relay in tests is a real WebSocket server on an ephemeral loopback port
(`tests/infrastructure/unit/daemon/fake_relay.py`). No real relay is exercised by this repository.
