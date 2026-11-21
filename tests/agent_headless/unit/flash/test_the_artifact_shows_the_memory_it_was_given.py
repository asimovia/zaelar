"""The turn artifact must show the MEMORY that was shown to the model (V2-255).

It comes from a harness proposal for the problem V2-254 left open —nothing prevents a FOURTH copy of the
background-pill rule—: **do not watch the WRITERS; watch the ARTIFACT.** A list of surfaces has proved incomplete
three times because someone has to remember to expand it; but all of them, known and as-yet-unknown, end up in the
same place: a prompt sent to a model. And we already record that
(`observer.turn_detail`, which is **the single point closed by BOTH channels**, voice and probe).

The property, stated about the output: *no prompt sent to a model contains the text of a namespaced slot pill unless
the request names it.*

For that property to be verifiable, the artifact has to CONTAIN the part being checked. And it did not. Measured on
2026-08-21 with the empty session: the recall block lands at character **2,896** of a 16,585-character prompt, 104
characters from the 3,000-character head — and in a real turn the cached state and recent conversation come BEFORE
it, so it ALWAYS falls out.

A verifier reading that artifact would say “clean” about a dirty prompt. It is tonight’s rule applied to the record:
**a ceiling is dangerous only if the reader accepts prefixes**.
"""
import pytest

from nucleo.turn.prompt import builder as fp
from voice import observer as ob

MARCA = "PILDORA_DE_FONDO_MARCADOR"
RECALL = f"Puede que venga a cuento (de tu memoria):\n· {MARCA}"


# The shared STATE is read from the DATABASE, so without control the prompt measures something different on each
# machine —and in the full-map run, another suite may leave it pointing at a database with real memory—. This case
# measures the TRUNCATION, not how much memory the runner has: with loose state it passed by itself and failed in the
# full map (2026-08-29), which is exactly what a test that measures its environment looks like.
_ESTADO = ("── QUIÉN ERES ──\nEres zaelar.\n\n── QUIÉN TIENES DELANTE ──\nEl operador se llama Marc.")


def _prompt(recent: str = "", estado: str = _ESTADO) -> str:
    import unittest.mock as _mock
    from memory import state_cache as memory_cache
    with _mock.patch.object(memory_cache, "get", lambda: (estado, "Marc")):
        s, _ = fp.build_flash_system(recall_block=RECALL, recent_block=recent)
    return s


# ── the measured case ───────────────────────────────────────────────────────────────────────────────────────────

# ── the other direction: it is still a TRUNCATION, and says how much was left out ──────────────────────────────

def test_un_prompt_largo_SIGUE_recortandose():
    """Sensitivity: “making room for memory” must not become storing the entire prompt — this record is persisted
    on every turn."""
    enorme = "x" * 40000
    out = ob._prompt_excerpt(enorme)
    assert len(out) < len(enorme)


def test_y_el_hueco_se_NOMBRA_para_que_nadie_lo_lea_como_ausencia():
    """This lets a verifier say “I cannot certify” instead of “clean” — the INFRA/FAIL distinction the harness
    already uses. Without it, the proposal to watch the artifact lies silently."""
    out = ob._prompt_excerpt("x" * 40000)
    assert "OMITIDOS" in out and "caracteres" in out


def test_lo_que_cabe_entero_no_se_toca():
    assert ob._prompt_excerpt("corto") == "corto"


# ── the artifact is where the two channels meet ───────────────────────────────────────────────────────────────


# ── the margin, stated as a NUMBER ────────────────────────────────────────────────────────────────────────────
# The case above passes or fails depending on how much space what comes BEFORE the recall occupies, and that grows
# on its own: each new state block (V2-490 added one) pushes memory toward the truncated center. A boolean does not
# warn that the margin is running out — it warns once it has run out, by which point the artifact has been lying for
# some time.
