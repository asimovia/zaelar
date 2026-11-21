"""A rule he dictates in the conversation, written ONCE and said back as it was understood (V2-046 A1, V2-633, V2-806).

The conversation host's `set_rule` act hands his sentence here (`conversation_host/acts_self._rule`):
`rules.shape.write` makes one structured model call against the declared vocabulary and stores, removes or lists rows
of the rules table — style knobs, permission gates and notes alike, by scope. No regex decides the direction or the
scope of a rule. What it returns is the line the model may say: the shaper's own restatement, with the rows it names
when it lists or asks, or the sentence that a permission about one person was kept as a note, not applied.
"""
from __future__ import annotations

import asyncio

from loguru import logger


async def write(directive: str, text: str, emit) -> dict:
    """Shape and store the rule; `{**result, "line"}` with what was understood, or {} when nothing was written."""
    import rules.shape as _shape
    try:
        res = await asyncio.to_thread(_shape.write, directive, text)
    except Exception as e:  # noqa: BLE001 — said back as «not written» by the caller
        logger.warning(f"rule not written: {e}")
        return {}
    for r in res.get("stored") or []:
        emit("brain", "🧬 user rule guardada (persiste)", text=(r["text"] or directive)[:100], role="system",
             extra={"id": r["id"], "scope": r["scope"], "kind": r["kind"], "key": r["key"]})
    for r in res.get("removed") or []:
        emit("brain", "🧬 user rule retirada", text=(r["text"] or r["id"])[:100], role="system", extra={"id": r["id"]})
    if any(r.get("key") == "excluded" for r in res.get("stored") or []):
        await asyncio.to_thread(_sheets_meet_the_rule)
    return {**res, "line": kept_not_applied(res) or repeat_back(res)}


def kept_not_applied(res: dict) -> str:
    """The line for a permission he stated about ONE PERSON that was kept as a NOTE instead of applied (V2-852 M4): a
    note stored at a consent class's scope (`<domain>/<channel>/<act>`) whose words name somebody of his directory
    (`contactos.people_named`). It says the sentence was kept, not applied, and how to say it so it applies. "" for
    any other write: a write that stored a subject row applied it."""
    import rules
    if any(str(r.get("scope") or "").startswith("subject:") for r in res.get("stored") or []):
        return ""
    for r in res.get("stored") or []:
        sc = str(r.get("scope") or "")
        if r.get("key") == rules.NOTE and sc.count("/") == 2 and not sc.startswith(("widget:", "item:")) \
                and _names_a_person(str(r.get("text") or "")):
            from i18n import langs
            return str(getattr(langs.spec(), "rule_kept_not_applied", "") or "")
    return ""


def _names_a_person(text: str) -> bool:
    try:
        from widgets.contactos import digest
        return bool(digest.people_named(text))
    except Exception as e:  # noqa: BLE001 — unreadable directory: the note's own restatement stands
        logger.debug(f"rules.spoken: directory unread ({e!r})")
        return False


def _sheets_meet_the_rule() -> None:
    """A rule that rules names out applies to the sheets already on screen too (V2-838), not only to the next one."""
    try:
        from widgets.results import category_gate
        category_gate.apply_rules()
    except Exception as e:  # noqa: BLE001 — the rule is stored; the next door that shows a sheet applies it
        logger.warning(f"the sheets on screen did not meet the new rule yet: {e}")


def repeat_back(res: dict) -> str:
    """What the agent says once: the shaper's own restatement, with the rows it names when it lists or asks."""
    import rules.shape as _shape
    say = str(res.get("say") or "").strip()
    rows = res.get("listed") or res.get("doubt") or []
    if rows:
        return (say.rstrip(".:") + ": " if say else "") + _shape.listing_line(rows)
    return say if (res.get("stored") or res.get("removed") or res.get("op") == "list") else ""
