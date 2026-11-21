"""A remark about the assistant is not a fact about him (node 13.149, C7).

His complaint about how the agent speaks («you are repeating yourself like a parrot») was filed in his memory as a fact.
The distiller decides what a turn leaves in memory; its own instructions now name a complaint or a comment about the
assistant — how it speaks, that it repeats itself, how it behaves — as something to discard, and what he asks it to
change for good as a rule of his, never a pill. Pinned on the distiller's system text, the one place that decides it.
"""
from __future__ import annotations

from nucleo.memory_agent.processor import distill_prompt


def test_the_distiller_discards_what_he_says_about_the_assistant():
    system = distill_prompt.messages("hola", {})[0]["content"]
    assert "LO QUE DICE DEL ASISTENTE NO es un hecho de él" in system
    assert "→ discard" in system.split("LO QUE DICE DEL ASISTENTE", 1)[1].split("★", 1)[0]
