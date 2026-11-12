"""observability/pii.py — personal data out of what is STORED, replaced by tags (V2-875).

Before a persisted event is written (when the person's `privacy.obfuscate` switch is on, the default), every
free-text value is rewritten:

  · SHAPES only a particular thing has → [EMAIL] [URL] [PHONE] [DATE] [NUMBER] — each recognised by its own shape
    (a phone by its digit count, a date by its fields in range), so a date or a time is never a [PHONE] and a time
    is kept as said;
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

class _Shape:
    """A pattern plus the test its match must pass to BE that thing (`search` and `sub`, like a compiled pattern)."""

    def __init__(self, pattern: str, ok=None, flags: int = 0):
        self._re, self._ok = re.compile(pattern, flags), ok or (lambda m: True)

    def search(self, text: str):
        return next((m for m in self._re.finditer(text) if self._ok(m)), None)

    def sub(self, repl: str, text: str) -> str:
        return self._re.sub(lambda m: repl if self._ok(m) else m.group(0), text)


def _a_date(m) -> bool:
    """A day by its own shape: Y-M-D, D/M[/Y] or M/D[/Y] in range; a two-part «12.11» or «12-11» only with two digits
    on each side and a month second — «17.30» is a time and «1.5» a decimal, neither is a date."""
    parts, seps = re.split(r"[/.-]", m.group(0)), set(re.findall(r"[/.-]", m.group(0)))
    n = [int(x) for x in parts]
    if len(parts[0]) == 4:
        return len(n) == 3 and 1 <= n[1] <= 12 and 1 <= n[2] <= 31
    if len(n) == 2 and seps != {"/"}:
        return len(parts[0]) == len(parts[1]) == 2 and 1 <= n[0] <= 31 and 1 <= n[1] <= 12
    a, b = n[0], n[1]
    return (1 <= a <= 31 and 1 <= b <= 12) or (1 <= a <= 12 and 1 <= b <= 31)


def _a_phone(m) -> bool:
    """A phone — or a code said in groups — by its own shape: six digits or more, whatever the grouping («12 34 56 78»
    is a phone where numbers have eight digits) and with no ceiling: two phones said in one breath are one run. A date
    is read before it and a time carries «:», so neither reaches here; what does is a doubt, and every doubt tags."""
    return sum(c.isdigit() for c in m.group(0)) >= 6


SHAPES = (
    ("email", _Shape(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    ("url", _Shape(r"(?:https?://|www\.)\S+|\b[\w-]+\.[a-z]{2,}/\S*", flags=re.I)),
    # A date or a time is never a phone: the date is read first, by its own shape and range, and a time («10:30»,
    # «17.30», «17h30») matches no shape at all — it names no one, and a stored session must say when things happened.
    ("date", _Shape(r"(?<![\d/.-])(?:\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[/.-]\d{1,2}(?:[/.-](?:\d{4}|\d{2}))?)(?![\d]|[/.-]\d)",
                    _a_date)),
    ("phone", _Shape(r"(?<![\d+])\+?\(?\d[\d\s().-]{5,}\d(?!\w|:\d)", _a_phone)),
    # A run of three or more digits — a year standing alone too: by its shape it cannot be told from a PIN.
    ("number", _Shape(r"(?<!\d)\d{3,}")),
)
_PUNCT = "\"'«»“”‘’()[]{}¿?¡!.,;:…"
_ENDS = ".!?…\n"
def _structural() -> frozenset:
    """The fields that describe an event, never rewritten: the indexed columns the events table declares
    (`bus/log._COLUMNS` — flow, session, family, kind, label, actor, model, version, piece). Read lazily: the
    tagger runs on the writers' threads, after the bus log exists."""
    try:
        from bus import log
        return frozenset(c[0] for c in log._COLUMNS)
    except Exception:  # noqa: BLE001 — without the schema every string is treated as text (more tags, never fewer)
        return frozenset()


def norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", s.casefold())).strip()


_known_cache: dict = dict(at=0.0, val={}, words=frozenset())   # a state record (when, names, pieces), not a word table
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
    whole: set[str] = set()

    def add(name, tag):
        k = norm(name)
        if k:
            out.setdefault(k, tag)
            whole.add(k)
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
        from memory import api as memory      # the facade: `memory.state` has no `load` (it raised, the guard never ran)
        st = memory.state() or {}
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
                    whole.add(k)
                    out.update({w: "[PERSON]" for w in k.split() if len(w) >= 3})
    except Exception as e:  # noqa: BLE001 — no address book: shapes and capitals still guard
        logger.debug(f"pii: contacts unreadable ({e!r})")
    for p in _places:
        whole.add(p)
    _known_cache.update(at=now, val=out, words=frozenset(set(out) - whole))
    return out


#: Kept whole: `evidence`, what the OUTSIDE world brought back (web results — title, url, snippet), which a debugging
#: session audits against what the agent said. It is not the person's data; it still passes the secrets scrub.
EXEMPT = "evidence"


def tag(text: str, names: dict[str, str] | None = None) -> str:
    """`text` with personal data replaced by tags. Never raises (on failure the whole text is withheld)."""
    if not isinstance(text, str) or not text.strip():
        return text
    try:
        # A PIECE of a known name (one word of «Nombre Manuel Baeza», «Ana Que…») is tagged only where it is written
        # as a name, capitalised. In lowercase it is any word of the sentence: tagging it stored «te dije su [PERSON]
        # y su apellido» for «nombre», «[PERSON]» for «que» and «con», and the stored session could not be read.
        mine = names is None
        names = known() if mine else names
        pieces = _known_cache.get("words", frozenset()) if mine else frozenset()
        for kind, pat in SHAPES:
            text = pat.sub(f"[{kind.upper()}]", text)
        out, opening, prev_tag = [], True, ""
        for tok in text.split(" "):
            core = tok.strip(_PUNCT)
            t = ""
            already = "[" in tok and "]" in tok          # a tag the shapes already wrote
            if core and not already and core[0].isalpha():
                key = norm(core)
                t = names.get(key, "")
                if t and key in pieces and not core[0].isupper():
                    t = ""
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


def _identifier(s: str) -> bool:
    """An id, a kind, a device, a trace, a model name — one token that is data about the event, not anyone's words:
    lowercase with letters, or joined by an id separator (`·` `:` `_`). Never an address (an email, a link)."""
    if " " in s or "@" in s or s.startswith(("http://", "https://", "www.")):
        return False
    return (any(c.isalpha() for c in s) and s == s.lower()) or any(c in s for c in "·:_")


def tag_obj(obj, names: dict[str, str] | None = None, _key: str = "", _fields: frozenset | None = None):
    """A copy of `obj` with every free-text value tagged; structural fields and identifiers untouched."""
    names = known() if names is None else names
    fields = _structural() if _fields is None else _fields
    if isinstance(obj, str):
        return obj if _key in fields or _identifier(obj) else tag(obj, names)
    if isinstance(obj, dict):
        return {k: (v if k == EXEMPT or (k in fields and not isinstance(v, (dict, list)))
                    else tag_obj(v, names, str(k), fields)) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [tag_obj(v, names, _key, fields) for v in obj]
    return obj
