#
# presentation.py — QUALITY CONTROL for how data is PRESENTED on a blank surface.
#
# Born from the 2026-08-10 incident (14:08:26 session). A Brain Worker did impeccable work —45 candidates compared,
# 3 proposals with round trips, prices, and surcharge for car height— and rendered it BADLY: three rich cards squeezed
# into two columns (one orphan in the last row), titles with three ideas inside wrapping to four lines and colliding
# with the price, and an important warning cut mid-word ("⚠️ Llevar tu c").
#
# The diagnosis was NOT "the model thinks it looks nice this way". It was that NOBODY was making the decision:
#   · `columns:2` was a model guess that OVERRAN the widget's own correct heuristic (3 cards → 1 column, i.e. the three
#     horizontal rows the operator expected);
#   · nobody had told the worker how much fits in a title — that information lived only in CSS;
#   · and our own `[:200]` cap silently cut text in the middle of a warning.
#
# Hence this module's three rules:
#
#   1. THE SURFACE OWNS GEOMETRY; THE FILLER MAY CHOOSE A TEMPLATE (amended V2-703). How many columns there are,
#      how wide a track is, how many lines a title gets — those stay here, because they are the things a model
#      guesses wrong and cannot see. What the filler MAY now do is name one of a closed set of templates
#      (`layout`: card | tile | row | compare) and decide WHICH datum goes in each slot. The operator's reason:
#      «esto no es una página web, esto es un sistema dinámico e inteligente que tiene que soportar cualquier tipo
#      de resultado, tanto si buscamos barcos como cafeteras, como recetas, como eventos históricos» — a boat puts
#      its length where a recipe puts its time, and no heuristic here can know that.
#      The old rule's reason survives as the GUARD: a name, never a number, and an impossible choice (a photo
#      template over results with no photos) falls back instead of drawing badly. `columns` stays forbidden —
#      that one really is geometry, and the incident below is what it cost.
#   2. LENGTH IS THE LAYOUT'S JOB (V2-797, replacing «budgets are declared»). The sheet used to publish how
#      many characters fit each field (title 34, subtitle 70), clip what it stored to that and report every longer
#      title as «the payload breaks the card». The card did not break: the text was cut on the server and the worker
#      was scolded for data it does not control (a listing's real name, a page's snippet). A long title is now laid
#      out by the card — clamped to its lines for the space it really has, whole on expand. What remains here are
#      STORAGE caps (a field is not a page) and data-quality checks that really break comparison.
#   3. SILENT CLIPPING IS FORBIDDEN. If something does not fit, cut on a word boundary, mark it with "...", and record
#      it as an incident. A warning cut mid-word is worse than omitting it.
#
# Intentionally GENERIC: it knows nothing about ferries, hotels, or results. A weather widget can remain a rigid,
# permanent format (does not declare `presentation` and nothing happens here); blank sheets that present findings,
# reports, or charts are the ones that need this flexibility WITH quality control.
#
from __future__ import annotations

# STORAGE caps per field (characters): what one field may hold before it stops being that field. Not layout — the
# card clamps whatever it is given to the space it has (V2-797). A surface may declare its own in its manifest.
DEFAULTS: dict = {
    "sheet_title": 160,
    "sheet_subtitle": 400,
    "title": 300,
    "subtitle": 300,
    "price": 60,
    "badge": 40,
    "part_title": 200,
    "fact_label": 60,
    "fact_value": 300,
    "source_detail": 300,
}

# UNIVERSAL rules for presenting data on a blank surface. This is the preset that guarantees quality: it describes NO
# domain, only how information is distributed across cards so it can be read at a glance.
_UNIVERSAL = """PRESENTACIÓN (control de calidad — aplica SIEMPRE que rellenes una superficie de datos)
Tu trabajo no acaba con encontrar el dato: acaba cuando se LEE de un vistazo. Reglas:
· UNA IDEA POR CAMPO. El `title` es el NOMBRE del resultado y nada más. La ruta, la compañía, el barco, el horario
  o la duración NO van en el título: van en `subtitle` (una línea) o en `facts` (dato duro).
· LA LONGITUD LA MAQUETA LA SUPERFICIE: recorta a la vista según el sitio que tenga y enseña el texto entero al
  abrirlo. No acortes un nombre real para que «quepa».
· LOS DATOS DUROS VAN EN `facts`, no en prosa. Precio, horario, duración, condiciones, medidas, valoración: cada
  uno su etiqueta y su valor. Así se comparan en columna y se pueden consultar después por voz. Los 1-4 que DECIDEN
  van además en `meta` (chips cortos bajo el título: distancia, horario, valoración…).
· NO DECIDAS EL LAYOUT. No mandes número de columnas ni maquetes con guiones, saltos ni tablas ASCII: la superficie
  reparte el espacio según la forma de lo que le des, y lo hace mejor que una suposición a ciegas.
· NADA IMPORTANTE AL FINAL DE UN CAMPO LARGO. Si una salvedad o un aviso importa, va en su propio `fact` o en su
  propia línea — nunca colgando del final de un párrafo que puede quedarse sin sitio.
· MISMA FORMA PARA TODOS LOS ITEMS. Si uno lleva precio y horario, todos. Comparar exige columnas comparables.
· CADA RESULTADO LLEVA SU `url`: la página donde lo encontraste. Es la única puerta a la ficha COMPLETA, con los
  cien campos que tú no has copiado, y sin ella el resultado es un callejón sin salida. Y su `image` si la hay:
  la superficie la muestra entera, no hace falta que la recortes ni que elijas una apaisada."""


def _manifest(widget_id: str) -> dict:
    try:
        from widgets import runtime
        return runtime.get(widget_id) or {}
    except Exception:
        return {}


def contract(widget_id: str) -> dict:
    """Field budgets for this surface: what its manifest declares over the defaults."""
    declared = (_manifest(widget_id).get("presentation") or {}).get("budgets") or {}
    out = dict(DEFAULTS)
    for k, v in declared.items():
        try:
            iv = int(v)
        except (TypeError, ValueError):
            continue
        if iv > 0:
            out[k] = iv
    return out


def is_blank_sheet(widget_id: str) -> bool:
    """Is this a BLANK surface (content decides its shape) or a rigid format?

    A weather widget is rigid: temperature, hours, icons, always the same — and that is fine. Presentation quality
    control only makes sense where the shape is decided on each delivery.
    """
    return bool((_manifest(widget_id).get("presentation") or {}).get("blank_sheet"))


def directive(widget_id: str = "") -> str:
    """Prompt block that guarantees presentation quality: the universal rules. Formats remain free, and no
    character budget travels any more — the surface lays out any length (V2-797)."""
    return _UNIVERSAL


def blank_sheets() -> list[str]:
    """BLANK surfaces from the catalog. Discovered by manifest, not by a hardcoded list: a new widget joins simply by
    declaring `presentation.blank_sheet`."""
    try:
        from widgets import runtime
        ids = [w.get("id") for w in (runtime.catalog() or [])]
    except Exception:
        return []
    return [i for i in ids if i and is_blank_sheet(i)]


def directive_for(text: str) -> str:
    """Presentation directive for the blank surfaces MENTIONED by this prompt.

    This lets quality control travel with the task without bloating every prompt: a worker that only needs to write a
    file does not receive card layout rules. And there is no per-widget wiring: if the prompt names a blank sheet, its
    budgets enter automatically.
    """
    low = (text or "").lower()
    hit = [w for w in blank_sheets() if w.lower() in low]
    if not hit:
        return ""
    return "\n\n".join(directive(w) for w in hit[:2])


def clip(text, limit: int) -> tuple[str, bool]:
    """Clip on a WORD boundary and mark the cut. Returns (text, was_clipped).

    Replaces scattered `str(x)[:N]`, which cut mid-word without saying so: that is how the real-case warning
    "⚠️ Llevar tu cadena..." was lost and became "⚠️ Llevar tu c".
    """
    s = "" if text is None else str(text).strip()
    if limit <= 0 or len(s) <= limit:
        return s, False
    cut = s[:limit]
    sp = cut.rfind(" ")
    if sp > limit * 0.6:          # there is a whole word to cut at; otherwise, a hard cut is better than one word
        cut = cut[:sp]
    return cut.rstrip(" ,;:·-") + "…", True


def audit(widget_id: str, payload: dict) -> list[str]:
    """Review a payload BEFORE rendering it and return DATA-QUALITY incidents in plain language — what breaks
    comparison or leaves a dead end, never a length (V2-797: length is the layout's job).

    In code, not only in the prompt: a prompt is a request, not a guarantee. Output from here is recorded in
    observability (and can be returned to the worker for fixing), so a payload that breaks the card stops being
    invisible.
    """
    out: list[str] = []

    if payload.get("columns") is not None:
        out.append("`columns` viene en el payload: el layout lo decide la superficie según la forma del contenido, "
                   "no quien la rellena — se ignora como orden y se trata como tope máximo")

    items = payload.get("items")
    items = items if isinstance(items, list) else []
    shapes = []
    for it in items:
        if not isinstance(it, dict):
            continue
        shapes.append((bool(it.get("parts")), bool(it.get("price")), bool(it.get("facts")),
                       bool(it.get("url"))))

    # Comparing requires comparable columns: if one item has a price and another does not, the mental table breaks.
    if len(shapes) > 1:
        for idx, name in ((1, "price"), (2, "facts"), (3, "url")):
            vals = {s[idx] for s in shapes}
            if len(vals) > 1:
                out.append(f"los items no tienen la MISMA forma: unos traen `{name}` y otros no — no se pueden comparar")

    # THE LINK OUT. A found result whose original page cannot be opened is a dead end: whatever the record shows
    # is whatever we chose to copy, and the rest of the listing —the thousand fields we did not judge worth
    # keeping— becomes unreachable. Operator, 2026-09-15: «asegúrate de que cuando un widget de resultados busca
    # cosas SIEMPRE muestre los links a la página web original». Rendering it was the widget's half (it was
    # dropping urls it had); SUPPLYING it is this one, and it is checked only where it makes sense — a sheet
    # built from the web, which is what declaring `sources` means. A sheet of the operator's own files has no
    # page to link to and is not accused of anything.
    if items and payload.get("sources") and not any(isinstance(i, dict) and i.get("url") for i in items):
        out.append("ningún resultado trae `url`: el operador no puede abrir la ficha original de ninguno — "
                   "cada item necesita el enlace a la página donde lo encontraste")
    return out
