"""The manager's configuration from data (V2-941, v3.1 §1.9): what is not mechanism comes from the genome and the
rules, never from a constant of the package.

  · `build()`  the `Config` of an account, once per session: the graces from genesis `conversation.thresholds`, each
    inside the bounds `genome.thresholds` declares for it, and the hold behind an open voice from the typed lane's own
    cap (`nucleo/input/typed.CAP_S`: one number while both paths live). A value out of its bounds, or a set out of the
    order the graces need (`Config.misordered`), is a PROBLEM: the host refuses it and the session takes the old path.
  · `prefs()`  the `Prefs` port: his rule, read at every decision that needs it (`rules.value` at scope `voice`), so a
    change applies to the next reply with no restart. The factory value is a default row built from genesis
    `conversation.prefs` (`rules/defaults.py`).
"""
from __future__ import annotations

import dataclasses
from typing import Any

from conversation.config import Config

PREFIX = "conversation."


def build(genesis: dict | None = None) -> tuple[Config, list[str]]:
    """The account's `Config` and the problems that refuse it (`[]`: it may run)."""
    if genesis is None:
        import genome
        genesis = genome.genesis()
    values = ((genesis.get("conversation") or {}).get("thresholds") or {})
    bounds = ((genesis.get("genome") or {}).get("thresholds") or {})
    known = {f.name for f in dataclasses.fields(Config)}
    out, problems = {}, []
    for key, v in values.items():
        if str(key).startswith("_"):
            continue
        b = bounds.get(PREFIX + key)
        if key not in known or not (isinstance(b, list) and len(b) == 2):
            problems.append(f"{key}: not a declared threshold of the manager")
        elif isinstance(v, bool) or not isinstance(v, int) or not b[0] <= v <= b[1]:
            problems.append(f"{key}: {v!r} outside {b}")
        else:
            out[key] = v
    from nucleo.input import typed
    cfg = Config(**out, cross_channel_hold_ms=int(typed.CAP_S * 1000))
    cfg = dataclasses.replace(cfg, **_sandbox_deadline())
    return cfg, problems + cfg.misordered()


#: a disposable engine's knobs to drive a provider timeout live (`sandbox.is_sandbox()`): the model's first-event
#: deadline, and a titular that holds its stream (`model.HANG_TITULAR`) so the stand-in is what answers
FIRST_MS_ENV = "ZAELAR_CONVERSATION_MODEL_FIRST_MS"


def _sandbox_deadline() -> dict:
    import os

    from nucleo.conversation_host import sandbox
    raw = (os.getenv(FIRST_MS_ENV) or "").strip()
    return {"model_first_ms": int(raw)} if raw.isdigit() and int(raw) > 0 and sandbox.is_sandbox() else {}


def prefs(key: str, default: Any) -> Any:
    """The `Prefs` port: his preference as it stands now."""
    import rules
    from rules.scope import VOICE
    return rules.value(rules.path(surface=VOICE), key, default)
