"""A browser task that STOPPED must be able to say so (V2-167).

Three use-case runs ended with the very same task state — `status="working"`, `phase_active=True`,
`results=None` — after the operator had already given up, and in all three zaelar told the truth and the truth
was useless, because the only truth it had was that the task was alive:

  · `restaurant-tonight-madrid` reached the right page (thefork.es/restaurant/casa-lucio-madrid/r146247) at
    19:28:47 and spent the next eleven minutes there, re-photographing it — `shot_rev` reached 10 over four
    URLs, so anything counting captures would have reported healthy movement while nothing moved.
  · `book-hotel-night-known__es` made ONE navigation in the whole run, to Booking's `chal_t=` anti-bot
    challenge, and reported `awaiting_login: false` — the only field that could have said «me han parado» is
    written exclusively by the real login flow, so it said there was nothing to say.
  · `find-theatre-tickets__es` walked through `chrome-error://chromewebdata/` and Google's `/sorry/index`
    CAPTCHA and came out the other side with `results: null`.

The two facts that were missing are therefore: how long since the task last MOVED, and whether the page it is
sitting on is a wall. Both already existed in the world; neither existed in the registry.
"""
from __future__ import annotations


import time

import pytest

from widgets.navegador import tasks


@pytest.fixture(autouse=True)
def _clean_registry():
    tasks._tasks.clear()
    yield
    tasks._tasks.clear()


# ── the wall ───────────────────────────────────────────────────────────────────────────────────────────────
# The three URLs are VERBATIM from the mechanism reports, not invented for the test.
BOOKING_WALL = ("https://www.booking.com/index.es.html?aid=304142&label=x&chal_t=1787158378677"
                "&force_referer=")
GOOGLE_WALL = "https://www.google.com/sorry/index?continue=https://www.google.com/search%3Fq%3Del%2Brey%2Bleon"
LOAD_ERROR = "chrome-error://chromewebdata/"
REAL_PAGE = "https://www.thefork.es/restaurant/casa-lucio-madrid/r146247"


def test_the_three_walls_that_were_measured_are_recognised():
    assert tasks.wall_reason(BOOKING_WALL)
    assert tasks.wall_reason(GOOGLE_WALL)
    assert tasks.wall_reason(LOAD_ERROR)


def test_and_an_ordinary_page_is_not_a_wall():
    """The other half: without this, “detect walls” and “always declare a wall” pass the same test. The
    restaurant page is exactly where the task HAD reached its destination."""
    assert tasks.wall_reason(REAL_PAGE) == ""
    assert tasks.wall_reason("https://www.thefork.es/search/madrid/Casa%20Lucio") == ""
    assert tasks.wall_reason("") == ""


def test_the_reason_is_said_in_words_the_operator_can_hear():
    """The field is read aloud: it cannot return the token that gave it away."""
    for url in (BOOKING_WALL, GOOGLE_WALL, LOAD_ERROR):
        reason = tasks.wall_reason(url)
        assert "chal_t" not in reason and "sorry" not in reason and "chrome-error" not in reason
        assert len(reason.split()) >= 3


def test_the_task_carries_its_wall_and_drops_it_when_it_moves_on():
    tid = tasks.create("reservar hotel")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url=BOOKING_WALL, page_title="Booking.com")
    assert tasks.active_progress()[0]["wall"]
    tasks.update_view(tid, url="https://www.booking.com/searchresults.es.html?ss=Madrid")
    assert tasks.active_progress()[0]["wall"] == ""


# ── the stall ─────────────────────────────────────────────────────────────────────────────────────────────
def test_recapturing_the_same_page_is_not_progress():
    """The miniature restaurant run: four pages and then six captures of the last one. If a capture counted
    as progress, the task would be declared healthy exactly while it was dying."""
    tid = tasks.create("Reservar mesa en Casa Lucio")
    tasks.set_status(tid, "working")
    for url in ("https://www.thefork.es/", "https://www.thefork.es/restaurante/madrid",
                "https://www.thefork.es/search/madrid/Casa%20Lucio", REAL_PAGE):
        tasks.update_view(tid, url=url, page_title="thefork.es")
    tasks._tasks[tid]["last_progress"] = time.time() - 673      # the measured 11 minutes
    for rev in range(5, 11):                                    # shot_rev 5..10, same page
        tasks.update_view(tid, url=REAL_PAGE, shot_rev=rev)
    assert tasks.active_progress()[0]["stalled_s"] >= 600


def test_but_a_new_page_clears_it():
    tid = tasks.create("buscar entradas")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url="https://entradas.com/")
    tasks._tasks[tid]["last_progress"] = time.time() - 400
    tasks.update_view(tid, url="https://entradas.com/musicals/el-rey-leon-madrid-1773394/")
    assert tasks.active_progress()[0]["stalled_s"] < 5


def test_and_so_does_a_reported_step():
    """A milestone is reported work, even if the URL does not change (filling in a form, opening a dropdown)."""
    tid = tasks.create("reservar mesa")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url=REAL_PAGE)
    tasks._tasks[tid]["last_progress"] = time.time() - 400
    tasks.add_event(tid, "📋 6 horarios encontrados")
    assert tasks.active_progress()[0]["stalled_s"] < 5


def test_a_task_that_just_started_is_not_stalled():
    """The limit that prevents this from degenerating into “everything is stalled”: a newly created task is at 0."""
    tid = tasks.create("buscar hotel")
    tasks.set_status(tid, "working")
    assert tasks.active_progress()[0]["stalled_s"] < 5


# ── the wall is SEEN on screen ─────────────────────────────────────────────────────────────────────────────
#
# Operator request (2026-08-19): “since we have a graphical frontend… we could show the browser image
# on screen and say “Booking has blocked me” and show a capture of what happened and tell it that you can’t
# continue.” A field that exists only in the registry is not that: the capture has been on disk from the start;
# what was missing was saying so and opening the card that displays it.
def test_hitting_a_wall_says_it_in_the_feed():
    tid = tasks.create("Reservar habitación")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url=BOOKING_WALL, page_title="Booking.com")
    feed = [e["text"] for e in tasks.get(tid)["events"]]
    assert any("no puedo seguir" in t for t in feed)
    assert any("anti-robot" in t for t in feed)


def test_and_the_spinner_stops():
    """Una ruleta girando sobre una página bloqueada es la pantalla diciendo «trabajando» mientras no se
    trabaja — justo la clase de estado que puede mentir."""
    tid = tasks.create("Reservar habitación")
    tasks.set_status(tid, "working")
    tasks.set_phase(tid, "conduciendo el navegador", True)
    tasks.update_view(tid, url=BOOKING_WALL)
    assert tasks.get(tid)["phase_active"] is False
    assert "anti-robot" in tasks.get(tid)["phase"]


def test_and_the_card_is_opened_so_the_capture_can_be_seen():
    from voice import observer
    shown = []
    _orig = observer.emit
    observer.emit = lambda kind, label, **kw: (shown.append((kind, label, kw.get("extra") or {}))
                                               if kind == "widget" else None)
    try:
        tid = tasks.create("Reservar habitación")
        tasks.set_status(tid, "working")
        tasks.update_view(tid, url=BOOKING_WALL)
    finally:
        observer.emit = _orig
    assert any(lbl == "show" and extra.get("id") == tasks.inst_id(tid) for _k, lbl, extra in shown)


def test_but_it_is_announced_ONCE_not_on_every_capture():
    """El hotel hizo 13 revisiones de captura sobre la MISMA página del muro. Un aviso por captura sería la
    app gritando trece veces lo mismo."""
    tid = tasks.create("Reservar habitación")
    tasks.set_status(tid, "working")
    for rev in range(1, 14):
        tasks.update_view(tid, url=BOOKING_WALL, shot_rev=rev)
    assert len([e for e in tasks.get(tid)["events"] if "⛔" in e["text"]]) == 1


def test_and_an_ordinary_page_announces_nothing():
    tid = tasks.create("Reservar mesa")
    tasks.set_status(tid, "working")
    tasks.set_phase(tid, "conduciendo el navegador", True)
    tasks.update_view(tid, url=REAL_PAGE)
    assert tasks.get(tid)["events"] == []
    assert tasks.get(tid)["phase_active"] is True


# ── the bridge must remain the bridge ─────────────────────────────────────────────────────────────────────
def test_the_bridge_route_still_points_at_the_bridge():
    """Caught in a live run, one day after `_with_wall` was added: the helper had been inserted BETWEEN
    `@router.post("/api/navegador/act")` and `navegador_act`, so FastAPI registered the annotator as the
    endpoint. It takes one dict and returns it unchanged, so the route answered 200 with the request echoed
    back — no `ok`, no `error` — and `cli.nav` turned that into «ERROR: desconocido» for every action a Brain
    Worker tried. Every unit test still passed: nothing here had ever asserted WHICH function the path
    resolves to, and a decorator does not care what follows it."""
    from widgets.navegador.act_api import router

    hit = [r for r in router.routes if getattr(r, "path", "") == "/api/navegador/act"]
    assert hit, "la ruta del puente del navegador desapareció"
    assert hit[0].endpoint.__name__ == "navegador_act"
    assert {"task_id", "action", "args"} <= set(hit[0].endpoint.__annotations__)


# ── V2-186: the stall must reach the WORKER too ───────────────────────────────────────────────────────────
#
# The wall traveled to the worker (`_with_wall`) but the stall did not, so the two halves of the same fact ended up
# in different places: the FlashBrain turn learned that a task had stopped moving, but the only part that could
# do anything about it did not.
#
# Measured in `find-theatre-tickets__es` (2026-08-20 01:01): the worker navigated SEVEN times, reached the
# event’s correct page at 00:40:32, then made FOURTEEN capture reviews of that same page with no further
# navigation for about twenty minutes. It was not blocked or stopped: it was looking at the same page repeatedly.
# Nothing returned from the bridge said «llevas un rato aquí», so inside the loop each `look` was as good as the first.
def test_the_worker_is_told_when_its_own_task_stopped_moving():
    from widgets.navegador import act_api

    tid = tasks.create("Entradas El Rey León")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url="https://www.entradas.com/teatro-musical/el-rey-leon-t3328")
    tasks._tasks[tid]["last_progress"] = time.time() - 1200
    out = act_api._with_stall(tid, {"url": "https://www.entradas.com/teatro-musical/el-rey-leon-t3328"})
    assert out["stalled_s"] >= 1200
    assert "sin avanzar" in out["hint"] and "extraes" in out["hint"]


def test_but_a_task_that_just_arrived_is_told_nothing():
    """The sensitivity check: without this, “report the stall” and “always report it” pass equally—and a warning
    on every `look` would be noise in the worker’s context at every step of normal navigation."""
    from widgets.navegador import act_api

    tid = tasks.create("Entradas El Rey León")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url="https://www.entradas.com/")
    out = act_api._with_stall(tid, {"url": "https://www.entradas.com/"})
    assert "hint" not in out and "stalled_s" not in out


def test_and_a_WALL_wins_over_the_stall():
    """A wall already has its own way out and is more specific; saying both at once gives the worker two different
    pieces of advice about the same screen."""
    from widgets.navegador import act_api

    tid = tasks.create("Reservar hotel")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url=BOOKING_WALL)
    tasks._tasks[tid]["last_progress"] = time.time() - 1200
    out = act_api._with_stall(tid, act_api._with_wall({"url": BOOKING_WALL}))
    assert out.get("wall") and "hint" not in out


def test_the_two_halves_share_ONE_threshold():
    """The failure this engine keeps repeating: two copies of the same threshold drifting apart. Both sides read
    the same environment variable."""
    from widgets.navegador import act_api

    from widgets.navegador import live_sheet
    assert act_api._STALL_HINT_S == live_sheet._STALLED_S


# ── V2-188: the site’s OWN error page is also a wall ───────────────────────────────────────────────────────
#
# `cancel-subscription-before-charge__es`, V2-176 ronda 3. La tarea acabó en
# `https://www.netflix.com/NotFound?prev=https%3A%2F%2Fwww.netflix.com%2Fes-es%2FContactUs` y zaelar le dijo al
# operador, dos veces, que «la página no se ha abierto del todo», y después que el login estaba listo para que
# metiera sus credenciales. El juez lo llamó gaslighting. No lo era: **nada en el estado decía que aquello era
# una página de error**, así que «aún cargando» era lo más razonable que le quedaba por decir.
#
# Es el muro más silencioso de todos porque el navegador lo reporta como una navegación PERFECTA — y lo es:
# status 200, host real, la página renderiza. Solo que no es la página.
NETFLIX_404 = "https://www.netflix.com/NotFound?prev=https%3A%2F%2Fwww.netflix.com%2Fes-es%2FContactUs"


def test_a_sites_own_error_page_is_a_wall():
    assert "error" in tasks.wall_reason(NETFLIX_404)
    assert tasks.wall_reason("https://x.com/404")
    assert tasks.wall_reason("https://x.com/es/page-not-found")


def test_but_matched_as_a_whole_path_SEGMENT_and_never_as_a_substring():
    """“/notfound” is an error page; “404 ways to cook eggs” is not. The query is deliberately excluded: the
    measured URL carries `?prev=https://www.netflix.com/es-es/ContactUs`, so searching the full URL would trigger
    on the GOOD page it came from."""
    assert tasks.wall_reason("https://www.recetas.com/articles/404-ways-to-cook-eggs") == ""
    assert tasks.wall_reason("https://www.netflix.com/es-es/ContactUs") == ""
    assert tasks.wall_reason("https://www.thefork.es/restaurantes/madrid") == ""


# ── V2-176 round 3: waiting for HIM to sign in is the closest thing to a wall ─────────────────────────────
#
# El paraguas lo nombra como el frente más prometedor: «esto necesita tu cuenta, no puedo seguir» es una
# respuesta EXCELENTE, y hoy el agente prefiere inventarse el login. La pieza que faltaba no era detectarlo
# —`awaiting_login` existe, lo escribe el flujo de login real y `active_progress()` lo expone desde V2-167—
# sino que **`prompt.py` no lo leía nunca**. Así que una tarea parada en el login convivía con «Esa tarea
# sigue viva y te dará el resultado sola»: el operador esperando a la tarea, y la tarea esperándole a él.
#
# Es el mismo fallo que V2-185 con la salida cambiada: aquí no hay que ofrecer otro sitio ni dejarlo — hay que
# decirle que entre.
def _awaiting(tid):
    tasks._tasks[tid]["awaiting_login"] = True


def test_and_the_seam_carries_the_fact():
    """`active_progress()` es el sitio por el que la tarea le habla al turno; el dato no existía ahí, así que
    el turno solo podía elegir entre «sigue viva» y «está bloqueada»."""
    tid = tasks.create("Buscar hotel")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url=REAL_PAGE)
    assert tasks.active_progress()[0]["has_results"] is False
    tasks.set_results(tid, {"items": [1]})
    assert tasks.active_progress()[0]["has_results"] is True


# ── V2-193: con varias tareas vivas, el imperativo tiene que decir CUÁL ───────────────────────────────────
#
# `renew-gym-membership__es`, 2026-08-20 02:28: «desviaciones de atención severas (distracción con tareas de
# navegador no solicitadas) … mezclando dominios (Netflix/Teatro) al preguntar por el gimnasio».
#
# El bloque listaba las tres tareas correctamente y luego soltaba UN imperativo que empezaba por «ESA TAREA»
# — sin decir cuál. Con tres en marcha eso apunta a cualquiera, y el estado acababa MANDANDO entregar los
# resultados del teatro mientras el operador preguntaba por su gimnasio. Con una sola tarea la ambigüedad no
# existe, que es por lo que las cuatro caras se escribieron sin verla.
def _three_live():
    a = tasks.create("Cancelar la suscripción a Netflix")
    tasks.set_status(a, "working")
    tasks.update_view(a, url="https://www.netflix.com/login")
    tasks._tasks[a]["awaiting_login"] = True
    b = tasks.create("Entradas El Rey León")
    tasks.set_status(b, "working")
    tasks.update_view(b, url="https://www.entradas.com/el-rey-leon")
    tasks.set_results(b, {"items": [1]})
    c = tasks.create("Renovar cuota del gimnasio")
    tasks.set_status(c, "working")
    return a, b, c


# ── V2-200: la cara «ya encontró algo» estaba atada a un campo que nunca es cierto en vivo ────────────────
#
# V2-192 la ató a `results` de la propia tarea. Pero los TRES sitios que llaman a `set_results()` llaman a
# `finish()` acto seguido —`owner.py:660`, `dispatch._finalize_web`, `web_cc`— así que **una tarea ACTIVA con
# resultados no existe en producción**. Sus cuatro tests pasaban porque creaban ese estado a mano.
#
# Es el mismo fallo de V2-199 encontrado con el mismo método —comprobar contra el camino real en vez de contra
# el que uno imaginó— y esta vez el arreglo anterior no estaba roto: estaba MUERTO.
#
# La señal viva de que el worker ya encontró algo sí existe, en el otro registro: la amplitud que él mismo
# reporta (`hbnote considered --kept N`), leída por el seam que ya enlazaba los dos (`record_by_nav_task`).
def _worker_on(nav_tid, *, kept=0):
    from nucleo import dispatch as _d

    rec = _d.SessionRecord(task_id="w9", goal="x", kind="web")
    rec.status, rec.nav_task = "running", nav_tid
    _d._SESSIONS["w9"] = rec
    if kept:
        _d.session_considered("w9", considered=kept * 4, kept=kept)
    return _d


# ── el muro que vive en el CUERPO, no en la URL (V2-167, segunda mitad) ────────────────────────────────────
# Medido en una corrida REAL del caso del teatro el 2026-08-19: `entradas.com` contestó la página del evento
# con un «Access Denied» de detección de bots de Akamai. URL normal, status normal, `wall_reason()` ciego. El
# worker lo leyó del snapshot y se re-enrutó solo —así que la tarea NO se atascó— y por eso el agujero llevaba
# invisible: la única prueba de que existía era que el operador no vio nada.
#
# El texto de abajo es la forma de esa página (214 caracteres), no un ejemplo inventado.
AKAMAI_DENIED = ("Access Denied\n\nYou don't have permission to access \"http://www.entradas.com/teatro-musical/"
                 "el-rey-leon-t3328\" on this server.\n\nReference #18.5c7d4f17.1787159442.2b1e9c3\n\n"
                 "https://errors.edgesuite.net/18.5c7d4f17.1787159442.2b1e9c3")
CLOUDFLARE_WAIT = ("Just a moment...\n\nChecking your browser before accessing entradas.com.\n\n"
                   "Please enable JavaScript and cookies to continue.\n\nRay ID: 8f2a1c9d4e7b")


def test_the_body_served_wall_that_was_measured_is_recognised():
    assert tasks.body_wall_reason(AKAMAI_DENIED)
    assert tasks.body_wall_reason(CLOUDFLARE_WAIT)


def test_the_url_of_that_same_page_says_nothing():
    """Es la razón de existir de esta mitad: la URL del muro medido es una URL perfectamente buena, y el
    predicado de URL tiene razón en callarse. Si algún día `wall_reason` empezara a acertar aquí, sería porque
    alguien la ensanchó para leer texto — que es justo lo que este módulo decidió no hacer."""
    assert tasks.wall_reason("https://www.entradas.com/teatro-musical/el-rey-leon-t3328") == ""


def test_a_long_page_that_merely_TALKS_about_being_blocked_is_not_a_wall():
    """El riesgo que V2-167 dejó escrito: «no declarar muro sobre cualquier página que mencione la palabra».
    La defensa es la LONGITUD, así que hay que probarla con un artículo de verdad, largo y con la aguja
    dentro."""
    article = ("Cómo evitar que te bloqueen al comprar entradas online. " * 40
               + " Muchos usuarios reciben un Access Denied o un mensaje de unusual traffic al intentar "
                 "comprar, y algunas webs piden resolver un captcha. " + "Sigue leyendo. " * 40)
    assert len(article) > tasks.WALL_BODY_MAX_CHARS
    assert tasks.body_wall_reason(article) == ""


def test_an_ordinary_short_page_is_not_a_wall_either():
    assert tasks.body_wall_reason("") == ""
    assert tasks.body_wall_reason("El Rey León · Teatro Lope de Vega, Madrid · Sábado 20:30 · Desde 39 €") == ""
    assert tasks.body_wall_reason("Casa Lucio. Reserva tu mesa. Cava Baja 35, Madrid.") == ""


def test_the_body_reason_is_also_said_in_words_the_operator_can_hear():
    for text in (AKAMAI_DENIED, CLOUDFLARE_WAIT):
        reason = tasks.body_wall_reason(text)
        assert "Reference #" not in reason and "Ray ID" not in reason and "http" not in reason
        assert len(reason.split()) >= 3


def test_the_task_carries_a_body_served_wall_like_any_other():
    """La prueba que importa: el estado del turno tiene que enterarse. Antes de esto la app no se abría y
    el operador no veía nada, aunque el worker sí lo supiera."""
    tid = tasks.create("conseguir entradas para El Rey León")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url="https://www.entradas.com/teatro-musical/el-rey-leon-t3328",
                      page_title="Access Denied", page_text=AKAMAI_DENIED)
    assert tasks.active_progress()[0]["wall"]


def test_and_it_drops_the_wall_when_the_next_page_is_real():
    tid = tasks.create("conseguir entradas")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url="https://www.entradas.com/teatro-musical/el-rey-leon-t3328",
                      page_text=AKAMAI_DENIED)
    assert tasks.active_progress()[0]["wall"]
    tasks.update_view(tid, url="https://www.ticketmaster.es/artist/el-rey-leon-entradas/4043",
                      page_text="El Rey León. Teatro Lope de Vega. Entradas desde 39 €.")
    assert tasks.active_progress()[0]["wall"] == ""


def test_a_caller_that_has_no_text_keeps_the_url_only_behaviour():
    """Nadie más que la pestaña tiene el cuerpo. Omitir el texto no puede cambiar nada de lo que ya funcionaba,
    ni borrar un muro que la URL sí ve."""
    tid = tasks.create("reservar hotel")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url=BOOKING_WALL)
    tid2 = tasks.create("otra")
    tasks.set_status(tid2, "working")
    tasks.update_view(tid2, url=REAL_PAGE)
    walls = {r["id"]: r["wall"] for r in tasks.active_progress(limit=9)}
    assert walls[tid], "un muro que la URL ve no puede depender de que le pasen texto"
    assert walls[tid2] == ""


def test_the_peek_size_is_bigger_than_the_gate_that_judges_it():
    """El trampa silenciosa de este arreglo, y la única que invierte la defensa: si quien lee el cuerpo corta
    justo en el límite, un artículo de 50k llega «corto» y la puerta de longitud pasa TODAS las páginas. Por eso
    el tamaño de lectura vive aquí y no en el llamante."""
    assert tasks.WALL_BODY_PEEK_CHARS > tasks.WALL_BODY_MAX_CHARS
    long_article = "Access Denied. " + ("texto de relleno de un artículo real. " * 400)
    truncated_correctly = long_article[:tasks.WALL_BODY_PEEK_CHARS]
    assert tasks.body_wall_reason(truncated_correctly) == ""


# ── un muro GOLPEADO deja rastro, aunque el worker se re-enrute (V2-176, medido 2026-08-20 12:39) ────────────
#
# La primera medición del detector de muro del cuerpo salió a medias, y de la mejor manera posible: el juez cita
# TEXTUALMENTE la cadena que produce este módulo — «cuando `phase` indique *el sitio bloqueó el acceso*» — o sea
# que disparó en producción. Y aun así zaelar pasó DIEZ turnos diciendo «sigue sin dar señal de dónde está».
#
# La causa: `wall` se recalcula en cada `update_view`, así que describe la página donde está la pestaña AHORA. El
# worker se topó con el bloqueo, se re-enrutó a `elcorteingles.es` —que es lo correcto— y el hecho se borró con
# la siguiente captura. El obstáculo había ocurrido, ya no lo veía nadie, y al operador no se le dijo.
#
# Octava vez del mismo patrón en esta tanda, y la primera sobre un arreglo propio: un hecho que solo vive un
# turno es un hecho que la conversación pierde.
ACCESS_DENIED = ("Access Denied\n\nYou don't have permission to access this server.\n\nReference #18.5c7d")


def test_the_wall_survives_the_worker_moving_on():
    tid = tasks.create("conseguir entradas para El Rey León")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url="https://www.entradas.com/el-rey-leon", page_text=ACCESS_DENIED)
    tasks.update_view(tid, url="https://www.elcorteingles.es/entradas/search/?Ntt=El+Rey+Leon")
    row = tasks.active_progress()[0]
    assert row["wall"] == "", "la página actual no es un muro y no debe decir que lo es"
    assert row["walls_hit"] == 1, "el bloqueo ocurrió y ya no lo sabe nadie"


def test_and_it_remembers_WHICH_SITE_blocked_it():
    """«Me bloquearon» es un hecho; «me bloqueó entradas.com» es uno con el que el operador puede hacer algo."""
    tid = tasks.create("conseguir entradas")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url="https://www.entradas.com/el-rey-leon", page_text=ACCESS_DENIED)
    tasks.update_view(tid, url="https://www.elcorteingles.es/x")
    last = tasks.active_progress()[0]["last_wall"]
    assert last["site"] == "entradas.com"
    assert "robot" in last["reason"]


def test_the_site_is_a_HOST_not_a_url():
    """Se lee en voz alta: una query string entera es ruido."""
    assert tasks.host_of("https://www.entradas.com/teatro/x?Ntt=El+Rey+Le%C3%B3n&p=2") == "entradas.com"
    assert tasks.host_of("https://elcorteingles.es/") == "elcorteingles.es"
    assert tasks.host_of("") == ""
    assert tasks.host_of("no-es-una-url") == ""


def test_several_blocks_are_counted_and_bounded():
    """«Esto me pasa en todas partes» es una conclusión distinta de «me pasó una vez», y el operador la merece.
    Acotado para que un bucle no haga crecer la tarea sin techo."""
    tid = tasks.create("conseguir entradas")
    tasks.set_status(tid, "working")
    for i in range(tasks._MAX_WALLS + 4):
        tasks.update_view(tid, url=f"https://sitio{i}.test/x", page_text=ACCESS_DENIED)
        tasks.update_view(tid, url=f"https://sitio{i}.test/ok", page_text="entradas y horarios")
    assert tasks.active_progress()[0]["walls_hit"] == tasks._MAX_WALLS


def test_a_task_that_never_hit_one_says_nothing():
    """La otra mitad: sin esto, «recordar los bloqueos» y «decir que hubo bloqueos siempre» pasan el mismo test."""
    tid = tasks.create("reservar mesa")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url=REAL_PAGE, page_text="Casa Lucio · reserva tu mesa")
    row = tasks.active_progress()[0]
    assert row["walls_hit"] == 0 and row["last_wall"] == {}


def test_the_same_wall_twice_in_a_row_is_not_two_blocks():
    """`update_view` se llama en cada captura; sin la comparación con el muro anterior, quedarse mirando la misma
    página de bloqueo contaría decenas."""
    tid = tasks.create("conseguir entradas")
    tasks.set_status(tid, "working")
    for _ in range(5):
        tasks.update_view(tid, url="https://www.entradas.com/x", page_text=ACCESS_DENIED)
    assert tasks.active_progress()[0]["walls_hit"] == 1


# ── V2-352: the DataDome-style Spanish block, measured live on coches.net (2026-08-27) ──────────────────────
# HTTP 403, SAME url, body «…nos hizo pensar que eres un bot» — no needle covered that phrasing, so the wall
# was eaten in silence: round 14 burned 7 navigations and 189 s before the worker deduced the block from
# screenshots, and the sheet ended with 0 items.
COCHESNET_BOT = ("Coches.net Ups! Parece que algo no va bien... Algo en tu navegador nos hizo pensar que "
                 "eres un bot. Hay algunas razones por las que esto podría suceder: Estás utilizando una VPN o "
                 "un proxy. Comprueba tu conexión y vuelve a intentarlo.")


def test_the_coches_net_bot_block_is_a_wall():
    got = tasks.body_wall_reason(COCHESNET_BOT)
    assert got == "el sitio bloqueó el acceso (te tomó por un robot)", got


def test_an_article_discussing_bots_is_still_not_a_wall():
    # the length gate keeps protecting: prose ABOUT bot detection is content, not a block
    article = ("Los sistemas anti-bot modernos analizan tu navegador y a veces deciden que eres un bot "
               "aunque seas humano. " * 30)
    assert len(article) > 1200 and tasks.body_wall_reason(article) == ""


# ── V2-358: the wall signal no needle can miss — the HTTP status ────────────────────────────────────────────
# Measured on coches.net (2026-08-27): the SAME 403 arrives with two different bodies — «…eres un bot»
# (V2-352's needle) and a bare «Ups! Parece que algo no va bien…» (caught by nothing). Round 08:03: the worker
# re-tried the identical URL four times, no wall, no alternatives, sheet 0.


def test_a_403_is_a_wall_whatever_the_page_says():
    assert tasks.status_wall_reason(403) == "el sitio nos ha bloqueado el acceso (respuesta 403)"
    assert tasks.status_wall_reason(429) == "el sitio cortó por exceso de peticiones (respuesta 429)"


def test_an_ordinary_or_merely_broken_status_is_not_a_block():
    # 404 is the error-path segments' business; 500 is the site failing, not refusing us
    assert tasks.status_wall_reason(200) == "" and tasks.status_wall_reason(0) == ""
    assert tasks.status_wall_reason(404) == "" and tasks.status_wall_reason(500) == ""


def test_the_status_reaches_the_wall_through_update_view():
    tid = tasks.create("probar el muro por status")
    tasks.set_status(tid, "working")
    # the «Ups!» variant: ordinary URL, harmless words, 403 underneath
    tasks.update_view(tid, url="https://www.coches.net/segunda-mano/?priceMax=12000",
                      page_title="Ups! Parece que algo no va bien...",
                      page_text="Ups! Parece que algo no va bien... Comprueba tu conexión.", status=403)
    t = tasks.get(tid) or {}
    assert t.get("wall") == "el sitio nos ha bloqueado el acceso (respuesta 403)", t.get("wall")
    assert (t.get("walls") or []), "el muro golpeado tiene que dejar rastro"
    # …and a healthy page afterwards clears the live wall (history stays)
    tasks.update_view(tid, url="https://www.autoscout24.es/lst", page_title="AutoScout24",
                      page_text="Coches de segunda mano", status=200)
    assert (tasks.get(tid) or {}).get("wall") == ""


# ── V2-470: a wall the TASK knows reaches the worker, and a wall STREAK switches the CHANNEL ────────────────
# Measured in `cheapest-monitor__us` round 11 (2026-08-29 01:01, session a96c429b): the task recorded 403
# walls on amazon, bestbuy, bhphotovideo and dell — 15 wall mentions in the log — while the act responses
# carried exactly ONE «MURO» line (the google /sorry URL): `_with_wall` only sniffed the URL, so every
# status/body-detected wall died server-side. The worker burned 28 navigations pivoting from walled site to
# walled site, having `web_search` available the whole time, and the sheet ended with 0 rows.


def test_a_status_wall_reaches_the_act_response():
    from widgets.navegador import act_api
    tid = tasks.create("probar que el muro por status viaja")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url="https://www.amazon.com/dp/B0TEST", page_title="403 Forbidden",
                      page_text="Forbidden", status=403)
    snap = act_api._with_wall({"url": "https://www.amazon.com/dp/B0TEST", "title": "403 Forbidden"}, tid)
    assert snap.get("wall") == "el sitio nos ha bloqueado el acceso (respuesta 403)", snap.get("wall")


def test_walls_on_two_hosts_escalate_to_a_channel_switch():
    from widgets.navegador import act_api
    tid = tasks.create("probar la racha de muros")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url="https://www.amazon.com/dp/B0TEST", page_title="403", page_text="x", status=403)
    tasks.update_view(tid, url="https://www.bhphotovideo.com/c/product/1", page_title="403", page_text="x",
                      status=403)
    snap = act_api._with_wall({"url": "https://www.bhphotovideo.com/c/product/1", "title": "403"}, tid)
    streak = snap.get("wall_streak") or {}
    assert streak.get("n", 0) >= 2, snap
    assert {"amazon.com", "bhphotovideo.com"} <= set(streak.get("sites") or []), streak
    # one walled host is a site problem, not a channel problem — no escalation
    tid2 = tasks.create("un solo host no es racha")
    tasks.set_status(tid2, "working")
    tasks.update_view(tid2, url="https://www.amazon.com/dp/1", page_title="403", page_text="x", status=403)
    tasks.update_view(tid2, url="https://www.amazon.com/dp/2", page_title="403", page_text="x", status=403)
    snap2 = act_api._with_wall({"url": "https://www.amazon.com/dp/2", "title": "403"}, tid2)
    assert not snap2.get("wall_streak"), snap2


def test_the_streak_tells_the_worker_to_change_channel(capsys):
    from nucleo.cli import nav as nav_cli
    nav_cli._print_state({"ok": True, "url": "https://www.bhphotovideo.com/c/1", "title": "403",
                          "wall": "el sitio nos ha bloqueado el acceso (respuesta 403)",
                          "wall_streak": {"n": 3, "sites": ["amazon.com", "bhphotovideo.com"]}})
    out = capsys.readouterr().out
    assert "web_search" in out, out
    assert "cli.bridge" in out, "the instruction names the bridge, not just the tool"
    assert "amazon.com" in out and "bhphotovideo.com" in out, "the streak names the walled sites"
