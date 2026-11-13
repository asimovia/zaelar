"""«Go to the part about proof of work»: the passage is found by its BODY, and the turn's words say where it landed.

Demo sandbox 2026-11-13, F2 (build 138): the brief read `documento:goto` at 1.00 and the verdict completed the model.
The document had no heading naming proof of work — the topic lived in the paragraphs' bodies, hyphenated
(«proof-of-work»). The goto landed on the first paragraph carrying it, but its receipt named nothing, so the mouth
added nothing and the model's own words («Want me to scroll to it?») stood over a scroll that had already happened.

The class, three halves:
  · a word counts where a word of the block BEGINS with its stem — «work» is in «proof-of-work», never in «network»;
  · a hyphen between letters is a space on both sides — he may say «proof of work» or type «proof-of-work»;
  · the goto's receipt names the passage it landed on (`title`), so the mouth's `met` line says it; a goto that
    finds nothing refuses with the card's own sentence (`say`), which the mouth always says.
Disarms (named in the test): plain substring stems → «work» lands on «network»; no hyphen flattening → a typed
«proof-of-work» finds nothing in «proof of work»; no `title` → the reply names nothing.
"""
from __future__ import annotations

import pytest

from widgets import store
from widgets.documento.blocks import _best_block, lead

EN = "\n\n".join([
    "# Bitcoin — summary",
    "**Background.** A payment system without banks, carried by a peer-to-peer network of nodes.",
    "**The proposal.** Nodes collect transactions into blocks and use proof-of-work to timestamp each block.",
    "**Incentives.** Miners are paid in new coins and fees.",
])
ES = "\n\n".join([
    "# Bitcoin — resumen",
    "**Contexto.** Un sistema de pagos sin bancos, sostenido por una red entre pares de nodos.",
    "**La propuesta.** Los nodos agrupan transacciones en bloques y usan la prueba de trabajo para sellarlos.",
    "**Incentivos.** Los mineros cobran en monedas nuevas y comisiones.",
])
TYPED_SPACED = "**Mining.** Each block carries a proof of work that is costly to make and cheap to check."
NETWORK_FIRST = "\n\n".join([
    "**The network.** Nodes relay blocks to each other.",
    "**Work.** Every block has to carry the work it cost.",
])


@pytest.mark.parametrize("body,said,lands", [
    (EN, "go to the part about proof of work", "**The proposal.**"),
    (EN, "go to the part about proof-of-work", "**The proposal.**"),
    (EN, "show me where it talks about miners", "**Incentives.**"),
    (ES, "ve a la parte de la prueba de trabajo", "**La propuesta.**"),
    (ES, "llévame a lo de la prueba-de-trabajo", "**La propuesta.**"),
    (ES, "enséñame dónde habla de los mineros", "**Incentivos.**"),
])
def test_a_passage_no_heading_names_is_found_by_its_body(body, said, lands):
    got = _best_block(body, said)
    assert got.startswith(lands), f"«{said}» → «{got[:60]}»"


def test_a_hyphen_he_types_finds_the_compound_written_with_spaces():
    # disarm: no hyphen flattening → the stem «proof-» is in no block and nothing is found
    assert _best_block(TYPED_SPACED, "the proof-of-work part").startswith("**Mining.**")


def test_a_stem_counts_only_where_a_word_begins():
    # disarm: a plain substring → «work» sits inside «network» and the first block wins
    assert _best_block(NETWORK_FIRST, "the part about the work").startswith("**Work.**")


def test_the_passage_is_named_as_a_reader_calls_it():
    assert lead("**The proposal.** Nodes collect transactions") == "The proposal"
    assert lead("Step 3") == "Step 3"
    assert lead("A long paragraph with no lead at all that keeps going well past what anyone would call a name").endswith("…")


def test_the_goto_receipt_names_where_it_landed_and_the_mouth_says_it(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from i18n import langs
    from nucleo.turn import reply as R
    from widgets.documento import data
    monkeypatch.setattr(langs, "current_code", lambda: "en")
    data.apply_action("show", {"title": "Bitcoin", "body": EN})
    res = data.apply_action("goto", {"text": "go to the part about proof of work"})
    assert res["ok"] and res["title"] == "The proposal", res      # disarm: no `title` → the reply names nothing
    out = R.of_op("documento", "goto", res)
    assert out.verdict == "met" and out.object == "«The proposal»"
    owed = [t for _o, t in R.owed([out], "Want me to scroll to it?")]
    assert owed and "The proposal" in owed[0], owed


@pytest.mark.parametrize("lang,word", [("en", "isn't in the document"), ("es", "no está en el documento")])
def test_a_goto_that_finds_nothing_says_so_and_claims_no_scroll(tmp_path, monkeypatch, lang, word):
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from i18n import langs
    from nucleo.turn import reply as R
    from widgets.documento import data
    monkeypatch.setattr(langs, "current_code", lambda: lang)
    data.apply_action("show", {"title": "Bitcoin", "body": EN})
    res = data.apply_action("goto", {"text": "the part about quantum computers"})
    assert res["ok"] is False and res.get("say") == "widgets.documento.goto_not_found", res
    out = R.of_op("documento", "goto", res)
    assert out.verdict == "unmet" and word in out.reason, out
    owed = [t for _o, t in R.owed([out], "Here it is.")]
    assert owed and word in owed[0], owed
