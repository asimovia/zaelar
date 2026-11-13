"""What the turn costs between the end of his sentence and the model call (V2-903): admission, recall, prompt, cover.

    ./.venv/bin/python -m tests.voice.bench.pre_model_latency_bench [--brief-ms 250] [--recall-ms 400] [--lead-ms 300]

The stages are the turn's own code (`pipeline_admit.admit_the_turn`, the provider's `compose_the_prompt`, the cover's
arm), in the order `nucleo/turn/pipeline.run` calls them. The two remote dependencies are doubles with a fixed delay, so
the numbers are the turn's ordering, not a provider's: the brief (Jev) lands `--brief-ms` after it is fired and answers
the memory question by the sentence's label; the full recall answers after `--recall-ms`, the local lexical half after
10 ms. Two ears: `eager` fires the brief (and whatever else the end-of-turn announcement starts) `--lead-ms` before the
turn is confirmed, as Deepgram Flux does; `confirmed` has no announcement (a typed line, another ear). The clock starts
when the turn is confirmed and stops when the model call would be opened; `recall` counts the turns whose prompt
carried the durable recall (on a memory turn it should be all of them, on a plain one it is tokens nobody needed). Sentences ES / EN / JA, everyday orders and
questions plus real memory questions.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import statistics
import threading
import time
from types import SimpleNamespace

#: (lang, sentence, needs durable memory)
TURNS = [
    ("es", "pon música de Queen", False), ("es", "abre la agenda", False),
    ("es", "¿qué tiempo hace en Madrid?", False), ("es", "cierra el vídeo", False),
    ("es", "busca vuelos a Lisboa para el viernes", False), ("es", "sube el volumen", False),
    ("es", "¿cuánto es diecisiete por tres?", False), ("es", "manda un mensaje a Raquel diciendo que llego tarde", False),
    ("es", "apúntame dentistas mañana a las cinco", False), ("es", "vale, gracias", False),
    ("es", "¿qué noticias hay hoy?", False), ("es", "para la música", False),
    ("es", "¿cómo se llama mi sobrina?", True), ("es", "¿qué te dije de mi viaje a Japón?", True),
    ("es", "¿a qué soy alérgico?", True), ("es", "pídeme la pizza de siempre", True),
    ("en", "play some jazz", False), ("en", "open my calendar", False), ("en", "what's the weather in Boston?", False),
    ("en", "turn it down a bit", False), ("en", "find me a cheap hotel in Rome", False), ("en", "thanks, that's all", False),
    ("en", "what's my sister's name?", True), ("en", "where did I park the car last week?", True),
    ("en", "what did I tell you about the meeting with Ana?", True),
    ("ja", "音楽をかけて", False), ("ja", "東京の天気は？", False), ("ja", "カレンダーを開いて", False),
    ("ja", "先週話した旅行の件、覚えてる？", True), ("ja", "私の犬の名前は何だっけ？", True),
]

MEMORY_KEYS = ("durable_memory",)


def _doubles(brief_s: float, recall_s: float, labels: dict) -> None:
    """Jev and the retriever, replaced by fixed delays."""
    from nucleo import jev
    from nucleo.turn import brief_screen
    from nucleo.turn.prompt import recall as recall_mod

    jev.enabled = lambda: True

    def _many(state, questions, *, timeout_s=None, question_id="brief"):
        time.sleep(brief_s)
        out = {"_latency_ms": int(brief_s * 1000), "_call_id": "bench", "_ready_at": time.time(), "_usage": {}}
        for key, q in questions.items():
            opts = list((q or {}).get("criteria") or {})
            choice = opts[0] if opts else ""
            if key in MEMORY_KEYS:
                choice = "remember" if labels.get(state.strip(), False) else "none"
            out[key] = {"choice": choice, "confidence": 0.95, "probs": {choice: 0.95}}
        return out

    jev.choose_many_sync = _many
    brief_screen.ride_the_brief = lambda *a, **k: None

    def _compose_recall(q="", timings=None, lexical_only=False, skip_newest=None, his_words=""):
        time.sleep(0.01 if lexical_only else recall_s)
        return ("── RECUERDOS ──\n· a fact he told us", [1])

    recall_mod.compose_recall = _compose_recall

    from nucleo import memory_agent

    async def _ingest(*a, **k):
        return None

    memory_agent.ingest_utterance = _ingest
    from voice.engine.speech import filler_audio as fa
    fa.enabled = lambda: True
    fa.answering_fast = lambda: False
    fa.stranded = lambda: False


def _brain():
    return SimpleNamespace(_window=[{"role": "user", "content": "hola"}, {"role": "assistant", "content": "¡Hola!"}],
                           _directive="", _last_reply="¡Hola!", _seeded=True, _acc_gen=0, _last_filler="")


async def _one(text: str, *, eager: bool, lead_s: float) -> tuple[float, bool]:
    from nucleo.turn import pipeline_admit, brief_turn
    from nucleo.flash import show_target
    from voice.engine.llm.providers import turn_prompt
    from voice.engine.speech import filler_audio as fa
    import inspect

    brain = _brain()
    attention = SimpleNamespace(typed_line=lambda t: False, clamp_input=lambda t, n: (t, False))
    motor = SimpleNamespace(_show_target=show_target, asyncio=asyncio, os=os)
    emit = lambda *a, **k: None  # noqa: E731
    if eager:
        fire = brief_turn.fire_early
        (fire(text, brain=brain) if "brain" in inspect.signature(fire).parameters else fire(text))
        await asyncio.sleep(lead_s)
    t0 = time.perf_counter()
    blk = await pipeline_admit.admit_the_turn(motor=motor, attention=attention, brain=brain, emit=emit,
                                              first_turn=False, text=text)
    kw = dict(brain=brain, emit=emit, operator_text=blk["operator_text"], self=SimpleNamespace(_phase=""),
              text=blk.get("text", text))
    if "brief" in inspect.signature(turn_prompt.compose_the_prompt).parameters:
        kw["brief"] = blk.get("_brief")
    p = await turn_prompt.compose_the_prompt(**kw)
    if hasattr(fa, "decide_and_arm"):
        await fa.decide_and_arm(brain, text, messages=p["messages"], brief=blk.get("_brief"))
    else:
        fa.cover_the_turn(brain, text, messages=p["messages"], brief=blk.get("_brief"))
    ms = (time.perf_counter() - t0) * 1000
    return ms, any("a fact he told us" in str(m.get("content") or "") for m in p["messages"])


async def _run(args) -> None:
    labels = {t: m for _l, t, m in TURNS}
    _doubles(args.brief_ms / 1000, args.recall_ms / 1000, labels)
    rows: dict = {}
    carried: dict = {}
    await _one("warm up", eager=False, lead_s=0)
    for eager in (True, False):
        for lang, text, mem in TURNS:
            for _ in range(args.runs):
                from nucleo.turn import brief_turn
                brief_turn._PREFIRED.clear()
                ms, got = await _one(text, eager=eager, lead_s=args.lead_ms / 1000)
                key = ("eager" if eager else "confirmed", lang, "memory" if mem else "plain")
                rows.setdefault(key, []).append(ms)
                carried[key] = carried.get(key, 0) + int(got)
                await asyncio.sleep(max(args.brief_ms, args.recall_ms) / 1000 + 0.05)   # let stray threads land
    print(f"brief {args.brief_ms} ms · recall {args.recall_ms} ms · eager lead {args.lead_ms} ms · runs {args.runs}")
    print(f"{'ear':10} {'lang':4} {'turn':7} {'n':>3} {'p50 ms':>8} {'p90 ms':>8} {'max ms':>8} {'recall':>7}")
    for key in sorted(rows):
        v = sorted(rows[key])
        p90 = v[min(len(v) - 1, int(len(v) * 0.9))]
        print(f"{key[0]:10} {key[1]:4} {key[2]:7} {len(v):>3} {statistics.median(v):>8.0f} {p90:>8.0f} {max(v):>8.0f} {carried[key]:>3}/{len(v):<3}")
    allv = [x for k, v in rows.items() for x in v]
    print(f"all p50 {statistics.median(allv):.0f} ms · mean {statistics.mean(allv):.0f} ms")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brief-ms", type=float, default=250.0)
    ap.add_argument("--recall-ms", type=float, default=400.0)
    ap.add_argument("--lead-ms", type=float, default=300.0)
    ap.add_argument("--runs", type=int, default=1)
    args = ap.parse_args()
    os.environ.setdefault("ZAELAR_JEV", "1")
    threading.excepthook = lambda a: None
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
