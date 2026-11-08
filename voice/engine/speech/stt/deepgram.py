"""Deepgram STT — remote streaming. Two ears behind one provider name (V2-863):

  · **Flux** (`flux-*`, default `flux-general-multi`) — Deepgram's conversational model. It does not only transcribe:
    it says when the turn ENDED (its own end-of-turn model, ~260 ms after the last word) and, before confirming it,
    announces an EAGER end of turn that the pipeline reads as a preflight transcript — the turn brief fires on it and
    LiveKit's preemptive generation starts the model on it (`voice/engine/pipeline/eager_brief.py`). A turn that
    resumes cancels the eager one. With Flux the session's turn detection is `"stt"` (`agent.py`): the end of turn is
    the model's, not a silence we count.
  · **nova-3** (`ZAELAR_STT_MODEL_DG=nova-3`) — the previous ear: words only, the end of turn by silence
    (`voice/endpointing.py` + the lexical veto in `speech/turn/semantic.py`).

Measured before the change (12 real sessions, 2026-11-08): the silence hold alone was 1.9 s p50 / 2.6 s p90 of
every turn — the largest single piece of the gap between the operator's last word and the first sound he heard.
"""
from __future__ import annotations

from livekit.plugins import deepgram as _deepgram

from ...core import langs
from ...core.config import SETTINGS
from . import gazetteer, registry


def is_flux(model: str | None = None) -> bool:
    """`flux-*` → the conversational ear. Pure; reads the configured model when none is given."""
    return str(model if model is not None else SETTINGS.stt_model_deepgram).strip().lower().startswith("flux")


def flux_active() -> bool:
    """Is the session's STT the Flux ear? (`deepgram` provider AND a `flux-*` model.) Read by `agent.py` to pick
    the turn-detection mode and the endpointing that goes with it."""
    return SETTINGS.stt_provider == "deepgram" and is_flux()


def _keyterms(model: str, first_run: bool) -> list[str]:
    # TERM BOOSTING — only the places EXPECTED in his speech (`gazetteer.expected_terms`): a national list sent
    # on every session turned ordinary words into towns (V2-812 T-07, measured there). Empty by default.
    # Three conditions, and each one is a way to go deaf rather than mishear a town:
    #   · nova-3 or Flux only. The v1 plugin RAISES on `keyterm` with any other model, and that exception happens
    #     while the session is being built, so a `ZAELAR_STT_MODEL_DG=nova-2` would take the whole STT down with it.
    #   · not while the language is still auto-detecting. Seeding Spanish toponyms into the first sentence would
    #     bias the very classification that picks the operator's language (`i18n.init.detect`).
    #   · non-empty. An unknown language has no list, and sending an empty one is noise on every request.
    if first_run or not (str(model).startswith("nova-3") or is_flux(model)):
        return []
    return list(gazetteer.boost_terms(langs.current_code()) or [])


@registry.register("deepgram")
def build(vad=None):
    first_run = langs.first_run_auto()
    model = SETTINGS.stt_model_deepgram
    boost = _keyterms(model, first_run)
    from nucleo.energy import egress as llm_egress
    if is_flux(model):
        # EGRESS: a mediated deployment opens the socket through egress with its own credential; Flux lives on /v2,
        # its own family there (`deepgram_flux`), because egress routes by the provider's BASE.
        base_url, api_key = llm_egress.route_url(llm_egress.base_of("deepgram_flux") + "/listen",
                                                 SETTINGS.deepgram_api_key or "")
        opts: dict = {}
        if boost:
            opts["keyterm"] = boost
        if SETTINGS.stt_eager_eot > 0:
            # The eager event is what the brief and the preemptive model start on; Deepgram requires eager ≤ end.
            opts["eager_eot_threshold"] = min(SETTINGS.stt_eager_eot, SETTINGS.stt_eot_threshold)
        # FIRST RUN → no hint (the multilingual model listens to everything, so `i18n.init.detect` can classify the
        # first sentence); once a language is chosen, hint it. `flux-general-multi` is the only model that takes a hint.
        if not first_run and str(model).strip().lower() == "flux-general-multi":
            opts["language_hint"] = [langs.current_code()]
        return _deepgram.STTv2(
            model=model,
            api_key=api_key or None,
            base_url=base_url.replace("https://", "wss://", 1) if base_url.startswith("https://") else base_url,
            eot_threshold=SETTINGS.stt_eot_threshold,
            eot_timeout_ms=SETTINGS.stt_eot_timeout_ms,
            **opts,
        )

    opts = {}
    if boost:
        opts["keyterm"] = boost
    # EGRESS: a mediated deployment opens the socket through egress with its own credential (`nucleo.energy.egress`).
    base_url, api_key = llm_egress.route_url(llm_egress.base_of("deepgram") + "/listen", SETTINGS.deepgram_api_key or "")
    return _deepgram.STT(
        model=model,
        api_key=api_key or None,
        base_url=base_url,
        # FIRST RUN → `"multi"` (multilingual nova-3, with code-switching): with no language chosen yet, we cannot
        # pin one down, or `i18n.init.detect`'s auto-detection would receive the operator's sentence transcribed
        # through the wrong model and there would be nothing left to classify. NOTE: omitting the parameter does not
        # work here —the Deepgram server falls back to en-US, which is not auto—; we must explicitly request "multi".
        # Once a language has been chosen, use the usual one: LIVE, and the change applies on reconnection.
        language="multi" if first_run else langs.current_code(),
        interim_results=True,
        **opts,
    )
