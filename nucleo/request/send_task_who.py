"""nucleo/request/send_task_who.py — a send reaches the person he named, or it asks ONE question: never a guess.

The fourth piece of `nucleo/request/send_task` (V2-847: «a message to whom he named or to nobody»), measured on the
multi-turn bench (2026-11-12) with two Raquels on WhatsApp:

  · `readdressed` — «send Raquel a WhatsApp saying I'm running late» came out as `reply {n: 1}`: a reply goes to whoever
    wrote row 1 (Ana López, a stranger to this order), and «Raquel Jofre» on the next turn kept `n: 1`. An act whose
    recipient the CARD resolves from a row reference (`slots.recipient.from == "card"`) reaches that row's person; when
    his words name somebody of his directory and that person is not who the row reaches, the act is not his: it becomes
    the card's act that writes to a PERSON (the leaving act whose recipient is `his_words`, the manifest's `primary`
    first) with the person his words name and the same words. Nothing is read off phrasing: the slots, the card's own
    `recipients_of` and the directory decide.
  · `which` — the model wrote «Raquel Salvador Esteban» for his «Raquel» while his word reaches two people the directory
    cannot tell apart (no one leads by `clear_margin`, CRIT-M12): the recipient slot is the AGENT's, not his. Or it passed
    his «Raquel» as he said it, and that reaches the same two. Either is the one question «which Raquel?» on the send's
    row (before anything runs, so his answer has a row to fill), with the people his word reaches as candidates — his answer fills
    the slot and the same row runs (`send_task_answer.answered`). A word that leads to one person is his (`is_his`)
    and never asks.
"""
from __future__ import annotations

from nucleo.request import base, note

RECIPIENT, TEXT, CHANNEL = "recipient", "text", "channel"


def _key(slots: dict, slot: str) -> str:
    d = slots.get(slot) or {}
    return str(d.get("key") or slot) if d else ""


def _person_act(wid: str) -> str:
    """The card's leaving act that writes to a PERSON his words name, the manifest's `primary` first; "" when none."""
    from nucleo.request.ending import leaving_acts
    from nucleo.workers import exit_slots
    from widgets import effects
    acts = (effects._manifest(base(wid)).get("actions") or {})
    fits = [a for a in leaving_acts(wid)
            if (exit_slots.declared(base(wid), a).get(RECIPIENT) or {}).get("from") == "his_words"
            and _key(exit_slots.declared(base(wid), a), TEXT)]
    return sorted(fits, key=lambda a: (not bool((acts.get(a) or {}).get("primary")), a))[0] if fits else ""


def _as_said(word: str, said: str) -> str:
    """His word as he wrote it (the folded token back to his spelling), so the card's door and the question name it."""
    from nucleo.acts.message_names import TOK, fold
    return next((t for t in TOK.findall(str(said or "")) if fold(t) == word), word)


def _reaches_nobody(wid: str, action: str, payload: dict) -> bool:
    """A row-reference act that names nobody either answers the conversation on screen (the card's `recipients_of`
    stays silent about it on purpose) or reaches no one at all — the act would refuse (`contract.would_refuse`)."""
    try:
        from widgets import contract
        return bool(contract.would_refuse(base(wid), action, dict(payload or {})))
    except Exception as e:  # noqa: BLE001 — unread: keep the call
        note(e)
        return False


def readdressed(wid: str, action: str, payload: dict | None, said: str, *, emit=None) -> tuple[str, str, dict]:
    """`(wid, action, payload)` as the act he ordered: unchanged unless a row-reference act would reach somebody his words
    do not name while they name somebody else (see the module). Never raises."""
    p = dict(payload or {})
    try:
        from nucleo import on_his_behalf as _ob
        from nucleo.acts import message
        from nucleo.request.send_task_words import his_word_for_people
        from nucleo.workers import exit_slots
        slots = exit_slots.declared(base(wid), action)
        if (slots.get(RECIPIENT) or {}).get("from") != "card":
            return wid, action, p
        who = _ob.who_of(wid, action, p)
        if any(message.is_his(w, [said]) for w in who):
            return wid, action, p
        if not who and not _reaches_nobody(wid, action, p):
            return wid, action, p                # the conversation on screen, which naming again would only slow
        text = str(p.get(_key(slots, TEXT)) or "")
        word, rows = his_word_for_people(said, text)
        act = _person_act(wid) if word and rows else ""
        if not act:
            return wid, action, p
        to = exit_slots.declared(base(wid), act)
        person = str(rows[0].get("name") or "") if len(rows) == 1 else _as_said(word, said)
        out = {_key(to, RECIPIENT): person, _key(to, TEXT): text}
        chan = str(p.get(_key(slots, CHANNEL)) or p.get("platform") or p.get("channel") or "")
        if chan and _key(to, CHANNEL):
            out[_key(to, CHANNEL)] = chan
        _emit(emit, "📨 a reply to someone he did not name → a message to the one he named",
              f"{wid}:{action} → {act} · {', '.join(who)} → {person}",
              {"cat": "flash", "id": wid, "from_action": action, "action": act, "row_person": who, "his": person})
        return wid, act, {k: v for k, v in out.items() if k and str(v or "").strip()}
    except Exception as e:  # noqa: BLE001 — unread: the call stands, and the exit door still asks about its person
        note(e)
        return wid, action, p


def which(art: dict, said: str) -> tuple[str, str, list[str]] | None:
    """`(slot, payload key, candidates)` when the person slot is the agent's pick among several people his word reaches
    alike; None when it is his, names nobody of his, or his word leads to one person. Never raises."""
    try:
        from nucleo.request.send_task import AGENT
        from nucleo.request.send_task_words import his_word_for_people
        from widgets import directory
        slots = art.get("slots") or {}
        payload = dict(art.get("payload") or {})
        text = str(payload.get(str((slots.get(TEXT) or {}).get("key") or TEXT)) or "")
        chan = str(payload.get(str((slots.get(CHANNEL) or {}).get("key") or CHANNEL)) or "")
        for slot, d in slots.items():
            if str(d.get("rule") or "") != "his_words":
                continue
            plat = chan.strip().lower()
            # the value itself reaching several alike (his «Raquel», as the card's own usage asks the model to pass
            # it) — or, when the value is the agent's pick, the word of his it was picked from
            hits = directory.resolve(str(payload.get(str(d.get("key") or slot)) or ""), tolerant=False, platform=plat)
            if len(hits) < 2 and str(d.get("source") or "") == AGENT:
                word, _rows = his_word_for_people(said, text)
                hits = directory.resolve(word, tolerant=False, platform=plat) if word else []
            if len(hits) < 2:
                continue
            names = [str(c.get("name") or "") for c in hits[:directory.CANDIDATES_MAX] if c.get("name")]
            return slot, str(d.get("key") or slot), names
    except Exception as e:  # noqa: BLE001 — unread: the exit door still asks about a person he did not name
        note(e)
    return None


def said_word(art: dict, slot: str, said: str) -> str:
    """His word for the person the «which?» is about, as he said it."""
    from nucleo.request.send_task_words import his_word_for_people
    payload = dict(art.get("payload") or {})
    text = str(payload.get(str(((art.get("slots") or {}).get("text") or {}).get("key") or "text")) or "")
    word, _rows = his_word_for_people(said, text)
    if word:
        return _as_said(word, said)
    key = str(((art.get("slots") or {}).get(slot) or {}).get("key") or slot)
    return str(payload.get(key) or "").strip() or slot


def which_line(word_said: str, names: list[str]) -> str:
    """«¿Cuál Raquel? Tengo a …» from the language table (`send_which_recipient`)."""
    try:
        from i18n import langs
        tpl = str(getattr(langs.current_language(), "send_which_recipient", "") or "")
        if tpl:
            return tpl.format(who=word_said, names=", ".join(names))
    except Exception as e:  # noqa: BLE001
        note(e)
    return f"{word_said}? ({', '.join(names)})"


def _emit(emit, label: str, text: str, extra: dict) -> None:
    try:
        if emit is None:
            from voice.observer import emit as _e
            emit = _e
        emit("brain", label, text=str(text or "")[:300], role="system", extra=extra)
    except Exception as e:  # noqa: BLE001
        note(e)
