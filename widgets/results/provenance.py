"""widgets/results/provenance.py — a result is a FINDING, never a status: every row names where it came from (V2-868 D4).

Measured on the operator's console: an errand parked on a sign-in wrote ONE row whose facts were its own status
(«login pending», «daily check 11:00») plus a price it recalled from memory, and the sheet showed it as a result.
Nothing in a status says where it was found — and that is the structural difference, not its words: a row that
STATES data (a price, facts, a score, parts) is a finding, and a finding has a `url` (the page it was read on, or a page of one of its parts), or names a `source` the sheet knows (its Sources
tab, or the sources the same write reports). A row with neither is filed in `rejected` with a reason the worker
reads in the action's reply, and never reaches the list. A row that states nothing (a bare name) claims nothing.
The screen applies to what the WORKER writes (see `WRITER`): the engine's producers read a page or an index.
"""
from __future__ import annotations

#: The payload key the worker's bridge stamps on every write it makes to this sheet (`nucleo/cli/worker_api_exec`,
#: `widget_data`), overriding whatever the worker wrote there. The engine's own producers — a browser extraction
#: (`intake.push`), Zaelar's search (`nucleo/acts/search_sheet`) — carry the page or the index they read by
#: construction; the WORKER is the one writer that can put its own status on the sheet, so its rows are screened.
WRITER, WORKER = "writer", "worker"
#: The reason a row without provenance is filed with (English: ours, not the worker's words).
WHY = "no url and no known source — a result says where it was found"
#: Who filed it, on the rejected row (the category gate files as «category gate»).
FILED_BY = "provenance"


def _domain(url: str) -> str:
    u = str(url or "").strip().lower()
    host = u.split("//", 1)[-1].split("/", 1)[0]
    return host[4:] if host.startswith("www.") else host


def _norm(s) -> str:
    return " ".join(str(s or "").strip().lower().split())


def known(data: dict, payload: dict | None = None) -> set[str]:
    """Every name and domain of a source the sheet knows: its Sources tab plus the sources this write reports."""
    out: set[str] = set()
    raw = list(data.get("sources") or []) + list(((payload or {}).get("sources") or []) if isinstance(
        (payload or {}).get("sources"), list) else [])
    for s in raw:
        if not isinstance(s, dict):
            continue
        if s.get("name"):
            out.add(_norm(s["name"]))
        if s.get("url"):
            out.add(_domain(s["url"]))
    out.discard("")
    return out


#: The fields by which a row STATES something about the world (a price, facts, a score). A bare name claims nothing
#: that could be false; a row that states data must say where it read it.
CLAIMS = ("price", "facts", "score", "parts")


def sourced(item: dict, sources: set[str]) -> bool:
    """Does `item` say where it was found? A url of its own or of one of its parts, or a source the sheet knows. A row
    that states no data (no price, facts, score or parts) claims nothing and needs no provenance."""
    if not any(item.get(k) not in (None, "", [], {}) for k in CLAIMS):
        return True
    if str(item.get("url") or "").strip():
        return True
    if any(isinstance(p, dict) and str(p.get("url") or "").strip() for p in item.get("parts") or []):
        return True
    src = item.get("source")
    return bool(src) and (_norm(src) in sources or _domain(str(src)) in sources)


def screen(data: dict, items: list[dict], payload: dict | None = None) -> tuple[list[dict], dict]:
    """(rows with provenance, extra for the action's reply). Rows without one go to `data["rejected"]`. Only a write
    the worker's bridge stamped (`WRITER`) is screened."""
    if str((payload or {}).get(WRITER) or "") != WORKER:
        return items, {}
    srcs = known(data, payload)
    on, off = [], []
    for it in items:
        (on if sourced(it, srcs) else off).append(it)
    if not off:
        return on, {}
    from widgets.results import data as _d
    cur = list(data.get("rejected") or [])
    seen = {(_norm(x.get("url")) or _norm(x.get("title"))) for x in cur}
    for it in off:
        row = {"title": str(it.get("title") or "")[:300], "why": WHY, "source": FILED_BY}
        key = _norm(row["title"])
        if key and key not in seen:
            seen.add(key)
            cur.append(row)
    data["rejected"] = cur[:_d._MAX_REJECTED]
    titles = [str(it.get("title") or "")[:80] for it in off]
    return on, {"no_provenance": titles,
                "note_for_worker": ("Not listed, filed in rejected (" + WHY + "): " + " · ".join(titles)
                                    + ". A status of your own task (a sign-in pending, a schedule) is not a result: "
                                      "say it in your report, never as a row.")}
