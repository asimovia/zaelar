"""nucleo/acts/correction_undo.py — a correction that does the last act on ANOTHER row undoes the first one.

Multi-turn bench (2026-11-12): «mueve la reunión con Marta de mañana a las diez a las doce» moved the 10:00; «no,
perdona, la otra, la de las cinco — la de las diez déjala como estaba» is ONE correction with two consequences: the
other row moves, and the first goes back. The model emitted the move of the other row only; the first stayed at 12:00.

The mechanism bounds a consequence, never a judgement: only when the brief reads `corrects_last` surely AND his turns'
last act was this card's (`stop.corrected_card`, a fact), the correcting act is the SAME action of that card, and the
card itself answers that its last act can be undone for an act on another row (`widgets.<card>.data.undo_of`, the
card's own hook — the card knows what its act wrote and where it was). Then the undo runs first, once per act, through
the same door. No word of his sentence is read here.

The correction is ONE unit, whatever the model emitted (bench 2026-11-12, 3 of 4 in Spanish): the model wrote only the
move BACK — the undo — and never the move of the other row, and the mouth said «Listo.». So the act it corrects is
recorded at the door (`_OWED`), a door question asks what kind of correction it is (`KEY`, asked only on such a turn,
`brief_doors.DOORS["correct"]`), and when the turn's acts have landed `complete` reads the card's END STATE
(`widgets.<card>.data.correction_owed`): on a sure «another item» whatever is still owed — the move back, the same move
on the other row — runs through the same door; when the card cannot name the other row, or the verdict is not sure
enough to act, the mouth says only part was done instead of a completion nobody attested.
"""
from __future__ import annotations

import importlib

from loguru import logger

_UNDONE: set = set()
#: The undo each turn ran, by its trace: the model's OWN move back in the same turn («leave the 10 am one as it was»,
#: written as a second call) is that undo already — run again it would move the row that now sits in its place.
_RAN: dict = {}
UNDONE, ALREADY = "undone", "already"
#: This turn's calls on a card, by trace: a move back the model ALREADY wrote earlier in the turn is the undo itself.
_SEEN: dict = {}
#: Set while the undo itself runs through the door: its own call must not meet this hook again.
_IN_UNDO = __import__("contextvars").ContextVar("correction_undo_in_undo", default=False)


#: The door question: what kind of correction this is. Asked only when a correcting act of the card's last act is at
#: the door (`brief_doors.DOORS["correct"]`), never on the turn's own trip.
KEY = "correction_kind"
ANOTHER, SAME, UNDO_ONLY = "another_item", "same_item", "undo_only"
INSTRUCTIONS = ("We just did something for the operator, described below, and he is correcting it. Which correction "
                "is it, in any wording or language? 'another_item' when we did it to the WRONG item and he wants "
                "exactly the same change made to a different one (the item we changed is left or put back as it "
                "was); 'same_item' for any other change — the item was right but the change was wrong, or he wants "
                "a different change (another time, day or value) on any item; 'undo_only' when he only wants what we "
                "did undone, and nothing else changed.")
CRITERIA = {ANOTHER: "the change went to the wrong item: exactly the same change, made to another item instead",
            SAME: "a different change — another time, day or value — on the same item or on another one",
            UNDO_ONLY: "only undo what we did; nothing else is to change"}
#: The correcting act of THIS turn, by trace: `{trace: {wid, card, action, last, apply, undone}}`.
_OWED: dict = {}
#: How long `complete` waits for the card's own ops of the turn, and for the door's verdict.
WAIT_S = 2.0


def question(_ctx=None) -> dict | None:
    """The door question about his last act (None when there is none to correct)."""
    try:
        from nucleo.flash import redo_decision
        op = redo_decision.last_op()
        if not op:
            return None
        return {"instructions": f"{INSTRUCTIONS} [What we just did: {redo_decision._describe(op)}]",
                "criteria": dict(CRITERIA)}
    except Exception as e:  # noqa: BLE001
        logger.debug(f"correction_undo: no question — {e!r}")
        return None


def _same(call: dict, undo: dict) -> bool:
    """Is this call the undo again — every key it carries, the undo carries with the same value?"""
    norm = lambda v: " ".join(str(v or "").split()).lower()  # noqa: E731
    keys = [k for k, v in (call or {}).items() if str(v or "").strip()]
    return bool(keys) and all(k in undo and norm(call[k]) == norm(undo[k]) for k in keys)


def _base(wid: str) -> str:
    return str(wid or "").split("::", 1)[0].strip().lower()


def undo_first(wid: str, action: str, payload: dict | None, brief, *, apply, emit=None) -> str:
    """Run the card's undo of his last act before this correcting act, when every condition above holds: `UNDONE`.
    `ALREADY` when this call IS the undo this turn already ran (the caller drops it); "" otherwise. Never raises."""
    if _IN_UNDO.get():
        return ""
    try:
        from voice import trace as _trace
        tr = str(_trace.current() or "")
        ran = _RAN.get(tr)
        if ran and ran[0] == _base(wid) and ran[1] == str(action or "") and _same(dict(payload or {}), ran[2]):
            return ALREADY
        seen = _SEEN.setdefault(tr, [])
        if len(_SEEN) > 8:
            for k in list(_SEEN)[:-8]:
                _SEEN.pop(k, None)
        earlier = list(seen)
        seen.append((_base(wid), str(action or ""), dict(payload or {})))
        from nucleo import done_ops
        from nucleo.request import stop
        card = _base(wid)
        if not card or _base(stop.corrected_card(brief)) != card:
            return ""
        last = done_ops.his_last()
        if _base(last.get("wid")) != card or str(last.get("action") or "") != str(action or ""):
            return ""
        key = (str(last.get("trace") or ""), float(last.get("at") or 0.0))
        if key in _UNDONE or (key[0] and key[0] == str(_trace.current() or "")):
            return ""                        # undone already, or an act of THIS turn (his own two-act order)
        mod = importlib.import_module(f"widgets.{card}.data")
        if callable(getattr(mod, "correction_owed", None)) and tr not in _OWED:
            _OWED.clear()                    # one turn's correction at a time
            _OWED[tr] = {"wid": wid, "card": card, "action": str(action or ""), "brief": brief,
                         "last": dict(last.get("payload") or {}), "apply": apply, "undone": False}
            from nucleo.turn import brief_doors
            brief_doors.fire(brief, "correct")
        hook = getattr(mod, "undo_of", None)
        got = hook(action, dict(last.get("payload") or {}), dict(payload or {})) if callable(hook) else None
        if not got or any(c == card and a == got[0] and _same(p, got[1]) for c, a, p in earlier):
            return ""                        # no undo, or the model already wrote it earlier in this turn
        _UNDONE.add(key)
        if tr in _OWED:
            _OWED[tr]["undone"] = True
        _RAN.clear()
        _RAN[str(_trace.current() or "")] = (card, str(got[0]), dict(got[1]))
        if callable(emit):
            emit("brain", "↩️ a correction onto another row — the last act is undone first", text=f"{wid}:{got[0]}",
                 role="system", extra={"cat": "flash", "id": wid, "action": got[0], "payload": got[1]})
        tok = _IN_UNDO.set(True)
        try:
            apply(wid, got[0], got[1])
        finally:
            _IN_UNDO.reset(tok)
        return UNDONE
    except Exception as e:  # noqa: BLE001 — unread: the correcting act runs alone, as before
        logger.debug(f"correction_undo: not undone ({e!r})")
        return ""


async def complete(tasks=()) -> list:
    """After the turn's acts on the card landed: what the correction still owes, read from the card's END STATE. On a
    sure `another_item` the owed calls run through the same door (their ops join `tasks`); a correction the card cannot
    finish, or a verdict not sure enough to act, is an `unmet` outcome — never a completion nobody attested. [] when
    this turn corrected nothing, the engine already ran the undo (the model named the other row), or nothing is owed."""
    try:
        from voice import trace as _trace
        st = _OWED.pop(str(_trace.current() or ""), None)
        if not st or st["undone"]:
            return []
        import asyncio
        mine = [t for w, t in (tasks or ()) if str(w).split("::")[0] == st["card"] and not t.done()]
        if mine:
            await asyncio.wait(mine, timeout=WAIT_S)
        hook = getattr(importlib.import_module(f"widgets.{st['card']}.data"), "correction_owed", None)
        owed = hook(st["action"], st["last"]) if callable(hook) else None
        if not owed or not (owed.get("calls") or owed.get("open")):
            return []
        from nucleo.turn import brief_doors, verdicts
        await brief_doors.landed(st["brief"], "correct", WAIT_S, ask=False)
        choice, info = verdicts.read(st["brief"], KEY, None)
        if not info or choice != ANOTHER:
            return []
        sure = verdicts.read(st["brief"], KEY, None, min_confidence=verdicts.VETO)[1] is not None
        if sure and owed.get("calls") and not owed.get("open"):
            from voice.observer import emit
            emit("brain", "↩️ a correction onto another row — what it still owed runs at the door", role="system",
                 text=f"{st['wid']}:{len(owed['calls'])}", extra={"cat": "flash", "id": st["wid"], "calls": owed["calls"]})
            tok = _IN_UNDO.set(True)
            try:
                for act, payload in owed["calls"]:
                    st["apply"](st["wid"], act, dict(payload))
            finally:
                _IN_UNDO.reset(tok)
            return []
        return _part_only(st["card"], st["action"])
    except Exception as e:  # noqa: BLE001 — unread: the model's acts stand, as before
        logger.debug(f"correction_undo: not completed ({e!r})")
        return []


def _part_only(card: str, action: str) -> list:
    from i18n import langs
    from nucleo.circuit import verdict as V
    from nucleo.flash import card_receipt
    from nucleo.turn.reply import Outcome
    tpl = str(getattr(langs.current_language(), "reply_part_only", "") or "")
    if not tpl:
        return []
    line = tpl.format(cards=card_receipt.card_name(card))
    return [Outcome(V.UNMET.name, card, action, reason=line, said=line)]


def reset() -> None:
    _OWED.clear()
    _UNDONE.clear()
    _RAN.clear()
    _SEEN.clear()
