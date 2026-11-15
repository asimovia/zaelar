"""nucleo/play/programme.py — what the programme of an action IS, read from its manifest.

Nothing is decided here by a name: every field is a declaration the widget already makes.

  · `confirm` — the action asks before it runs (`widgets.actions.classify` is `confirm`);
  · `leaves`  — it reaches the world outside this machine (`widgets.effects.leaves`);
  · `verify`  — how its end state is read once the executor returned:
        `check`      it declares `done_when`: the declared end state is looked at;
        `unreadable` it declares `done_when_unreadable`: nobody can see it land, the outcome is `unverified`;
        `return`     it declares neither: the executor's own return is the evidence.

An action no widget declares has NO programme (`None`): there is nothing to run.
"""
from __future__ import annotations

CHECK, UNREADABLE, RETURN = "check", "unreadable", "return"


def _spec(wid: str, action: str) -> dict | None:
    from widgets import runtime
    man = runtime.get(str(wid or "").split("::", 1)[0].strip().lower()) or {}
    spec = (man.get("actions") or {}).get(str(action or "").strip())
    return spec if isinstance(spec, dict) else None


def of(wid: str, action: str) -> dict | None:
    spec = _spec(wid, action)
    if spec is None:
        return None
    from widgets import actions, effects
    if spec.get("done_when"):
        verify = CHECK
    elif str(spec.get("done_when_unreadable") or "").strip():
        verify = UNREADABLE
    else:
        verify = RETURN
    return {"confirm": actions.classify(spec, action) == actions.CONFIRM,
            "leaves": effects.leaves(wid, action),
            "verify": verify}


def verdict_event(programme: dict, landed: bool | None) -> str:
    """The event the `verifying` step receives. `landed` is what the look at the declared end state returned
    (None = it could not be read); an action with no end state to look at never claims more than it has."""
    how = str((programme or {}).get("verify") or "")
    if how == UNREADABLE:
        return "unreadable"
    if how == RETURN:
        return "landed"
    if landed is None:
        return "unreadable"
    return "landed" if landed else "absent"
