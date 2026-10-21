"""Errors and account pages shown VERBATIM speak the instance language.

Install errors from the wizard, vault errors, the daemon's "never reached it" codes, the OAuth result pages
and the connector labels / "why not" tooltips all reached the screen as hardcoded Spanish, whatever language
the instance ran in — and the OAuth pages declared `<html lang='es'>` on top. Every one of them now resolves
through pack `ui` (`i18n.runtime.text`): the active language first, English when that language has no
string, and the page declares the ACTIVE code.

The variants are deliberate: Spanish (a preset pack), and a third language with no generated pack, which
must fall back to English — never to Spanish, and never to the raw key.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[4]
GENESIS = ENGINE / "i18n" / "genesis"


@pytest.fixture
def lang(monkeypatch):
    from i18n import runtime as _rt

    def _set(code: str) -> None:
        monkeypatch.setenv("ZAELAR_LANGUAGE", code)
        _rt.invalidate()
    yield _set
    _rt.invalidate()


def _vault_error(passphrase: str = "ab") -> str:
    from memory import vault
    with pytest.raises(vault.VaultError) as e:
        vault.create(passphrase)
    return str(e.value)


def test_a_vault_error_falls_back_to_english_in_a_language_without_a_pack(lang):
    lang("sw")
    assert _vault_error() == "The passphrase must be at least 4 characters long"


def test_a_vault_error_is_spanish_in_spanish(lang):
    lang("es")
    assert _vault_error() == "la passphrase debe tener al menos 4 caracteres"


def test_a_wizard_install_error_names_the_installer_in_the_instance_language(lang):
    from server import wizard_api
    lang("sw")
    en = asyncio.run(wizard_api.install(id="no-such-installer", model=""))
    lang("es")
    es = asyncio.run(wizard_api.install(id="no-such-installer", model=""))
    assert en == {"ok": False, "error": "unknown installer: no-such-installer"}
    assert es == {"ok": False, "error": "instalador desconocido: no-such-installer"}


@pytest.mark.parametrize("code, failed, done", [
    ("sw", "Could not connect", "You can go back to your zaelar card."),
    ("es", "No se pudo conectar", "Ya puedes volver a la tarjeta de zaelar."),
])
def test_the_oauth_page_carries_the_active_language(lang, code, failed, done):
    from connectors import oauth_callback
    lang(code)
    bad = oauth_callback.page(False, "boom", family="agenda")
    good = oauth_callback.page(True, "", family="agenda", label="Google Calendar")
    for page in (bad, good):
        assert f"<html lang='{code}'>" in page
    assert failed in bad and "boom" in bad
    assert done in good


def test_the_spotify_page_carries_the_active_language_and_escapes_the_detail(lang):
    from server import spotify_api
    lang("sw")
    page = spotify_api._page(False, "<script>x</script>")
    assert "<html lang='sw'>" in page and "Could not connect" in page
    assert "<script>x</script>" not in page          # the provider's error param is never markup


def test_a_connector_label_follows_the_instance_language(lang):
    from connectors import registry
    lang("sw")
    assert registry._label("youtube-audio", "?") == "YouTube (free audio)"
    lang("es")
    assert registry._label("youtube-audio", "?") == "YouTube (audio gratis)"


def test_every_impossible_connector_and_daemon_code_has_a_sentence_in_both_presets():
    en = json.loads((GENESIS / "en" / "ui.json").read_text(encoding="utf-8"))
    es = json.loads((GENESIS / "es" / "ui.json").read_text(encoding="utf-8"))
    keys = [f"daemon.err.{c}" for c in ("not_installed", "not_running", "no_daemon_from_cloud")]
    for f in sorted((ENGINE / "connectors" / "catalog").glob("*.json")):
        m = json.loads(f.read_text(encoding="utf-8"))
        if m.get("state") == "not-possible":
            keys.append(f"connectors.{m['id']}.why_not")
    missing = [(lng, k) for k in keys for lng, d in (("en", en), ("es", es)) if not str(d.get(k) or "").strip()]
    assert not missing, missing
