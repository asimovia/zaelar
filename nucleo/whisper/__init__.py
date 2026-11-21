"""nucleo/whisper — the whisperer: a typed slot filled BETWEEN requests, never a voice (V2-889 F2, V2-942).

Independent of the conversation manager, kept OFF and with no subscriber (V2-942 W1): nothing calls it today. What it
reads from a closed request and what it may do with a misunderstanding are open (V2-942 T4, T5). Its entry is
`run.on_turn_closed(payload)`, on its own thread; a deterministic gate decides whether it is worth a call (`gate.py`);
its output is a typed slot with no instruction field (`slot.py`); in shadow the slot is only measured — what it would
render (`render.py`) is an event, wired into no prompt.
"""
