"""V2-451 · the rows block depended on the TAB, so an errand without a browser showed none.

`_sheet_top_rows` resolves the sheet FROM the browser task, and `navegador_lines()` only composes cards if
there are tasks. An errand resolved by SEARCH has no tab: it fills the sheet and the prompt does not name a
single row — and it does not even emit the V2-438 warning, because it lives inside the function nobody calls.

Measured in `cheapest-monitor__us` (2026-08-28, 24/7 set):

    navegador_task_id: ""            ← there was no browser for the entire round
    results_sheet: 6 rows with name and price (Dell S2725QC, LG 27UP650-W, BenQ GW2790QT…)
    delivery_completeness: {named: 0, available: 6, shown_to_model: false}
    unresolved_errand_sheets: TODO down to zero — not even one warning

and the blocker judge: «it responded with an empty promise ("I'll get back to you") without delivering anything.
The results sheet already had 6». This is the cause left open since V2-432, V2-441, and V2-444: the sheet belongs
to the ERRAND (V2-259), and the prompt only knew how to read it through the browser.
"""
import pytest

from nucleo import dispatch as D
from nucleo.workers.session import SessionRecord
from widgets.navegador import tasks as T
from widgets.results import data as SHEET


@pytest.fixture(autouse=True)
def _clean():
    T._tasks.clear()
    D._SESSIONS.clear()
    yield
    T._tasks.clear()
    D._SESSIONS.clear()


def _encargo_sin_navegador(sheet="v451-1", filas=(("Dell S2725QC", "$280"), ("LG 27UP650-W", "$230"))):
    rec = SessionRecord(task_id="w1", goal="cheapest 4K monitor", kind="web")
    rec.status, rec.sheet = "running", sheet
    D._SESSIONS["w1"] = rec
    if filas:
        SHEET.apply_action("present", {"sheet": sheet, "title": "Resultados",
                                       "items": [{"title": t, "price": p} for t, p in filas]})
    return rec


#: The ROW HEAD, never the bare marker. Since V2-556 the block's own INSTRUCTION quotes «ENCONTRADO (en su
#: hoja)» to tell the model what to look for, so the bare string matches a prompt with zero rows — the very
#: confusion `verify.py` documents at `_ROWS_HEAD_TAREA`. The separator prefix only ever precedes real rows.
_ROW_HEAD = " — ENCONTRADO (en su hoja): "


def test_el_resumen_del_encargo_LLEVA_su_hoja():
    """The plumbing: without the field in `pending_summaries`, the block has nothing to read, and the four above
would pass with only a partial fix."""
    rec = _encargo_sin_navegador()
    fila = next(x for x in D.pending_summaries() if x["id"] == "w1")
    assert fila.get("sheet") == rec.sheet


def test_y_sigue_reconociendo_la_del_NAVEGADOR():
    """Sensitivity in the other direction: teaching it to read the new one must not cost the old one, which is
what measures all rounds with a browser."""
    from tests.use_cases.e2e.agent.verify import _ROWS_HEAD, _rows_in
    assert _rows_in(f"NAVEGADOR …{_ROWS_HEAD}«Bici Orbea — 150€». OJO: la hoja") == ["Bici Orbea"]


def test_el_formateador_conserva_las_TRES_reglas_que_costaron_una_ronda_cada_una():
    from widgets.navegador.errand_sheet import fila
    assert fila({"title": "Fontanero", "tel": "600123456"}) == "«Fontanero — 600123456»"      # V2-240
    assert "SIN PRECIO" in fila({"title": "Monitor"})                                          # V2-360
    assert "aún no es un candidato" in fila(                                                   # V2-376
        {"title": "9 precios 2026", "facts": [{"label": "origen", "value": "búsqueda web"}]})


def test_el_TELEFONO_tambien_se_lee_de_los_facts():
    """It comes from both places depending on who extracts it; reading only one loses half."""
    from widgets.navegador.errand_sheet import fila
    assert "600111222" in fila({"title": "Cerrajero", "facts": [{"label": "Teléfono", "value": "600111222"}]})
