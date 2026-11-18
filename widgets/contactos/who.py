"""widgets/contactos/who.py — WHO a said name can be: ranked candidates, each with how sure the match is.

Measured 2026-11-18 on a real directory (2 705 rows): he said «send a message to <first name> <a word>». The word
was no surname of hers and no row carried it. The lookup the worker used dropped
the word and handed back six people of that first name as if they were the answer; the ranking the doors use found
nobody and fell to a spelling guess that named a seventh. Neither said the one true thing: «the first name is these
people's, the second word is nobody's».

So a NAME (never a sentence) is scored against every row, word by word, with no model and no table of names:

  · a said word against a word of a name: the same word · the same SOUND (`directory.sound`: c/k/q, b/v, ll/y,
    a silent h, accents) · a STEM («Salva» of «Salvador») · a word inside a name written joined · one slip of
    spelling (a letter missing, added, changed or swapped);
  · in ANY order, each said word taking a different word of the name; every name the row is known by is tried
    (the shown one, the ones other sources gave, each chat's), and his own word for the person (`aliases`) is the
    person outright;
  · what he said, joined, SOUNDING like an address or a handle the row holds («odile varga» · `odilevarga@…`).

A row's `confidence` is `sure` (every word, by word or sound), `likely` (every word, some by stem or slip, or the
address) or `partial` (some word of his is on the row and another is not). `find` answers with the best tier
only: full matches when there are any; otherwise the partial ones, closest first, WITH the words nobody carries —
a question for him with names in it, never a match.
"""
from __future__ import annotations

import re

#: What one said word is worth against one word of a name.
SAME, SOUND, STEM, INSIDE, SLIP = 1.0, 0.9, 0.75, 0.7, 0.6
#: What a whole said name is worth when it only sounds like an address or a handle of the row.
ADDRESS = 0.8
#: The shortest stem, the shortest word a slip is forgiven in, and the shortest joined name read against a handle.
STEM_MIN, SLIP_MIN, ADDRESS_MIN = 3, 5, 6
#: What a name said WHOLE adds over a name that has more words than he said; and the lead one full match needs.
WHOLE, LEAD = 0.1, 0.1
#: How many candidates one answer carries.
LIMIT = 6


def _slip(a: str, b: str) -> bool:
    """One slip apart: a letter missing, added, changed, or two neighbours swapped."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) > len(b):
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    if len(a) == len(b):
        return a[i + 1:] == b[i + 1:] or (i + 1 < len(a) and a[i] == b[i + 1] and a[i + 1] == b[i] and a[i + 2:] == b[i + 2:])
    return a[i:] == b[i + 1:]


def word(w: str, t: str) -> float:
    """How well the said word `w` is the name's word `t` (both lowercase, accents off) — one of the worths above, 0."""
    from widgets.directory import sound
    if w == t:
        return SAME
    sw, st = sound(w), sound(t)
    if len(sw) >= 2 and sw == st:
        return SOUND
    if len(w) >= STEM_MIN and len(t) > len(w) and (t.startswith(w) or st.startswith(sw)):
        return STEM
    if len(w) >= STEM_MIN and len(t) - len(w) >= 4 and t.endswith(w):
        return INSIDE
    if min(len(sw), len(st)) >= SLIP_MIN - 1 and min(len(w), len(t)) >= SLIP_MIN and _slip(sw, st):
        return SLIP
    return 0.0


def _against(words: list[str], toks: tuple[str, ...]) -> tuple[float, list[str]]:
    """The said words against ONE name: (mean worth, the said words it does not carry). Each said word takes its best
    word of the name still free — the order he said them in is nothing."""
    free, total, missing = list(toks), 0.0, []
    for w in sorted(words, key=len, reverse=True):
        best, at = 0.0, -1
        for i, t in enumerate(free):
            s = word(w, t)
            if s > best:
                best, at = s, i
        if at < 0:
            missing.append(w)
            continue
        total += best
        free.pop(at)
    return total / max(1, len(words)), missing


def left_over(name, words: list[str]) -> list[str]:
    """The words of `name` that the said words do not carry — [] when the whole name is in what he said."""
    from widgets.directory import _tokens
    return _against(_tokens(name), tuple(words))[1]


def _handles(c: dict) -> list[str]:
    """The letters of every address and handle the row holds, as they SOUND — the part before the @ only: what
    follows names a company, and everybody in it."""
    from widgets.directory import _emails, sound
    raw = list(_emails(c))
    for ch in c.get("channels") or []:
        raw += [str((ch or {}).get("handle") or ""), str((ch or {}).get("email") or "")]
    out = []
    for v in raw:
        v = str(v or "").lower()
        letters = re.sub(r"[^a-z]", "", v.partition("@")[0])
        if len(letters) >= ADDRESS_MIN:
            out.append(sound(letters))
    return out


def score(q: str, c: dict, words: list[str] | None = None) -> dict:
    """`{score, confidence, missing, by}` of the said name `q` (normalised) against one row; `score` 0 for no match."""
    from widgets import directory as d
    words = d._tokens(q) if words is None else words
    if not words:
        return {"score": 0.0, "confidence": "", "missing": [], "by": ""}
    said = [d.sound(w) for w in words]
    for a in c.get("aliases") or []:
        if d._norm(a) == q or [d.sound(t) for t in d._tokens(a)] == said:
            return {"score": SAME + 2 * WHOLE, "confidence": "sure", "missing": [], "by": "alias"}
    best, missing, whole = 0.0, list(words), 0.0
    for n in d.names(c):
        toks = d._tokens_of(n)
        s, miss = _against(words, toks)
        w = WHOLE if not miss and len(toks) == len(words) else 0.0       # the whole name, nothing left over
        if (len(miss), -s - w) < (len(missing), -best - whole):
            best, missing, whole = s, miss, w
    if missing:
        joined = d.sound("".join(words))
        if len(joined) >= ADDRESS_MIN and any(h == joined for h in _handles(c)):
            return {"score": ADDRESS, "confidence": "likely", "missing": [], "by": "address"}
        if not any(len(w) >= STEM_MIN for w in words if w not in missing):      # only a particle is on the row
            return {"score": 0.0, "confidence": "", "missing": missing, "by": ""}
        return {"score": best, "confidence": "partial", "missing": missing, "by": "name"}
    return {"score": best + whole, "confidence": "sure" if best >= SOUND else "likely", "missing": [], "by": "name"}


def find(name: str, people: list[dict] | None = None, limit: int = LIMIT) -> dict:
    """The people a said NAME can be: `{people: [{contact, score, confidence, missing, by}…], confidence, unmatched,
    more}` — the best tier only (see the module note), closest first within a worth. `confidence` is `one` (a single
    full match, or one that leads), `several` (full matches to choose among), `partial` (nobody carries every word:
    `unmatched` are the said words NO row carries) or `none`."""
    from widgets import directory as d
    from . import groups as _groups
    raw = str(name or "").strip().strip(d._QUOTES)
    q = d._norm(raw)
    words = d._tokens(q)
    if not words:
        return {"people": [], "confidence": "none", "unmatched": [], "more": 0}
    people = [c for c in (d._contacts() if people is None else people) if d.level(c)
              and c.get("kind") in (None, "", "person", "company")]
    nats = _groups.declared()
    import time
    since = time.time() - d.active_days() * 86400
    rows = []
    for c in people:
        got = score(q, c, words)
        if got["score"]:
            rows.append({**got, "contact": c})
    kept = {id(t[2]) for t in d._one_row_per_person([(0, 0, r["contact"]) for r in rows])}
    rows = [r for r in rows if id(r["contact"]) in kept]          # a row named by its handle is its namesake
    full = [r for r in rows if r["confidence"] != "partial"]
    tier = full or rows
    tier.sort(key=lambda r: (-len(words) + len(r["missing"]), -round(r["score"], 2),
                             -d._points(0, r["contact"], since, nats), -d._last_seen(r["contact"])))
    if not tier:
        return {"people": [], "confidence": "none", "unmatched": words, "more": 0}
    if full:
        lead = len(full) == 1 or (full[0]["confidence"] == "sure" and full[0]["score"] - full[1]["score"] >= LEAD)
        return {"people": full[:1] if lead else full[:limit], "confidence": "one" if lead else "several",
                "unmatched": [], "more": 0 if lead else max(0, len(full) - limit)}
    carried = {w for r in rows for w in words if w not in r["missing"]}
    return {"people": tier[:limit], "confidence": "partial", "unmatched": [w for w in words if w not in carried],
            "more": max(0, len(tier) - limit)}
