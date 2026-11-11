"""V2-883 — a periodic job is an OBJECT: one reader, one door by reference, and an honest result.

The class: the scheduler's rows had no reader a turn could address them by (the prompt listed whole names, often a
sentence with an order number in it), and one writer that matched a name EXACTLY and whose boolean nobody read — so
«delete the periodic job» was either a promise, an errand with no door, or a spoken «deleted» over nothing.

What these pin, each with another wording or language than the one that was measured:
  · the reader is the card shape (`{id, label, field, hint}`), with a SHORT label;
  · a reference resolves through the cards' own resolver — a spoken label, a whole name, an id; a stale id is no
    row (never read as a position); a reference naming nothing is refused with the candidates;
  · the door answers what is TRUE afterwards (the job is no longer listed), and a miss is SAID, in his language,
    never «cancelled»;
  · the turn's live record lists the jobs by reference;
  · the tag carries a name with spaces and accents (a narrower class dropped it as a malformed tag).
"""
from __future__ import annotations

import asyncio

import pytest

from i18n import langs
from nucleo.cli import turn
from nucleo.pulse import scheduler
from tests.platform import turn_harness as H

PARCEL = ("Seguimiento del paquete del pedido 4021-778-55 de la tienda online, mirar el estado y avisar si cambia "
          "algo importante")
WATER = "Regar las plantas del balcón"


@pytest.fixture
def jobs():
    """The REAL scheduler inside the typed turn's isolation (the harness stubs it), with two jobs of his."""
    real = scheduler.create, scheduler.cancel
    with H.Isolated("es"):
        stub = scheduler.create, scheduler.cancel
        scheduler.create, scheduler.cancel = real
        try:
            a = scheduler.create("mira el estado de mi pedido", "0 11 * * *", name=PARCEL)
            b = scheduler.create("riega", "every 2d", name=WATER)
            yield {"parcel": str(a["id"]), "water": str(b["id"])}
        finally:
            turn.reset("v883")
            for j in scheduler.list_jobs(active_only=True):
                scheduler.cancel(str(j["id"]))
            scheduler.create, scheduler.cancel = stub


def _listed() -> set[str]:
    return {str(j["id"]) for j in scheduler.list_jobs(active_only=True)}


# ── the reader ─────────────────────────────────────────────────────────────────────────────────────────────────
def test_the_reader_is_the_card_shape_with_a_short_label(jobs):
    rows = {r["id"]: r for r in scheduler.ref_index()}
    assert set(rows) == {jobs["parcel"], jobs["water"]}
    parcel = rows[jobs["parcel"]]
    assert parcel["field"] == scheduler.FIELD and parcel["hint"], parcel
    assert len(parcel["label"]) <= scheduler.LABEL_CHARS + 1 and parcel["label"].startswith("Seguimiento del paquete")
    assert rows[jobs["water"]]["label"] == WATER, "a short name is its own label"


def test_create_answers_with_the_reference_the_job_is_addressed_by(jobs):
    r = scheduler.create("di hola", "every 3h", name="Saludo de la tarde")
    assert r["ok"] and r["label"] == "Saludo de la tarde" and str(r["id"]) in _listed()


# ── the reference ──────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("said", ["seguimiento del paquete", "the parcel tracking: seguimiento paquete pedido",
                                  "#{parcel}", "{parcel}"])
def test_a_spoken_label_or_an_id_resolves_to_the_job(jobs, said):
    hit = scheduler.find(said.format(**jobs))
    assert hit["job"] and hit["job"]["id"] == jobs["parcel"], hit


def test_a_reference_naming_no_job_is_refused_with_the_candidates(jobs):
    hit = scheduler.find("la tarea de los correos")
    assert hit["job"] is None and hit["needs"] == "no_match"
    assert WATER in hit["candidates"], hit


def test_a_stale_id_is_no_row_never_a_position(jobs):
    """A number is an id the reader printed; one that is gone must not fall through to «the Nth job» — with the
    first job gone, its id read as a position named the job that is left."""
    assert scheduler.cancel(jobs["parcel"]) is True
    for gone in (jobs["parcel"], "1"):
        if gone in _listed():
            continue
        assert scheduler.find(gone)["job"] is None, f"the gone id {gone} resolved to {scheduler.find(gone)}"


# ── the door ───────────────────────────────────────────────────────────────────────────────────────────────────
def test_the_door_cancels_by_label_and_answers_what_is_true(jobs):
    r = scheduler.unschedule("quita el seguimiento del paquete")
    assert r["ok"] and r["id"] == jobs["parcel"] and r["label"].startswith("Seguimiento"), r
    assert jobs["parcel"] not in _listed() and jobs["water"] in _listed()


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_miss_is_refused_in_his_language_and_cancels_nothing(jobs, lang, monkeypatch):
    monkeypatch.setattr(langs, "current_language", lambda: langs.spec(lang))
    r = scheduler.unschedule("the daily email digest")
    assert not r["ok"] and r["error"] == "no_match", r
    assert r["message"].startswith(langs.spec(lang).cron_no_match.split("{")[0]) and WATER in r["message"], r
    assert _listed() == {jobs["parcel"], jobs["water"]}, "a miss touched a job"


def test_cancel_by_an_id_that_is_gone_is_false(jobs):
    assert scheduler.cancel(jobs["water"]) is True
    assert scheduler.cancel(jobs["water"]) is False, "cancelling nothing answered True"


# ── the turn: the reader in its prompt, the tag, the mouth ─────────────────────────────────────────────────────
def test_the_live_record_lists_the_jobs_by_reference(jobs):
    from nucleo.turn.prompt import live_record
    line = live_record._cron_line()
    assert f"id {jobs['parcel']} «Seguimiento del paquete" in line, line
    assert PARCEL not in line, "the whole 100-character name is not a reference"
    assert "cancel_scheduled" in line


def test_the_live_record_says_none_when_nothing_is_scheduled(jobs):
    """«None» is a fact too: with no line, an order over a job that does not exist was promised («Vale, la quito»)."""
    from nucleo.turn.prompt import live_record
    for j in list(_listed()):
        scheduler.cancel(j)
    assert "Ya programado: nada." in live_record._cron_line()


def test_the_tag_carries_a_name_with_spaces_and_accents():
    from voice import tag_protocol
    got = []
    tag_protocol.strip_tags("Hecho. [[cron.cancel:Riego del balcón]]", lambda a, e: got.append((a, e)), True)
    assert ("cron.cancel", {"name": "riego del balcón"}) in got, got


class _Model:
    """The model says it is done and emits the tag with what HE said — the shape of the measured turn."""
    tag = ""

    async def stream(self, *_a, **_kw):
        yield "Hecho, ya está quitada."
        yield f"[[cron.cancel:{self.tag}]]"

    async def complete(self, *_a, **_kw):
        return ""


def _turn(monkeypatch, tag: str, words: str) -> dict:
    return _run_with(type("M", (_Model,), {"tag": tag}), words)


def _run_with(model, words: str) -> dict:
    """The model stub lives exactly as long as the turn. A `monkeypatch` here restored the harness's fake AFTER the
    `jobs` fixture had put the real client back (monkeypatch is set up first, by the root conftest, so it undoes
    last), and every later test in the process ran against `RecordedModel`."""
    from nucleo.llm import fast_client
    old, fast_client.FastClient = fast_client.FastClient, model
    try:
        return asyncio.run(turn.run_turn(words, sid="v883", ingest=False, execute=True))
    finally:
        fast_client.FastClient = old


def test_a_miss_is_not_spoken_as_done(jobs, monkeypatch):
    res = _turn(monkeypatch, "la tarea de los correos", "borra la tarea de los correos")
    head = langs.spec("es").cron_no_match.split("{")[0]
    assert head in res["reply"], res["reply"]
    assert _listed() == {jobs["parcel"], jobs["water"]}


def test_a_hit_by_its_label_is_cancelled_in_the_turn(jobs, monkeypatch):
    res = _turn(monkeypatch, "seguimiento del paquete", "quita el seguimiento del paquete")
    assert jobs["parcel"] not in _listed(), res
    assert langs.spec("es").cron_no_match.split("{")[0] not in res["reply"], res["reply"]


# ── the door as a TOOL: measured, the model picked `stop_worker` over the inline tag ─────────────────────────────────
def test_the_tool_is_offered_only_while_a_job_is_scheduled(jobs):
    from nucleo.flash import router
    names = lambda ctx: {t["function"]["name"] for t in router.tools(ctx)}   # noqa: E731
    assert "cancel_scheduled" in names(router.tool_context())               # read from the scheduler's state
    for j in list(_listed()):
        scheduler.cancel(j)
    assert "cancel_scheduled" not in names(router.tool_context())


class _ToolModel:
    async def stream(self, *_a, on_tool_call=None, **_kw):
        res = on_tool_call("cancel_scheduled", {"job": self.job})
        if asyncio.iscoroutine(res):
            await res
        yield "Hecho."

    async def complete(self, *_a, **_kw):
        return ""


@pytest.mark.parametrize("job, gone", [("riego del balcón", "water"), ("the email digest", None)])
def test_the_tool_cancels_by_label_and_a_miss_is_said(jobs, monkeypatch, job, gone):
    res = _run_with(type("T", (_ToolModel,), {"job": job}), f"borra {job}")
    head = langs.spec("es").cron_no_match.split("{")[0]
    if gone:
        assert jobs[gone] not in _listed() and head not in res["reply"], res["reply"]
    else:
        assert _listed() == {jobs["parcel"], jobs["water"]} and head in res["reply"], res["reply"]
