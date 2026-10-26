"""widgets/mensajeria/mail_rules.py — his criteria over the provider's categories are ROWS of the rules table
(V2-807 T-03, V2-806).

The default is the provider's own sorting (Gmail's Primary / Promotions / Social…): no row, nothing to apply. What he
says on top of it is a `pref` row at `widget:mensajeria`, one per criterion, so it is listed, edited and removed by
id like every other rule (⚙ Settings → Rules, «qué reglas tengo», the card's own list), survives a restart, and is
read by code on every page ask:

  · `mail_route:<who>` = <category>  «los de Amazon que vayan a Principal» — composed into the provider's own
                                      query by the connector, so the lists AND their counts follow it;
  · `mail_hide:<category>` = true     «no me enseñes Social» — the entry leaves the rail.

Nothing here moves mail in his real mailbox: a route changes what a category LISTS, never where a message lives.

Mapping his sentence to a row is the turn model's verdict over what is DECLARED — the categories the provider
returned and a sender he named — passed as `mail_sort`'s payload; there is no verb table here, and a category the
provider never returned is refused, not invented.
"""
from __future__ import annotations

SCOPE = "widget:mensajeria"
ROUTE = "mail_route:"
HIDE = "mail_hide:"
_PUNCT = "._%+@-"      # what an address or a domain may carry beside letters and digits


def _rules():
    import rules
    return rules


def _mine() -> list[dict]:
    return [r for r in _rules().all_rows(include_defaults=False)
            if r["scope"] == SCOPE and r["source"] == "user" and r.get("active", True)
            and str(r["key"]).startswith((ROUTE, HIDE))]


def routes() -> list[dict]:
    """`[{"from", "to"}]` — what the connector composes into each category's query."""
    return [{"from": r["key"][len(ROUTE):], "to": str(r["value"])} for r in _mine() if r["key"].startswith(ROUTE)]


def hidden() -> set[str]:
    return {r["key"][len(HIDE):] for r in _mine() if r["key"].startswith(HIDE) and r["value"]}


def listing() -> list[dict]:
    """His criteria as the card shows them: `[{id, text}]`, oldest first, in his words."""
    return [{"id": r["id"], "text": r["text"] or r["key"]} for r in sorted(_mine(), key=lambda r: r["created_at"])]


def sender(raw) -> str:
    """A sender as the provider's search reads it — an address, a domain or one word — or "" when it is not one."""
    who = str(raw or "").strip().lower().lstrip("@")
    ok = 0 < len(who) <= 120 and who[0].isalnum() and all(c.isalnum() or c in _PUNCT for c in who)
    return who if ok else ""


def _say(key: str, default: str, **kw) -> str:
    try:
        from i18n import runtime as _rt
        text = _rt.text(f"widgets.mensajeria.{key}", default)
    except Exception as e:  # noqa: BLE001 — no language table: the English default stands
        import logging
        logging.getLogger("zaelar.mensajeria.mail_rules").info(f"mail rules: i18n unreadable ({e})")
        text = default
    for k, v in kw.items():
        text = text.replace("{" + k + "}", str(v))
    return text


def _cat_name(key: str) -> str:
    return _say(f"cat_{key}", key)


def apply(payload: dict, declared: list[str]) -> dict:
    """One spoken criterion → one row (or one row gone). `declared` = the categories the provider returned.
    Returns `{ok, changed, said}` or `{ok: False, error, message}`."""
    r = _rules()
    words = str(payload.get("said") or "").strip()
    forget = str(payload.get("forget") or "").strip()
    if forget:
        who = sender(forget)
        gone = [x for x in _mine() if x["id"] == forget or (who and x["key"] in (ROUTE + who, HIDE + who))]
        for x in gone:
            r.remove(x["id"])
        if not gone:
            return {"ok": False, "error": "no_rule", "message": _say("rule_none", "There is no such mail criterion.")}
        return {"ok": True, "changed": "removed", "said": "; ".join(x["text"] for x in gone)}
    if not declared:
        return {"ok": False, "error": "no_categories",
                "message": _say("rule_no_categories", "This mailbox has no categories, only folders.")}
    for field in ("hide", "show"):
        cat = str(payload.get(field) or "").strip().lower()
        if not cat:
            continue
        if cat not in declared:
            return {"ok": False, "error": "unknown_category", "message": _say(
                "rule_unknown_category", "Your provider has no such category. It has: {list}.",
                list=", ".join(_cat_name(c) for c in declared))}
        if field == "show":
            r.clear(SCOPE, HIDE + cat)
            return {"ok": True, "changed": "shown", "said": _cat_name(cat)}
        text = words or _say("rule_hide", "Don't show {cat}", cat=_cat_name(cat))
        r.add(SCOPE, "pref", HIDE + cat, True, text=text, origin="mensajeria.mail_sort")
        return {"ok": True, "changed": "hidden", "said": text}
    to = str(payload.get("to") or payload.get("category") or "").strip().lower()
    who = sender(payload.get("from"))
    if not who:
        return {"ok": False, "error": "no_sender", "message": _say(
            "rule_no_sender", "Tell me the sender as an address, a domain or one word (e.g. amazon.com).")}
    if to not in declared:
        return {"ok": False, "error": "unknown_category", "message": _say(
            "rule_unknown_category", "Your provider has no such category. It has: {list}.",
            list=", ".join(_cat_name(c) for c in declared))}
    text = words or _say("rule_route", "Mail from {from} goes to {to}", **{"from": who, "to": _cat_name(to)})
    r.add(SCOPE, "pref", ROUTE + who, to, text=text, origin="mensajeria.mail_sort")
    return {"ok": True, "changed": "routed", "said": text}
