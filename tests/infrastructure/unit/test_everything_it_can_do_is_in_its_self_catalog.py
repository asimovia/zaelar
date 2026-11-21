"""Everything the agent can do is in its catalogue of itself (V2-932).

Measured 2026-11-17: with the camera's «look at me» on, the agent said «te veo» and nine seconds later «no tengo cámara».
It had no description of itself: a question about what it is or how to do something of its own was answered by guess.
The answer is `about_self` over `nucleo/self/catalog.json`, and a catalogue only works while it is COMPLETE — a new act,
tool, voice-named surface, settings section, built connector or shipped widget that no entry covers is a thing the
agent cannot explain. This test is that completeness, read off the engine's own declarations:

  · `nucleo/acts/self_controls.ACTS`              → `act:<id>`
  · the tool catalogue (`router.TOOLS`)            → `tool:<name>`
  · the voice-named native surfaces (`widgets/system_surfaces.py`, the JS's mirror) → `surface:<id>`
  · the Settings sections and tabs (`frontend/app/components/ConfigPanel.js` SECTIONS + TABS) → `settings:<id>`
  · `connectors/catalog/*.json` with `state: built` → `connector:<id>`
  · the shipped widget manifests (`widgets/<id>/manifest.json`) → `widget:<id>`

Each is covered by some entry or listed in `NOT_USER_FACING`, which only shrinks. Every covered id exists, every entry
has its words in English and Spanish, every live fact it needs has a reader, and the tool's schema stays under its cap.

Disarm: add an act to `self_controls.Act` → `test_every_capability_is_covered` names it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]

#: Declared ids no person asks about. SHRINK-ONLY: a new entry here needs the reason beside it.
NOT_USER_FACING = {
    "tool:not_understood",   # the turn's own «I did not understand» signal, answered with one line that asks him
}
NOT_USER_FACING_MAX = 1

#: The `about_self` schema's ceiling in estimated tokens (`fast_client.est_tokens`): it is paid on every turn.
TOOL_TOKENS_MAX = 190

_FIELDS = ("what", "voice", "button", "not")


def _js_ids(const: str) -> set[str]:
    js = (ENGINE / "frontend" / "app" / "components" / "ConfigPanel.js").read_text(encoding="utf-8")
    block = re.search(rf"const {const} = \[(.*?)\];", js, re.S)
    assert block, f"ConfigPanel.js no longer declares {const}"
    return set(re.findall(r'id:\s*"([^"]+)"', block.group(1)))


def _capabilities() -> set[str]:
    from nucleo.acts import self_controls
    from nucleo.flash import router
    from widgets import system_surfaces
    ids = {f"act:{a}" for a in self_controls.ACTS}
    ids |= {f"tool:{t['function']['name']}" for t in router.TOOLS}
    from nucleo.conversation_host import acts as _host     # the conversation manager's reads and acts (INI-078)
    ids |= {f"tool:{t.name}" for t in _host.HostTools().catalog()}
    ids |= {f"surface:{s}" for s in system_surfaces.SYSTEM_SURFACES}
    ids |= {f"settings:{s}" for s in _js_ids("SECTIONS") | _js_ids("TABS")}
    for p in sorted((ENGINE / "connectors" / "catalog").glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        if d.get("state") == "built":
            ids.add(f"connector:{d.get('id') or p.stem}")
    for p in sorted((ENGINE / "widgets").glob("*/manifest.json")):
        if not p.parent.name.startswith("_"):
            ids.add(f"widget:{json.loads(p.read_text(encoding='utf-8')).get('id') or p.parent.name}")
    return ids


def _covered() -> dict[str, str]:
    from nucleo.self import about
    out: dict[str, str] = {}
    for e in about.catalog():
        for c in e.get("covers") or ():
            assert c not in out, f"«{c}» is covered twice ({out[c]} and {e['id']}): one entry answers for it"
            out[c] = e["id"]
    return out


def test_every_capability_is_covered():
    missing = sorted(_capabilities() - set(_covered()) - NOT_USER_FACING)
    assert not missing, ("the agent can do these and cannot explain them — add each to an entry's `covers` in "
                         f"nucleo/self/catalog.json (and its words in i18n/genesis/*/self.json): {missing}")


def test_every_covered_id_exists():
    ghosts = sorted((set(_covered()) | NOT_USER_FACING) - _capabilities())
    assert not ghosts, f"the catalogue covers ids the engine does not declare (renamed or removed?): {ghosts}"
    assert not NOT_USER_FACING & set(_covered()), "an id is both covered and declared not user-facing"


def test_the_not_user_facing_list_only_shrinks():
    assert len(NOT_USER_FACING) <= NOT_USER_FACING_MAX, "NOT_USER_FACING grew: cover the new id in an entry instead"
    assert NOT_USER_FACING_MAX - len(NOT_USER_FACING) == 0, "NOT_USER_FACING shrank: lower NOT_USER_FACING_MAX"


def test_every_entry_has_its_words_in_english_and_spanish():
    from i18n import packs
    from nucleo.self import about
    ids = about.topics()
    assert len(ids) == len(set(ids)), "two entries share an id"
    for code in packs.PRESET:
        pack = packs.preset("self", code)
        topics = pack.get("topics") or {}
        assert set(topics) == set(ids), f"{code}/self.json topics differ from the catalogue: {set(topics) ^ set(ids)}"
        for tid in ids:
            lacking = [f for f in _FIELDS if not str((topics[tid] or {}).get(f) or "").strip()]
            assert not lacking, f"{code}/self.json «{tid}» lacks {lacking}"
        assert all(str((pack.get("live") or {}).get(k) or "").strip() for k in ("camera", "face")), code


def test_every_needed_fact_has_its_reader():
    from nucleo.self import about, snapshot
    for n in about.declared_needs():
        assert callable(getattr(snapshot, n, None)), f"«{n}» is needed by an entry and snapshot.py has no reader"


def test_the_tool_offers_exactly_the_catalogue_and_stays_small():
    from nucleo.flash import router
    from nucleo.llm.fast_client import est_tokens
    from nucleo.self import about
    tool = next(t for t in router.TOOLS if t["function"]["name"] == "about_self")
    assert tool["function"]["parameters"]["properties"]["topic"]["enum"] == about.topics()
    assert "about_self" in router.FAMILIES["memory"], "a question announces nothing: the tool is never trimmed"
    n = est_tokens(len(json.dumps(tool, ensure_ascii=False)))
    assert n <= TOOL_TOKENS_MAX, f"about_self costs {n} tokens on every turn (cap {TOOL_TOKENS_MAX})"
