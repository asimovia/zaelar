"""The document's text read as BLOCKS (headings, paragraphs) and the bound errand's PROCESS view.
The units the card renders and `goto` aims at, the outline `view_data` declares, and the narrative derived from the
dispatcher's live record of a REPORT errand (V2-644).
"""
from __future__ import annotations


#: The process view keeps the same bounds as the results sheet's live view (`widgets/results/live.py`).
_MAX_PHASES = 40
_MAX_PHASE_CHARS = 160


def _clean_phases(raw) -> list:
    if not isinstance(raw, (list, tuple)):
        return []
    return [str(x)[:_MAX_PHASE_CHARS] for x in raw if str(x or "").strip()][-_MAX_PHASES:]


def _process(db: dict):
    """The PROCESS view of the bound errand — derived from the dispatcher's live record on every read (storing it
    would leave a stale copy); once the errand is over, the history persisted by `finish_task` remains.
    Fail-soft: without a dispatcher, a bound task shows its stored history and `alive: False`.
    Always a dict, never None (the golden pins view_data's SHAPE): never an errand's surface =
    `{alive: False, phases: []}`, rendered as the plain document."""
    tid = str(db.get("task") or "")
    stored = _clean_phases(db.get("process"))
    if not tid and not stored:
        return {"alive": False, "phases": [], "title": ""}
    live = {}
    if tid:
        try:
            from nucleo import dispatch as _disp
            live = _disp.task_progress(tid) or {}
        except Exception:  # noqa: BLE001
            live = {}
    if live.get("alive"):
        plan = _clean_phases(live.get("plan"))           # V2-820: the worker's declared steps, and how many are done
        return {"alive": True, "phases": _clean_phases(live.get("phases")), "plan": plan,
                "done": max(0, min(int(live.get("done") or 0), len(plan))),
                "title": str(db.get("task_title") or "")}
    return {"alive": False, "phases": stored, "title": str(db.get("task_title") or "")}


def _sections(body: str) -> list:
    out = []
    for b in _blocks(body):
        if b.startswith("#"):
            level = len(b) - len(b.lstrip("#"))
            out.append({"n": len(out) + 1, "title": b.lstrip("# ").strip(), "level": level})
    return out


_STOP = {"the", "and", "that", "with", "this", "from", "show", "section", "part", "where", "which", "what", "about",
         "explaining", "explains", "why", "los", "las", "del", "que", "una", "sobre", "sección", "parte", "donde",
         "enséñame", "muéstrame", "llévame"}


def _blocks(body: str) -> list:
    """Headings on their own, paragraphs as one block each — the units the card renders."""
    out, buf = [], []
    for line in str(body or "").splitlines():
        t = line.strip()
        if t.startswith("#"):
            if buf:
                out.append(" ".join(buf)); buf = []
            out.append(t)
        elif not t:
            if buf:
                out.append(" ".join(buf)); buf = []
        else:
            buf.append(t)
    if buf:
        out.append(" ".join(buf))
    return out


_HYPHENS = "-\u2010\u2011"   # a hyphen joining two letters, never a spaced dash


def _flat(text: str) -> str:
    """Lowercase, a hyphen between two letters read as a space: «proof-of-work» and «proof of work» are one wording."""
    s = str(text or "").lower()
    return "".join(" " if c in _HYPHENS and 0 < i < len(s) - 1 and s[i - 1].isalnum() and s[i + 1].isalnum() else c for i, c in enumerate(s))


def _best_block(body: str, query: str) -> str:
    """The block that best matches: an exact phrase wins; else most query words, a heading winning a tie. A NUMBER the query
    names is the passage's identity — only a block that carries it can match («Paso 2» never lands on «Paso 1», «step 12»
    never on «step 120»). A word counts where a word of the block BEGINS with its stem («work» is in «proof-of-work», never
    in «network»), both sides reading a hyphen between letters as a space."""
    from widgets.numbers_said import numbers_in
    q = _flat(str(query or "").strip())
    if not q:
        return ""
    nums = numbers_in(q)
    blocks = [b for b in _blocks(body) if nums <= numbers_in(b)]
    for b in blocks:
        if len(q) >= 8 and q in _flat(b):
            return b.lstrip("# ").strip()
    words = {w.strip(".,;:«»\"'()?¿!¡") for w in q.split()}
    words = {w for w in words if len(w) >= 4 and w not in _STOP}
    if not words:
        return next((b.lstrip("# ").strip() for b in blocks if b.startswith("#")), "") if nums else ""
    stems, best, score = [w[:6] for w in words], "", 0.0   # a stem: «colonies» finds «Colonies»
    for i, b in enumerate(blocks):
        toks = "".join(c if c.isalnum() else " " for c in _flat(b)).split()   # its words, at every non-letter
        n = sum(1 for st in stems if any(t.startswith(st) for t in toks))
        sc = n + (0.5 if b.startswith("#") else 0) - i * 1e-4
        if n and sc > score:
            best, score = b.lstrip("# ").strip(), sc
    return best


def lead(block: str) -> str:
    """What a reader calls the passage `goto` landed on: its heading, its bold lead («The proposal»), or its first words."""
    t = str(block or "").strip()
    rest = s[2:] if (s := t.lstrip("#").lstrip())[:2] in ("**", "__") else ""
    m = rest[:end] if (end := min([i for i in (rest.find("**", 1), rest.find("__", 1)) if i > 0] or [0])) and "\n" not in rest[:end] else ""   # a bold lead
    name = m or t.lstrip("# ")
    name = " ".join("".join(c for c in name if c not in "*_`~>#[]").split())
    return (name if m or len(name) <= 60 else name[:60].rsplit(" ", 1)[0] + "…").rstrip(".:;, ")
