"""V2-875 — the person's permission switches decide what the agent keeps.

  · location: a screen's fix becomes the state's `here` (rounded to ~1 km, named by reverse geocoding), only with the
    switch on; switching it off forgets it; the prompt says where he is now, or names the gap;
  · files: the daemon's folder doors refuse a new folder while the switch is off;
  · observability: nothing of the agent's events reaches disk while it is off (capture and live screens untouched);
  · obfuscate: what is kept carries tags — [PERSON] [PLACE] [NAME] [PHONE] [EMAIL] [DATE] [NUMBER] — never the data,
    and the structural fields stay as they were.
"""
from __future__ import annotations

import json
import time

import pytest

from config import privacy, v2
from observability import persist, pii


@pytest.fixture()
def switches(tmp_path, monkeypatch):
    monkeypatch.setattr(v2, "_PATH", tmp_path / "v2.json")
    privacy._cache.update(stamp=False, val=None)

    def set_(**kw):
        v2.set("privacy", kw)
        privacy._cache.update(stamp=False, val=None)
    yield set_
    privacy._cache.update(stamp=False, val=None)


NAMES = {"ana": "[PERSON]", "barcelona": "[PLACE]", "lopez": "[PERSON]", "maria": "[PERSON]"}


def test_every_switch_starts_on() -> None:
    assert v2._DEFAULTS["privacy"] == {"location": True, "files": True, "observability": True, "obfuscate": True}


@pytest.mark.parametrize("said, kept", [
    ("voy a Barcelona mañana con Ana María López.", "voy a [PLACE] mañana con [PERSON]."),
    ("Llámame al +34 612 345 678 o a ana@example.org", "Llámame al [PHONE] o a [EMAIL]"),
    ("Barcelona está lejos. Mañana vemos a Pedro en Sevilla.", "[PLACE] está lejos. Mañana vemos a [NAME] en [NAME]."),
    ("I went to Paris with John on 12/05/2026", "I went to [NAME] with [NAME] on [DATE]"),
    ("reserva para 4 el viernes", "reserva para 4 el viernes"),
])
def test_personal_data_becomes_tags(said: str, kept: str) -> None:
    assert pii.tag(said, NAMES) == kept


def test_the_structure_of_an_event_is_never_rewritten() -> None:
    ev = {"kind": "transcript", "label": "Heard", "dev": "mobile:Ab", "trace": "T1", "text": "con Ana en Barcelona",
          "window": [{"role": "user", "text": "Llama a Ana"}]}
    out = pii.tag_obj(ev, NAMES)
    assert {k: out[k] for k in ("kind", "label", "dev", "trace")} == {"kind": "transcript", "label": "Heard",
                                                                      "dev": "mobile:Ab", "trace": "T1"}
    assert out["text"] == "con [PERSON] en [PLACE]" and out["window"][0]["text"] == "Llama a [PERSON]"
    assert ev["text"] == "con Ana en Barcelona", "the live event is a copy's source, never modified"


def test_what_is_stored_follows_the_switches(switches, monkeypatch) -> None:
    monkeypatch.setattr(pii, "known", lambda ttl_s=60.0: NAMES)
    ev = {"kind": "transcript", "text": "voy a Barcelona"}
    assert json.loads(persist.line(ev))["text"] == "voy a [PLACE]"            # default: kept, tagged
    switches(obfuscate=False)
    assert json.loads(persist.line(ev))["text"] == "voy a Barcelona"
    switches(observability=False)
    assert persist.line(ev) is None                                           # nothing reaches disk


def test_the_events_table_keeps_nothing_with_observability_off(switches, monkeypatch) -> None:
    from bus import log
    monkeypatch.setattr(pii, "known", lambda ttl_s=60.0: NAMES)
    rec = {"topic": "observer", "payload": {"kind": "transcript", "text": "con Ana"}}
    assert log._stored([rec])[0]["payload"]["text"] == "con [PERSON]"
    assert rec["payload"]["text"] == "con Ana", "the other sinks share the payload: never rewritten in place"
    switches(observability=False)
    assert log._stored([rec]) == []


def test_a_screens_location_becomes_the_state_rounded_and_named(switches, monkeypatch) -> None:
    from memory import api as memory
    from nucleo import where
    written = {}
    monkeypatch.setattr(memory, "set_state", lambda f: written.update(f) or f)
    monkeypatch.setattr(where, "reverse", lambda lat, lon, lang="": {"place": "Barcelona", "region": "Catalonia",
                                                                      "country": "Spain"})
    out = where.report(41.387397, 2.168568, 12, "mobile:Ab")
    assert out["ok"] and written["here"]["place"] == "Barcelona"
    assert (written["here"]["lat"], written["here"]["lon"]) == (41.39, 2.17), "never finer than ~1 km"
    assert written["here"]["accuracy"] >= 1000
    switches(location=False)
    assert where.report(41.38, 2.16) == {"ok": False, "reason": "off"}


def test_the_prompt_says_where_he_is_now_or_names_the_gap() -> None:
    from nucleo import where
    now = {"here": {"place": "Barcelona", "region": "Catalonia", "country": "Spain", "at": time.time() - 240}}
    (line,) = where.prompt_lines(now)
    assert "Barcelona, Catalonia, Spain" in line and "4 min" in line
    stale = {"here": {**now["here"], "at": time.time() - where.FRESH_S - 1}}
    assert "NO SABES" in where.prompt_lines(stale)[0]
    assert where.prompt_lines({**stale, "location": "Soria"}) == []


def test_turning_location_off_forgets_where_he_is(switches, monkeypatch) -> None:
    import asyncio
    import json as _json

    from memory import api as memory
    from server import config_api
    cleared = []
    monkeypatch.setattr(memory, "state", lambda: {"here": {"place": "Barcelona"}})
    monkeypatch.setattr(memory, "set_state", lambda f: cleared.append(f) or f)
    # The route's function itself — booting the whole app here would leave its background threads running.
    r = asyncio.run(config_api.set_v2({"section": "privacy", "patch": {"location": False}}))
    assert _json.loads(r.body)["ok"] and {"here": None} in cleared


def test_the_files_switch_refuses_a_new_folder(switches) -> None:
    from server import daemon_api
    assert daemon_api._files_off() is None
    switches(files=False)
    assert daemon_api._files_off().status_code == 403
