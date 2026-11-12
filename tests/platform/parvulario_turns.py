"""The kindergarten bench, MULTI-TURN — a conversation of two or three turns, judged by where it LEFT things.

The single-turn bench (`parvulario.py`) asks «did this order decide the right act?». A person does not talk in single
orders: he answers the agent's own «¿cuál?», corrects the last turn («no, la otra», «I meant tomorrow»), continues with a
pronoun («cancélalo»), builds a request over three turns, says «sí» to what the agent just offered. Each case here is
one of those classes, in Spanish and in English with a word changed (hotel → restaurant, Seville → Los Angeles), and it
states the END STATE — what the agenda holds, who the message went to — never the wording of a reply.

How it runs: one `turn_harness.Isolated(live=True)` per case (the real fast model and the real Jev, an isolated
workspace, database and widget store), the turns in order through the SAME typed voice turn and the same session, so
the conversation window, «what we just did» and the cards' stores carry over exactly as they do between two things he
says. Every consequence door stays closed except `widget.data` for the LOCAL cards (`LOCAL_CARDS`: the agenda and the
directory), which write only the isolated store — so a correction can move what the first turn wrote. A message never
leaves: `mensajeria` stays dry and its act is read from the turn's tool calls.

    ./.venv/bin/python -m tests.platform.parvulario --multi              # every multi-turn case, live
    ./.venv/bin/python -m tests.platform.parvulario --multi --only otra-es
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import json
import time
import unicodedata

#: The cards whose `widget.data` door opens in a multi-turn case: they write the case's isolated store and nothing else.
LOCAL_CARDS = frozenset({"agenda", "contactos"})


def meeting(*words: str, day: str = "", start: str = "", end: str = "") -> dict:
    """A row the agenda must (or must not) hold: one of `words` in its text, and the day/hours when given.
    `day` is `+N` (days from today), `sat` (the next Saturday) or empty (any day)."""
    return {"words": [w.lower() for w in words], "day": day, "start": start, "end": end}


#: (id, lang, class, seeded state, turns, end state). Seeded state: `agenda` rows (`turn_harness` fixtures), `history`
#: (the turns before the first one, as the window holds them), `open` (cards on screen). End state keys:
#: `has` / `lacks` (agenda rows), `after` ({turn index: has}) for a state a middle turn must have reached,
#: `sent` (words the message act must carry) and `not_sent` (words no message act may carry).
CASES = [
    # 1 · the answer to its own «¿cuál?» — two Raquels with WhatsApp, BOTH talked to this week (`TWO_RAQUELS`), so his
    #     «Raquel» reaches two people alike and the send must ask (with the bench's own directory one of them leads by a
    #     recent conversation, and CRIT-M12 sends to her without asking — a different class). He names one after the
    #     first turn; the judge reads who each send ROW went to: none may go to the other Raquel.
    ("cual-es", "es", "answer to «¿cuál?»", {"directory": "two_raquels"},
     ["Mándale un whatsapp a Raquel diciéndole que llego tarde", "A Raquel Jofre"],
     {"sent": ["jofre", "tarde"], "not_sent": ["salvador"]}),
    ("cual-en", "en", "answer to «which one?»", {"directory": "two_raquels"},
     ["Send Raquel a WhatsApp saying I'm running late", "Raquel Jofre"],
     {"sent": ["jofre", "late"], "not_sent": ["salvador"]}),
    # 2 · «no, la otra» — the first turn moved the 10:00, the second says it was the 17:00 one
    ("otra-es", "es", "correction «no, la otra»",
     {"open": ["agenda"], "agenda": [{"title": "Reunión con Marta", "day": "+1", "start": "10:00", "end": "11:00"},
                                     {"title": "Reunión con Marta", "day": "+1", "start": "17:00", "end": "18:00"}]},
     ["Mueve la reunión con Marta de mañana a las diez a las doce",
      "No, perdona, la otra, la de las cinco. La de las diez déjala como estaba"],
     {"has": [meeting("marta", day="+1", start="10:00"), meeting("marta", day="+1", start="12:00")],
      "lacks": [meeting("marta", day="+1", start="17:00")]}),
    ("otra-en", "en", "correction «no, the other one»",
     {"open": ["agenda"], "agenda": [{"title": "Meeting with Mark", "day": "+1", "start": "10:00", "end": "11:00"},
                                     {"title": "Meeting with Mark", "day": "+1", "start": "17:00", "end": "18:00"}]},
     ["Move tomorrow's 10 am meeting with Mark to noon",
      "No, sorry, the other one, the 5 pm one. Leave the 10 am one as it was"],
     {"has": [meeting("mark", day="+1", start="10:00"), meeting("mark", day="+1", start="12:00")],
      "lacks": [meeting("mark", day="+1", start="17:00")]}),
    # 3 · «I meant…» — the day of what the first turn wrote is corrected; one row, on the corrected day
    ("dia-es", "es", "correction «quería decir pasado mañana»", {"open": ["agenda"]},
     ["Apúntame mañana a las nueve de la noche una cena en el restaurante Casa Lucio",
      "No, perdona, quería decir pasado mañana"],
     {"after": {0: [meeting("lucio", day="+1", start="21:00")]},
      "has": [meeting("lucio", day="+2", start="21:00")], "lacks": [meeting("lucio", day="+1")]}),
    ("dia-en", "en", "correction «I meant the day after»", {"open": ["agenda"]},
     ["Put a dinner at the Nobu restaurant in Los Angeles in my calendar tomorrow at 9 pm",
      "No, sorry, I meant the day after tomorrow"],
     {"after": {0: [meeting("nobu", day="+1", start="21:00")]},
      "has": [meeting("nobu", day="+2", start="21:00")], "lacks": [meeting("nobu", day="+1")]}),
    # 4 · a pronoun continuation — «cancélalo» right after creating it
    ("pronombre-es", "es", "pronoun «cancélalo»", {"open": ["agenda"]},
     ["Apúntame pasado mañana a las cinco de la tarde el fisio", "Cancélalo"],
     {"after": {0: [meeting("fisio", day="+2", start="17:00")]}, "lacks": [meeting("fisio")]}),
    ("pronombre-en", "en", "pronoun «cancel it»", {"open": ["agenda"]},
     ["Put the dentist in my calendar the day after tomorrow at 5 pm", "Cancel it"],
     {"after": {0: [meeting("dentist", day="+2", start="17:00")]}, "lacks": [meeting("dentist")]}),
    # 5 · an elaborate request built over three turns — what, then where, then when
    ("tres-es", "es", "request built over 3 turns", {"open": ["agenda"]},
     ["Quiero apuntar algo en la agenda para el sábado",
      "Una comida con Pedro Salvador en el hotel Alfonso XIII de Sevilla",
      "A las dos de la tarde, y que dure dos horas"],
     {"has": [meeting("alfonso", day="sat", start="14:00", end="16:00")]}),
    ("tres-en", "en", "request built over 3 turns", {"open": ["agenda"]},
     ["I want to add something to my calendar for Saturday",
      "Lunch with Pedro Salvador at the Gjelina restaurant in Los Angeles",
      "At 1 pm, for two hours"],
     {"has": [meeting("gjelina", day="sat", start="13:00", end="15:00")]}),
    # 6 · «sí» to the offer the agent just made (the offer is in the window, as his last turn left it)
    ("si-es", "es", "«sí» to its own offer",
     {"open": ["agenda"], "history": [
         {"role": "user", "text": "¿Qué tengo mañana?"},
         {"role": "assistant", "text": "Mañana no tienes nada apuntado. ¿Quieres que te apunte el gimnasio a las "
                                       "siete de la tarde, como cada semana?"}]},
     ["Sí"],
     {"has": [meeting("gimnasio", day="+1", start="19:00")]}),
    ("si-en", "en", "«yes» to its own offer",
     {"open": ["agenda"], "history": [
         {"role": "user", "text": "What do I have tomorrow?"},
         {"role": "assistant", "text": "Nothing in your calendar tomorrow. Shall I put tennis in at 7 pm, like "
                                       "every week?"}]},
     ["Yes please"],
     {"has": [meeting("tennis", day="+1", start="19:00")]}),
]


# ── the judge (pure: a unit test drives it with synthetic states) ───────────────────────────────────────────
def _fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", str(s or "").lower()) if not unicodedata.combining(c))


def resolve_day(spec: str, today: _dt.date | None = None) -> str:
    today = today or _dt.date.today()
    if not spec:
        return ""
    if spec == "sat":
        return (today + _dt.timedelta(days=(5 - today.weekday()) % 7 or 7)).isoformat()
    return (today + _dt.timedelta(days=int(spec))).isoformat()


def _hhmm(v) -> str:
    s = str(v or "").strip()
    if len(s) == 4 and s[1] == ":":
        s = "0" + s
    return s[:5]


def _matches(row: dict, want: dict, today: _dt.date | None) -> bool:
    text = _fold(" ".join(str(row.get(k) or "") for k in ("title", "location", "notes", "description")))
    if not any(_fold(w) in text for w in want["words"]):
        return False
    if want["day"] and str(row.get("date") or "") != resolve_day(want["day"], today):
        return False
    if want["start"] and _hhmm(row.get("startTime")) != want["start"]:
        return False
    if want["end"] and _hhmm(row.get("endTime")) != want["end"]:
        return False
    return True


def _desc(want: dict) -> str:
    return "/".join(want["words"]) + "".join(f" {k}={want[k]}" for k in ("day", "start", "end") if want[k])


def agenda_failures(meetings: list, has=(), lacks=(), today: _dt.date | None = None) -> list[str]:
    why = []
    for want in has:
        if not any(_matches(m, want, today) for m in meetings):
            why.append(f"agenda lacks «{_desc(want)}»")
    for want in lacks:
        hit = [m for m in meetings if _matches(m, want, today)]
        if hit:
            why.append(f"agenda still holds «{_desc(want)}» ({hit[0].get('date')} {hit[0].get('startTime')})")
    return why


def two_raquels() -> dict:
    """The bench's directory with Raquel Jofre talked to as recently as Raquel Salvador: «Raquel» names both alike."""
    import time as _t
    from tests.platform import parvulario as p
    d = json.loads(json.dumps(p.DIRECTORY))
    for c in d["contacts"]:
        if c["id"] == "c3":
            c["channels"][0].update(volume=5, last_seen=_t.time() - 2 * 86400)
    return d


DIRECTORIES = {"two_raquels": two_raquels}


def send_rows() -> list[dict]:
    """The send tasks the case's turns opened (`nucleo/request/send_task`), as the act each one HOLDS now — its card,
    action and payload after any answer filled it — and whether it went: a row still waiting on its question, or
    cancelled, sent nothing. This is the message's end state; the model's call is only what it proposed."""
    from memory import tasks_store as ts
    out = []
    for r in ts.tasks_where(states=ts.LIVE_STATES + ts.DONE_STATES, visible_only=False, limit=200):
        art = (ts.artifacts_of(str(r.get("id") or "")) or {}).get("send")
        if not isinstance(art, dict) or not art.get("action"):
            continue
        out.append({"widget": art.get("widget"), "action": art.get("action"), "payload": art.get("payload") or {},
                    "went": str(r.get("state") or "") in ("running", "done")})
    return out


def _sends(calls: list) -> list[str]:
    """The message acts the turns decided (dry), as text: a `send_to` on the messages card, or a reply to an inbox row
    (`reply_message`, whose recipient is that row's sender, so a reply never carries a name he did not get mail from)."""
    out = []
    for c in calls:
        s = json.dumps(c, ensure_ascii=False, default=str).lower()
        if "send_to" in s or "reply_message" in s or ("mensajeria" in s and "send" in s):
            out.append(s)
    return out


def message_failures(calls: list, sent=(), not_sent=(), rows=None) -> list[str]:
    """`rows` (the send tasks, `send_rows`) when the turns opened any: what WENT is judged, a row waiting on its «which?»
    sent nothing. Without rows, the turns' own message calls are the evidence (a worker-route send never runs dry)."""
    if rows:
        calls = [{"name": "widget_data", "args": {"widget_id": r["widget"], "action": r["action"], "payload": r["payload"]}}
                 for r in rows if r.get("went")]
    sends, why = _sends(calls), []
    if sent and not any(all(_fold(w) in _fold(s) for w in sent) for s in sends):
        why.append(f"no message act carries {list(sent)} ({len(sends)} send act(s))")
    for w in not_sent:
        if any(_fold(w) in _fold(s) for s in sends):
            why.append(f"a message act went to {w!r}")
    return why


def end_state_failures(end: dict, meetings: list, calls: list, today: _dt.date | None = None,
                       rows=None) -> list[str]:
    return (agenda_failures(meetings, end.get("has", ()), end.get("lacks", ()), today)
            + message_failures(calls, end.get("sent", ()), end.get("not_sent", ()), rows))


# ── the run ─────────────────────────────────────────────────────────────────────────────────────────────────
class _LocalCardsOpen:
    """Inside a dry turn, the `widget.data` door passes for `LOCAL_CARDS` only: the agenda and the directory write the
    case's isolated store, every other door (a message, a worker, a cron, music) stays closed. Restored on exit."""

    def __enter__(self):
        from nucleo import consequence as c
        self._c, self._real = c, c.passes

        def passes(door, **what):
            if door == "widget.data" and str(what.get("widget") or "") in LOCAL_CARDS:
                tok = c._blocked.set(c._blocked.get() - {"widget.data"})
                try:
                    return self._real(door, **what)
                finally:
                    c._blocked.reset(tok)
            return self._real(door, **what)

        c.passes = passes
        return self

    def __exit__(self, *_e):
        self._c.passes = self._real


def _seed_case(cid: str, lang: str, seed: dict) -> dict:
    from tests.platform import parvulario as p
    return {"id": cid, "lang": lang, "phrase": "", "screen": {"open": list(seed.get("open") or [])},
            "memory": {"agenda": list(seed.get("agenda") or [])} if seed.get("agenda") else {},
            "widgets": {"contactos": (DIRECTORIES[seed["directory"]]() if seed.get("directory")
                                      else json.loads(json.dumps(p.DIRECTORY))),
                        "mensajeria": json.loads(json.dumps(p.INBOX))},
            "connectors": ["whatsapp", "email"], "expect": "talk", "source": "parvulario"}


def run_one(spec, timeout_s: float = 90.0) -> dict:
    from tests.platform import parvulario as p
    from tests.platform import turn_harness as th
    cid, lang, klass, seed, turns, end = spec
    sid = f"parvulario:{cid}"
    row = {"id": cid, "class": klass, "turns": [], "why": []}
    t0 = time.time()
    with p._GoogleLinked(), th.Isolated(lang, live=True) as iso, _LocalCardsOpen():
        iso.seed(_seed_case(cid, lang, seed))
        from nucleo.cli import turn as cli_turn
        from widgets.agenda import data as agenda
        if seed.get("history"):
            brain = cli_turn._brain(sid)
            brain._window[:] = [{"role": t["role"], "content": t["text"]} for t in seed["history"]]
            brain._seeded = True
        calls: list = []
        try:
            for i, phrase in enumerate(turns):
                t1 = time.time()
                try:
                    res = asyncio.run(asyncio.wait_for(
                        cli_turn.run_turn(phrase, sid=sid, ingest=False, execute=False), timeout_s))
                except Exception as e:  # noqa: BLE001 — a failed turn is reported, the case goes on
                    res = {"ok": False, "error": f"{type(e).__name__}: {e}"[:200]}
                turn_calls = list(res.get("tool_calls") or [])
                calls += turn_calls
                reply = res.get("reply")
                reply = " ".join(reply) if isinstance(reply, list) else str(reply or "")
                row["turns"].append({"say": phrase, "reply": reply[:160], "ms": round((time.time() - t1) * 1000),
                                     "error": "" if res.get("ok", True) else str(res.get("error") or "")[:160],
                                     "calls": [json.dumps(c, ensure_ascii=False, default=str)[:200] for c in turn_calls][:3]})
                for want_has in (end.get("after") or {}).get(i, ()):
                    why = agenda_failures(agenda.load_db().get("meetings") or [], has=[want_has])
                    row["why"] += [f"after turn {i + 1}: {w}" for w in why]
            meetings = list(agenda.load_db().get("meetings") or [])
            sends = send_rows()
            row["why"] += end_state_failures(end, meetings, calls, rows=sends)
            row["sends"] = [f"{'→' if r['went'] else '…'} {r['action']} {json.dumps(r['payload'], ensure_ascii=False)[:120]}"
                            for r in sends]
            row["agenda"] = [f"{m.get('date')} {m.get('startTime')}-{m.get('endTime')} {m.get('title')}" for m in meetings]
        finally:
            cli_turn.reset(sid)
    row["ok"] = not row["why"]
    row["ms"] = round((time.time() - t0) * 1000)
    return row


def run(only: str = "", repeat: int = 1, as_json: str = "") -> int:
    rows = []
    for spec in CASES:
        if only and only != spec[0]:
            continue
        for _ in range(repeat):
            r = run_one(spec)
            rows.append(r)
            print(f"{'✅' if r['ok'] else '❌'} {r['id']:13} {r['ms']:6} ms  {r['class']}", flush=True)
            for t in r["turns"]:
                print(f"     » {t['say'][:70]}\n       « {t['reply'][:110]}" + (f"  ⚠ {t['error']}" if t["error"] else ""))
            if not r["ok"]:
                print(f"     ↳ {'; '.join(r['why'])[:400]}\n     agenda: {r.get('agenda')}\n     sends: {r.get('sends')}")
    green = sum(r["ok"] for r in rows)
    print(f"\n{green}/{len(rows)} green (multi-turn)")
    if as_json:
        with open(as_json, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=1)
    return 0 if rows and green == len(rows) else 1
