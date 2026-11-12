"""LLM family — vendor-agnostic providers behind one registry.

The pipeline depends only on ``build_llm``; each vendor is a builder function in
``providers/`` returning a LiveKit ``llm.LLM``. Adding a vendor = one file there.

zaelar note: the hermes/duo/direct providers are added later by another
change; ``providers/__init__`` only imports the vendor providers ported here.
"""
from __future__ import annotations

from livekit.agents.llm import LLM

from ..core.registry import Registry

registry = Registry("LLM")


def build_llm(provider: str, model: str = "") -> LLM:
    from . import providers  # noqa: F401 — registers the builders (V2-891: on first use, never on import)
    return registry.create(provider, model=model)  # type: ignore[return-value]


def available() -> list[str]:
    from . import providers  # noqa: F401
    return registry.names()

# V2-891 — the providers are imported on FIRST USE, not with this package: the `nucleo` provider pulls the whole
# brain (memory, widgets, the turn), and the voice's own process imports this package without ever building it.

__all__ = ["build_llm", "available", "registry"]
