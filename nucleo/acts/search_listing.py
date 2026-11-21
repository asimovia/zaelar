"""The listing half of the search door (V2-556; refactor2710-06 T-05): one turn, one sheet, and an honest handoff.

`fast_pass` runs the listing ladder (`search.listing`: SERP → HTTP+JSON-LD → Unlocker) under a single-digit-second
deadline. ENOUGH rows land in the results sheet now and the turn answers with them; NOT enough → the same sheet keeps
what was found and which doors were tried, and a Brain Worker INHERITS it (`ctx["sheet"]`, the relay seam), so he
watches one box from the first finding to the final report. A new hunt is an ERRAND born here, in the turn, before the
pass runs (`errand.born`, V2-844 F1a): its durable row carries his whole request and its uid names the sheet, so the box
and the errand are one id from the first row on. `hunt` is the conversation host's door (`acts_tasks._listings`): the
fact of the pass, never a sentence — the model says what was found.
"""
from __future__ import annotations


from loguru import logger


#: How long the turn waits for the fast pass before it speaks and lets it finish alone.
FAST_PASS_BUDGET_S = 12.0


def _note(what: str) -> None:
    logger.debug(f"acts.search_listing: {what}")


#: The tool as FlashBrain sees it; its argument names are this door's contract. Wording is load-bearing and gated
#: by the catalogue's budget (node 2.13).
TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "search_listings",
        "description": (
            "Busca ANUNCIOS/productos en venta o alquiler (coche, piso, portátil, entradas…): resultados "
            "reales con precio y enlace en la hoja de resultados. Si el mercado no da bastante, este sistema "
            "lanza ÉL SOLO la búsqueda a fondo: di que sigues buscando y JAMÁS llames además a "
            "escalate_to_slowbrain por la misma caza. No es un dato puntual (web_search) ni HACER algo en "
            "una web (escalate_to_slowbrain). CONSERVA los filtros que el operador no retiró."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string",
                          "description": "Qué se busca, autocontenido; SIN el precio (va aparte)."},
                "price_max": {"type": "number", "description": "Precio máximo (solo número), si lo dio."},
                "price_min": {"type": "number", "description": "Precio mínimo (solo número), si lo dio."},
                "condition": {"type": "string", "description": "nuevo/usado/reacondicionado, si lo dijo."},
            },
            "required": ["query"],
        },
    },
}


def _late_fast_pass(task) -> None:
    """The fast pass that outlived its turn: its outcome is on the timeline, never lost in a thread."""
    import asyncio as _aio
    try:
        res = task.result() or {}
        from voice.observer import emit as _emit
        _emit("brain", "🛒 la pasada rápida acabó después del turno", role="system",
              text=f"delivered={bool(res.get('delivered'))} n={res.get('n', 0)} sheet={res.get('sheet', '')}",
              extra={"cat": "flash", **{k: res.get(k) for k in ("delivered", "n", "sheet")}})
    except _aio.CancelledError:
        _note("the loop went down before the late pass reported; its sheet write is unaffected")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"acts.search_listing: the late fast pass failed ({e!r})")


async def hunt(asked_text: str, args: dict) -> dict:
    """The hunt with no face (INI-078 F2 7c): start its flow, run the fast pass up to `FAST_PASS_BUDGET_S`, and return
    the fact — `{"kind", "res"}`. `kind`: `late` (the pass outlived the budget and still writes its sheet), `done`
    (`res` is the pass's verdict). Nothing is joined to an open flow by likeness (INI-078 segregation S2/S3): the model
    names an open task by its #number, so a hunt that reaches here is a new one, with its own sheet. The rows go to the
    results sheet, shown by the pass; who says what was found is the caller's."""
    import asyncio

    from nucleo.errands import launches as _launches
    from nucleo.acts.errand import whole_request
    operator_text = whole_request(str(asked_text or ""))   # V2-844 F1a: never the cut turn's tail
    from nucleo import matching
    asked = operator_text if matching.content_words(operator_text) else str(args.get("query") or "")   # «Okay.» names nothing
    errand_id, new_sheet = _born(asked)
    lid = _launches.opened(operator_text or str(args.get("query") or ""), new_sheet)
    task = asyncio.ensure_future(asyncio.to_thread(
        fast_pass, str(args.get("query") or ""), price_max=args.get("price_max"), price_min=args.get("price_min"),
        condition=str(args.get("condition") or "").strip(), operator_text=operator_text, sheet="",
        new_sheet=new_sheet, errand_id=errand_id))
    task.add_done_callback(lambda _t: _launches.closed(lid))   # by then its delivery or escalation carries it
    done, _pending = await asyncio.wait({task}, timeout=FAST_PASS_BUDGET_S)
    if not done:
        task.add_done_callback(_late_fast_pass)
        return {"kind": "late", "res": {"delivered": False, "n": 0, "escalated": 0, "ctx": "", "sheet": "",
                                        "pending": True}}
    try:
        res = task.result()
    except asyncio.CancelledError:
        raise
    except Exception as e:  # noqa: BLE001 — a search that explodes must not take the turn with it
        logger.warning(f"acts.search_listing: the fast pass failed, the turn goes on ({e!r})")
        res = {"delivered": False, "n": 0, "escalated": 0, "ctx": "", "reason": str(e), "sheet": ""}
    return {"kind": "done", "res": res}


def _born(asked: str) -> tuple[int, str]:
    """A new flow is an errand born before the pass runs: its id and its uid, which is its sheet (V2-844 F1a)."""
    try:
        from nucleo.acts.errand import born
        return born(asked, {"surface": "lista", "kind": "web"})
    except Exception as e:  # noqa: BLE001
        logger.warning(f"acts.search_listing: the hunt's errand was not born ({e!r})")
        return 0, ""


from nucleo.acts.search_sheet import compose_context, fast_pass  # noqa: E402,F401 — the blocking pass and its sheet
