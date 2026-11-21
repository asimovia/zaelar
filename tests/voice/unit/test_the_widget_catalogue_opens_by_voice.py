"""V2-761 — «ábreme la lista de widgets / el catálogo de apps / qué widgets tengo» opens the wall's Apps tab.

The operator: *«el usuario solo va a poder abrir esto por voz… ábreme la lista de widgets, ábreme la lista de
apps, ábreme el catálogo de apps, ábreme el catálogo de widgets, dime qué widgets tengo disponibles»* — and it
must answer to «apps» and «widgets» alike.

There are three doors a voice order can come through, and each is pinned here:

1. the ACTION MAP (whole-utterance phrases, no model) — the seed packs carry the phrases and validate;
2. the model's `show_panel` tool — its description names the tab and the canon maps the argument onto it;
3. the model's `show_widget` tool (it picks the wrong one: «apps» sounds like a thing to show) — the name
   resolver names the SYSTEM surface `apps`, and the provider routes that surface
   to the panel instead of asking «which widget?».

And the neighbours that must NOT move, because a descriptor that steals a word from its neighbour is a defect
this repo has paid for three times: «abre la aplicación de música» still opens the music card, «vuelve al
catálogo» (the video card's own words) still names nothing, «abre whatsapp» still opens messaging.
"""
from __future__ import annotations


import json
from pathlib import Path

import pytest

from nucleo.actionmap import executor
from nucleo.self.catalogs import canon_panel
from widgets import runtime

ENGINE = Path(__file__).resolve().parents[3]


# ── door 3: the name resolver ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("phrase", [
    "ábreme las apps", "abre la lista de widgets", "ábreme el catálogo de widgets", "abre el catálogo de apps",
    "dime qué widgets tengo disponibles", "abre mis aplicaciones", "open my widgets", "open the app catalog",
    # his exact words in session 952923e3 (2026-09-24), each of which ended in «no tengo un catálogo»:
    "Enséñame el catálogo de aplicaciones.", "Vale, enséñame el catálogo de widgets.",
    "Vale, ábreme la lista de widgets customizados.", "¿Qué APPs tengo customizadas?",
    "O los widgets. Ábreme esa lista.",
])
def test_the_catalogue_phrases_name_the_apps_surface(phrase):
    res = runtime.identify(phrase)
    assert res["system"] == "apps" and res["match"] is None, f"{phrase!r} resolved to {res}"


@pytest.mark.parametrize("phrase,widget", [
    ("abre la aplicación de música", "musica"), ("abre el widget de música", "musica"),
    ("abre whatsapp", "mensajeria"), ("ábreme el vídeo", "youtube"),
])
def test_a_named_widget_is_never_stolen_by_the_catalogue(phrase, widget):
    res = runtime.identify(phrase)
    assert res["match"] == widget and res["system"] is None, f"{phrase!r} resolved to {res}"


@pytest.mark.parametrize("phrase,tab", [
    ("Vale, ábreme la lista de widgets customizados.", "apps-custom"), ("¿Qué APPs tengo customizadas?", "apps-custom"),
    ("abre mis widgets personalizados", "apps-custom"), ("Enséñame el catálogo de aplicaciones.", "apps"),
])
def test_asking_for_HIS_widgets_opens_the_custom_sub_tab(phrase, tab):
    from nucleo.self.catalogs import apps_tab
    assert apps_tab(phrase) == tab


def test_the_models_catalogue_says_which_widgets_are_his():
    """«Las apps personalizadas que tengas tú hechas no me salen en la lista que veo» — the fact existed
    (`origin`, `forked_from`) and never reached the model. The row now carries it."""
    from widgets import brief, selection
    cat = [{"id": "youtube", "whenToUse": "vídeo", "origin": "user", "forked_from": {"origin": "builtin"}},
           {"id": "canvas-shows-day", "whenToUse": "mi día", "origin": "user"},
           {"id": "musica", "whenToUse": "música"}]
    real = selection.candidates
    selection.candidates = lambda *a, **k: [{"w": w} for w in cat]
    try:
        out = brief.for_prompt([], [], "")
    finally:
        selection.candidates = real
    rows = {ln.split(" — ")[0].strip("- "): ln for ln in out.splitlines() if ln.startswith("- ")}
    assert "custom (su copia de la de sistema)" in rows["youtube"]
    assert "custom (creada por él)" in rows["canvas-shows-day"]
    assert "custom" not in rows["musica"]


def test_the_video_cards_own_catalogue_is_not_this_one():
    assert runtime.identify("vuelve al catálogo")["system"] is None


@pytest.mark.parametrize("sid,phrase,tab", [
    ("apps", "O los widgets. Ábreme esa lista.", "apps"),
    ("apps", "Vale, ábreme la lista de widgets customizados.", "apps-custom"),
    ("chat", "abre el chat", "chat"), ("config", "abre los ajustes", ""), (None, "hola", ""),
])
def test_only_a_tab_of_the_wall_becomes_a_panel_event(sid, phrase, tab):
    from nucleo.self.catalogs import wall_tab_for
    assert wall_tab_for(sid, phrase) == tab


# ── door 2: the show_panel tool ────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("arg,tab", [
    ("apps", "apps"), ("widgets", "apps"), ("lista de widgets", "apps"), ("catálogo de apps", "apps"),
    ("aplicaciones", "apps"), ("mis widgets custom", "apps-custom"), ("apps-custom", "apps-custom"),
    ("conectores whatsapp", "conectores"), ("conectores", "conectores"), ("programadas", "programadas"),
])
def test_the_panel_argument_lands_on_the_apps_tab(arg, tab):
    assert canon_panel(arg) == tab


# ── door 1: the action map ─────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("lang,phrase", [("es", "abreme la lista de widgets"), ("es", "abre el catalogo de apps"),
                                         ("es", "que widgets tengo disponibles"), ("en", "open the widget catalog"),
                                         ("en", "what apps do i have")])
def test_the_seed_packs_carry_the_phrases_and_they_execute(lang, phrase):
    pack = json.loads((ENGINE / f"i18n/genesis/{lang}/actionmap.json").read_text(encoding="utf-8"))
    hit = next((e for e in pack["entries"] if e.get("phrase") == phrase), None)
    assert hit, f"{lang}: no seed for {phrase!r}"
    assert hit["action"] == {"do": "show_panel", "tab": "apps", "action": "open"}
    assert executor.validate(hit["action"]) == "", "the executor refuses the apps tab"


@pytest.mark.parametrize("lang,phrase,tab", [
    ("es", "quiero ver las apps", "apps"), ("es", "ponme la lista de apps", "apps"), ("es", "llevame a las apps", "apps"),
    ("es", "dime que widgets tengo disponibles", "apps"), ("es", "que apps tengo customizadas", "apps-custom"),
    ("es", "abreme mis widgets personalizados", "apps-custom"),
    ("en", "bring up the apps", "apps"), ("en", "i want to see the apps", "apps"),
    ("en", "open my custom widgets", "apps-custom"), ("en", "what custom apps do i have", "apps-custom"),
])
def test_what_the_lane_no_longer_takes_is_seeded_in_both_languages(lang, phrase, tab):
    """V2-903 a6: the lane needs an open order now, and its verb grammar is Spanish — what it took on the noun alone,
    and every English phrase, is DATA in the action map's seeds (custom tab included), never a new regex."""
    pack = json.loads((ENGINE / f"i18n/genesis/{lang}/actionmap.json").read_text(encoding="utf-8"))
    hit = next((e for e in pack["entries"] if e.get("phrase") == phrase), None)
    assert hit and hit["action"] == {"do": "show_panel", "tab": tab, "action": "open"}, (lang, phrase)
    assert executor.validate(hit["action"]) == ""
    assert pack["version"] >= 19, "new seeds under an old version reach no existing install"


def test_the_packs_were_versioned_so_existing_installs_import_them():
    """A pack only re-imports on a version bump (`store.seed`) — new phrases in an old version reach nobody."""
    for lang in ("es", "en"):
        pack = json.loads((ENGINE / f"i18n/genesis/{lang}/actionmap.json").read_text(encoding="utf-8"))
        assert pack["version"] >= 10, f"{lang}: the pack carries the apps phrases under an old version"

