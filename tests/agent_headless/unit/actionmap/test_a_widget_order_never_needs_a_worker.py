"""A widget order is served deterministically, in EVERY language (V2-682 T-3).

Measured on the operator's engine, 2026-09-12, the English sessions. «Hey. Uh, can you open my agenda,
please?» was ESCALATED TO A BRAIN WORKER, which then died on a provider 400. So did four agenda edits, a
video and a playlist. His verdict on the class, verbatim: *«cualquier cosa que sea localizar vídeo, música o
cosas así son prácticamente búsquedas directas del sistema»*.

Two independent causes, and neither was about English:

1. **The action map is an exact whole-utterance lookup, and a POSSESSIVE defeated it.** «open the agenda»
   matched; «open MY agenda» did not. Spanish had the identical hole («abre mi agenda», «ábreme la agenda»),
   which is the proof this was never an English defect — it was a thin table in both packs, and English's was
   thinner (434 phrases against Spanish's 729).

2. **The tool selector reads the sentence that CLOSES the request, not the request.** He asked for a Neil
   Armstrong video across four fragments; three were ruled ambient and the turn that reached the model was
   «Do you understand?». That names nothing, so `media` was trimmed and `play_video` was absent from the
   catalog of the very turn asking for a video — leaving `escalate_to_slowbrain` as the only door.

Both fixes are language-neutral by construction: the seeds land in BOTH packs, and the carried layer reads
whatever words the window holds.
"""
import json
from pathlib import Path

import pytest

from nucleo.actionmap.normalize import normalize
from nucleo.actionmap.store import _pack_entries


@pytest.fixture
def trimming_on(monkeypatch):
    """The `carried` layer only means anything while the catalog is TRIMMED, and V2-726 F0 turned
    trimming off by default on 2026-09-20: sending the whole catalog every turn costs 35% LESS,
    because a catalog that changes shape invalidates DeepSeek's prefix cache (72 measured calls;
    see `tool_selection.enabled`). The layer and its window are untouched, so these cases switch
    the trim on to describe them. On what ships, the media tool is never trimmed off a media turn
    for the stronger reason that nothing is trimmed at all."""
    monkeypatch.setenv("ZAELAR_TOOL_SELECTION", "1")

SEEDS = Path(__file__).resolve().parents[4] / "i18n" / "genesis"


def _table(lang: str) -> dict:
    pack = json.loads((SEEDS / lang / "actionmap.json").read_text(encoding="utf-8"))
    return {normalize(e["phrase"]): e["action"] for e in _pack_entries(pack)}


# ── 1 · the sentences from his own session, and their Spanish twins ──────────────────────────────────
@pytest.mark.parametrize("lang,phrase,expected", [
    # the literal turn that spawned a Brain Worker
    ("en", "can you open my agenda", {"do": "show_widget", "widget": "agenda"}),
    ("en", "open my agenda", {"do": "show_widget", "widget": "agenda"}),
    ("en", "show me my agenda", {"do": "show_widget", "widget": "agenda"}),
    # «Close the music» — answered «Paused.» three times, because only «stop the music» was in the table
    ("en", "close the music", {"do": "close_widget", "widget": "musica"}),
    ("en", "close the music widget", {"do": "close_widget", "widget": "musica"}),
    ("en", "close the music player", {"do": "close_widget", "widget": "musica"}),
    # «Now show me the music widget, not the video widget» — the video card opened instead
    ("en", "show me the music widget", {"do": "show_widget", "widget": "musica"}),
    ("en", "close the video widget", {"do": "close_widget", "widget": "youtube"}),
    # the SAME holes in Spanish: this was never an English defect
    ("es", "abre mi agenda", {"do": "show_widget", "widget": "agenda"}),
    ("es", "abreme la agenda", {"do": "show_widget", "widget": "agenda"}),
    ("es", "puedes abrir mi agenda", {"do": "show_widget", "widget": "agenda"}),
    ("es", "cierra la musica", {"do": "close_widget", "widget": "musica"}),
    ("es", "ensename el widget de musica", {"do": "show_widget", "widget": "musica"}),
    ("es", "cierra el widget de video", {"do": "close_widget", "widget": "youtube"}),
])
def test_the_order_is_resolved_without_a_model(lang, phrase, expected):
    assert _table(lang).get(normalize(phrase)) == expected


def test_stopping_the_music_still_pauses_it(monkeypatch):
    """The counterweight to «close the music» → close the card: the order that means PAUSE must not have
    moved with it."""
    assert _table("en")[normalize("stop the music")]["action"] == "pause"
    assert _table("es")[normalize("para la musica")]["action"] == "pause"


def test_one_phrase_still_holds_one_opinion():
    """A phrase expanded from two grids with two different actions is a coin toss at import order. The
    messaging LENS grid owns «my messages» (it opens the card AND sets the lens), so the show grid must not
    claim it — this is the collision the first draft of this change introduced and this case caught."""
    for lang in ("es", "en"):
        pack = json.loads((SEEDS / lang / "actionmap.json").read_text(encoding="utf-8"))
        seen: dict[str, str] = {}
        for e in _pack_entries(pack):
            ph, a = normalize(e["phrase"]), json.dumps(e["action"], sort_keys=True)
            assert seen.get(ph, a) == a, f"[{lang}] {ph!r} maps to two different actions"
            seen[ph] = a


def test_every_widget_reachable_in_one_language_is_reachable_in_the_other():
    """The measured asymmetry, frozen: on 2026-09-12 the English pack held 434 phrases against Spanish's
    729, and what that costs is not phrasing — it is a widget the operator cannot open by voice at all."""
    def widgets(lang: str, do: str) -> set[str]:
        return {a.get("widget") for a in _table(lang).values()
                if isinstance(a, dict) and a.get("do") == do and a.get("widget")}
    for do in ("show_widget", "close_widget"):
        es, en = widgets("es", do), widgets("en", do)
        assert es == en, f"{do}: only in es {sorted(es - en)} · only in en {sorted(en - es)}"


# ── 2 · the selector sees the REQUEST, not only the sentence that closes it ──────────────────────────
def _tools(*names):
    return [{"type": "function", "function": {"name": n}} for n in names]


CATALOG = ("escalate_to_slowbrain", "web_search", "recall", "show_widget", "play_video", "play_music")


def _names(out):
    return {(t.get("function") or {}).get("name") for t in out}


# ── 3 · what the carried text is built from ──────────────────────────────────────────────────────────
WINDOW = [
    {"role": "user", "text": "close all widgets"},
    {"role": "assistant", "text": "Now playing a music video for you"},
    {"role": "user", "text": "I wanna see a video of Neil Armstrong"},
    {"role": "user", "text": "Do you understand?"},
]


# ── 4 · the wiring: a decision nobody calls is a decision that does not exist ────────────────────────
def _source_without_comments(path: Path) -> str:
    """Comment-stripped, per the V2-573 trap: a guard that matches the COMMENT explaining a call stays
    green after the call itself is deleted."""
    out = []
    from tests import voice_turn_source     # V2-778 F1: the voice turn is read whole, moved blocks included
    for line in voice_turn_source.read(path).splitlines():
        s = line.split("#", 1)[0]
        out.append(s)
    return "\n".join(out)
