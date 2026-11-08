"""search/media.py — the MEDIA door of the search service: what can be PLAYED that his words name (V2-860 T2.1).

    from search import find_media
    got = find_media("pon Sueñacuentos", catalogue=connectors.music.catalog.search)
    got["candidates"]   # [{kind: show|playlist|album|track|video, name, owner, source, uri, video_id, fit}, …]

A separate door, NOT a seventh route of `find()`: the question every turn asks (`route.question`) does not change.
Measured on a phone (2026-11-07): «pon Sueña cuentos» took the first SONG the catalogue returned («Sueña», another
artist) while the podcast «Sueñacuentos» was in the same answer. The class: nothing compared his words with the
NAMES of every kind the catalogue knows. Here they are compared — a string comparison against the catalogue's own
answer, never a table of our words — and the whole (podcast, list, album) his words NAME is told apart from a song.

Sources, in order: music → the caller's catalogue (the connected account, else iTunes — the connector owns that
chain and passes it in; this package never imports a connector), then `search.video.find_videos` when the catalogue
has nothing; video → `find_videos`. The web is not a source: it may fix a misheard NAME, and the door is asked again.
Never raises. One observability row per call through the service's hook.
"""
from __future__ import annotations

import time
import unicodedata

from loguru import logger

from . import hooks as _hooks

#: How well his words must fit a podcast/list/album NAME for «play X» to play THAT instead of a song, and by how
#: much it must beat the best song. Below either, the song road stays as it was.
CONTEXT_FIT = 0.5
CONTEXT_MARGIN = 0.15
#: The kinds a catalogue answer carries, where each lives in it, which field is its owner, and the word a request and
#: a reply use for it (`play_music.kind`, the card's numbered list — V2-861); a whole is all but a song.
_KINDS = (("show", "shows", "owner", "podcast"), ("playlist", "playlists", "owner", "list"),
          ("album", "albums", "artist", "album"), ("track", "tracks", "artist", "song"))
_WHOLES = frozenset(kind for kind, _key, _owner, _word in _KINDS if kind != "track")
#: The kind a request NAMES («a list», «the podcast») → the candidate kind it means, and back.
ASKED_KINDS = {word: kind for kind, _key, _owner, word in _KINDS}
SPOKEN_KIND = {kind: word for kind, _key, _owner, word in _KINDS}
#: How many results of each kind are compared (the catalogue answers in relevance order).
_PER_KIND = 8
_PRIVATE = ("item",)


def _norm(s: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c))
    return " ".join("".join(c if c.isalnum() else " " for c in s.lower()).split())


def name_fit(query: str, name: str) -> float:
    """0..1 — how well a catalogue NAME matches his words: 1.0 for the same words (spaces aside: «Sueña cuentos» is
    «Sueñacuentos»), otherwise the F1 of the words they share, two of his words written together counting as one of
    the name's. Extra words of his lower it a little and never to zero."""
    q, n = _norm(query), _norm(name)
    if not q or not n:
        return 0.0
    if q.replace(" ", "") == n.replace(" ", ""):
        return 1.0
    qw, nw = q.split(), set(n.split())
    used_q, hit_n = set(), set()
    for i, w in enumerate(qw):
        if w in nw:
            used_q.add(i)
            hit_n.add(w)
        elif i + 1 < len(qw) and w + qw[i + 1] in nw:
            used_q.update((i, i + 1))
            hit_n.add(w + qw[i + 1])
    if not hit_n:
        return 0.0
    precision, recall = len(used_q) / len(qw), len(hit_n) / len(nw)
    return round(2 * precision * recall / (precision + recall), 3)


def _fit(query: str, name: str, owner: str) -> float:
    fit = name_fit(query, name)
    if owner:
        fit = max(fit, name_fit(query, f"{name} {owner}"), name_fit(query, f"{owner} {name}"))
    return round(fit, 3)


def _candidate(kind: str, item: dict, query: str, owner_key: str) -> dict:
    name = str((item.get("title") if kind in ("track", "video") else item.get("name")) or "")
    owner = str(item.get(owner_key) or "")
    return {"kind": kind, "name": name, "owner": owner, "source": str(item.get("source") or ""),
            "uri": str(item.get("uri") or ""), "video_id": str(item.get("videoId") or item.get("video_id") or ""),
            "fit": _fit(query, name, owner), "item": item}


def rank(query: str, answer: dict) -> list[dict]:
    """Every podcast, list, album and song of a catalogue answer as a candidate, best fit first. A song keeps a tie
    (an album named like its single plays the single, as it always did); otherwise the catalogue's order stays."""
    out = []
    for kind, key, owner_key, _word in _KINDS:
        for it in ((answer or {}).get(key) or [])[:_PER_KIND]:
            if isinstance(it, dict):
                out.append(_candidate(kind, it, query, owner_key))
    return sorted(out, key=lambda c: (-c["fit"], c["kind"] != "track"))


def named_whole(query: str, candidates: list[dict], kind: str = "") -> "dict | None":
    """The podcast, list or album his words NAME — it fits them at least `CONTEXT_FIT`, beats the best song by
    `CONTEXT_MARGIN`, and carries a uri to open it by. None otherwise: the song road stays as it was.

    `kind` is the kind HE named (`ASKED_KINDS`, V2-861: «put some LIST… Sueñacuentos» played the podcast of the
    same name over four lists): the best fit of that kind wins with no margin over the songs, and «a song» keeps the
    song road. A named kind with nothing of it that fits falls back to the rule above."""
    cands = [c for c in (candidates or []) if isinstance(c, dict)]
    want = ASKED_KINDS.get(str(kind or "").strip().lower(), "")
    if want == "track":
        return None
    if want:
        mine = [c for c in cands if c.get("kind") == want and c.get("uri") and c.get("fit", 0.0) >= CONTEXT_FIT]
        if mine:
            return max(mine, key=lambda c: c.get("fit", 0.0))
    song = max((c.get("fit", 0.0) for c in cands if c.get("kind") == "track"), default=0.0)
    wholes = [c for c in cands if c.get("kind") in _WHOLES and c.get("uri")]
    best = max(wholes, key=lambda c: c.get("fit", 0.0), default=None)
    if best is None or best["fit"] < CONTEXT_FIT or best["fit"] < song + CONTEXT_MARGIN:
        return None
    return best


def _videos(query: str, k: int) -> list[dict]:
    from .video import find_videos
    hits = find_videos(query, k) or []
    return sorted((_candidate("video", {**h, "source": "youtube"}, query, "channel") for h in hits if isinstance(h, dict)),
                  key=lambda c: -c["fit"])


def find_media(query: str, kind: str = "music", k: int = 6, *, catalogue=None, video: bool = True) -> dict:
    """{query, kind, source, candidates} — what can be played that his words name. `catalogue(query) -> answer` is
    the music catalogue the caller owns (the connector's `catalog.search`); without one, music falls to video
    (`video=False`: a caller that only asks which whole his words name pays no video lookup). Empty candidates is
    the honest «not found». Never raises."""
    q = " ".join(str(query or "").split())
    out = {"query": q, "kind": kind, "source": "", "candidates": []}
    if not q:
        return out
    t0 = time.monotonic()
    try:
        if kind != "video" and catalogue is not None:
            answer = catalogue(q) or {}
            cands = rank(q, answer)
            if cands:
                out.update(source=str(answer.get("source") or ""), candidates=cands[:max(k, 1) * 4])
        if not out["candidates"] and (video or kind == "video"):
            vids = _videos(q, k)
            if vids:
                out.update(source="youtube", candidates=vids[:k])
    except Exception as e:  # noqa: BLE001 — a door that fails answers «not found», it never takes the caller down
        logger.debug(f"search.media: {q!r} failed: {e!r}")
        out["failure"] = f"{type(e).__name__}: {str(e)[:160]}"
    whole = named_whole(q, out["candidates"])
    _hooks.note("search", "🎵 media search", role="system", text=q[:160],
                extra={"route": "media", "kind": kind, "source": out["source"], "n": len(out["candidates"]),
                       "named": (whole or {}).get("kind", ""), "ms": int((time.monotonic() - t0) * 1000),
                       **({"failure": out["failure"]} if out.get("failure") else {})})
    return out


def public(candidate: dict) -> dict:
    """A candidate without its private reference to the raw catalogue row — what a card or a worker is handed."""
    return {k: v for k, v in (candidate or {}).items() if k not in _PRIVATE}
