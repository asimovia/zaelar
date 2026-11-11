"""Where the map's places come from (V2-879 O1): the ROWS of the results sheet, or a place he NAMED.

Measured in the sandbox, es and en, with zero rows on the sheet and a search still running: «ponme esas cafeterías en
el mapa» / «put those coffee shops on the map» reached the map as `show` with eight coffee shops the model named from
its own knowledge, as plain strings, and the turn said «Te las pongo en el mapa». The class: the map's `show` took
its places from anywhere, so nothing tied what it painted to what he was pointing at.

Two sources, both honest:
  · `rows` — rows of the sheet, by their 1-based number or title, or `"all"`: resolved HERE from the sheet's own data
    (read-only), so a pin is a row he can see. Over a sheet with no rows the answer says so; it never paints another.
  · `places` — free places. Kept when the place IS a row of the sheet he is looking at (the row wins: its link
    travels), or when HE said its name (`nucleo.his_words`), or when no sheet is on screen or being filled («show me
    Madrid», a plan the turn itself laid out). Over a sheet that is on screen or still filling, a free place that is
    neither a row nor his word is the model's own — not a source — and is refused, naming what the sheet holds.

Nothing here reads his words for a meaning: a free place's own name is looked for in what he said, the way a selector
is. Pure reads; never writes the sheet.
"""
from __future__ import annotations

import time

from loguru import logger

from widgets import textmatch as _tm

ALL = "all"
#: How far back his words still name a place («the second one» minutes after «where is Retiro?»).
_HIS_WORDS_S = 30 * 60


def _r():
    from widgets.results import data as r
    return r


def _open_sheets() -> set | None:
    """Sheet ids the canvas reports OPEN (`results::x` → `x`, plain `results` → ``); None when it never reported."""
    try:
        from server.voice_api import open_instances
        inst = open_instances()
    except Exception as e:  # noqa: BLE001 — unknown, not «none open»
        logger.debug(f"map.sheet: open apps unread — {type(e).__name__}: {e}")
        return None
    if not inst:
        return None
    out = set()
    for cid in inst:
        base, _, sid = str(cid).partition("::")
        if base.strip().lower() == "results":
            out.add(_r()._safe_sheet(sid))
    return out


def _live_sheets() -> set:
    try:
        from widgets.results.sheet_names import _live_sheets as live
        return set(live())
    except Exception as e:  # noqa: BLE001
        logger.debug(f"map: live sheets unread — {type(e).__name__}: {e}")
        return set()


def _sheet(sid: str, *, live: set, open_: set | None) -> dict | None:
    try:
        view = _r().view_data(sid) or {}
    except Exception as e:  # noqa: BLE001
        logger.debug(f"map.sheet: sheet {sid!r} unread — {e!r}")
        return None
    return {"id": sid, "title": str(view.get("title") or "").strip(),
            "items": [i for i in (view.get("items") or []) if isinstance(i, dict)],
            "live": sid in live, "open": bool(open_ and sid in open_)}


def _named_sheet(sheet, have: list) -> str | None:
    """The existing sheet a `sheet` value names — its id or its title, as the card shows it (measured, en: the model
    sent the sheet's TITLE). A name that matches no sheet names none: it never becomes an empty sheet of its own."""
    r, want = _r(), _tm.fold(str(sheet).removeprefix("results::"))
    for sid in have:
        if want and (_tm.fold(sid) == want or _tm.fold((r.view_data(sid) or {}).get("title")) == want):
            return sid
    return None


def referent(sheet=None) -> dict | None:
    """The sheet «those» points at: the one named, else the newest OPEN one, else the newest still filling.
    `{"id", "title", "items", "live", "open"}`, or None when no sheet is on screen or being filled."""
    r = _r()
    try:
        have = r.sheets()
    except Exception as e:  # noqa: BLE001
        logger.debug(f"map: sheets unread — {type(e).__name__}: {e}")
        have = []
    open_, live = _open_sheets(), _live_sheets()
    sid = _named_sheet(sheet, have) if sheet is not None and str(sheet).strip() else None
    if sid is None:
        sid = next((pool[-1] for pool in ([s for s in have if open_ and s in open_], [s for s in have if s in live])
                    if pool), None)
    return None if sid is None else _sheet(sid, live=live, open_=open_)


def newest_with_rows() -> dict | None:
    """When nothing is on screen or filling, `rows` still means the newest sheet that has rows."""
    try:
        for sid in reversed(_r().sheets()):
            got = _sheet(sid, live=set(), open_=None)
            if got and got["items"]:
                return got
    except Exception as e:  # noqa: BLE001
        logger.debug(f"map.sheet: sheets unread — {e!r}")
    return None


def as_place(row: dict) -> dict:
    """One sheet row as a place the map locates: its title, its subtitle as the address hint, its own link."""
    return {"name": str(row.get("full_title") or row.get("title") or "").strip()[:120],
            "address": str(row.get("subtitle") or "").strip()[:200], "url": str(row.get("url") or "").strip()[:500],
            "note": str(row.get("price") or row.get("badge") or "").strip()[:160]}


def pick_rows(ref, sheet: dict) -> tuple[list, list]:
    """(rows named, references that named no row). `ref` is `"all"`, one reference, or a list of them."""
    items = sheet.get("items") or []
    refs = ref if isinstance(ref, list) else [ref]
    if any(str(x).strip().lower() in (ALL, "*") for x in refs if not isinstance(x, (dict, list))):
        return list(items), []
    find = _r()._find
    got, missed = [], []
    for x in refs:
        if isinstance(x, dict):
            x = x.get("title") or x.get("name") or x.get("id") or ""
        row = find(items, "", index=x) if isinstance(x, (int, str)) and str(x).strip() else None
        if row is None:
            missed.append(str(x))
        elif row not in got:
            got.append(row)
    return got, missed


def _said_by_him(name: str) -> bool:
    words = {t for t in _tm.fold(name.split(",")[0]).split(" ") if len(t) > 2 and t not in _tm._GENERIC}
    if not words:
        return False
    try:
        from nucleo import his_words
        said = his_words.since(time.time() - _HIS_WORDS_S)
    except Exception as e:  # noqa: BLE001 — his words unread: not his
        logger.debug(f"map: his words unread — {type(e).__name__}: {e}")
        return False
    return any(words <= set(_tm.fold(t).split(" ")) for t in said)


def judge_free(places: list, sheet: dict | None) -> tuple[list, list]:
    """(places kept, names refused). A free place that is a row of the sheet becomes that row; one he named stays;
    over a sheet on screen or still filling, any other is the model's own and is refused."""
    if sheet is None:
        return places, []
    find, items = _r()._find, sheet.get("items") or []
    kept, refused = [], []
    for p in places:
        row = find(items, p.get("name") or "") if items else None
        if row is not None:
            kept.append(as_place(row))
        elif _said_by_him(p.get("name") or ""):
            kept.append(p)
        else:
            refused.append(p.get("name") or "")
    return kept, refused


def refusal(sheet: dict, refused: list) -> dict:
    """The answer when a call over a sheet carried nothing that is a row of it or a place he named."""
    n = len(sheet.get("items") or [])
    where = f"the sheet «{sheet['title']}»" if sheet.get("title") else "the results sheet"
    state = f"{where} has {n} row{'' if n == 1 else 's'}" + (" and its search is still going" if sheet["live"] else "")
    named = ", ".join(x for x in refused[:5] if x)
    return {"ok": False, "error": "not_a_sheet_row", "sheet_rows": n, "refused": refused[:12],
            "detail": (f"{state}" + (f"; {named} — not rows of it, nor places he named" if named else "")
                       + ". Pass `rows` (numbers, titles or \"all\") for the places on the sheet; places of your own "
                       "are never a stand-in for rows that are not there. Nothing was pinned.")}
