"""The engine's seams for the `a2a` library (V2-866): where its grants live, who decides a standing «never», what the
calendar item reads, which contacts discovery looks up, and the outbound scanner. Pure adapters — no network, no
thread; `server/a2a_api.py` builds the agent from them only when A2A is switched on."""
from __future__ import annotations

import datetime as _dt
from dataclasses import asdict

from loguru import logger

import a2a

RULE_KIND, RULE_KEY, RULE_ORIGIN = "gate", "a2a", "a2a"
_MAX_DAYS = 14


def grant_scope(audience: str, item: str) -> str:
    """`contact:<cid>` → `subject:<cid>/a2a/<item>` (V2-857); a group or `network` keeps its own name."""
    who = audience[len("contact:"):] if audience.startswith("contact:") else audience
    return f"subject:{who}/a2a/{item}"


class RulesGrantStore:
    """`GrantStore` over the rules table: one `gate`/`a2a` row per grant, its value the grant itself. A row of that
    key is applied by code only (the prompt reads `consent` rows), so a grant costs no prompt."""

    def list(self) -> list:
        from rules import store
        out = []
        for r in store.rows():
            if r.get("key") != RULE_KEY or r.get("origin") != RULE_ORIGIN or not r.get("active", True):
                continue
            try:
                out.append(a2a.Grant(**r["value"]))
            except (TypeError, KeyError) as exc:
                logger.debug("a2a: server/a2a_wiring.py:list failed: {!r}", exc)
                continue
        return out

    def put(self, g) -> None:
        from rules import store
        store.put({"id": f"a2a_{g.id}", "scope": grant_scope(g.audience, g.item), "kind": RULE_KIND, "key": RULE_KEY,
                   "value": asdict(g), "except": [], "source": "user", "text": "", "created_at": g.created,
                   "active": True, "until": g.expires_at or None, "origin": RULE_ORIGIN})

    def delete(self, grant_id: str) -> None:
        from rules import store
        store.delete(f"a2a_{grant_id}")


def policy(cid: str, item: str, verb: str) -> str | None:
    """`Grants.policy` → `consent.decide_act`: the grant row is his yes, so only his own standing rule for this
    person or this class (`ask` / `never`) speaks; otherwise no opinion and the row decides."""
    try:
        from nucleo import consent
        v = consent.decide_act(f"a2a.{verb}", channel=item, level="standard", his_yes=True, licensed=True,
                               subject=cid)
    except Exception as e:                                  # noqa: BLE001 — a broken policy denies nothing new
        logger.debug(f"a2a policy unread: {type(e).__name__}")
        return None
    verdict = str(v.get("verdict") or "")
    if verdict == consent.REFUSE:
        return "never"
    if verdict == consent.ASK_CONSENT:
        return "ask"
    return None


def busy(frm: str, to: str) -> list[dict]:
    """The calendar item's free/busy: timed appointments between two dates, intervals only (no title leaves)."""
    from widgets.agenda import data as agenda_data, free
    try:
        d0 = _dt.date.fromisoformat(str(frm)[:10])
        d1 = _dt.date.fromisoformat(str(to or frm)[:10])
    except ValueError as exc:
        logger.debug("a2a: server/a2a_wiring.py:busy failed: {!r}", exc)
        return []
    meetings = agenda_data.load_db().get("meetings") or []
    out = []
    for i in range(min(max((d1 - d0).days, 0) + 1, _MAX_DAYS)):
        day = (d0 + _dt.timedelta(days=i)).isoformat()
        for s, e, _title in free.busy(meetings, day):
            out.append({"start": f"{day}T{s // 60:02d}:{s % 60:02d}", "end": f"{day}T{e // 60:02d}:{e % 60:02d}"})
    return out


def public_profile() -> dict:
    from config import v2
    p = v2.get("a2a").get("public_profile")
    return dict(p) if isinstance(p, dict) else {}


def contacts() -> list[dict]:
    """Discovery's input: `[{cid, name, emails, phones}]` from the contacts widget."""
    from widgets.contactos import data, model
    out = []
    for c in data.load_db().get("contacts") or []:
        emails, phones = model.values(c, "emails"), model.values(c, "phones")
        if c.get("id") is not None and (emails or phones):
            out.append({"cid": str(c["id"]), "name": str(c.get("name") or ""), "emails": emails, "phones": phones})
    return out


def scan_outbound(text: str) -> str | None:
    """The engine's outbound scanner (the same one a cluster message passes): a reason blocks the send."""
    from connectors.meshkore import security
    _clean, reason = security.scan_outbound(text)
    return reason


# ── widget-declared items (V2-866 F3 item 6) ────────────────────────────────────────────────────────────────────
# A widget declares WHAT it shares in its manifest (`shareable`); the engine holds HOW each projection is read,
# keyed `<widget>:<projection>`. A projection with no reader here is not served (the peer gets `unknown_item`).

def _agenda_items(args: dict) -> list[dict]:
    """One task list's items — title and done/todo only (no dates, no notes leave)."""
    from widgets.agenda import data as agenda_data, task_read
    rows = task_read.items(agenda_data.load_db(), str(args.get("list") or task_read.GENERAL))
    return [{"title": r["title"], "done": r["status"] == "done"} for r in rows][:100]


def _activity_summary(_args: dict) -> list[dict]:
    """The last activities: kind, day, distance, minutes, average heart rate — never the route."""
    from widgets.activity import data as act
    out = []
    for h in (act.view_data().get("history") or [])[:5]:
        out.append({"kind": h.get("kind"), "started_at": h.get("started_at"), "distance_m": h.get("distance_m"),
                    "elapsed_s": h.get("elapsed_s"), "hr_avg": h.get("hr_avg")})
    return out


def _freebusy_reader(args: dict) -> list[dict]:
    return busy(str(args.get("from", "")), str(args.get("to", "")))


READERS = {"agenda:freebusy": _freebusy_reader, "agenda:items": _agenda_items,
           "activity:summary": _activity_summary}


def declare_widget_items(reg) -> list[str]:
    """Every built-in widget manifest's `shareable` entries → items of `reg` (overrides a default of the same id)."""
    import json
    from pathlib import Path
    out = []
    root = Path(__file__).resolve().parents[1] / "widgets"
    for man in sorted(root.glob("*/manifest.json")):
        try:
            entries = json.loads(man.read_text(encoding="utf-8")).get("shareable")
        except (OSError, ValueError) as exc:
            logger.debug("a2a: server/a2a_wiring.py:declare_widget_items failed: {!r}", exc)
            continue
        if entries:
            out += a2a.declare_manifest(reg, man.parent.name, entries, READERS)
    return out
