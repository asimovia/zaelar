"""A clear order is acknowledged plainly, never restated (INI-042 #40).

Measured: «Entendido: lo pongo tal cual en la nota, apuntando que corre en la nube…» — after a clear order the reply
paraphrased it before confirming. The operator asks for «Entendido» and nothing more. The turn's operating prose
forbade exactly that word and asked to «say it in ONE sentence», which the model filled with his own order.
"""
from __future__ import annotations

import ast
import inspect

from nucleo.turn.prompt import operating


def _prose() -> str:
    """Every string the module hands the model, joined: the rule is read as the model reads it."""
    return "".join(n.value for n in ast.walk(ast.parse(inspect.getsource(operating)))
                   if isinstance(n, ast.Constant) and isinstance(n.value, str))


def test_a_clear_order_is_acknowledged_with_entendido_and_nothing_else():
    prose = _prose()
    assert "No le devuelves sus palabras (a una orden, «Entendido» y ya)" in prose
    assert "«es cierto», «entendido»" not in prose, "the plain ack he wants is not on the forbidden list"
    assert "dilo en UNA frase" not in prose, "nothing asks the confirmation to carry a sentence of its own"
