"""nucleo/llm/prewarm.py — warms the HOT PATH at startup (V2-024).

The operator saw 6–8s on the FIRST turn and about 1s thereafter. The cause: the first FlashBrain call
(a cloud provider) establishes TLS, performs the handshake, and starts the model cold. We absorb
that HERE, during server startup—while the frontend renders the brain-mesh loader—with a MINIMAL fire-and-forget
query, so the model is warm (~1s) when the user can interact. It also warms search Chromium
(`search/browser`) — unless the resources policy says not to (`prewarm_browser`, V2-872: a host that stops when
idle pays that warm-up on every boot; see `browser_prewarm_wanted`). It never blocks startup or raises.
"""
from __future__ import annotations

import asyncio
import time

from loguru import logger


async def run() -> None:
    """Fire-and-forget from the lifespan: warm FlashBrain, the search browser, reranker, and embeddings in parallel."""
    await asyncio.gather(_warm_flash(), _warm_browser(), _warm_rerank(), _warm_embed())


async def _warm_flash() -> None:
    try:
        from nucleo.llm.fast_client import FastClient, available, spec_from_config
        spec = spec_from_config()
        # Local (Ollama) ya se mantiene caliente con keep_alive en la 1ª invocación; sin key no hay conexión que montar.
        if spec.is_local() or not available(spec):
            _emit_prewarm("flash", 0, spec.model, note="local/sin-key: nada que calentar")
            return
        # FASE 1: calentar con la FORMA REAL del turno (system prompt COMPLETO + router.TOOLS), no un "ping" pelado.
        # Así el 1er turno real no paga el frío del prompt grande + esquemas de tools + el establecimiento TLS (que
        # con el keepalive largo del cliente sobrevive hasta que el operador habla). Mide TTFT y total.
        from nucleo.turn.prompt.builder import build_flash_system
        from nucleo.flash.router import TOOLS
        try:
            system, _ = build_flash_system()
        except Exception:
            system = "warmup"
        messages = [{"role": "system", "content": system}, {"role": "user", "content": "hola"}]
        metrics: dict = {}
        t0 = time.time()
        ttft = None
        async for _chunk in FastClient().stream(messages, spec=spec, tools=TOOLS, max_tokens=1, metrics=metrics):
            if ttft is None:
                ttft = round((time.time() - t0) * 1000)
        total = int((time.time() - t0) * 1000)
        logger.info(f"prewarm FlashBrain OK ({spec.model}, ttft={ttft}ms total={total}ms, "
                    f"prompt≈{metrics.get('prompt_tokens_est')}tok/{metrics.get('prompt_chars')}ch) — 1er turno caliente")
        _emit_prewarm("flash", total, spec.model, ttft=ttft, metrics=metrics)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"prewarm FlashBrain saltado (sin efecto en la voz): {e}")
        _emit_prewarm("flash", 0, "?", note=f"saltado: {e}")


def _emit_prewarm(what: str, ms: int, model: str, *, ttft: int | None = None,
                  metrics: dict | None = None, note: str = "") -> None:
    """Evento OBSERVABLE del prewarm en /debug (FASE 1): así se VE si el calentamiento disparó tras cada restart, su
    latencia, y el tamaño del prompt de calentamiento — para diagnosticar el cold-start del 1er turno. Best-effort."""
    try:
        from voice.observer import emit
        extra = {"warm": what, "ttft_ms": ttft, "prewarm_ms": ms, "model": model,
                 "module": "prewarm", "func": f"prewarm._warm_{what}"}
        if metrics:
            extra.update({"prompt_chars": metrics.get("prompt_chars"),
                          "prompt_tokens": metrics.get("prompt_tokens", metrics.get("prompt_tokens_est")),
                          "n_tools": metrics.get("n_tools"), "cold_estimate": metrics.get("cold_estimate")})
        emit("perf", f"🔥 prewarm {what} {ms}ms" + (f" (ttft {ttft}ms)" if ttft else "") + (f" — {note}" if note else ""),
             role="system", extra=extra)
    except Exception:
        pass


def browser_prewarm_wanted(declared, idle_stop_min: int) -> bool:
    """Is the search Chromium warmed at boot? (V2-872 W3.) `declared` is the deployment's own
    `prewarm_browser` (from its `config/resources.json`), or None when that file does not set it.

    A declared value always wins. Undeclared, the answer depends on whether the host STOPS WHEN IDLE
    (`ZAELAR_IDLE_STOP_MIN` > 0): such a host boots many times a day — often for a request that brings no real
    activity — and each boot would pay the Chromium start in full (measured 53-96 s of CPU on a small shared-CPU
    host, with the quota spent and the voice throttled behind it), so the default there is NOT to warm it. A
    host that stays up (a self-hosted laptop) warms it once and keeps it: the repo default (`true`) holds.
    Not warming loses nothing but the first search's start: every door of `search/browser.py` calls
    `ensure_started()` before it uses the context, so the first search starts the browser itself."""
    if declared is not None:
        return bool(declared)
    return idle_stop_min <= 0


def _browser_prewarm_from_config() -> bool:
    """The live inputs: the DEPLOYMENT file's own key (the repo default is `true` and would hide the idle-stop flip),
    then the repo default where the host stays up."""
    import json
    import os
    from nucleo import idle_stop
    from nucleo.workers import envelope
    path, declared = os.path.join(envelope._HERE, "resources.json"), None
    try:
        with open(path, encoding="utf-8") as fh:              # the deployment's own file is optional
            declared = json.load(fh).get("prewarm_browser")
    except Exception as e:  # noqa: BLE001 — absent or unreadable (the envelope warns): the default holds
        logger.debug(f"prewarm: no deployment prewarm_browser ({e!r})")
    if declared is None and not idle_stop.window_min():
        declared = envelope.policy().get("prewarm_browser", True)
    return browser_prewarm_wanted(declared, idle_stop.window_min())


async def _warm_browser() -> None:
    try:
        if not _browser_prewarm_from_config():
            _emit_prewarm("browser", 0, "chromium", note="skipped by policy: starts at first use")
            return
        from search import browser as browser_search
        t0 = time.time()
        ok = await browser_search.ensure_started()
        ms = int((time.time() - t0) * 1000)
        if ok:
            logger.info(f"prewarm browser_search OK ({ms}ms) — búsqueda Google lista")
            _emit_prewarm("browser", ms, "chromium")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"prewarm browser_search saltado (búsqueda caerá a DDG): {e}")
        _emit_prewarm("browser", 0, "chromium", note=f"saltado: {e}")


async def _warm_rerank() -> None:
    """Carga el modelo del reranker del recall largo (V2-030) en un thread idle, para que la 1ª consulta que
    dispare recall no pague la carga del cross-encoder (~1-2s en frío). Solo si el proveedor local está activo;
    off-hot-path y fail-open (si el modelo no está, el recall degrada al orden del retriever, sin romper)."""
    try:
        from memory import rerank
        if rerank.provider() != "local":
            return  # 'off' → nada; 'openai'/cloud → la key ya está caliente, no hay modelo que cargar
        t0 = time.time()
        # una llamada mínima FUERZA la descarga/carga del cross-encoder ONNX en el executor idle.
        ok = await asyncio.to_thread(rerank.rerank, "ping", [{"text": "a", "score": 0.0}, {"text": "b", "score": 0.0}])
        ms = int((time.time() - t0) * 1000)
        if ok is not None:
            logger.info(f"prewarm reranker OK ({rerank._model()}, {ms}ms) — recall listo")
            _emit_prewarm("rerank", ms, rerank._model())
        else:
            # No es un error: desde 2026-08-23 la PRIMERA carga tiene presupuesto de reloj, así que en una máquina
            # que nunca ha bajado el modelo (~1.1 GB) esto vuelve sin él y la descarga sigue por detrás. Se DICE:
            # el silencio se leería como que el reranker está caliente mientras cada recall sale sin reordenar.
            # Se pregunta por `status()` y NO por `memory.rerank_local`: el estado ya viaja ahí y meter la mano en
            # un interno de memoria desde el motor es justo lo que el trinquete de frontera existe para impedir.
            st = rerank.status()
            nota = st.get("gave_up") or ("descargando en segundo plano" if st.get("loading") else "no listo")
            logger.info(f"prewarm reranker aún no disponible ({rerank._model()}, {ms}ms): {nota}")
            _emit_prewarm("rerank", ms, rerank._model(), note=nota)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"prewarm reranker saltado (recall caerá al orden del retriever): {e}")
        _emit_prewarm("rerank", 0, "?", note=f"saltado: {e}")


async def _warm_embed() -> None:
    """Carga el modelo de EMBEDDINGS (fastembed ONNX u Ollama) en un thread idle, para que la 1ª query de recall del
    turno no pague la carga en frío (~2s medido con fastembed) — que por sí sola ya se come el presupuesto del
    recall (`ZAELAR_RECALL_BUDGET_MS`, def 800ms) y causa `recall_timeout` en el primer intento de cada arranque
    (hallazgo de la auditoría 2026-07-26: 14/14 recalls logueados en un día venían con `recall_timeout=true`).
    Ollama con keep_alive ya se mantiene caliente solo; esta llamada solo tiene coste real la 1ª vez con fastembed."""
    try:
        from memory import embeddings
        t0 = time.time()
        await asyncio.to_thread(embeddings.embed, "ping")
        ms = int((time.time() - t0) * 1000)
        logger.info(f"prewarm embeddings OK ({embeddings.active_backend()}, {ms}ms) — recall listo en frío")
        _emit_prewarm("embed", ms, embeddings.active_backend())
    except Exception as e:  # noqa: BLE001
        logger.warning(f"prewarm embeddings saltado (1er recall pagará la carga en frío): {e}")
        _emit_prewarm("embed", 0, "?", note=f"saltado: {e}")
