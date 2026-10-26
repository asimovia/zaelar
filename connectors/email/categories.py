"""connectors/email/categories.py — the Inbox as the PROVIDER sorts it, and the unread count of every folder
(V2-807 T-01).

Over IMAP a Gmail Inbox holds every category at once — Primary, Promotions, Social, Updates, Forums — which is why
the card counted «1603 unread» where his Primary had 14. Gmail does not expose categories as folders; it exposes
them through its search extension (`X-GM-EXT-1`, `X-GM-RAW "category:primary"`). `categories.json` declares that
extension by the CAPABILITY that announces it, so nothing here is a guess about a provider's name: a server that
advertises the extension and answers a category's search has that category; any other server has folders only.

His own criteria ride on top as ROUTES — `{"from": "amazon.com", "to": "primary"}` — composed into the provider's
own query (`{category:primary from:amazon.com}` for Primary, `-from:amazon.com` for every other category), so the
lists and their counts follow his rule and nothing moves in his real mailbox. A route token is an address, a domain
or a word; anything else is dropped, so a route can never inject search syntax.

Every read is read-only and runs inside a connection the caller opened and selected.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

_log = logging.getLogger("zaelar.email.categories")

_DECL = json.loads((Path(__file__).with_name("categories.json")).read_text(encoding="utf-8"))["extensions"]
_TOKEN_PUNCT = "._%+@-"     # what an address or a domain may carry beside letters and digits
MAX_FOLDERS = 40


def supported(im) -> dict | None:
    """The declared extension this server advertises, or None."""
    caps = {(c if isinstance(c, str) else c.decode("ascii", "ignore")).upper()
            for c in (getattr(im, "capabilities", None) or ())}
    return next((dict(v, name=k) for k, v in _DECL.items() if k.upper() in caps), None)


def clean_routes(routes) -> list[dict]:
    """Routes reduced to what can be composed safely: a token the provider's `from:` reads, to a declared key."""
    out = []
    for r in routes or []:
        who, to = str((r or {}).get("from") or "").strip().lower(), str((r or {}).get("to") or "").strip().lower()
        if to and 0 < len(who) <= 120 and who[0].isalnum() and all(c.isalnum() or c in _TOKEN_PUNCT for c in who):
            out.append({"from": who, "to": to})
    return out


def query(ext: dict, key: str, routes=None) -> str:
    """The provider's search for one category with his routes applied."""
    rs = clean_routes(routes)
    base = ext["category"].format(key=key)
    mine = [ext["from"].format(who=r["from"]) for r in rs if r["to"] == key]
    others = [ext["from"].format(who=r["from"]) for r in rs if r["to"] != key]
    q = "{" + " ".join([base] + mine) + "}" if mine else base
    return " ".join([q] + ["-" + o for o in others])


def _search(im, ext: dict, q: str) -> list[int] | None:
    st, data = im.uid("SEARCH", ext["search"], '"' + q.replace("\\", "").replace('"', "") + '"')
    if st != "OK":
        return None
    out = []
    for chunk in data or []:
        raw = chunk.decode("ascii", "ignore") if isinstance(chunk, (bytes, bytearray)) else str(chunk or "")
        out.extend(int(t) for t in raw.split() if t.isdigit())
    return sorted(set(out))


def summary(im, ext: dict, routes=None) -> list[dict]:
    """`[{key, unread}]` for every declared category whose search the server answers, in declared order. The Inbox
    must already be selected."""
    out = []
    for key in ext["keys"]:
        try:
            uids = _search(im, ext, query(ext, key, routes) + " " + ext["unread"])
        except Exception as e:  # noqa: BLE001 — a category the server cannot search is not listed
            _log.info(f"email categories: {key} not searchable ({type(e).__name__})")
            continue
        if uids is not None:
            out.append({"key": key, "unread": len(uids)})
    return out


def page_uids(im, ext: dict, key: str, routes=None, before=None, limit: int = 30) -> tuple[list[int], str | None, bool]:
    """One page of a category, newest first: (uids, next cursor, complete). The cursor is the lowest UID shown."""
    uids = _search(im, ext, query(ext, key, routes)) or []
    try:
        cut = int(str(before)) if before else None
    except (TypeError, ValueError):
        cut = None
    pool = [u for u in uids if cut is None or u < cut]
    take = pool[-max(1, int(limit)):]
    complete = len(take) == len(pool)
    return sorted(take, reverse=True), (None if complete or not take else str(min(take))), complete


def unseen_counts(im, folders: list[dict]) -> dict[str, int]:
    """{folder name: unread} as the server counts it (`STATUS (UNSEEN)`), for the folders listed."""
    out = {}
    for f in (folders or [])[:MAX_FOLDERS]:
        name = str(f.get("name") or "")
        try:
            st, data = im.status(f'"{name}"' if " " in name else name, "(UNSEEN)")
            m = re.search(rb"UNSEEN (\d+)", (data or [b""])[0] or b"") if st == "OK" else None
            if m:
                out[name] = int(m.group(1))
        except Exception as e:  # noqa: BLE001 — a folder without a count shows none, never 0
            _log.info(f"email categories: no count for a folder ({type(e).__name__})")
    return out
