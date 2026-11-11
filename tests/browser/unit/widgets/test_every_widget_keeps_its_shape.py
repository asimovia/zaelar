"""Every shipped widget keeps its shape, and none grows back (refactor2710-12 T-05).

The shape: no Python file over 400 lines, no client module (`widget.js` or `js/*.js`) over 600 — a file over that
splits into a folder of concerns (`data.py` stays the contract, `js/` holds the client's parts). The files that were
over before this pass and are owned by a later one are listed with the size they had: they may only shrink. And each
widget's total, Python and client, may only shrink from what was measured when the shape landed (2026-10-28).
"""
from __future__ import annotations

from pathlib import Path

ENGINE = Path(__file__).resolve().parents[4]
WIDGETS = ENGINE / "widgets"
PY_MAX, JS_MAX = 400, 600

#: Over the shape today, owned by a later pass. Empty since refactor2710-99 split the last nine; only shrink.
GRANDFATHERED: dict[str, int] = {}
#: widget → (Python lines, client lines), measured 2026-10-28; results lowered by V2-831 R9 and R9b (tightening paid
#: for the door flattener and its labels). Lower it when a widget shrinks; never raise it.
# 2026-11-08 (apps principles: a provider is a preference, each app declares a real end state and its next step on unmet, the source can be named — `on_unmet`, `here`, outbox, writes log, set_seq/rev/fetched_at): agenda +196/+0, archivos +54/+0, contactos +25/+0, documento +19/+0, fotos +60/+0, imagenes +6/+0, map +34/+0, markets +13/+0, mensajeria +123/+0, musica +20/+0, results +35/+0 (mensajeria +3 Python is another session's, measured on main).
CEILINGS = {
    "results": (3135, 1618),  # +25 py / +43 js 2026-11-11 V2-877 #9 (4.466): the sheet paints only what he reads and fits the hand; +100 py / −2 js 2026-11-09 V2-868 D4 (4.416): a worker's row says where it was found or lands in Rejected (`results/provenance.py`, the screen at the sheet's one door); # +4 2026-11-08 V2-861 (5.73): `choose` takes a row's number or words through `detail`'s finder, the refusal shared (`find.no_row`); +2 V2-840 H5 (12.840): a criteria change on a finished errand's sheet is handed to the circuit (`nucleo/circuit/reopen.py`); +301 V2-840 H4 (7.87): every row brings its picture — page cover backfill + local copy, in the background, the gap counted at the door (`results/media.py`); +3 V2-837×V2-838 merge (the door event and the rule read meet in one module); +53 V2-838 (12.838): the door reads his standing exclusions, names the rule, rechecks every sheet when one is written; +86 V2-837 G10 (7.86): one door event per push with its counts (`results/door_event.py`); +68 V2-835 T1/T2 (12.835, 12.837): a declared exclusion at the door, and the pool a present narrows from (results/pool.py); +13 V2-831 audit A7 (4.331): a fact keeps its key, labelled from the pack on every read; +8 audit A8 (4.322): a row with a link or picture of its own is kept (modularity §8)
    "agenda": (5606, 1943),  # +61 js 2026-11-11 V2-876 P-30…P-32 (4.462): the phone card — one control row, wrapping titles, the opening hour, `fmtWhen`, the bell as a target; +42 py 2026-11-10 V2-872 F2 (2.843): a series notice hands over to the next occurrence right after it rings and at start (`reminders.py`), so an engine woken for one notice never sleeps through the next; +53 2026-11-06 (4.392): an appointment's notice follows its row — the Google tick fetches without the lock and merges under it (`service.fetch`/`merge`), the asked notice rings on the row written (`_row`), the tick sweeps notices no row carries (`reminders.drop_orphans`); +14/−1 V2-834 T36 (S1 audit H7): a meeting is answered as seen — the row minus its declared bookkeeping (`details.as_seen`), one function for open_meeting and show_day instead of two hand-picked subsets; +12/+3 V2-831 T-19 pass 9 Z1 (4.334): their answer needs a source (modularity §8); refactor2710-06 T-06: the notice bounds MOVED in (agenda/notice.py), flash −1 755
    # +21 archivos / +15 fotos 2026-11-08 V2-861 (5.73): the explorer numbers its rows and opens one by number or name
    # (`_named_entry`), the gallery numbers what a search found.
    "archivos": (1140, 1127), "clock": (19, 82), "contactos": (3069, 1626),  # +4 V2-857 phase 2: a person is a rule's subject (`digest.people_named`); +142/+308 V2-854 F5 (4.390, 4.391): the card shows his groups (rail, strip, selection), aliases, relation and agents (`js/people.js`), a relation files a person in its native group, the WhatsApp mirror derived, a message to a group handed to the conversation (`message_group`); +378 V2-854 F1 (2.1500): his groups as rows with an id (`groups.py`, `group_actions.py`), linked agents, the derived unclassified, where a word came from; +10 V2-850 (4.358): people_named carries what his chats call a person; +3 V2-850 (4.358): the record names its chat name; +20 V2-850 (2.1010): «which Raquel?» answered with the closest three; +33 V2-849 (4.356): the digest, people_named and ref_index closest first; +54 V2-849 (4.355): aliases and relation — `set_alias`, the declared `relations`, schema v3
   
    # map +15 py / +66 js, markets +27 js 2026-11-11 V2-877 #8 (4.465): the base map always drawn (his area or the world), corner zoom and one-finger pan; the markets empty page with its field and the phone sizes
    "documento": (473, 371), "fotos": (317, 259), "imagenes": (387, 239), "map": (297, 228),  # documento +47 V2-862 (4.413): a report is KEPT at its end (library file + the task copy) and restored by the reopen door; imagenes +18 V2-834 T37 (S1 audit H8): the picture in front is in its digest
    "markets": (247, 168),  # +6 py 2026-11-10 V2-873 (4.218): a `range` that names no period is refused with its field
    "mensajeria": (5858, 2722),  # +10 py 2026-11-10 V2-872 F2 (2.842): the durable `taken` ledger is asked BEFORE the classifier (`owner/apply.py`), so a re-delivered message never reaches the model twice; +10 py 2026-11-09 #208 (V2-850): a refused send closes its check, a who-question leaves the open conversation; +5 V2-857 phase 6: each automatic reply is read by the one act door with the person it goes to (`directory.subject_of`, shared with the errand mandate); +100 V2-852/857: an act's dry refusal is readable before any question (`would_refuse`, `draft_named`) and the autoresponder yields to the message's owner (`_owned_elsewhere`); +19 V2-851 F5b (2.1211): a send that names nobody is an ASK_FACT at the door, and the card declares the missing fact (`needs_of`) so a gate asks the fact, not his consent; +1 V2-850 (2.1010): the which-question carries its names (`say_args`);  # +83 V2-847/V2-849 (2.1009, 4.354, 4.355): who a reply to a number reaches (`recipients_of`, `reply_target`), a feed dropped from an older store, the «which one?» question closest first with what tells them apart, his answer kept
    "musica": (1929, 2695),  # +47/+14 2026-11-10 V2-873 (4.440): «here» is written by the page player's report; the card reports its player's refusal (`player_error`, `_ytRefused`), the refused song is skipped and our pick moves on; +37/+27 2026-11-08 (5.74): the card shows only a session that is ours — blank when Spotify plays elsewhere and it was never ours, locked with take control / let it be when ours was taken (`now_playing._ours_taken`, `release`, `js takenBy`), and the bar always says where it sounds; +3 2026-11-08 (5.74): a refusal carries its provider and the device it names (`actions._a_playback`); +20/+40 2026-11-08 (5.74): Spotify sounding on another device of the account — the card is told where (`now_playing._elsewhere`), `take_over` is declared, and the strip asks twice before taking control (`js/browse.js`, its style); +123 2026-11-08 V2-861 (5.72): a request said to the agent opens the card blank on its search and keeps the numbered candidates with their owners (`browse.begin_search/after_play`), `play_result` picks one by number, name or owner, the digest names them; +22/+15 2026-11-08 V2-860 T2.4 (5.71): the card's search ranks through the media door and hands back what can be played, a tapped uri takes `music.play_whole`, the «Podcasts» shelf; +2/+810 4544306d9 (2026-11-02, notes.md «the responsive pass»): one app with a desktop face and a phone face — the arrangement read from the card's box (`js/layout.js`, `js/style_layout.js`), bottom nav, mini-player, the queue as drawer/sheet, a `collection` face; presentation only, every file inside its shape
    "navegador": (6109, 187),  # +14 2026-11-09 V2-836 (#256): the browser launches through his tunnel's local forwarder while it is up (`navegador/owner_page.py` `_egress_args`); # +308 2026-11-09 V2-575 P3 (4.420): the relay transport to his daemon (`navegador/owner_login/relay_link.py`), the session import that survives a relaunch (`owner_page.py`) and the phone block (`authenticate.py`); # +25 2026-11-09 V2-868 D3 (2.1656): `awaiting_login`/`blocked` park the errand as a wait (`tasks/fields.py`, `auth_memory.py` answers it on a confirmed sign-in); # +186 V2-575 P2 (2026-11-09): the sign-in window on the local daemon — the loopback transport, the backend switch and the window's watcher (`navegador/owner_login/daemon_link.py`); +107 V2-837 G6 (7.85): every navigation's status, time, size and wall (`navegador/page_outcome.py`); +68 V2-835 T5 (4.351/4.352): a login wait ends with its task/tab/time, a fallen-back launch is labelled and blocked, the wall note informs instead of offering a sign-in
    "search": (150, 132), "timer": (127, 314), "youtube": (3394, 1754),  # search +23 py / +39 js 2026-11-11 V2-877 #12 (4.467): a search card shows its own state; youtube +17 js 2026-11-11 V2-876 P-24 (4.471): the phone player; timer +16 js / clock +16 js 2026-11-11 V2-876 P-33 (4.463/4.464): the timer's own starts, the clock's zone by name; +15 js 2026-11-10 V2-873 (4.441): the card and its own <video> report what they play (`ytState`)
     # +10 V2-833 F0: the page lookups report what they got (map, markets, search: +2 each)
}


def _lines(p: Path) -> int:
    return p.read_text(encoding="utf-8").count("\n") + 1


def _widgets() -> dict[str, Path]:
    return {d.name: d for d in sorted(WIDGETS.iterdir())
            if d.is_dir() and not d.name.startswith(("_", ".")) and (d / "manifest.json").is_file()}


def _files(d: Path):
    for p in sorted(d.rglob("*")):
        if p.suffix in (".py", ".js") and "__pycache__" not in p.parts and "_data" not in p.parts:
            yield p


def _over(sizes: dict[str, int]) -> list[str]:
    bad = []
    for rel, n in sorted(sizes.items()):
        cap = GRANDFATHERED.get(rel, PY_MAX if rel.endswith(".py") else JS_MAX)
        if n > cap:
            bad.append(f"{rel}: {n} > {cap}")
    return bad


def _sizes() -> dict[str, int]:
    return {p.relative_to(WIDGETS).as_posix(): _lines(p) for d in _widgets().values() for p in _files(d)}


def _totals() -> dict[str, tuple[int, int]]:
    out = {}
    for wid, d in _widgets().items():
        py = sum(_lines(p) for p in _files(d) if p.suffix == ".py")
        out[wid] = (py, sum(_lines(p) for p in _files(d) if p.suffix == ".js"))
    return out


def test_no_widget_file_is_over_its_shape():
    assert not _over(_sizes()), "split it into a folder of concerns: " + "; ".join(_over(_sizes()))


def test_no_widget_grows_and_every_widget_has_its_number():
    totals = _totals()
    assert set(totals) == set(CEILINGS), f"a widget without a ceiling (or one gone): {set(totals) ^ set(CEILINGS)}"
    grew = [f"{w}: {totals[w]} > {CEILINGS[w]}" for w in totals
            if totals[w][0] > CEILINGS[w][0] or totals[w][1] > CEILINGS[w][1]]
    assert not grew, grew


def test_a_grandfathered_file_only_shrinks_and_leaves_the_list_when_it_fits():
    sizes = _sizes()
    stale = [rel for rel in GRANDFATHERED if rel not in sizes or sizes[rel] <= (PY_MAX if rel.endswith(".py") else JS_MAX)]
    assert not stale, f"these fit the shape now (or are gone): take them off GRANDFATHERED: {stale}"


def test_disarm_an_oversize_file_is_named(monkeypatch):
    assert _over({"x/data.py": PY_MAX + 1, "x/js/a.js": JS_MAX}) == [f"x/data.py: {PY_MAX + 1} > {PY_MAX}"]
    monkeypatch.setitem(GRANDFATHERED, "x/old.py", 634)
    assert _over({"x/old.py": 635}) == ["x/old.py: 635 > 634"]
