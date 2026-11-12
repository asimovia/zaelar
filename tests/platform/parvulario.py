"""The kindergarten bench — the five everyday orders, ES and EN, through the REAL voice turn (V2-887).

The operator's yardstick (2026-11-11): «localizar un contacto, mandar un mensaje, leer un email, poner una canción,
apuntar una cita». Each case runs one live turn — the real fast model and the real Jev — through `turn_harness`
with every consequence door closed, and asks two things: did the turn DECIDE the act (the right door, with the
person or the thing he named in its payload), and how long did it take. A turn that only talks, asks «shall I?», or
opens a card instead of acting is red.

    ./.venv/bin/python -m tests.platform.parvulario            # every case, live
    ./.venv/bin/python -m tests.platform.parvulario --only send-es --repeat 3
    ./.venv/bin/python -m tests.platform.parvulario --multi        # the multi-turn cases (`parvulario_turns.py`)

Not part of the unit gate: it spends model calls. Isolated: never the operator's directory, agenda or connectors.
"""
from __future__ import annotations

import argparse
import json
import sys
import time

DIRECTORY = {"contacts": [
    {"id": "c1", "kind": "person", "name": "Raquel Salvador Esteban", "aliases": [], "relation": "",
     "phones": ["+34 600 111 222"],
     "channels": [{"platform": "whatsapp", "handle": "34600111222@s.whatsapp.net",
                   "chatId": "34600111222@s.whatsapp.net", "volume": 5, "last_seen": time.time() - 2 * 86400}]},
    {"id": "c2", "kind": "person", "name": "raquel.salvadoresteban", "aliases": [], "relation": "",
     "channels": [{"platform": "email", "handle": "raquel.salvadoresteban@bt.com",
                   "chatId": "raquel.salvadoresteban@bt.com", "volume": 1, "last_seen": 0}]},
    {"id": "c3", "kind": "person", "name": "Raquel Jofre", "aliases": [], "relation": "",
     "channels": [{"platform": "whatsapp", "handle": "34600333444@s.whatsapp.net",
                   "chatId": "34600333444@s.whatsapp.net", "volume": 1, "last_seen": 0}]},
    {"id": "c4", "kind": "person", "name": "Pedro Salvador", "aliases": [], "relation": "",
     "channels": [{"platform": "whatsapp", "handle": "34600555666@s.whatsapp.net",
                   "chatId": "34600555666@s.whatsapp.net", "volume": 1, "last_seen": 0}]},
]}

#: The messages card with WhatsApp and the mailbox CONNECTED, and one mail waiting — what a linked install shows.
INBOX = {"platforms": {"whatsapp": {"status": "connected", "qr": None}, "email": {"status": "connected", "qr": None},
                       "telegram": {"status": "off", "qr": None}},
         "items": [{"platform": "email", "messageId": "m-1", "chatId": "ana.lopez@example.org",
                    "senderId": "ana.lopez@example.org", "from": "Ana López", "isGroup": False,
                    "subject": "Presupuesto de la reforma",
                    "body": "Hola, te mando el presupuesto: 4.200 € con IVA, empezamos el lunes si te va bien.",
                    "urgencia": "media", "dirigido_a_mi": True, "ts": time.time() - 3600}]}

# (id, lang, phrase, open cards, accepted decisions, words the act's payload must carry)
CASES = [
    ("contact-es", "es", "¿Cuál es el teléfono de Raquel Salvador?", [],
     ("read contactos", "data-op contactos:show_contact", "data-op contactos:show_view", "talk"), ("600",)),
    ("contact-en", "en", "What's Raquel Salvador's phone number?", [],
     ("read contactos", "data-op contactos:show_contact", "data-op contactos:show_view", "talk"), ("600",)),
    ("send-es", "es", "Mándale un whatsapp a Raquel Salvador diciéndole que llego diez minutos tarde", [],
     ("data-op mensajeria:send_to",), ("raquel salvador", "tarde")),
    ("send-en", "en", "Send Raquel Salvador a WhatsApp saying I'll be ten minutes late", [],
     ("data-op mensajeria:send_to",), ("raquel salvador", "late")),
    ("mail-es", "es", "Léeme el último correo que me ha llegado", [],
     ("read mensajeria", "data-op mensajeria:show_view", "data-op mensajeria:open", "data-op mensajeria:read"), ("ana",)),
    ("mail-en", "en", "Read me the last email I got", [],
     ("read mensajeria", "data-op mensajeria:show_view", "data-op mensajeria:open", "data-op mensajeria:read"), ("ana",)),
    ("song-es", "es", "Pon Bohemian Rhapsody de Queen", [], ("music play",), ()),
    ("song-en", "en", "Play Bohemian Rhapsody by Queen", [], ("music play",), ()),
    ("meeting-es", "es", "Apúntame el viernes de doce a ocho de la tarde el partido de baloncesto", [],
     ("data-op agenda:add_meeting",), ("partido",)),
    ("meeting-en", "en", "Put the basketball game on Friday from noon to 8 pm in my calendar", [],
     ("data-op agenda:add_meeting",), ("basketball",)),
    # His session of 2026-11-11, the orders that failed there
    ("alias-es", "es", "Ponle el alias Raquel a Raquel Salvador Esteban", ["contactos"],
     ("data-op contactos:set_alias",), ("raquel",)),
    ("alias-en", "en", "Give Raquel Salvador Esteban the nickname Rachel", ["contactos"],
     ("data-op contactos:set_alias",), ("rachel",)),
    ("import-es", "es", "Tengo conectado Google, impórtame todos los contactos", ["contactos"],
     ("data-op contactos:sync_contacts", "data-op contactos:sync_source"), ()),
    ("import-en", "en", "Google is connected, import all my contacts", ["contactos"],
     ("data-op contactos:sync_contacts", "data-op contactos:sync_source"), ()),
    ("search-add-es", "es", "Busca a qué hora juega el Real Madrid de baloncesto este viernes", [],
     ("search", "escalate"), ()),
]


def _case(cid, lang, phrase, open_cards, _accept, _words) -> dict:
    return {"id": cid, "lang": lang, "phrase": phrase, "screen": {"open": list(open_cards)},
            "widgets": {"contactos": json.loads(json.dumps(DIRECTORY)), "mensajeria": json.loads(json.dumps(INBOX))},
            "connectors": ["whatsapp", "email"], "expect": _accept[0], "accept": list(_accept[1:])}


class _GoogleLinked:
    """Google Calendar and Google Contacts read as CONNECTED for the turn (the bench's install has no tokens; his has
    them). Only the link state is faked — every act still stops at the closed consequence doors."""

    def __enter__(self):
        import importlib
        self._saved = []
        for mod, pid, label in (("connectors.contacts.oauth", "google-contacts", "Google Contacts"),
                                ("connectors.calendar.oauth", "google", "Google Calendar")):
            m = importlib.import_module(mod)
            row = {"id": pid, "label": label, "connected": True, "app_configured": True}
            for name, fake in (("status", lambda *a, _r=row, **k: [dict(_r)]),
                               ("tokens_present", lambda *a, **k: True)):
                if hasattr(m, name):
                    self._saved.append((m, name, getattr(m, name)))
                    setattr(m, name, fake)
        return self

    def __exit__(self, *_e):
        for m, name, old in reversed(self._saved):
            setattr(m, name, old)


def _payload_text(out) -> str:
    return json.dumps([c for c in out.tool_calls], ensure_ascii=False, default=str).lower() + " " + out.reply.lower()


def run(only: str = "", repeat: int = 1) -> int:
    from tests.platform import turn_harness as th
    rows, green = [], 0
    for spec in CASES:
        if only and only != spec[0]:
            continue
        for _ in range(repeat):
            case = _case(*spec)
            with _GoogleLinked():
                out = th.run_case(case, live=True, timeout_s=90)
            why = out.failures(case)
            # A card op runs DRY here (the `widget.data` door is closed), so a view op brings no content back: the words
            # are checked only where the turn READ the card or wrote the act's own payload.
            dry_view = out.decision.startswith("data-op ") and out.decision.endswith(":show_view")
            missing = [] if dry_view else [w for w in spec[5] if w not in _payload_text(out)]
            if missing and not why:
                why.append(f"the act does not carry {missing}")
            ok = not why
            green += ok
            rows.append({"id": spec[0], "ok": ok, "decision": out.decision, "ms": round(out.ms),
                         "reply": out.reply[:140], "why": why[:2],
                         "calls": [str(c)[:160] for c in out.tool_calls][:3]})
            print(f"{'✅' if ok else '❌'} {spec[0]:12} {round(out.ms):6} ms  {out.decision:32} «{out.reply[:90]}»"
                  + ("" if ok else f"\n     ↳ {'; '.join(why)[:300]}"), flush=True)
    total = len(rows)
    print(f"\n{green}/{total} green · median {sorted(r['ms'] for r in rows)[total // 2] if rows else 0} ms")
    return 0 if green == total else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", default="")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--multi", action="store_true", help="the multi-turn cases, judged by their end state")
    ap.add_argument("--json", default="", help="with --multi: write the rows here")
    a = ap.parse_args(argv)
    if a.multi:
        from tests.platform import parvulario_turns
        return parvulario_turns.run(a.only, a.repeat, a.json)
    return run(a.only, a.repeat)


if __name__ == "__main__":
    sys.exit(main())
