"""widgets/contactos/sources.py — WHERE the imported directories come from, and when (V2-714).

`imports.py` decides how a foreign row folds into ours; this decides who is asked and how often. Same cut
as `gcontacts.py`: the widget's data layer never talks to a connector, and a connector never writes to the
store.

## The three, and they are not alike

  · **telegram** — the account enumerates its own address book and its own dialogs, so this is EXACT. The
    connector owns the client, so the request goes on its queue and the answer comes back through the same
    seam every other Telegram pull uses.
  · **whatsapp** — the bridge accumulates what the socket tells it. There is no «give me everything» call
    on this platform (see `absorb`), so a pass brings what is known SO FAR and the card says so.
  · **meshkore** — no connector call at all: the clusters are already in this house
    (`manager.clusters()`). A cluster is a group whose members are AGENTS, and reading it costs nothing,
    so it is refreshed on every pass.

## Continuous import is continuous DISCOVERY

`tick` runs from the widget cron while the source is on. It never rewrites a field he can edit — that rule
lives in `imports.merge_contacts` and this module has no way to override it.

## What the platform changes reaches the directory by itself (2026-11-18)

A person renamed on the platform, a number learned behind an account: PUSHED when the connector can tell
(`contacts_bus.take_pushed`, absorbed as a `refresh` — it only touches people already here), and PULLED on every
pass of a linked source.

## A linked source feeds the directory by itself (2026-11-18, 2026-11-21)

Linking a source IS the ask, and there is no switch to undo it. ONE door, `import_linked`, reads every linked source
(Google Contacts and the import-only ones) and is called from exactly three places: when a source is linked (the
Google consent, a messaging account seen connected for the first time), and at the engine's start for every source
whose book was never read here (a fresh install, the start a reset ends in, a source linked while the engine was off). After that the inbound half runs on its own cadence (`tick`, every `EVERY_S`). A
person it brings that a row already proves (a phone, an address, an account — `identity.find`) becomes a CHANNEL of
that row; only the others become rows.

## The directory is not bounded by the message window

How much of an account's PAST is copied is bounded (`connectors/messaging/history.py`); who is IN the directory
is not. A pass reads the platform's own book — its address book and every named one-to-one conversation it lists —
so a person with no message inside the window is still a row.
"""
from __future__ import annotations

import time

from loguru import logger
from widgets.say import say

#: Sources this module can pull. `google-contacts` is NOT here: it has its own two-way sync in
#: `gcontacts.py`, which is a different contract and stays that way.
KNOWN = ("telegram", "whatsapp", "meshkore")

#: How long between automatic passes. Generous on purpose: an address book is not a feed, and a pass that
#: brings nothing new still costs a platform round-trip.
EVERY_S = 900.0


def state(db: dict) -> dict:
    """Per-source sync state for the card: `{last, added, error}`."""
    raw = db.setdefault("sources", {})
    for s in KNOWN:
        raw.setdefault(s, {"last": 0.0, "added": 0, "error": ""})
    return raw


def connected(source: str) -> bool:
    """Is the underlying connector actually linked? A sync switch on a source he never connected would be
    a promise the card cannot keep."""
    try:
        from connectors import registry
        for d in registry.descriptors():
            if str(d.get("id") or "") == source:
                return bool(d.get("connected"))
    except Exception:  # noqa: BLE001
        pass
    return False


#: How each source is named to him.
_LABEL = {"telegram": "Telegram", "whatsapp": "WhatsApp", "meshkore": "MeshKore", "google-contacts": "Google"}


def connected_sources(but: str = "") -> list[str]:
    """The sources whose connector is linked RIGHT NOW (Google Contacts and the import-only ones) — what an offer
    names; `but` is left out. Only a linked connector is offered: an offer the next turn cannot keep is no offer."""
    out = [s for s in ("google-contacts", *KNOWN) if connected(s)]
    return [s for s in out if s != str(but or "").strip().lower()]


# ── the three normalisers ───────────────────────────────────────────────────────────────────────────────

def _meshkore_payload() -> dict:
    """Clusters as GROUPS whose members are agents (V2-714).

    A cluster is exactly the shape `imports.merge_groups` wants — it has a name, an id that does not
    change (`cluster_id`), and a member list (`online`). The members are not people, so they arrive as
    `kind: "agent"`: addressable through the cluster channel, and never folded into somebody's family.
    """
    try:
        from connectors import meshkore as _mk
        rows = _mk.get_manager().clusters()
    except Exception as e:  # noqa: BLE001
        logger.debug(f"contactos.sources: meshkore unavailable ({e})")
        return {"contacts": [], "groups": []}
    groups = []
    for c in rows or []:
        name = str(c.get("name") or "").strip()
        cid = str(c.get("cluster_id") or name)
        if not name:
            continue
        members = [{"name": str(h), "kind": "agent",
                    "externalIds": {"meshkore": f"{cid}/{h}"},
                    "channels": [{"platform": "meshkore", "handle": f"{name}/{h}"}]}
                   for h in (c.get("online") or []) if str(h or "").strip()]
        groups.append({"name": name, "platform": "meshkore", "subtype": "cluster",
                       "externalIds": {"meshkore": cid},
                       "channels": [{"platform": "meshkore", "handle": name, "chatId": cid}],
                       "members": members})
    return {"contacts": [], "groups": groups}


def _ask_connector(source: str, timeout: float = 25.0) -> dict:
    """Put a contacts request on the connector's queue and wait for its answer.

    The queue is the seam every other pull in these two connectors already uses (`_drain_fetch`,
    `_drain_history`): the connector owns its client and its event loop, and nothing outside it may touch
    either. A timeout is not an error worth shouting about — the next tick asks again.
    """
    try:
        from connectors.messaging import contacts_bus
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"sin bus de contactos ({e})"}
    try:
        return contacts_bus.request(source, timeout=timeout)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def _payload(source: str) -> dict:
    if source == "meshkore":
        return {"ok": True, **_meshkore_payload()}
    return _ask_connector(source)


# ── the two entry points ────────────────────────────────────────────────────────────────────────────────

def sync_now(source: str) -> dict:
    """One pass of one source, right now. Returns the counts `apply_action` speaks back."""
    source = (source or "").strip().lower()
    if source not in KNOWN:
        return {"ok": False, "error": f"no sé importar contactos de «{source}» — tengo {', '.join(KNOWN)}"}
    if source != "meshkore" and not connected(source):
        return {"ok": False, "error": "source_not_connected", "source": source}
    t0 = time.time()
    got = _payload(source)
    logger.info(f"contactos: {source} contestó en {time.time() - t0:.1f}s → ok={got.get('ok')} "
                f"pending={bool(got.get('pending'))} {len(got.get('contacts') or [])} personas")
    if got.get("pending"):
        return {"ok": False, "pending": True, "error": str(got.get("error") or "")}
    try:
        return _absorb(source, got)
    except Exception as e:  # noqa: BLE001 — it runs in a pool thread that nobody awaits past 8 s: say it HERE
        logger.exception(f"contactos: no pude incorporar lo que trajo {source}: {e}")
        return {"ok": False, "error": f"no pude incorporar los contactos de {source}: {e}"}


def _absorb(source: str, got: dict, *, refresh: bool = False) -> dict:
    """Fold one connector answer into the directory — the answer asked for now, one that arrived late, or (with
    `refresh`) what the platform pushed: only people already here, and never counted as a pass of the source."""
    from . import data as _d, imports
    with _d.store.mutating(_d.WIDGET_ID):         # the merge and a concurrent add must not erase each other
        return _absorb_locked(source, got, _d, imports, refresh)


def _absorb_locked(source: str, got: dict, _d, imports, refresh: bool = False) -> dict:
    db = _d.load_db()
    st = state(db)[source]
    if not got.get("ok", True) or got.get("error"):
        st["error"] = str(got.get("error") or "no pude leer esa fuente")
        _d.store.save(_d.WIDGET_ID, db)
        return {"ok": False, "error": st["error"]}
    if not refresh:
        _names_seen(source, got.get("contacts") or [])
    res = imports.absorb(db, got, source=source, **({"refresh": True} if refresh else {}))
    if not refresh:
        st.update({"last": time.time(), "added": int(res.get("added") or 0), "error": "",
                   "partial": bool(got.get("partial"))})
    _d.store.save(_d.WIDGET_ID, db)
    logger.info(f"contactos: {'refresh' if refresh else 'import'} {source} → +{res['added']} new, "
                f"{res['filled']} completed, {res.get('merged', 0)} folded into one person")
    return {"ok": True, "source": source, **res}


def _names_seen(source: str, rows: list[dict]) -> int:
    """Add to each arriving person the names its own conversation has carried in the message log
    (`connectors.messaging.archive.chats`) — the account by its conversation id, or by the phone that id is. A linked
    device is told a chat's name once and the log keeps every name it saw: the same account can be the name she
    chose on one id and the name he saved on another. A name several accounts carry is nobody's (the log files
    his own name under every conversation he wrote in). Returns how many rows gained a name; never raises."""
    from . import identity
    try:
        from connectors.messaging import archive
        by: dict[str, set] = {}
        holders: dict[str, set] = {}
        for ch in archive.chats(source) or []:
            cid, name = str(ch.get("chatId") or ""), " ".join(str(ch.get("name") or "").split())
            if ch.get("kind") != "person" or not cid or not identity.real_name(name):
                continue
            key = identity._account_phone(source, "chatId", cid) or cid
            by.setdefault(key, set()).add(name)
            holders.setdefault(name.casefold(), set()).add(key)
        gained = 0
        for r in rows:
            cid = str((r.get("externalIds") or {}).get(source) or "")
            keys = {cid, identity._account_phone(source, "chatId", cid), identity.phone_key(r.get("phone"))} - {""}
            names = sorted(n for k in keys for n in by.get(k, ()) if len(holders[n.casefold()]) == 1)
            names = [n for n in names if n.casefold() != str(r.get("name") or "").casefold()
                     and n not in (r.get("knownAs") or [])]
            if names:
                r["knownAs"] = list(r.get("knownAs") or []) + names
                gained += 1
        return gained
    except Exception as e:  # noqa: BLE001 — the pass goes on with the names the platform gave
        logger.debug(f"contactos.sources: the log's names for {source} were not read ({e})")
        return 0


def _due(source: str, st: dict, now: float) -> bool:
    """Is a pass owed? Every `EVERY_S` for a linked source (MeshKore's clusters are always in this house)."""
    if now - max(float(st.get("last") or 0.0), float(st.get("tried") or 0.0)) < EVERY_S:
        return False
    return source == "meshkore" or connected(source)        # asked last: it reads the connectors' registry


def import_linked(only: tuple = ()) -> dict:
    """THE door that fills the directory from every linked source (or the ones `only` names): Google Contacts read,
    never written to, and each import-only source read once. Called when a source is linked, at the end of a reset
    and at a start for every book never read here — never on a timer. Returns each source's counts; never raises."""
    from . import gcontacts
    out = {}
    for s in only or ("google-contacts", *KNOWN):
        try:
            if s == "google-contacts":
                if gcontacts.linked():
                    out[s] = gcontacts.pull()
            elif s == "meshkore" or connected(s):
                out[s] = sync_now(s)
        except Exception as e:  # noqa: BLE001 — one source that fails never stops the others
            out[s] = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    logger.info(f"contactos: import of the linked sources → { {k: v.get('added', v.get('error')) for k, v in out.items()} }")
    return out


def import_in_background(only: tuple = ()) -> None:
    """`import_linked` on its own thread: a reset, a start or a consent never waits on a platform's book."""
    __import__("threading").Thread(target=import_linked, args=(only,), name="contacts-import", daemon=True).start()


def unread(db: dict) -> tuple:
    """The sources whose book was never read into this directory — the start reads the linked ones among them."""
    st = {**state(db), "google-contacts": db.get("sync") or {}}
    return tuple(s for s in ("google-contacts", *KNOWN) if not float(st[s].get("last") or 0.0))


_SEEN: set = set()


def linked_now(source: str) -> None:
    """A messaging account was seen connected (its connector says so on every pass): the first time in this process,
    when its book was never read here, it is read now."""
    if source in _SEEN or source not in KNOWN:
        return
    _SEEN.add(source)
    from . import data as _d
    if not float(state(_d.load_db())[source].get("last") or 0.0):
        import_in_background((source,))


def owe_members(db: dict) -> list[str]:
    """Once per store: every source that gave groups WITH members is owed a read — the pass that tells who is his
    (its book, his conversations) from who was only seen in a group, and keeps the second out of sight
    (`imports.merge_groups`). The sources marked."""
    if db.get("members_kept"):
        return []
    db["members_kept"] = 1
    out = []
    for s, st in state(db).items():
        has = any(c.get("kind") == "group" and c.get("members") and (c.get("platform") or c.get("source")) == s
                  for c in db.get("contacts") or [])
        if has and st.get("last"):
            st["partial"] = True
            out.append(s)
    return out


def _tried(source: str) -> None:
    """Stamp an automatic try, so a source that answers nothing is not asked again on every tick."""
    from . import data as _d
    with _d.store.mutating(_d.WIDGET_ID):
        db = _d.load_db()
        state(db)[source]["tried"] = time.time()
        _d.store.save(_d.WIDGET_ID, db)


def tick(ctx) -> None:
    """Continuous import, from the widget cron. Best-effort and quiet: a source that cannot be read is a
    line in the log and a message on the card, never a raised turn."""
    from . import data as _d
    # An answer that came back after its ask gave up is absorbed here, whether or not the source is «on»:
    # he asked for it, and it arrived (2026-09-26 — Telegram takes ~25 s, the ask waited 25 s).
    for s in ("telegram", "whatsapp"):
        try:
            from connectors.messaging import contacts_bus
            late = contacts_bus.take_late(s)
            if late is not None:
                r = _absorb(s, late)
                logger.info(f"contactos.sources: respuesta tardía de {s} incorporada → {r.get('added', 0)} nuevos")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"contactos.sources: no pude incorporar la respuesta tardía de {s}: {e}")
    try:                                     # what a platform pushed: a rename, a number learned (refresh only)
        from connectors.messaging import contacts_bus
        for s, rows in (contacts_bus.take_pushed() or {}).items():
            if s in KNOWN and rows:
                _absorb(s, {"ok": True, "contacts": rows, "groups": []}, refresh=True)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"contactos.sources: what the platform pushed was not absorbed: {e}")
    try:
        db = _d.load_db()
        due = [s for s, st in state(db).items() if _due(s, st, time.time())]
    except Exception:  # noqa: BLE001
        return
    for s in due:
        try:
            _tried(s)
            sync_now(s)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"contactos.sources: tick de {s} falló: {e}")
