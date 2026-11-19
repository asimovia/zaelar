"""LEAVE A GROUP («borra los grupos X y "Lista de la compra"», «delete the groups X and Y»): he leaves each named group
and the chat is removed from his list. It cannot be undone, so it resolves EVERY name against his own group chats
first — one name not found or ambiguous and nothing is ordered, with the candidates named so he can be asked.

Every module-level name of `data` is read through it (`_d.<name>`), so a patch on `data` still governs every call.
"""
from __future__ import annotations

from .. import data as _d

_LEAVE_PLATFORMS = ("whatsapp", "telegram")
_QUOTES = "«»\"'“”‘’"


def _norm(s) -> str:
    from ..views.thread import _norm_txt
    return " ".join(_norm_txt(str(s or "").strip(_QUOTES + " ")).split())


def _group_chats(db: dict, platform: str = "") -> list[dict]:
    """His GROUP chats as the card holds them: the connector's chat list rows of kind group, and the group threads
    held here. One row per (platform, chatId)."""
    rows: dict = {}
    for plat in _LEAVE_PLATFORMS:
        if platform and plat != platform:
            continue
        for cid, r in (((db.get("chat_index") or {}).get(plat) or {}).get("rows") or {}).items():
            if isinstance(r, dict) and (r.get("kind") == "group" or str(cid).endswith("@g.us")) and r.get("name"):
                rows[(plat, str(cid))] = {"platform": plat, "chatId": str(cid), "name": str(r["name"])}
    for k, th in (db.get("threads") or {}).items():
        plat, _sep, cid = str(k).partition("|")
        if plat in _LEAVE_PLATFORMS and (not platform or plat == platform) and cid and isinstance(th, dict) \
                and (th.get("isGroup") or cid.endswith("@g.us")) and th.get("name"):
            rows.setdefault((plat, cid), {"platform": plat, "chatId": cid, "name": str(th["name"])})
    for g in _directory_groups(platform):   # his groups the directory holds, whether or not the chat list was loaded
        rows.setdefault((g["platform"], g["chatId"]), g)
    return list(rows.values())


def _directory_groups(platform: str = "") -> list[dict]:
    """The group rows of his directory (a linked source feeds them, V2-934) with the chat each lives in. Measured
    2026-11-18: «delete those two groups» found nothing because the card's chat list had never been opened, while his
    directory held both."""
    out = []
    try:
        from widgets import directory
        for c in directory._contacts():
            if str(c.get("subtype") or c.get("kind") or "") != "group" or not c.get("name") or not directory.level(c):
                continue                      # a hidden or blocked row is not a group he has
            for ch in c.get("channels") or []:
                plat, cid = str(ch.get("platform") or ""), str(ch.get("chatId") or "")
                # WhatsApp only: its group id is the chat's own (`…@g.us`); Telegram's directory id is not the
                # chat list's marked id, and a wrong one reaches the wrong dialog
                if plat == "whatsapp" and (not platform or plat == platform) and cid.endswith("@g.us"):
                    out.append({"platform": plat, "chatId": cid, "name": str(c["name"])})
    except Exception as e:  # noqa: BLE001 — an unreadable directory adds nothing; the card's own list stands
        from loguru import logger
        logger.debug(f"leave_group: the directory's groups unread — {e!r}")
    return out


def _match(pool: list[dict], said: str) -> list[dict]:
    """The rows a spoken name means: the exact names (accents and case aside) when any, else those containing it."""
    want = _norm(said)
    if not want:
        return []
    exact = [r for r in pool if _norm(r["name"]) == want]
    return exact or [r for r in pool if want in _norm(r["name"])] or _sounds(pool, said)


def _sounds(pool: list[dict], said: str) -> list[dict]:
    """The rows whose name carries EVERY word he said by the one ranking names are read with (`contactos/who`: the same
    word, its sound — a silent h, b/v —, a stem or one slip): «Club Hípica» is «Club Ípica». Never a partial."""
    try:
        from widgets import directory
        from widgets.contactos import who
        q = directory._norm(str(said or "").strip(_QUOTES + " "))
        words = directory._tokens(q)
        hits = [(who.score(q, {"name": r["name"]}, words), r) for r in pool] if words else []
        full = [(s, r) for s, r in hits if s.get("score") and s.get("confidence") != "partial"]
        best = max((s["score"] for s, _r in full), default=0)
        return [r for s, r in full if s["score"] >= best - 1e-9]
    except Exception as e:  # noqa: BLE001 — unread: what the literal match found stands
        from loguru import logger
        logger.debug(f"leave_group: names unread by sound — {e!r}")
        return []


def _names(raw, pool: list[dict]) -> list[str]:
    """His names, one per group: a list, or a text split on «,», « y », « and » — unless the whole text IS one of
    his groups (a group called «Ana y Luis» stays one)."""
    out: list[str] = []
    for x in ([raw] if isinstance(raw, str) else list(raw or [])):
        s = str(x or "").strip(_QUOTES + " ")
        if not s:
            continue
        if any(_norm(r["name"]) == _norm(s) for r in pool):
            out.append(s)
            continue
        out += [p.strip(_QUOTES + " ") for p in s.replace(" y ", ",").replace(" and ", ",").split(",")
                if p.strip(_QUOTES + " ")]
    return out


def resolve(db: dict, payload: dict) -> tuple[list[dict], dict | None]:
    """`(the group rows he named, None)`, or `([], refusal)` when one name is not found or is ambiguous."""
    raw = str(payload.get("platform") or payload.get("channel") or "").strip().lower()
    platform = _d._PLAT_ALIASES.get(raw, raw) if raw else ""
    if platform and platform not in _LEAVE_PLATFORMS:
        return [], {"ok": False, "error": "leave_group solo sale de grupos de 'whatsapp' o 'telegram'",
                    "missing": "platform"}
    pool = _group_chats(db, platform)
    said = _names(payload.get("groups") or payload.get("group") or payload.get("name"), pool)
    if not said:
        return [], {"ok": False, "error": "leave_group necesita `groups`: los nombres de los grupos", "missing": "groups"}
    found, problems, candidates = [], [], {}
    for s in said[:20]:
        hits = _match(pool, s)
        if len(hits) > 1 and payload.get("every") is True:      # he said «all of them»: every group that name is
            found += [h for h in hits if h not in found]
            continue
        if len(hits) == 1:
            if hits[0] not in found:
                found.append(hits[0])
            continue
        if hits:
            candidates[s] = [f"{h['name']} ({h['platform']})" for h in hits[:6]]
            problems.append(f"«{s}»: hay varios — {', '.join(candidates[s])}")
        else:
            candidates[s] = []
            problems.append(f"«{s}»: no está en tu lista de grupos")
    if problems:
        return [], {"ok": False, "error": "no salgo de ningún grupo hasta saber cuáles son: " + " | ".join(problems),
                    "missing": "groups", "candidates": candidates}
    return found, None


def refusal(payload: dict) -> dict | None:
    """What `leave_group` would refuse, read before any question is asked (`would_refuse`)."""
    return resolve(_d.load_db(), dict(payload or {}))[1]


def shown(payload: dict) -> dict:
    """The groups as FOUND in his list, for the confirmation's `{groups}` blank — never his raw words."""
    found, no = resolve(_d.load_db(), dict(payload or {}))
    return {} if no else {"groups": ", ".join(f"«{r['name']}»" for r in found)}


def _a_leave_group(action, payload) -> dict:
    db = _d.load_db()
    found, no = resolve(db, dict(payload or {}))
    if no:
        return no
    ref = _d._outbound.new_ref()
    lane = _d._outbound.lane.passes("group_leave", "", {"ref": ref})   # held → nothing is queued
    names = [r["name"] for r in found]
    plats = sorted({r["platform"] for r in found})
    from .. import sent as _sent    # the order's receipt: one outbox row, settled when every chat is gone
    _sent.outbox_open(db, ref, {"platform": plats[0] if len(plats) == 1 else "", "name": ", ".join(names)}, "",
                      kind="group_leave")
    _sent.outbox_wait(db, ref, [f"{r['platform']}|{r['chatId']}" for r in found])
    said = payload.get("groups") or payload.get("group") or payload.get("name")
    for r in db.get("outbox") or []:      # his words as he said them: what the declared end state is rendered from
        if r.get("ref") == ref:
            r["said"] = said if isinstance(said, str) else ", ".join(str(x) for x in said or [])
    for plat in plats:
        db.setdefault("pending_group_leave", []).append(
            {"platform": plat, "ref": ref, "lane": lane,
             "chats": [{"chatId": r["chatId"], "name": r["name"]} for r in found if r["platform"] == plat]})
    _d.store.save(_d.WIDGET_ID, db)
    return {"ok": True, "result": {"groups": names, "platforms": plats, "ref": ref,
                                   "detail": "pedido a la app; saldrán de tu lista de chats"}, **_d.view_data()}
