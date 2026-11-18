"""nucleo/self/face_recent.py — what the face just did and saw, as words for the model (V2-928).

The operator, 2026-11-18: if the face winks, shakes its head or smiles and he asks «why did you smile?», the model must
find in the state what just happened — the face is not inert, it is aware of what goes on. The screen keeps a short list
of NAMES (`frontend/app/presence/recent.js`): gestures of his the face perceived on the device (`saw`) and gestures of
the face's own that have a reason (`did`: an answer to his, a nod or shake while saying yes or no). It reports the list
with its beat; this module cleans it, keeps it beside the screen (`voice/screens.py`, process memory, never stored), and
words it from the `self` language pack — one line in the live tail only while something happened in the last 30 s.

What crosses: names and an age in seconds. Never an image, a score or a number about a face. A name the pack does not
word is dropped AT THE DOOR (`clean`), so nothing the screen sends ever reaches the model as text of its own — not in
the live line, not in `about_self`'s facts: the pack is the closed set.
The face's idle life (glances, its resting smile) is not in the list on purpose: it has no reason to tell; the line says
that a gesture not listed was the face's own life.
"""
from __future__ import annotations

import time

WINDOW_S = 30.0
MAX_ACTS = 8
_KINDS = ("saw", "did")


def _name(v) -> str:
    s = str(v or "")
    return s if 2 <= len(s) <= 16 and s.isascii() and s.replace("_", "").isalpha() and s.islower() else ""


def _vocab() -> dict:
    """The names the pack words (English is the reference; both packs carry the same keys — pinned by the test)."""
    from nucleo.self import about
    w = (about.words("en").get("live") or {}).get("face_recent") or {}
    return {"saw": set(w.get("saw") or ()) | set(w.get("saw_plain") or ()), "did": set(w.get("did") or ()),
            "said": set(w.get("said") or ())}


def _why_ok(why: str, said: set) -> bool:
    return why == "answer" or (why.startswith("said_") and why.removeprefix("said_") in said)


def clean(acts) -> list[dict]:
    """The screen's list → only entries the pack words: `{kind, name, why?, of?, age_s}`, at most MAX_ACTS."""
    v, out = _vocab(), []
    for a in acts if isinstance(acts, list) else ():
        if not isinstance(a, dict) or a.get("kind") not in _KINDS or _name(a.get("name")) not in v[a["kind"]]:
            continue
        age = a.get("age_s")
        if not isinstance(age, (int, float)) or isinstance(age, bool) or not 0 <= age <= WINDOW_S:
            continue
        e = {"kind": a["kind"], "name": a["name"], "age_s": float(age)}
        if a["kind"] == "did":
            why, of = _name(a.get("why")), _name(a.get("of"))
            if not _why_ok(why, v["said"]):
                continue
            e["why"] = why
            if why == "answer" and of in v["saw"]:
                e["of"] = of
        out.append(e)
    return out[-MAX_ACTS:]


def recent(now: float | None = None) -> list[dict]:
    """The acts of the last WINDOW_S, newest first, from the screen that reported last (`age_s` as of now)."""
    from voice import screens
    now = time.time() if now is None else now
    best = max((e.get("face") for e in screens.open_screens() if e.get("face")), key=lambda f: f["at"], default=None)
    if not best:
        return []
    acts = [{**a, "age_s": round(a["age_s"] + now - best["at"])} for a in best["acts"]]
    return sorted((a for a in acts if a["age_s"] <= WINDOW_S), key=lambda a: a["age_s"])


def _clause(a: dict, w: dict, answered: set) -> str:
    saw, did, said = w.get("saw") or {}, w.get("did") or {}, w.get("said") or {}
    forms, age, plain = w.get("forms") or {}, a["age_s"], w.get("saw_plain") or {}
    if a["kind"] == "saw":
        if a["name"] in plain:              # arriving, leaving: a fact, not a gesture to answer
            return str(forms.get("plain", "")).format(saw=plain[a["name"]], age=age)
        if a["name"] in answered or a["name"] not in saw:
            return ""                       # an answered gesture is told by its answer
        return str(forms.get("let_go", "")).format(saw=saw[a["name"]], age=age)
    if a["name"] not in did:
        return ""
    if a.get("why") == "answer" and a.get("of") in saw:
        return str(forms.get("answer", "")).format(saw=saw[a["of"]], did=did[a["name"]], age=age)
    word = said.get(str(a.get("why") or "").removeprefix("said_")) if str(a.get("why")).startswith("said_") else None
    return str(forms.get("said", "")).format(did=did[a["name"]], said=word, age=age) if word else ""


def line(words: dict, now: float | None = None) -> str:
    """The live tail's line, or "" when nothing worded happened in the window (an idle turn pays nothing)."""
    w = words.get("face_recent") if isinstance(words, dict) else None
    if not isinstance(w, dict) or not w.get("line"):
        return ""
    acts = recent(now)
    answered = {a.get("of") for a in acts if a["kind"] == "did" and a.get("why") == "answer"}   # what PLAYED, not intended
    clauses = [c for c in (_clause(a, w, answered) for a in acts) if c]
    return str(w["line"]).format(acts="; ".join(clauses)) if clauses else ""
