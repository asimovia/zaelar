"""connectors/music/base.py — provider-agnostic music CONTRACT (V2-041).

zaelar plays music by VOICE ("play music", "play Frank Sinatra"). The mechanism CANNOT be tied to one specific
provider: Spotify today, YouTube Music / Apple / radio stream tomorrow. This module defines the **SINGLE contract**
that any music connector implements (`MusicProvider`) and the data types it returns (`Track`, `NowPlaying`).
FlashBrain and — later, as a SEPARATE piece — the music widget ALWAYS speak to this contract through the facade
(`connectors.music`), never to a specific provider.

Invariant: "the music widget works with ANY connector that can stream". A provider enters the registry
(`registry.register`) by declaring that it satisfies this contract; the facade chooses the CONNECTED one.
All calls are SYNCHRONOUS (network I/O) -> the hot-path caller runs them with `asyncio.to_thread` (like
`web_search`), never in the event loop.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Track:
    """A track, normalized and provider-independent."""
    id: str = ""
    uri: str = ""                 # opaque id playable by the provider (e.g. 'spotify:track:...')
    title: str = ""
    artist: str = ""
    album: str = ""
    art: str = ""                 # cover-art URL (for the future widget)
    duration_ms: int = 0

    def label(self) -> str:
        return f"{self.title} — {self.artist}" if self.artist else (self.title or self.uri)


@dataclass
class NowPlaying:
    """Current playback state (for the future widget and voice Q&A)."""
    playing: bool = False
    track: "Track | None" = None
    device: str = ""
    volume: "int | None" = None
    provider: str = ""
    #: Milliseconds into the track, as of the moment this was read (V2-717). It is a PHOTOGRAPH, never a
    #: clock: whoever paints a progress bar with it advances it from the instant it arrived. 0 means «this
    #: provider does not say», which is not the same as «the song is at the start» — the caller draws no
    #: progress bar at all rather than one pinned at zero.
    progress_ms: int = 0
    #: Play modes (V2-795): whether the next song is picked at random, and what happens at the end of one
    #: («off» stops after the queue, «one» replays the song, «all» starts the queue over).
    shuffle: bool = False
    repeat: str = "off"
    #: The provider's own id for the device producing the sound (V2-812) — "" for one that plays in the page.
    device_id: str = ""


@dataclass
class MusicResult:
    """Uniform result of a playback action (consumed by the voice ack)."""
    ok: bool
    provider: str = ""
    action: str = ""
    track: "Track | None" = None
    reason: str = ""              # stable failure code: no_provider | not_connected | no_track | no_device | error
    message: str = ""             # ready SPEAKABLE sentence (operator language) — FlashBrain says it as-is
    extra: dict = field(default_factory=dict)


class MusicProvider(ABC):
    """Contract implemented by ANY connector capable of streaming music.

    `name` = stable id ('spotify', 'youtube'...). `connected()` = valid credentials/session exist to play NOW. A
    provider is only offered to the facade if `connected()` is True. Control methods return a `MusicResult` with a
    speakable sentence (`message`) — they never raise to the caller (fail-safe: voice never breaks on music failure).
    """

    name: str = "base"
    #: True when next/previous only move inside the provider's own playback CONTEXT (V2-795): a list must then be
    #: handed over whole (`play_list`), because a track started alone is a context with nothing after it.
    plays_lists_as_context: bool = False
    #: WHERE this provider makes sound (V2-812). `plays_in_page`: in the page of the screen that shows the music card
    #: (it can play wherever he is). `plays_elsewhere`: on a device of its own (a Spotify Connect speaker, phone or
    #: computer), so a start is only true once the provider says that device is sounding (`confirm`), and it is only
    #: chosen when it has a device on the screen that asked (`device_near`).
    plays_in_page: bool = False
    plays_elsewhere: bool = False

    @abstractmethod
    def connected(self) -> bool: ...

    @abstractmethod
    def search(self, query: str, limit: int = 5) -> "list[Track]": ...

    def seek(self, seconds: float = 0.0, relative: bool = False) -> MusicResult:
        """Move the playhead (V2-717): to `seconds`, or BY `seconds` when `relative`.

        Deliberately NOT abstract. A provider that plays out of process can do this over its API; one that
        plays inside the page cannot be asked from here at all — it can only leave an intention behind for
        the page to apply. Anything that implements neither keeps the honest default: unsupported, said
        plainly, instead of an ok that moved nothing.
        """
        return MusicResult(ok=False, provider=self.name, action="seek", reason="unsupported",
                           message="")

    @abstractmethod
    def play(self, query: str = "", uri: str = "") -> MusicResult:
        """Play: by natural-language `query` (search + play the first), by explicit `uri`, or — with neither — resume
        whatever was there."""

    @abstractmethod
    def pause(self) -> MusicResult: ...

    @abstractmethod
    def resume(self) -> MusicResult: ...

    @abstractmethod
    def next(self) -> MusicResult: ...

    @abstractmethod
    def previous(self) -> MusicResult: ...

    @abstractmethod
    def set_volume(self, percent: int) -> MusicResult: ...

    @abstractmethod
    def now_playing(self) -> "NowPlaying | None": ...

    # ── QUEUE (V2-047 F4): play several "one after another" without the operator intervening at each cut ───────
    # Generic to the contract but OPTIONAL: a provider with a native queue (Spotify) implements it against its API;
    # the browser fallback (YouTube) keeps it in its store and advances on the player's `ended` event. Base =
    # unsupported (fail-safe), so a provider that does not have it yet does not break voice.
    def enqueue(self, query: str = "", uri: str = "") -> MusicResult:
        """Add a track to the QUEUE (does not interrupt current playback). Base: unsupported."""
        return MusicResult(ok=False, provider=self.name, action="queue", reason="unsupported")

    def on_ended(self) -> MusicResult:
        """The current track ENDED -> play the next one from the queue (if any). Base: unsupported (providers with
        native auto-advance, like Spotify, do not need it)."""
        return MusicResult(ok=False, provider=self.name, action="ended", reason="unsupported")

    def play_list(self, items: "list[tuple[str, str]]") -> MusicResult:
        """Play SEVERAL tracks as one playback context — `items` = [(query, uri), …] in order (V2-795). Only for a
        provider that declares `plays_lists_as_context`: its skip moves inside a context and nowhere else
        (Spotify), so a list must be handed over whole. Everyone else takes the facade's road: the first now,
        the rest queued — their queue is their own."""
        return MusicResult(ok=False, provider=self.name, action="play", reason="unsupported")

    # ── PLAY MODES and the QUEUE as a list (V2-795) — optional, base = unsupported, said plainly ──────────────
    def set_shuffle(self, on: bool) -> MusicResult:
        """Pick the next queued song at random (`on`) or in order."""
        return MusicResult(ok=False, provider=self.name, action="shuffle", reason="unsupported")

    def set_repeat(self, mode: str) -> MusicResult:
        """`off` | `one` | `all`."""
        return MusicResult(ok=False, provider=self.name, action="repeat", reason="unsupported")

    def queue_items(self) -> "list[Track] | None":
        """What will play next, in order. None = this provider does not expose its queue."""
        return None

    def queue_edit(self, op: str, index: int = -1, to: int = -1) -> MusicResult:
        """`remove` the item at `index`, `move` it to `to`, or `clear` the queue. Base: unsupported (a provider
        whose API offers none of these — Spotify — keeps a read-only queue, which is the honest answer)."""
        return MusicResult(ok=False, provider=self.name, action="queue_" + (op or ""), reason="unsupported")

    def play_context(self, uri: str, label: str = "") -> MusicResult:
        """Play a whole album/playlist the provider knows by its own uri. Base: unsupported (the caller then
        plays it track by track, by words)."""
        return MusicResult(ok=False, provider=self.name, action="play", reason="unsupported")

    # ── CATALOGUE (V2-795) — optional; None = «ask someone else» (`connectors.music.catalog` falls back) ────
    def search_catalog(self, query: str, limit: int = 8) -> "dict | None":
        """{tracks, artists, albums, playlists} as plain dicts (see `connectors.music.catalog`)."""
        return None

    def artist_page(self, artist_id: str) -> "dict | None":
        """{artist, top, albums} for one artist of THIS provider's catalogue."""
        return None

    def album_page(self, album_id: str) -> "dict | None":
        """{album, tracks} for one album of THIS provider's catalogue."""
        return None

    # ── PLACEMENT (V2-812) — only for a provider that `plays_elsewhere` ─────────────────────────────────────
    def device_near(self, screen_kind: str) -> "dict | None":
        """A device of this provider that sits with a screen of that kind (`phone` / `computer`): {id, name}, or
        None when it has none there."""
        return None

    def confirm(self, res: MusicResult, device_id: str = "") -> MusicResult:
        """Read back a start: the same result once the provider reports the device SOUNDING it, else a result with
        `reason="not_sounding"`. Base: a provider that plays in this process has nothing to read back."""
        return res

    def status(self) -> dict:
        """Redacted PUBLIC view for the UI (never secrets). Overridable; base = connection only."""
        return {"provider": self.name, "connected": bool(self.connected())}
