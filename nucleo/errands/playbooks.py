"""nucleo/errands/playbooks.py — the playbooks that continue as an errand with a third party, as DATA (V2-683, V2-859).

The operator asked for workflows — «deberíamos tener workflows para reservar un restaurante, organizar una
reunión…» — and drew the boundary himself: «que esos workflows además fueran dinámicos, porque las preferencias de
otro usuario podrían ser diferentes». So a playbook is a BRIEFING, not a script:

  · `done_when` — the condition that CLOSES it, machine-checkable (`verify.py` runs it);
  · `needs` — ids of what has to be known before acting (worded per language, `errands.needs.<id>`), so the errand
    ASKS instead of inventing (the V2-652 scar: a worker typed a placeholder NIF into a real form, twice);
  · the brief — a few sentences of how this kind of thing is done well, per language (`errands.brief.<kind>`).

**There is ONE notion of playbook (V2-859 T562).** `meeting` and `booking` are names in the worker's catalogue
(`nucleo/workers/prompts/playbook.py`); the worker names one at checkpoint 1, the exit door stamps that name on the
message that leaves, and the errand born from it inherits it (`kind_of`). This module used to guess the kind from
the objective's WORDS with a `matches` table — a table of verbs is not a router (V2-750), and its words were
Spanish, so an English operator's errands fell to `generic`.

Three properties keep it a shortcut instead of a fence, and each is a test:
  1. an errand with NO playbook still runs (the generic path);
  2. the operator's own preferences layer OVER genesis (`config/playbooks.json`, his brief replaces the pack's);
  3. nothing here names a person, a company or a site: swap «reunión»→«cena» and it still stands.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from loguru import logger

_GENESIS = Path(__file__).resolve().parents[1] / "genesis.json"
_cache: dict | None = None
_override_cache: tuple[float, dict] = (0.0, {})

#: The brief travels on EVERY wake and in the pack, so it is bounded — measured in the test, not hoped for.
MAX_BRIEF = 700


def _genesis() -> dict:
    global _cache
    if _cache is None:
        import genome   # V2-859: a refused genesis reads as the last good generation, never half a file
        _cache = genome.genesis()
    return _cache


def _override_path() -> Path:
    try:
        from nucleo import workspace
        return workspace.root() / "config" / "playbooks.json"
    except Exception:
        return Path("config/playbooks.json")


def _override() -> dict:
    """The operator's own file, re-read when it changes on disk (`style_policy`'s mtime cache, same reason:
    a rule he gave by voice has to govern the very next move, and survive a restart)."""
    global _override_cache
    p = _override_path()
    try:
        mtime = p.stat().st_mtime
    except Exception:
        return {}
    if _override_cache[0] == mtime:
        return _override_cache[1]
    try:
        data = dict(json.loads(p.read_text(encoding="utf-8")) or {})
    except Exception as e:  # noqa: BLE001
        logger.warning(f"errands: config/playbooks.json ilegible ({e!r}) — mandan los valores de fábrica")
        data = {}
    _override_cache = (mtime, data)
    return data


def settings() -> dict:
    """The errand knobs: `shadow`, `grace_h`, `max_days`, `default_window_h`."""
    out = dict(_genesis().get("errands") or {})
    out.update(_override().get("errands") or {})
    return out


def playbooks() -> dict:
    """Every playbook, the operator's file layered over genesis. `_comment` keys are documentation — the
    convention the rest of `genesis.json` already uses — so anything that is not a dict is not a playbook."""
    out = {k: dict(v) for k, v in (_genesis().get("playbooks") or {}).items() if isinstance(v, dict)}
    for k, v in (_override().get("playbooks") or {}).items():
        if isinstance(v, dict):
            merged = dict(out.get(k) or {})
            merged.update(v)
            out[k] = merged
    return out


def get(kind: str) -> dict:
    return dict(playbooks().get(str(kind or "").strip().lower()) or {})


def _words(path: str):
    try:
        from i18n import langs
        return langs.words(path)
    except Exception:  # noqa: BLE001 — a missing pack never blocks an errand
        return None


def brief_for(kind: str) -> str:
    """His own brief for this kind (`config/playbooks.json`) wins; else the language pack's; '' with neither."""
    kind = str(kind or "").strip().lower()
    if not kind or kind not in playbooks():
        return ""
    mine = str(get(kind).get("brief") or "")
    return (mine or str(_words(f"errands.brief.{kind}") or ""))[:MAX_BRIEF]


def done_when(kind: str) -> dict:
    return dict(get(kind).get("done_when") or {})


def needs(kind: str) -> list:
    """The ids of what has to be known before acting (genesis), stamped on the errand at birth."""
    return [str(n) for n in (get(kind).get("needs") or []) if str(n).strip()]


def need_words(ids) -> list:
    """Each need in the active language; an id the pack does not word is shown as written (a need his own file
    spelled out in words stays readable)."""
    return [str(_words(f"errands.needs.{n}") or n) for n in (ids or []) if str(n).strip()]


def kind_of(playbook: str) -> str:
    """The errand's kind: the playbook the task NAMED (carried on the message that left), when it is one of these;
    `generic` otherwise. Never a reading of the objective's words, never a refusal — an errand whose playbook is not
    here still runs."""
    name = str(playbook or "").strip().lower()
    return name if name and name in playbooks() else "generic"


# ── what the model is told about the operator's own calendar ────────────────────────────────────────────
def free_slots_line(errand: dict, now: float | None = None) -> str:
    """What is ALREADY TAKEN in the operator's agenda inside this errand's window.

    Deliberately the busy intervals and not «free slots»: a gap this module computed would be a promise
    about his time made by arithmetic — his agenda holds all-day entries, travel and things with no hour,
    and proposing a slot that is technically empty is how a meeting lands on top of something real. Saying
    what is taken lets the model propose around it and say so honestly.
    """
    now = time.time() if now is None else now
    try:
        from widgets.agenda import data as agenda
        rows = (agenda.view_data() or {}).get("meetings") or []
    except Exception:
        return ""
    today = time.strftime("%Y-%m-%d", time.localtime(now))
    end_day = time.strftime("%Y-%m-%d", time.localtime(float(errand.get("deadline") or now)))
    out = []
    for m in rows:
        d = str(m.get("date") or "")
        if not (today <= d <= end_day):
            continue
        hour = str(m.get("startTime") or "").strip()
        title = str(m.get("title") or "").strip()[:40]
        out.append(f"{d} {hour or 'todo el día'} {title}".strip())
        if len(out) >= 8:
            break
    return " · ".join(out)
