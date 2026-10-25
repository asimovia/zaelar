"""widgets/screen_policy.py — how a widget behaves when the same agent is open on several screens (V2-792).

Every widget declares it in its manifest, `"screens"`, because only the widget knows what it is:

  · `"shared"` — a REFLECTION of data (a calendar, contacts, a list, a map, results). It may be open on any number
    of screens at once; a request opens it on the screen that asked and the others get a chip; every open copy
    shows the same data live.
  · `"single"` — it takes the DEVICE's sound or picture (a video, music). It lives on ONE screen at a time: asking
    for it from another screen MOVES it — the screen that had it stops and closes its copy, the new one opens it.
    Orders about it (pause, volume, next) reach it wherever it plays.

One rule ties it to the rest of the manifest: a widget that takes an exclusive output channel (`runtime.output`,
the speaker) cannot be `shared` — two screens would play it at once. A manifest without the field resolves the same
way (`runtime.output` → single, otherwise shared), so a widget written before the field existed still behaves; and
every widget the generator creates or modifies leaves with the field written (`widgets/validator.py`).
"""
from __future__ import annotations

SHARED = "shared"
SINGLE = "single"
VALUES = (SHARED, SINGLE)


def of(man: dict) -> str:
    """The policy a manifest resolves to."""
    v = str((man or {}).get("screens") or "").strip().lower()
    if v in VALUES:
        return v
    rt = (man or {}).get("runtime")
    return SINGLE if isinstance(rt, dict) and rt.get("output") else SHARED


def problem(man: dict, *, required: bool = False) -> str | None:
    """Why a manifest's `screens` is wrong, or None. `required` = a widget just created must say it explicitly."""
    raw = (man or {}).get("screens")
    if raw is None:
        if required:
            return ("manifest must declare \"screens\": \"shared\" (a reflection of data, may be open on several "
                    "screens at once) or \"single\" (takes the device's sound or picture — a video, music — and "
                    "lives on one screen at a time)")
        return None
    if str(raw).strip().lower() not in VALUES:
        return f"'screens' invalid ({raw!r}); use \"shared\" or \"single\""
    rt = (man or {}).get("runtime")
    if str(raw).strip().lower() == SHARED and isinstance(rt, dict) and rt.get("output"):
        return ("'screens' is \"shared\" but runtime.output takes the device's "
                f"{rt.get('output')} — two screens would play it at once; declare \"screens\": \"single\"")
    return None


def of_card(card_id: str) -> str:
    """The policy of a card on the canvas (`youtube`, `results::t7`). Unknown widget → shared."""
    base = str(card_id or "").split("::", 1)[0].strip().lower()
    if not base:
        return SHARED
    try:
        from . import runtime
        for w in runtime.catalog():
            if str(w.get("id") or "").lower() == base:
                return of(w)
    except Exception as e:  # noqa: BLE001 — no catalog: the safe default never plays twice by itself
        from loguru import logger
        logger.debug(f"screen_policy: catalog unreadable for {base}: {e!r}")
    return SHARED
