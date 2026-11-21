"""The three brain decisions that wrecked the 2026-08-02 session (search + on-screen report).

Each block captures a regression observed in the real trace (`.meshkore/logs/timeline-latest.jsonl`, 12:51→13:08):

  · `_classify_kind`   — «reflejando el cambio en el widget de informes» was dispatched to the CODE GENERATOR, which
                         spent 3.5 min rewriting `widget.js` for something that was a data op. Filling ≠ programming.
  · `danger`           — «(proyecto compra y venta de motos)» triggered the irreversible-action confirmation gate on
                         a RESEARCH task, which stalled asking for a pointless OK.
  · `dialog.push_user` — STT split the request into 6 chunks; each turn overwrote the previous one and the `raise` of
                         CancelledError carried off the operator's sentence → the brain never saw the word "piscina".
"""

from nucleo import danger


# ── filling a widget with data is NOT rewriting its code ─────────────────────────────────────────────────

# ── the confirmation gate is for irreversible ORDERS, not topics mentioned in passing ────────────────────
def test_research_task_is_not_gated_as_irreversible():
    assert not danger.is_dangerous(
        "Termina la búsqueda ampliada del operador (proyecto compra y venta de motos): completa el informe con "
        "los resultados y puebla el widget results con lo encontrado")
    assert not danger.is_dangerous("busca opciones de compra y venta de motos y ponme un informe")
    assert not danger.is_dangerous("prepara una lista de sitios de compraventa de coches")


def test_a_real_irreversible_order_still_asks_for_ok():
    assert danger.is_dangerous("compra la moto que te he dicho")
    assert danger.is_dangerous("paga la factura de la luz")
    assert danger.is_dangerous("publica el anuncio en Wallapop")
    assert danger.is_dangerous("borra la cuenta")
    # context in parentheses cannot HIDE a real order that is present in the main text
    assert danger.is_dangerous("compra el billete (viaje de trabajo, proyecto compra y venta)")


# ── RECURRING commitments and cancellations (V2-133, use-case batch from 2026-08-18) ───────────────────────
def test_a_recurring_charge_asks_for_ok_even_without_the_word_pay():
    """`renew-gym-membership__es`: «renuévame la cuota del gimnasio» moves real money and did NOT contain the verb
    pagar, so it passed without a gate. The TESTER had to stop it live — «no me has dicho cuánto vas
    a pagar ni me has pedido confirmación»."""
    assert danger.is_dangerous("renuévame la cuota del gimnasio")          # REAL imperative: renuev-, not renov-
    assert danger.is_dangerous("renueva mi membresía del gimnasio de este mes")
    assert danger.is_dangerous("contrata la tarifa nueva de la luz")
    assert danger.is_dangerous("renew my gym membership")


def test_unsubscribing_asks_for_ok_because_it_is_irreversible():
    """`cancel-subscription-before-charge__es` states explicitly that asking for confirmation here is the
    CORRECT behavior, not a defect."""
    assert danger.is_dangerous("cancela mi suscripción de Netflix antes de que me cobren")
    assert danger.is_dangerous("dame de baja de Netflix")
    assert danger.is_dangerous("anula el pedido de Amazon")
    assert danger.is_dangerous("cancel my Netflix subscription")


def test_the_commitment_gate_does_not_fire_on_things_that_cost_nothing():
    """A gate that fires where it should not leaves the task stalled waiting for an OK the operator does not understand — the
    2026-08-02 incident that already motivated the two precision fixes to `_order_text`."""
    for req in ("resérvame mesa para 2 esta noche en Casa Lucio",   # reserving a table does not move money
                "cancela la búsqueda que estabas haciendo",         # cancelling ≠ cancelling a commitment
                "renueva el gráfico del widget",
                "búscame un monitor barato de segunda mano"):
        assert not danger.is_dangerous(req), req


def test_a_reminder_about_a_charge_is_a_note_not_an_order():
    """«Apúntame que el jueves tengo que renovar el seguro» (the `remember-and-remind-deadline` case) asks for a
    NOTE. The order is «apúntame», and it does not move money: gating it would leave the reminder waiting for an OK for
    something no one was going to execute."""
    assert not danger.is_dangerous("apúntame que el jueves tengo que renovar el seguro del coche")
    assert not danger.is_dangerous("recuérdame que tengo que renovar la cuota del gimnasio")


# ── researching ≠ driving a browser ────────────────────────────────────────────────────────────────────

# ── the imperative with a CLITIC, and the reminder that is not an order (V2-128, 2026-08-18) ──────────────────────────
def test_an_imperative_with_a_clitic_still_asks_for_ok():
    """In Spanish, the form that REALLY gives an order has the pronoun attached. `_DANGER_RE` compared
    bare forms with `\\b`, so they all escaped the gate. This is the third place where the same oversight bites
    (it already happened with «resérvame» and «renuévame»): the pattern is written with the infinitive, while the
    operator speaks in the imperative."""
    for req in ("págala tú antes del día 5", "cómpralo ya", "bórralo de mi cuenta",
                "cancélala antes del día 15", "publícalo en Wallapop", "págamelo con la tarjeta"):
        assert danger.is_dangerous(req), req


def test_a_clitic_is_REQUIRED_so_ordinary_conjugations_do_not_gate():
    """Without requiring a clitic, «compras»/«publicas»/«cancelan» —which are not orders— would enter through the same door."""
    for req in ("¿cuánto compras al mes?", "normalmente publicas los lunes", "cancelan el vuelo mañana"):
        assert not danger.is_dangerous(req), req


def test_asking_to_be_REMINDED_of_a_payment_is_not_an_order_to_pay():
    """The reminder trimming was only handled by `_COMMITMENT_RE`: «recuérdame PAGAR la factura» triggered the gate through
    `_DANGER_RE` and left a confirmation waiting for an OK for a payment no one was going to execute."""
    assert not danger.is_dangerous("recuérdame pagar la factura de la luz antes del día 5")
    assert not danger.is_dangerous("apúntame que tengo que pagar el IBI")


def test_a_real_order_AFTER_a_reminder_clause_is_not_swallowed():
    """The trimming extends to the end of the SENTENCE, not the end of the text: with `.*`, the real order
    that followed was lost."""
    assert danger.is_dangerous("recuérdame pagar la factura. Y de paso págala tú")
