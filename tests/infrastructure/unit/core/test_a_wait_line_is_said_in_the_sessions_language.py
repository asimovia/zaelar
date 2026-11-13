"""A wait line, a filler or a one-word ack is said in the SESSION's language — never a constant of one language (V2-877 #10).

## What was seen

The App Review account, with the interface in English, heard «Un segundo…» and «Te aviso en cuanto lo tenga» next to
«Sure…» and «Let me search…». The pickers (`langs.pick_filler` / `pick_cover` / `pick_ack`) already read the one
place that knows the language (`langs.current_code()`, i.e. `ZAELAR_LANGUAGE`), and the store screenshots were taken
in both languages on the same account, so the mixed fillers were the chat history of two languages. What the search
for the class found is the part no test could see: SHORT spoken lines written as constants in code — «Listo, lo tienes
en la hoja de resultados» (every browser task's ending, spoken as-is in any language), «Hecho.», «Sigo con ello.»,
«Tienes {n} abiertas: ¿cuál cierro…?». The prose ratchet beside this file
(`test_what_the_operator_hears_is_in_his_language.py`) only reads sentences of 25+ characters with three Spanish
stopwords, so a filler is below its floor by construction.

## What is measured here

1. The PACK: every wait/filler/ack key exists, non-empty, in every shipped pack, and the English value is not the
   Spanish one (the «ENERGY» shape of #3, on the spoken side).
2. The PICKERS: with the session in English every one of them answers from the English pack, with Spanish from the
   Spanish pack. Seen RED with `langs.spec()` pinned to one language.
3. The RATCHET, exact instead of heuristic: a string literal in product code that IS a spoken line of the Spanish
   pack, or a literal handed as the fallback of a pack field (`getattr(lang, "data_ack", "Hecho.")`,
   `getattr(...) or "Sigo con ello."`), is that line frozen in one language. The files that still hold one are
   listed, and the list only shrinks — they belong to modules another change owns, named in V2-877 #10.
"""
from __future__ import annotations

import ast
import json
import re
import subprocess
from pathlib import Path

import pytest

from tests.lang import LANGS, speaking

ENGINE = Path(__file__).resolve().parents[4]
GENESIS = ENGINE / "i18n" / "genesis"

#: The spoken wait family: what the mouth says while work starts, runs, is retried or is acknowledged.
FILLER_KEYS = ("fillers", "fillers_action", "fillers_social", "fillers_ack", "covers_widget", "covers_search",
               "covers_recall", "acks", "data_ack", "data_acks", "filler_holding", "filler_errand_taken",
               "filler_still_working", "holding_lines", "filler_waited", "still_on_it", "work_started",
               "mute_lines", "spark_pending", "instances_which_show", "instances_which_close",
               "navegador.done", "navegador.done_on_sheet", "navegador.partial", "navegador.partial_on_sheet",
               "vault_rule.voice_on", "vault_rule.voice_off")

#: Files that still hold a spoken line of one language as a constant. MEASURED; edited DOWNWARD only.
_STILL_HOLDING = {
    "nucleo/flash/post_stream_settle.py",  # «Hecho.» / «Aquí lo tienes.» in the except branches
    "nucleo/turn/wait_lines.py",           # «Sigo con ello.» / «Perdona, ¿me lo repites?» fallbacks
}


def _pack(code: str) -> dict:
    return json.loads((GENESIS / code / "voice.json").read_text(encoding="utf-8"))


def _at(tree: dict, path: str):
    node = tree
    for part in path.split("."):
        node = node.get(part) if isinstance(node, dict) else None
    return node


def _strings(node) -> set[str]:
    if isinstance(node, str):
        return {node.strip()}
    if isinstance(node, list):
        return set().union(*(_strings(x) for x in node)) if node else set()
    if isinstance(node, dict):
        return set().union(*(_strings(v) for k, v in node.items() if not k.startswith("_"))) if node else set()
    return set()


# ── 1 · the pack ──────────────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("key", FILLER_KEYS)
def test_every_wait_line_exists_in_every_pack_and_is_translated(key):
    vals = {code: _at(_pack(code), key) for code in LANGS}
    empty = [c for c, v in vals.items() if v in (None, "", [], {})]
    assert not empty, f"«{key}» is missing or empty in {empty}"
    assert _strings(vals["en"]).isdisjoint(_strings(vals["es"])), \
        f"«{key}»: the English pack holds the Spanish words {_strings(vals['en']) & _strings(vals['es'])}"


# ── 2 · the pickers ───────────────────────────────────────────────────────────────────────────────────────────

def _pickers():
    from i18n import langs
    from nucleo.turn import wait_lines
    from widgets import instances
    from widgets.navegador import owner  # noqa: F401 — the package first: owner_actions is imported through it
    from widgets.navegador import owner_actions
    return {
        "filler": lambda: langs.pick_filler(kind="neutral"),
        "filler_action": lambda: langs.pick_filler(kind="action"),
        "filler_social": lambda: langs.pick_filler(kind="social"),
        "filler_ack": lambda: langs.pick_filler(kind="ack"),
        "cover_search": lambda: langs.pick_cover("search"),
        "cover_recall": lambda: langs.pick_cover("recall"),
        "ack": lambda: langs.pick_ack(),
        "holding": lambda: wait_lines.holding_line([], None),
        # as `nucleo/turn/pipeline_close.py` calls it: with `lang=None` it falls to its «Sigo con ello.» constant
        "still_working": lambda: wait_lines.mute_backstop([], langs.current_language(), True, reached_worker=True),
        "mute": lambda: wait_lines.mute_line([], None),
        "browser_done": lambda: owner_actions.ending_line("", True),
        "browser_partial": lambda: owner_actions.ending_line("", False),
        "which_card": lambda: instances._ask("close", 2, "«A» or «B»"),
    }


def _shaped(said: str, pool: set[str]) -> bool:
    """`said` is one of the pool's templates with its `{…}` slots filled."""
    return any(re.fullmatch(re.sub(r"\\\{\w+\\\}", ".+", re.escape(p)), said) for p in pool if "{" in p)


PICKERS = ("filler", "filler_action", "filler_social", "filler_ack", "cover_search", "cover_recall", "ack", "holding",
           "still_working", "mute", "browser_done", "browser_partial", "which_card")


def test_every_picker_is_measured():
    assert set(PICKERS) == set(_pickers())


@pytest.mark.parametrize("name", PICKERS)
@pytest.mark.parametrize("code", LANGS)
def test_a_wait_line_comes_from_the_sessions_pack(name, code, monkeypatch):
    from nucleo.workers import quota_wait
    monkeypatch.setattr(quota_wait, "asleep_line", lambda *_a, **_k: "")    # no worker chain asleep here
    with speaking(code):
        said = _pickers()[name]().strip()
    other = "es" if code == "en" else "en"
    mine, theirs = _strings(_pack(code)), _strings(_pack(other))
    assert said, f"{name}: nothing to say in «{code}»"
    assert said in mine or _shaped(said, mine), f"{name} in a «{code}» session said {said!r}, not a line of its pack"
    assert said not in theirs, f"{name} in a «{code}» session said {said!r}, a line of the «{other}» pack"


def test_the_vault_rule_is_confirmed_in_the_sessions_language(monkeypatch):
    from memory import state
    from nucleo.acts import memory as acts_memory
    monkeypatch.setattr(state, "set_security_flag", lambda *_a, **_k: None)
    for code in LANGS:
        with speaking(code):
            on = acts_memory.apply_rule(("secrets_voice", True))
            off = acts_memory.apply_rule(("secrets_voice", False))
        assert (on, off) == (_at(_pack(code), "vault_rule.voice_on"), _at(_pack(code), "vault_rule.voice_off"))


# ── 3 · the ratchet ───────────────────────────────────────────────────────────────────────────────────────────

def _spoken_es() -> set[str]:
    """The SENTENCES only the Spanish pack holds (detector vocabulary — bare words — is left to its own rules)."""
    es, en = _strings(_pack("es")), _strings(_pack("en"))
    return {v for v in es - en if re.search(r"[.…?!]$", v) and re.search(r"[^\W\d_]", v)}


def _keys() -> set[str]:
    return {k for k in _pack("en") if not k.startswith("_")}


def _words(node) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str) and bool(re.search(r"[^\W\d_]{2}", node.value))


def _field_read(node, keys: set[str]) -> bool:
    """`getattr(<lang>, "<pack field>", …)`, bare or inside `str(…)`."""
    if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "str" and node.args:
        node = node.args[0]
    return (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "getattr" and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant) and node.args[1].value in keys)


def _frozen(src: str, spoken: set[str], keys: set[str]) -> list[str]:
    """The spoken lines this source writes as constants: a Spanish pack line, or a literal fallback of a pack field."""
    out = []
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.strip() in spoken:
            out.append(n.value)
        if _field_read(n, keys) and isinstance(n, ast.Call) and getattr(n.func, "id", None) == "getattr" \
                and len(n.args) == 3 and _words(n.args[2]):
            out.append(n.args[2].value)
        if isinstance(n, ast.BoolOp) and isinstance(n.op, ast.Or) and _field_read(n.values[0], keys) \
                and _words(n.values[-1]):
            out.append(n.values[-1].value)
    return out


def _measure() -> dict[str, list[str]]:
    spoken, keys = _spoken_es(), _keys()
    files = subprocess.run(["git", "ls-files", "*.py"], cwd=ENGINE, capture_output=True, text=True).stdout.split()
    found = {}
    for f in files:
        if f.startswith(("tests/", "i18n/")) or "/_user/" in f:
            continue
        try:
            hits = _frozen((ENGINE / f).read_text(encoding="utf-8"), spoken, keys)
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        if hits:
            found[f] = hits
    return found


def test_the_ratchet_sees_a_short_line_and_a_fallback():
    spoken, keys = {"Sigo con ello.", "Hecho."}, {"still_on_it", "data_ack"}
    assert _frozen('x = "Sigo con ello."', spoken, keys), "a filler under the prose ratchet's 25-character floor"
    assert _frozen('x = getattr(lang, "data_ack", "Done.")', spoken, keys), "a fallback in the OTHER language too"
    assert _frozen('x = str(getattr(lang, "still_on_it", "") or "Still on it.")', spoken, keys)
    assert not _frozen('x = getattr(lang, "data_ack", "")', spoken, keys), "an empty fallback says nothing"
    assert not _frozen('x = getattr(f, "kind", "un secreto")', spoken, keys), "not a pack field"
    assert not _frozen('x = langs.words("still_on_it", default="")', spoken, keys), "the door is the way out"


def test_no_new_spoken_line_is_frozen_in_one_language():
    new = {f: v for f, v in _measure().items() if f not in _STILL_HOLDING}
    assert not new, ("a spoken line is a constant of one language instead of a key of `i18n/genesis/<code>/voice.json`"
                     f" read through `langs.words` — an English session hears it in Spanish:\n  {new}")


def test_the_retired_ones_stay_retired():
    gone = _STILL_HOLDING - set(_measure())
    assert not gone, f"retired — take them out of _STILL_HOLDING so they cannot come back: {sorted(gone)}"
