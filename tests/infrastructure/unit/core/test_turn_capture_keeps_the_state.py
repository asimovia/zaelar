"""The forensic capture of a turn must preserve the part that CHANGES (V2-195).

`observer.turn_detail` exists to answer “what did the model see?”—its own docstring says: “why did it
re-escalate during an ambient turn? = look at which window/prompt it saw.” And it was saving `system[:8000]`
from a prompt measuring ~19,000 characters.

The static persona comes first and **`prompt.live_state()` is composed at the END**, so what got cut was
exactly the half that changes every turn: the time, background tasks, the browser block, a wall, a pending
confirmation.

On 2026-08-20, that truncation made five turns from a measured run appear never to have the browser block—
while the browser emitted 74 events in that same run. Three steps into concluding that an entire night of
fixes was invisible to the model, when the only thing missing was the artifact. A diagnosis that truncates
the very evidence it is asked for is worse than having none: it looks like an answer.
"""
from __future__ import annotations

from voice import observer


def _prompt(head: str = "PERSONA", tail: str = "ESTADO", filler: int = 30_000) -> str:
    return head + ("x" * filler) + tail


def test_the_TAIL_survives_because_that_is_where_the_live_state_goes():
    ex = observer._prompt_excerpt(_prompt())
    assert ex.endswith("ESTADO")


def test_and_the_head_too_because_the_rules_live_there():
    assert observer._prompt_excerpt(_prompt()).startswith("PERSONA")


def test_and_the_gap_is_NAMED_so_a_hole_is_not_read_as_an_absence():
    """That is the entire lesson of the finding: I read a gap as an absence. If the excerpt says how much is
    missing and where the state is, nobody else will make that mistake."""
    ex = observer._prompt_excerpt(_prompt())
    # V2-756 — the sentence changed with the rule: the excerpt no longer drops the middle whole, it
    # keeps what is ON SCREEN too, so promising only «el estado vivo va al final» had become a lie.
    # Anchored on the claim — the hole is NAMED — instead of on the words that named it.
    assert "OMITIDOS" in ex and "no se omiten" in ex.lower()


def test_the_apps_reported_state_lines_reach_the_record_too():
    """V2-884: the state lines sit just BEFORE the on-screen band, headed by the legend; the excerpt keeps them, so
    «what did the model believe each screen showed?» is read from the record and not reconstructed."""
    from widgets import state_render
    assert state_render.LEGEND.startswith(observer._STATE_MARK)
    middle = "y" * 9000 + "\n" + state_render.LEGEND + "\n- youtube: playing «x»\n\nitems ahora (de lo ABIERTO …)\n- a"
    ex = observer._prompt_excerpt("PERSONA" + "x" * 6000 + middle + "z" * 7000 + "ESTADO")
    assert "- youtube: playing «x»" in ex and "items ahora (de lo ABIERTO" in ex


def test_two_screens_reporting_one_app_are_two_records():
    """V2-884: the flood guard of `widget` events keeps the screen — the second screen's report within 150 ms is a
    report of its own, not a repeat."""
    observer.emit("widget", "state", extra={"id": "youtube", "dev": "phone", "changed": {"playing": "True"}})
    second = observer.emit("widget", "state", extra={"id": "youtube", "dev": "desk", "changed": {"playing": "True"}})
    again = observer.emit("widget", "state", extra={"id": "youtube", "dev": "desk", "changed": {"playing": "True"}})
    assert second is not None and again is None


def test_a_short_prompt_is_kept_whole():
    assert observer._prompt_excerpt("corto") == "corto"


def test_and_a_REAL_turn_keeps_its_browser_block():
    """The check that matters, using the real prompt rather than filler."""
    from nucleo.turn.prompt import builder as _p
    from widgets.navegador import tasks

    tasks._tasks.clear()
    tid = tasks.create("Reservar noche en el hotel")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url="chrome-error://chromewebdata/")
    try:
        system, _ = _p.build_flash_system(turn_text="¿lo tienes ya?")
        ex = observer._prompt_excerpt(system)
        assert "NAVEGADOR" in ex
        assert "· MURO: " in ex
    finally:
        tasks._tasks.clear()
