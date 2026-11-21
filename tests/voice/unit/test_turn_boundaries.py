#
# test_turn_boundaries.py — ONE SENTENCE = ONE TURN, and a turn that dies leaves a trace.
#
# Anchored to a REAL session: `.meshkore/logs/sessions/9748acc2-….jsonl` (2026-08-10, 13:20:50). The operator dictated
# «Fenomenal. ¿Me vas a buscar un ferry para ir de Denia a Ibiza el día diecisiete de agosto… para un coche de cinco
# metros… y cuatro personas, entre ellas dos niños de nueve y once años.» and STT delivered it in EIGHT FINAL
# transcriptions. Consequences, all visible in that log:
#   · T3/T4/T5 opened a turn with HALF a sentence; T5 even spoke («¿De Denia a dónde, Ricart?»), asking about the
#     destination the operator was saying at that moment.
#   · T6 carried the COMPLETE request and received no response: 13 ms later «Muéstrame los resultados» arrived and
#     LiveKit cancelled it while building the prompt. Not a single line in the log explained it, and the criteria were
#     lost → the next turn talked about «los resultados» without knowing what they were and opened a blank surface,
#     saying «Aquí lo tienes».
# The three mechanisms that close it are fixed here so they cannot come loose again.
#

import pytest

# VERBATIM fragments from the session (events i=59/62/69/83…104), in the order they arrived.
FRAGMENTS = [
    "Fenomenal. ¿Me vas a buscar un ferry para ir",
    "Fenomenal. ¿Me vas a buscar un ferry para ir de Denia",
    "Fenomenal. ¿Me vas a buscar un ferry para ir de Denia a",
    "Fenomenal. ¿Me vas a buscar un ferry para ir de Denia a Ibiza el día diecisiete de agosto, si es lunes, si no, "
    "pues el día dieciocho de agosto. Quiero que sea el más rápido posible, para un coche de cinco metros, metro "
    "ochenta de alto, y cuatro personas, entre ellas dos niños de nueve y once años.",
]
NEXT_SENTENCE = "Muéstrame los resultados."


# ── 1. The fragment signal is STRUCTURAL (no verb tables or language-specific logic) ─────────────────────────────

# ── 2. A superseded turn neither speaks nor acts ─────────────────────────────────────────────────────────────────

class _FakeBrain:
    def __init__(self, utterance_text):
        self._utterance = {"text": utterance_text, "at": 0.0}
        self._window = []


# ── 3. Turn boundaries: the values come from the module written for this purpose ─────────────────────────────────

def test_endpointing_uses_the_measured_values_not_livekit_defaults():
    """`voice/endpointing.py` was born from real sessions and remained ORPHANED: the engine moved to LiveKit
    and nobody wired it in, so the turn closed with the 0.5 s default. It is now the source of truth."""
    from voice import endpointing as ep
    from voice.engine.pipeline.agent import _endpointing_opts
    opts = _endpointing_opts(flux=False)          # the VAD ear (nova-3): the dynamic hold
    assert opts["min_delay"] == ep.HOLD_BASE
    assert opts["max_delay"] == ep.HOLD_MAX
    assert opts["min_delay"] > 0.5, "0,5 s es el default de LiveKit: es lo que partía la frase del operador"
    assert opts["mode"] == "dynamic", "hold creciente = lo que hold_secs() calculaba a mano"


def test_with_flux_the_endpointing_is_fixed_and_a_long_pause_cannot_poison_it(monkeypatch):
    """Flux decides the end of turn; the only silence added after it is `stt_flux_min_delay`, FIXED. Measured on a cloud
    Machine 2026-11-19: with LiveKit's dynamic average, one sentence the STT did not transcribe followed by a pause put
    every later turn at the 3 s ceiling (`eou=3.00s`) for the rest of the session; fixed, it stays at 0.25 s."""
    from voice.engine.core.config import SETTINGS
    from voice.engine.pipeline.agent import _endpointing_opts
    for k in ("ZAELAR_ENDPOINT_MIN_S", "ZAELAR_ENDPOINT_MAX_S"):
        monkeypatch.delenv(k, raising=False)
    d = SETTINGS.stt_flux_min_delay
    assert _endpointing_opts(flux=True) == {"mode": "fixed", "min_delay": d, "max_delay": d}


def test_the_env_override_wins_over_the_flux_default(monkeypatch):
    """The stopgap on the Machines (`ZAELAR_ENDPOINT_MIN_S=0.25`, `ZAELAR_ENDPOINT_MAX_S=0.6`) keeps working until it is
    removed: an override, either one, is the dynamic mode with its bounds."""
    from voice.engine.pipeline.agent import _endpointing_opts
    monkeypatch.setenv("ZAELAR_ENDPOINT_MIN_S", "0.25")
    monkeypatch.setenv("ZAELAR_ENDPOINT_MAX_S", "0.6")
    assert _endpointing_opts(flux=True) == {"mode": "dynamic", "min_delay": 0.25, "max_delay": 0.6}


def test_endpointing_is_tunable_without_touching_code(monkeypatch):
    from voice.engine.pipeline.agent import _endpointing_opts
    monkeypatch.setenv("ZAELAR_ENDPOINT_MIN_S", "0.9")
    monkeypatch.setenv("ZAELAR_ENDPOINT_MAX_S", "3.5")
    assert _endpointing_opts() == {"mode": "dynamic", "min_delay": 0.9, "max_delay": 3.5}


def test_endpointing_never_lets_max_fall_below_min(monkeypatch):
    from voice.engine.pipeline.agent import _endpointing_opts
    monkeypatch.setenv("ZAELAR_ENDPOINT_MIN_S", "2.0")
    monkeypatch.setenv("ZAELAR_ENDPOINT_MAX_S", "0.5")
    opts = _endpointing_opts()
    assert opts["max_delay"] >= opts["min_delay"]


def test_endpointing_survives_a_garbage_env(monkeypatch):
    from voice import endpointing as ep
    from voice.engine.pipeline.agent import _endpointing_opts
    monkeypatch.setenv("ZAELAR_ENDPOINT_MIN_S", "no-es-un-numero")
    assert _endpointing_opts(flux=False)["min_delay"] == ep.HOLD_BASE


# ── 4. A turn that dies leaves a trace AND preserves the sentence ─────────────────────────────────────────────────

# ── 5. Opening a BLANK surface is not «here you go» ───────────────────────────────────────────────────────────────

# ── 6. The results ↔ search boundary is written where the model reads it ──────────────────────────────────────────

@pytest.mark.parametrize("query", ["muéstrame los resultados", "los resultados", "muéstrame las propuestas"])
def test_the_name_resolver_already_points_at_results(query):
    """Name/alias resolution (V2-082) DID work: it was the model, reading the catalog, that chose `search`.
    This test records that the resolver is not at fault—if it ever fails, that is another bug."""
    from widgets import runtime
    # The catalog is CACHED and other suites replace it with a synthetic one (test_selection_scale mounts 10,000
    # fake widgets). Without invalidation, this test measures another test's catalog, not the real one.
    runtime.invalidate()
    assert (runtime.identify(query) or {}).get("match") == "results"


def test_the_two_surfaces_declare_their_frontier():
    """`search` is the progress SIGNPOST; `results` is where findings land. Without saying so in the manifest—the
    only thing the model reads—«muéstrame los resultados» would open the empty spinner again."""
    import json
    import pathlib

    search = json.loads(pathlib.Path("widgets/search/manifest.json").read_text())
    results = json.loads(pathlib.Path("widgets/results/manifest.json").read_text())

    assert "results" in search["whenToUse"], "search debe remitir a results para los hallazgos"
    assert "search" in results["whenToUse"], "results debe decir que search es solo el progreso"
    # and results must warn that opening it produces nothing
    low = results["whenToUse"].lower()
    assert "no produce" in low or "en blanco" in low


# ── 7. FlashBrain NEVER gets stuck ────────────────────────────────────────────────────────────────────────────────
# Session 14:08:26: 23 consecutive turns without a response over 5 minutes. The operator asked «¿me estás escuchando?»
# and «¿estás operativo, sí o no?» and still got nothing. Measured in the log: turns of 35.7 s · 31.8 s · 32.2 s and one
# of 60.5 s, all with `partial_chars=0` and `ttft=None`—the model emitted not a single speakable token. The only
# deadline that existed was httpx's network timeout: 60 s. The operator's hard rule: FlashBrain always operational,
# even when the Brain Workers are slow.

def test_a_stalled_turn_is_a_warning_not_a_dead_provider():
    """FIXED 2026-08-12 with a live case: the deadline reused the entire error branch, so ONE turn
    cortado —del que la sesión se recupera al turno siguiente— dejaba el ◉ en ROJO con «no responde» y gritaba
    «Cerebro rápido caído». El modelo contestaba bien antes y después: el operador se queda mirando un LLM en rojo
    que funciona, y buscando una avería que no existe. Se separa el HECHO (este turno no salió) del DIAGNÓSTICO
    (el proveedor está caído). Sigue habiendo aviso — lo que no hay es un diagnóstico inventado."""
    import asyncio
    import json

    from voice import health_state
    from server.voice_api import status

    health_state.record("llm", "slow", "un turno se atascó (9000 ms sin respuesta) y lo corté")
    try:
        items = json.loads(bytes(asyncio.run(status()).body).decode("utf-8"))["items"]
        llm = next(i for i in items if i["key"] == "llm")
        assert llm["state"] == "warn", "un turno atascado avisa; no declara el proveedor caído"
        assert "atasc" in llm["detail"] and "no responde" not in llm["detail"]
    finally:
        health_state.clear("llm")


def test_a_real_provider_failure_still_goes_red(monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "es")          # the status row speaks the instance language
    """The counterweight to the previous test: downgrading a stall must not downgrade a real outage."""
    import asyncio
    import json

    from voice import health_state, llm_health
    from server.voice_api import status

    assert llm_health.classify("connection refused") == "outage"
    health_state.record("llm", "outage", "connection refused")
    try:
        items = json.loads(bytes(asyncio.run(status()).body).decode("utf-8"))["items"]
        llm = next(i for i in items if i["key"] == "llm")
        assert llm["state"] == "error" and "no responde" in llm["detail"]
    finally:
        health_state.clear("llm")
