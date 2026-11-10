"""observability/pii.py — personal data out of what is STORED, replaced by tags (V2-875).

Before a persisted event is written (when the person's `privacy.obfuscate` switch is on, the default), every
free-text value is rewritten:

  · SHAPES only a particular thing has → [EMAIL] [URL] [PHONE] [DATE] [NUMBER];
  · names THIS agent knows → [PERSON] (every name of every contact), [PLACE] (the places of the state — home and
    where a screen is now — and every place the location door resolved), [NAME] (the memory's concept hubs);
  · any other word that starts with a capital and does not open a sentence → [NAME].

Deterministic, no model and no vocabulary of any language: shapes and the agent's own data. The limit is stated, not
hidden: a name never seen that opens a sentence, or is written in lowercase, passes. Every doubt tags — a tag too
many costs a debugging session some detail; a name stored cannot be taken back. Structural fields (kind, ids, the
device, timestamps, labels the engine writes) are never touched, so the event keeps its shape for every reader.

The shapes and the normaliser are shared with `genome/privacy.py`, which DROPS instead of tagging.
"""
from __future__ import annotations

import re
import time
import unicodedata

from loguru import logger

SHAPES = (
    ("email", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    ("url", re.compile(r"(?:https?://|www\.)\S+|\b[\w-]+\.[a-z]{2,}/\S*", re.I)),
    ("phone", re.compile(r"\+?\d[\d\s().-]{5,}\d")),
    ("date", re.compile(r"\b\d{1,4}[/.-]\d{1,2}(?:[/.-]\d{1,4})?\b")),
    ("number", re.compile(r"\d{3,}")),
)
_PUNCT = "\"'«»“”‘’()[]{}¿?¡!.,;:…"
_ENDS = ".!?…\n"
#: Fields that describe the event, not what anyone said: never rewritten.
STRUCTURAL = frozenset({
    "kind", "label", "id", "ids", "dev", "origin_dev", "to", "corr_id", "trace", "trace_id", "session_id", "sid",
    "topic", "role", "cat", "piece", "ver", "inst", "host", "model", "engine", "provider", "src", "source",
    "platform", "ts", "t", "t_ms", "rel_ms", "at", "i", "state", "phase", "widget", "card_id", "task_id", "ask_id",
    "action", "status", "reason", "lang", "voice", "channel",
})


def norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", s.casefold())).strip()


_known_cache: dict = {"at": 0.0, "val": {}}
_places: set[str] = set()


def note_place(*names) -> None:
    """The location door tells us every place it resolved: they are particular from then on."""
    for n in names:
        k = norm(n)
        if k:
            _places.add(k)
            _places.update(w for w in k.split() if len(w) >= 3)
    _known_cache["at"] = 0.0


def known(ttl_s: float = 60.0) -> dict[str, str]:
    """{normalised name or word: TAG} from this agent's own data. Cached for a minute. Never raises."""
    now = time.monotonic()
    if now - _known_cache["at"] < ttl_s:
        return _known_cache["val"]
    out: dict[str, str] = {}

    def add(name, tag):
        k = norm(name)
        if k:
            out.setdefault(k, tag)
            for w in k.split():
                if len(w) >= 3:
                    out.setdefault(w, tag)
    try:
        from memory import api as memory
        for n in memory.concept_names(200):
            add(n, "[NAME]")
    except Exception as e:  # noqa: BLE001 — no memory: the rest still guards
        logger.debug(f"pii: concept names unreadable ({e!r})")
    try:
        from memory import state
        st = state.load() or {}
        for v in (st.get("location"), (st.get("here") or {}).get("place"), (st.get("here") or {}).get("region")):
            for part in str(v or "").split(","):
                add(part, "[PLACE]")
    except Exception as e:  # noqa: BLE001
        logger.debug(f"pii: state unreadable ({e!r})")
    for p in _places:
        out[p] = "[PLACE]"
    try:
        from widgets import directory, store
        # Read only an address book that EXISTS: loading a missing one seeds it, and a seed is a write that emits an
        # event — from the observer's own writer thread, once a minute, forever.
        for c in (directory._contacts() if store.exists("contactos") else []):
            for name in directory.names(c):
                k = norm(name)
                if k:
                    out[k] = "[PERSON]"
                    out.update({w: "[PERSON]" for w in k.split() if len(w) >= 3})
    except Exception as e:  # noqa: BLE001 — no address book: shapes and capitals still guard
        logger.debug(f"pii: contacts unreadable ({e!r})")
    _known_cache.update(at=now, val=out)
    return out


#: Kept whole: what the OUTSIDE world brought back (web results — title, url, snippet), which a debugging session audits
#: against what the agent said. It is not the person's data; it still passes the secrets scrub.
EXEMPT = frozenset({"evidence"})


def tag(text: str, names: dict[str, str] | None = None) -> str:
    """`text` with personal data replaced by tags. Never raises (on failure the whole text is withheld)."""
    if not isinstance(text, str) or not text.strip():
        return text
    try:
        names = known() if names is None else names
        for kind, pat in SHAPES:
            text = pat.sub(f"[{kind.upper()}]", text)
        out, opening, prev_tag = [], True, ""
        for tok in text.split(" "):
            core = tok.strip(_PUNCT)
            t = ""
            already = "[" in tok and "]" in tok          # a tag the shapes already wrote
            if core and not already and core[0].isalpha():
                t = names.get(norm(core), "")
                if not t and core[0].isupper() and not opening and not (len(core) == 1):
                    t = "[NAME]"
            if t:
                lead = tok[: len(tok) - len(tok.lstrip(_PUNCT))]
                trail = tok[len(tok.rstrip(_PUNCT)):]
                if t == prev_tag and not lead and out and out[-1].endswith(t):
                    out[-1] = out[-1] + trail        # «Ana María López» → one [PERSON]
                else:
                    out.append(lead + t + trail)
                prev_tag = t if not trail else ""
            else:
                out.append(tok)
                prev_tag = ""
            if tok:
                opening = tok.rstrip("»”’\")'")[-1:] in _ENDS
        return " ".join(out)
    except Exception as e:  # noqa: BLE001 — fail closed: an unreadable text is not stored as it was
        logger.debug(f"pii: tag failed ({e!r})")
        return "[WITHHELD]"


def tag_obj(obj, names: dict[str, str] | None = None, _key: str = ""):
    """A copy of `obj` with every free-text value tagged; structural fields untouched."""
    if names is None:
        names = known()
    if isinstance(obj, str):
        return obj if _key in STRUCTURAL else tag(obj, names)
    if isinstance(obj, dict):
        return {k: (v if k in EXEMPT or (k in STRUCTURAL and not isinstance(v, (dict, list)))
                    else tag_obj(v, names, str(k))) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [tag_obj(v, names, _key) for v in obj]
    return obj
