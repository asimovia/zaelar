"""Every «¿lo hago?» the agent asks can be answered in words — typed or said — not only with the button
(operator, 2026-09-28: «sí, te autorizo» has to send it for real).

Two readers: a reply that IS the declared yes/no is resolved before the model (`consent_ask.declared_answer`, V2-878
§4b), the brief's pick reads any other wording; anything else — «acepto que lo
envíes», another language — reaches the model with the tool that resolves the pending confirmation. That tool was
described as resolving a DELETION only, so over a pending SEND the model had no reason to reach for it."""
from nucleo.flash import router, router_catalog
from widgets import confirm


def test_the_declared_answers_resolve_before_the_model(monkeypatch):
    from nucleo.request import consent_ask
    for lang, yes, no in (("en", "Yes", "no"), ("es", "sí", "No.")):
        monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
        assert consent_ask.declared_answer(yes) == "yes" and consent_ask.declared_answer(no) == "no", lang
        assert consent_ask.declared_answer("sí, te autorizo") is None      # the brief's pick reads a longer one


def test_the_tool_is_offered_whenever_something_waits_for_his_yes():
    names = lambda ctx: {t["function"]["name"] for t in router.tools(ctx)}  # noqa: E731
    assert "confirm_widget_delete" in names(router.tool_context(confirm_pending=True, auth_pending=False))
    assert "confirm_widget_delete" not in names(router.tool_context(confirm_pending=False, auth_pending=False))


def test_the_tool_says_it_resolves_any_pending_confirmation_not_only_a_deletion():
    spec = next(t for t in router_catalog.TOOLS if t["function"]["name"] == "confirm_widget_delete")
    desc = spec["function"]["description"]
    assert "ENVIAR un mensaje" in desc and "CUALQUIER" in desc and "borrado pendiente" not in desc
