"""widgets/youtube/embed_check.py — a video whose owner refuses embedding is never OFFERED as playable (V2-877 #6).

Until now the card learned it only when the player said so (`onError` 101/150, availability.py): the search put the
video on screen, the player refused it, the card swapped to the next one and said «blocked by its owner — playing the
next one». The refusal is knowable BEFORE that: YouTube's public oEmbed endpoint answers 401 for a video whose owner
disabled embedding (404 for a removed or private one). The search hits are checked in parallel, the refused ones go on
the same blocklist the player feeds, and they never reach the catalog or a «play X».

Fail-open on purpose: no answer (timeout, network down, a 5xx) keeps the hit — the player's own swap still covers it,
and a search must never come back empty because this check could not run.
"""
from __future__ import annotations

import os
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from connectors import outcome as _outcome
from . import availability as _av

#: oEmbed's answers that mean «this surface cannot play it»: 401 = embedding disabled by the owner, 403 = refused,
#: 404 = removed or private. Mapped to the player's own codes so the blocklist reads the same either way.
_REFUSED = {401: "150", 403: "150", 404: "100"}


def _status(vid: str) -> int:
    url = ("https://www.youtube.com/oembed?format=json&url="
           + urllib.parse.quote_plus("https://www.youtube.com/watch?v=" + vid))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})

    def fetch() -> int:
        try:
            with urllib.request.urlopen(req, timeout=3) as r:
                return int(r.status)
        except urllib.error.HTTPError as e:      # an answer, not an outage: its code is the fact
            return int(e.code)
    return _outcome.call("youtube.oembed", "embeddable", fetch, refused=lambda s: s >= 500,
                         measure=lambda s: {"status": s})


def refused(vids: list) -> dict:
    """{videoId: player-style code} for the ids whose embed is refused. Unknown (no answer) is NOT refused."""
    ids = [v for v in dict.fromkeys(str(x or "") for x in vids) if v]
    if not ids or os.environ.get("ZAELAR_EMBED_CHECK") == "0":     # the suite stays off the network (conftest.py)
        return {}

    def one(v):
        try:
            return v, _status(v)
        except Exception:  # noqa: BLE001 — fail-open: an unanswered check never hides a video
            return v, 0
    with ThreadPoolExecutor(max_workers=min(6, len(ids))) as ex:
        return {v: _REFUSED[s] for v, s in ex.map(one, ids) if s in _REFUSED}


def keep_playable(db: dict, hits: list) -> list:
    """The hits whose embed is not refused; the refused ones join the player's blocklist, so they never come back."""
    bad = refused([h.get("videoId") for h in hits])
    for h in hits:
        vid = str(h.get("videoId") or "")
        if vid in bad:
            _av.remember_blocked(db, vid, str(h.get("title") or ""), bad[vid])
    return [h for h in hits if str(h.get("videoId") or "") not in bad]
