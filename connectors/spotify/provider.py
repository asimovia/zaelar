"""connectors/spotify/provider.py — Spotify as `MusicProvider` (V2-041).

Implements the agnostic `connectors.music.base` contract over `client.py` + `auth.py`. Translates Web API results to
`Track`/`NowPlaying`/`MusicResult` with SPEAKABLE phrases in the operator language, and handles NO_ACTIVE_DEVICE
(finds a Spotify Connect device and sends it the command) without bothering the operator unless none exists.
Fail-safe: never raises; any failure -> `MusicResult(ok=False,...)` with a friendly sentence.
"""
from __future__ import annotations

import logging
import time

from connectors.music.base import MusicProvider, MusicResult, NowPlaying, Track

from . import auth, client
from .client import SpotifyError

logger = logging.getLogger("zaelar.music.spotify")

#: How long a skip is given to show up in the player before «nothing changed» is believed (V2-795).
_SETTLE_S, _SETTLE_TRIES = 0.25, 6
#: Tracks one list hands Spotify as a single context, and how many uri-less ones may be looked up by words.
_MAX_CONTEXT, _MAX_LIST_LOOKUPS = 100, 15

def _t(key: str, **kw) -> str:
    """A speakable line in the active language — the `voice` pack's `music.spotify.<key>`."""
    from i18n import langs as _langs
    return _langs.words(f"music.spotify.{key}", default="").format(**kw)


def _clock(ms: int) -> str:
    """«2:07» — a position said the way it is written on a player, not in raw seconds."""
    total = max(0, int(ms) // 1000)
    return f"{total // 60}:{total % 60:02d}"


def _track_from(item: dict) -> "Track | None":
    if not item:
        return None
    artists = ", ".join(a.get("name", "") for a in (item.get("artists") or []) if a.get("name"))
    imgs = ((item.get("album") or {}).get("images") or [])
    return Track(
        id=item.get("id", ""),
        uri=item.get("uri", ""),
        title=item.get("name", ""),
        artist=artists,
        album=(item.get("album") or {}).get("name", ""),
        art=(imgs[0].get("url", "") if imgs else ""),
        duration_ms=int(item.get("duration_ms") or 0),
    )


#: Spotify's repeat words ↔ the contract's (V2-795).
_REPEAT_TO = {"off": "off", "one": "track", "all": "context"}
_REPEAT_FROM = {v: k for k, v in _REPEAT_TO.items()}


def _image(obj: dict) -> str:
    imgs = (obj or {}).get("images") or []
    return imgs[0].get("url", "") if imgs and isinstance(imgs[0], dict) else ""


def _artist_dict(a: dict) -> dict:
    return {"id": a.get("id", ""), "name": a.get("name", ""), "art": _image(a), "uri": a.get("uri", ""),
            "source": "spotify"}


def _album_dict(a: dict) -> dict:
    artists = ", ".join(x.get("name", "") for x in (a.get("artists") or []) if x.get("name"))
    return {"id": a.get("id", ""), "name": a.get("name", ""), "artist": artists, "art": _image(a),
            "year": str(a.get("release_date") or "")[:4], "uri": a.get("uri", ""), "source": "spotify"}


def _playlist_dict(p: dict) -> dict:
    return {"id": p.get("id", ""), "name": p.get("name", ""), "owner": ((p.get("owner") or {}).get("display_name")
            or ""), "art": _image(p), "uri": p.get("uri", ""),
            "count": int(((p.get("tracks") or {}).get("total")) or 0), "source": "spotify"}


class SpotifyProvider(MusicProvider):
    name = "spotify"
    plays_lists_as_context = True          # its next/previous move only inside the context it was handed

    def connected(self) -> bool:
        return bool(auth.client_id()) and auth.logged_in()

    # ── search ─────────────────────────────────────────────────────────────────────────────────────────
    def search(self, query: str, limit: int = 5) -> "list[Track]":
        if not (query or "").strip():
            return []
        try:
            res = client.search(query, types="track", limit=limit)
        except SpotifyError as e:
            logger.warning(f"búsqueda Spotify falló: {e}")
            return []
        items = ((res or {}).get("tracks") or {}).get("items") or []
        return [t for t in (_track_from(i) for i in items) if t]

    # ── device resolution (NO_ACTIVE_DEVICE) ─────────────────────────────────────────────────────────────
    def _pick_device(self) -> str:
        """Device id to use: active one, otherwise first available; '' if none exists."""
        try:
            devs = client.devices()
        except SpotifyError:
            return ""
        if not devs:
            return ""
        for d in devs:
            if d.get("is_active"):
                return d.get("id", "")
        return devs[0].get("id", "")

    def _run(self, fn, action: str, track: "Track | None" = None, msg_kw: dict = None) -> MusicResult:
        """Run a player action with NO_ACTIVE_DEVICE recovery (retry with a device_id)."""
        msg_kw = msg_kw or {}
        try:
            fn("")
            return MusicResult(ok=True, provider=self.name, action=action, track=track,
                               message=_t(action, **msg_kw))
        except SpotifyError as e:
            if e.code == "no_device":
                dev = self._pick_device()
                if not dev:
                    return MusicResult(ok=False, provider=self.name, action=action, reason="no_device",
                                       message=_t("no_device"))
                try:
                    fn(dev)
                    return MusicResult(ok=True, provider=self.name, action=action, track=track,
                                       message=_t(action, **msg_kw))
                except SpotifyError as e2:
                    return self._fail(action, e2)
            return self._fail(action, e)

    def _fail(self, action: str, e: SpotifyError) -> MusicResult:
        reason = {"premium": "premium", "auth": "not_connected", "no_device": "no_device"}.get(e.code, "error")
        key = {"premium": "premium", "not_connected": "not_connected", "no_device": "no_device"}.get(reason, "error")
        logger.warning(f"Spotify {action} → {e}")
        return MusicResult(ok=False, provider=self.name, action=action, reason=reason, message=_t(key))

    # ── control ──────────────────────────────────────────────────────────────────────────────────────────
    def play(self, query: str = "", uri: str = "") -> MusicResult:
        track = None
        if query and not uri:
            hits = self.search(query, limit=1)
            if not hits:
                return MusicResult(ok=False, provider=self.name, action="play", reason="no_track",
                                   message=_t("no_track", q=query))
            track = hits[0]
            uri = track.uri
        if uri:
            return self._run(lambda dev: client.play(uris=[uri], device_id=dev), "play", track,
                             {"label": track.label() if track else uri})
        return self._run(lambda dev: client.resume(device_id=dev), "resume")

    def pause(self) -> MusicResult:
        return self._run(lambda dev: client.pause(device_id=dev), "pause")

    def resume(self) -> MusicResult:
        return self._run(lambda dev: client.resume(device_id=dev), "resume")

    def next(self) -> MusicResult:
        return self._step(lambda dev: client.next_track(device_id=dev), "next")

    def previous(self) -> MusicResult:
        return self._step(lambda dev: client.previous_track(device_id=dev), "previous")

    def _step(self, fn, action: str) -> MusicResult:
        """A skip is only DONE when the song changed (V2-795). Spotify answers 204 to a skip with nothing after the
        current song — measured live: «pon la siguiente» ran, reported ok, and the same song kept playing. So the
        result names the song that sounds now, read back from the player, or says plainly that nothing changed."""
        before = self._item_id()
        res = self._run(fn, action)
        if not res.ok:
            return res
        for _ in range(_SETTLE_TRIES):
            time.sleep(_SETTLE_S)
            np = self.now_playing()
            if np is not None and np.track and np.track.id and np.track.id != before:
                res.track, res.message = np.track, _t("play", label=np.track.label())
                return res
        reason = "no_next" if action == "next" else "no_previous"
        return MusicResult(ok=False, provider=self.name, action=action, reason=reason,
                           message=_t("no_next" if action == "next" else "no_prev"))

    def _item_id(self) -> str:
        np = self.now_playing()
        return (np.track.id if np is not None and np.track else "") or ""

    # ── a LIST is one playback context (V2-795) ───────────────────────────────────────────────────────────
    def play_list(self, items: "list[tuple[str, str]]") -> MusicResult:
        """The whole list in ONE play call, so Spotify's own next/previous move inside it. A track that carries no
        Spotify uri is looked up by its words (bounded); one nobody finds is left out and counted."""
        uris, lookups, first = [], 0, None
        for q, u in items or []:
            if not str(u or "").startswith("spotify:track:"):
                u = ""
                if q and lookups < _MAX_LIST_LOOKUPS:
                    lookups += 1
                    hits = self.search(q, limit=1)
                    u = hits[0].uri if hits else ""
                    first = first or (hits[0] if hits and not uris else None)
            if u:
                uris.append(u)
        if not uris:
            return MusicResult(ok=False, provider=self.name, action="play", reason="no_track",
                               message=_t("no_track", q=(items[0][0] if items else "")))
        uris = uris[:_MAX_CONTEXT]
        res = self._run(lambda dev: client.play(uris=uris, device_id=dev), "play", first,
                        {"label": first.label() if first else (items[0][0] or uris[0])})
        res.extra = {**(res.extra or {}), "in_context": len(uris), "left_out": len(items) - len(uris)}
        return res

    def enqueue(self, query: str = "", uri: str = "") -> MusicResult:
        """Append one track to Spotify's own queue (the base answered «unsupported», so every «queue this» was
        silently dropped)."""
        if not str(uri or "").startswith("spotify:track:"):
            hits = self.search(query, limit=1) if query else []
            if not hits:
                return MusicResult(ok=False, provider=self.name, action="queue", reason="no_track",
                                   message=_t("no_track", q=query))
            uri = hits[0].uri
        return self._run(lambda dev: client.add_to_queue(uri, device_id=dev), "queue")

    def set_volume(self, percent: int) -> MusicResult:
        pct = max(0, min(100, int(percent or 0)))
        return self._run(lambda dev: client.set_volume(pct, device_id=dev), "volume", None, {"n": pct})

    def seek(self, seconds: float = 0.0, relative: bool = False) -> MusicResult:
        """Move the playhead (V2-717). A RELATIVE move needs to know where we are, and here that is one
        extra read — the device is not in this process, so there is no local clock to add to."""
        target = float(seconds or 0.0)
        if relative:
            np = self.now_playing()
            if np is None or not np.track:
                return MusicResult(ok=False, provider=self.name, action="seek", reason="no_track",
                                   message=_t("no_track", q=""))
            target = max(0.0, (np.progress_ms / 1000.0) + target)
        ms = max(0, int(round(target * 1000)))
        return self._run(lambda dev: client.seek(ms, device_id=dev), "seek", None, {"t": _clock(ms)})

    # ── play modes, the queue, whole albums (V2-795) ───────────────────────────────────────────────────────
    def set_shuffle(self, on: bool) -> MusicResult:
        return self._run(lambda dev: client.shuffle(bool(on), device_id=dev), "shuffle")

    def set_repeat(self, mode: str) -> MusicResult:
        state = _REPEAT_TO.get(mode, "off")
        return self._run(lambda dev: client.repeat(state, device_id=dev), "repeat")

    def queue_items(self) -> "list[Track] | None":
        try:
            q = client.queue()
        except SpotifyError as e:
            logger.warning(f"Spotify queue read failed: {e}")
            return None
        return [t for t in (_track_from(i) for i in (q.get("queue") or [])[:30]) if t]

    def play_context(self, uri: str, label: str = "") -> MusicResult:
        if not str(uri or "").startswith("spotify:"):
            return MusicResult(ok=False, provider=self.name, action="play", reason="unsupported")
        return self._run(lambda dev: client.play(context_uri=uri, device_id=dev), "play", None,
                         {"label": label or uri})

    # ── catalogue (V2-795) ────────────────────────────────────────────────────────────────────────────────
    def search_catalog(self, query: str, limit: int = 8) -> "dict | None":
        if not (query or "").strip():
            return None
        try:
            res = client.search(query, types="track,artist,album,playlist", limit=limit)
        except SpotifyError as e:
            logger.warning(f"Spotify catalogue search failed: {e}")
            return None
        from connectors.music import catalog as _cat
        return {
            "tracks": [_cat.track_dict(t, "spotify") for t in
                       (_track_from(i) for i in ((res.get("tracks") or {}).get("items") or [])) if t],
            "artists": [_artist_dict(a) for a in ((res.get("artists") or {}).get("items") or []) if a],
            "albums": [_album_dict(a) for a in ((res.get("albums") or {}).get("items") or []) if a],
            "playlists": [_playlist_dict(p) for p in ((res.get("playlists") or {}).get("items") or []) if p],
        }

    def artist_page(self, artist_id: str) -> "dict | None":
        from connectors.music import catalog as _cat
        try:
            a = client.artist(artist_id)
            top = client.artist_top_tracks(artist_id)
            albums = client.artist_albums(artist_id)
        except SpotifyError as e:
            logger.warning(f"Spotify artist page failed: {e}")
            return None
        return {"artist": _artist_dict(a),
                "top": [_cat.track_dict(t, "spotify") for t in (_track_from(i) for i in top[:10]) if t],
                "albums": [_album_dict(x) for x in albums if x]}

    def album_page(self, album_id: str) -> "dict | None":
        from connectors.music import catalog as _cat
        try:
            al = client.album(album_id)
        except SpotifyError as e:
            logger.warning(f"Spotify album page failed: {e}")
            return None
        meta = _album_dict(al)
        items = ((al.get("tracks") or {}).get("items") or [])
        tracks = []
        for it in items:
            t = _track_from({**it, "album": {"name": meta["name"], "images": al.get("images") or []}})
            if t:
                tracks.append(_cat.track_dict(t, "spotify"))
        return {"album": meta, "tracks": tracks}

    # ── status ─────────────────────────────────────────────────────────────────────────────────────────
    def now_playing(self) -> "NowPlaying | None":
        try:
            st = client.playback_state()
        except SpotifyError:
            return None
        if not st:
            return NowPlaying(playing=False, provider=self.name)
        dev = st.get("device") or {}
        return NowPlaying(
            playing=bool(st.get("is_playing")),
            track=_track_from(st.get("item") or {}),
            device=dev.get("name", ""),
            volume=dev.get("volume_percent"),
            provider=self.name,
            progress_ms=int(st.get("progress_ms") or 0),
            shuffle=bool(st.get("shuffle_state")),
            repeat=_REPEAT_FROM.get(str(st.get("repeat_state") or "off"), "off"),
        )

    def status(self) -> dict:
        s = auth.status()
        s.update({"provider": self.name, "connected": self.connected()})
        return s
