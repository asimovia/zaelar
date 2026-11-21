"""The answer to a waiting question is yes, no or NEITHER (V2-873, ES/EN).

Measured on a Spanish demo pass (2026-11-10):

  · «abre el que sea mejor oferta» (open the best offer — a link) was parked behind «Esto mueve dinero… ¿Sigo?», and
    «vale cierra los resultados» was then taken as the YES to that question and launched «Abrir la mejor oferta».

The classes, each with its mechanism:

  1. The parked errand's question waits on its ROW (a durable ask with two declared answers).
  2. With no pick, only a reply that IS one of the row's declared answers decides (V2-878 §4b: the word tables went):
     «vale cierra los resultados» is neither, whatever card order it opens. The declared yes is still the yes.
"""
from __future__ import annotations

import threading



ORDER = {"es": "vale cierra los resultados", "en": "ok close the results"}
BARE = {"es": "Sí", "en": "Yes"}         # the declared yes of each language (`answer_yes`)


def _brief(result: dict):
    ev = threading.Event()
    ev.set()
    return {"event": ev, "result": {"_call_id": "t", **result}, "_call_id": "t", "turn_id": "t",
            "open_ids": ["results"]}


def _v(choice, conf=0.95):
    return {"choice": choice, "confidence": conf, "probs": {choice: conf}, "used": True}


# ── V2-878 §4b: only the declared answer is read without the brief ─────────────────────────────────────────────


def test_the_waiting_line_exists_in_both_languages():
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[4]
    for lang in ("es", "en"):
        line = json.loads((root / f"i18n/genesis/{lang}/voice.json").read_text(encoding="utf-8"))["errand_still_waiting"]
        assert "{request}" in line, lang
