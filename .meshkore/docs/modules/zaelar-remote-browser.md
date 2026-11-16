# Remote browser — one seam between "launch a Chromium" and "reach one over CDP"

`nucleo/remote_browser.py` · criterion CRIT-R41 · test node 4.550 · V2-918 (2026-11-16)

## What it is

Every consumer of a browser in the engine asks this module first:

| Consumer | Where | Local mode (default) | Remote mode |
|---|---|---|---|
| Navigator widget (the task browser workers drive through `hbweb`) | `widgets/navegador/owner_page.py::_ensure_page` | `launch_persistent_context` on `widgets/_data/navegador/profile` | `connect_over_cdp` + a fresh `new_context` |
| Search / images / page HTML / video lookups | `search/browser.py::ensure_started` | `launch_persistent_context` on `memory/_data/search_browser` | `connect_over_cdp` + a fresh `new_context` |
| Boot prewarm | `nucleo/llm/prewarm.py::_warm_browser` | warms the search browser (policy `prewarm_browser`) | skipped: it would take a browser on every boot |

The local desktop daemon (`daemon/`) runs its own visible window on the user's computer and is not part of this seam.

## Configuration

Nothing set → **local**: exactly the behaviour before this seam. Remote mode is chosen by configuration only:

- `ZAELAR_BROWSER_CDP_URL` — a fixed endpoint (`http://host:port[/prefix]` or `ws://…`). Anything that speaks CDP: a
  Chromium started with `--remote-debugging-port`, a container next to the engine, a browser service.
- `ZAELAR_BROWSER_LEASE=1` — the endpoint is leased from the deployment's control plane at `CONTROL_PLANE_URL` with
  the host's `CONTROL_PLANE_SERVICE_TOKEN`:
  - `POST /browser/lease {ttl_s}` → `{ok, machine_id, cdp_url, expires_at}`
  - `POST /browser/renew {machine_id, ttl_s}` → `{ok, expires_at}`
  - `POST /browser/release {machine_id}`

  The engine asks for a 10-minute lease, reuses it while live, and renews it only when it was **used** since the last
  renewal; a lease nobody uses lapses on its own (a host that sleeps holds no browser).

## Rules

1. **In remote mode the engine launches no Chromium.** Not on failure either: an unreachable endpoint raises
   `RemoteBrowserUnavailable` with the reason in its message. The navigator surfaces it; the search returns `False`
   and its chain falls to the next index, as for any start failure.
2. **A browser that ended is reconnected, never reused** (`alive()` before handing out a cached page or context).
3. **A remote context gets everything that does not depend on a profile on disk**: viewport, locale, time zone, user
   agent, the navigation-outcome hook, the stealth script, timeouts, the consent cookies (`_CONSENT_COOKIES`) and the
   sessions the daemon handed over in this process (`_apply_imported_sessions`).

## What a remote browser does not carry

- **The persistent profile**: sessions a site remembered, banners accepted once, a site's trust in a returning
  browser. Every context starts blank. Restoring a session goes through `add_cookies` / an init script, the same path
  the daemon hand-over uses.
- **The daemon tunnel** (V2-836): its forwarder listens on the engine host's loopback, which a remote browser cannot
  reach, so the browsing leaves from wherever the browser runs.
- **A headed window**: remote mode is headless by construction.
- **Downloads to the engine's disk**: not verified over CDP yet.

## Tests

`tests/browser/unit/remote/test_a_remote_browser_is_reached_never_launched.py` (node 4.550): the launch is a fake that
fails the test if called; disarms are listed in its docstring.
