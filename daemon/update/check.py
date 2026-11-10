"""Is there a newer daemon? — found, VERIFIED, compared. Once a day in the background and whenever the person asks.

WHERE THE MANIFEST COMES FROM. The same rule as `get.sh` (`release_line`): among the `daemon-vX.Y.Z` releases that
carry `update-manifest.json`, the newest by version; only when none does, the newest release of any kind carrying it.
Never `releases/latest`, which is an engine release. The release tag it was found on must equal the `tag` inside the signed
manifest, so a valid manifest cannot be replayed from another release to point at that release's files.

WHAT REFUSES. No `.minisig` beside the manifest (the publisher had no signing key that day — the manifest is then
published unsigned on purpose, and this is where that becomes a refusal), a signature by a key this client does not
trust, a signature that does not match, a manifest that does not parse, a tag mismatch. Each ends in
`state = failed` with the sentence, and nothing is downloaded. An older or equal manifest is simply "up to date":
the comparison never moves the installed version backwards.
"""
from __future__ import annotations

import threading
import time
import urllib.request

from . import apply, current, manifest, minisign, public_keys, release_line, repo
from .state import STORE, Store

DAY_S = 24 * 3600
FIRST_CHECK_DELAY_S = 120          # never slow a start: the first background check waits two minutes
_MAX_JSON = 4 * 1024 * 1024        # the releases listing and the manifest are small; anything larger is refused
_USER_AGENT = "zaelar-daemon-update"


def http_get(url: str, timeout: float = 20.0, limit: int = _MAX_JSON) -> bytes:
    """GET over https only, bounded in size. The default transport; tests inject their own."""
    if not url.startswith("https://"):
        raise ValueError(f"refusing a non-https URL: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT, "Accept": "application/json, */*"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:   # noqa: S310 — https enforced above
        data = resp.read(limit + 1)
    if len(data) > limit:
        raise ValueError("response larger than expected")
    return data


def found_in(rel: dict | None) -> tuple[str, str, str | None] | None:
    """`(tag, manifest_url, signature_url | None)` of a release that carries the manifest, or None."""
    url = release_line.asset_url(rel, manifest.MANIFEST_NAME) if isinstance(rel, dict) else None
    if not url:
        return None
    return str(rel.get("tag_name") or ""), url, release_line.asset_url(rel, manifest.SIGNATURE_NAME)


def find_release(releases: list) -> tuple[str, str, str | None] | None:
    """The release to update from, out of a releases listing: the daemon's own line first (`release_line`)."""
    return found_in(release_line.choose(releases, manifest.MANIFEST_NAME))


def verify(data: bytes, signature: str | None, tag: str, keys: list) -> manifest.Manifest:
    """The whole trust decision over one manifest. Raises `minisign.SignatureError` / `manifest.ManifestError`."""
    if not signature:
        raise minisign.SignatureError("the update manifest is not signed — refused")
    minisign.verify(data, signature, keys)
    parsed = manifest.parse(data)
    if parsed.tag != tag:
        raise manifest.ManifestError(f"the manifest is for {parsed.tag!r} but was found on release {tag!r}")
    return parsed


def check(fetch=http_get, store: Store = STORE, now: float | None = None) -> dict:
    """One check. Returns `{ok, current, available, state, error}` and records it in `state.json`."""
    now = time.time() if now is None else now
    mine = current()
    try:
        apply.cleanup()
    except Exception:   # noqa: BLE001 — leftovers of a previous swap never block a check
        pass
    try:
        found = found_in(release_line.resolve(fetch, repo(), manifest.MANIFEST_NAME))
        if found is None:
            snap = store.update(last_check=now, last_result="no release publishes an update manifest yet")
            return _result(True, mine, snap)
        tag, manifest_url, sig_url = found
        data = fetch(manifest_url)
        signature = fetch(sig_url).decode("utf-8", "replace") if sig_url else None
        snap = store.snapshot()
        parsed = verify(data, signature, tag, public_keys(snap.get("next_key")))
    except (minisign.SignatureError, manifest.ManifestError) as e:
        snap = store.transition("failed", error=str(e), last_check=now, last_result=f"refused: {e}",
                                available=None)
        return _result(False, mine, snap)
    except Exception as e:   # noqa: BLE001 — offline, rate-limited, DNS: a failed CHECK, nothing else changes
        snap = store.update(last_check=now, last_result=f"could not check: {type(e).__name__}")
        return _result(False, mine, snap, error=f"could not reach the release server ({type(e).__name__})")

    # Rotation: a key announced by a manifest that just verified with a trusted key.
    if parsed.next_key and parsed.next_key != snap.get("next_key"):
        try:
            minisign.parse_public_key(parsed.next_key)
            store.update(next_key=parsed.next_key)
        except minisign.SignatureError:
            pass

    if manifest.is_newer(parsed, mine["version"], mine["build"]):
        summary = parsed.summary()
        result_line = f"{parsed.version} (build {parsed.build}) available"
        snap = store.snapshot()
        pending = snap.get("pending") or {}
        if snap["state"] == "ready" and pending.get("build") == parsed.build \
                and pending.get("version") == parsed.version:
            snap = store.update(last_check=now, last_result=result_line, available=summary)   # still ready
        elif snap["state"] == "downloading":
            snap = store.update(last_check=now, last_result=result_line, available=summary)   # one in flight
        else:
            apply.discard_pending(store)
            snap = store.transition("idle", last_check=now, last_result=result_line, available=summary,
                                    pending=None)
        out = _result(True, mine, snap)
        out["manifest"] = parsed
        return out
    if store.snapshot()["state"] == "downloading":
        snap = store.update(last_check=now, last_result="up to date")
    else:
        apply.discard_pending(store)
        snap = store.transition("idle", last_check=now, last_result="up to date", available=None, pending=None)
    return _result(True, mine, snap)


def _result(ok: bool, mine: dict, snap: dict, error: str = "") -> dict:
    return {"ok": ok, "current": mine, "available": snap.get("available"), "state": snap.get("state"),
            "error": error or snap.get("error", ""), "last_result": snap.get("last_result", "")}


def check_and_download(fetch=http_get, store: Store = STORE, **download_kw) -> dict:
    """Check; when something newer verified, download and verify it (→ `ready`). What the tray and the scheduler run."""
    result = check(fetch=fetch, store=store)
    parsed = result.pop("manifest", None)
    if parsed is not None and result["state"] != "ready":
        result.update(apply.download(parsed, fetch=fetch, store=store, **download_kw))
    return result


# ── the daily background check ─────────────────────────────────────────────────────────────────────────────────

_STARTED = threading.Event()


def _due(store: Store, now: float) -> bool:
    return now - float(store.snapshot().get("last_check") or 0) >= DAY_S


def _loop(store: Store) -> None:
    time.sleep(FIRST_CHECK_DELAY_S)
    while True:
        try:
            if _due(store, time.time()):
                result = check_and_download(store=store)
                if result.get("state") == "ready" and not apply.busy():
                    apply.install(store=store)
        except Exception:   # noqa: BLE001 — the scheduler never dies; the next hour tries again
            pass
        time.sleep(3600)


def ensure_started(store: Store = STORE) -> bool:
    """Start the background thread once, and only for an installed daemon (see `enabled()`)."""
    from . import enabled   # noqa: PLC0415
    if _STARTED.is_set() or not enabled():
        return False
    _STARTED.set()
    threading.Thread(target=_loop, args=(store,), name="daemon-update", daemon=True).start()
    return True
