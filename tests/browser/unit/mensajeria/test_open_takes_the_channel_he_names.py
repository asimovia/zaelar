"""«Abre <persona>» on the card that holds her mail AND her chat (desktop, 2026-11-14, failure 14).

He asked for a person's MESSAGE; `open {name}` resolved the first conversation on screen with that name — her mail —
and the turn said «Hecho.» with nothing declared to check it («sin condición declarada»). Two pieces:

  · a channel he NAMES travels as `platform` and bounds the resolution (ES «el WhatsApp de Anna», EN «Anna's
    WhatsApp»); with none named, what is on screen still wins, as before;
  · `open` declares its end state: the thread the card REPORTS open carries the name asked (and the channel named),
    so «done» is said only over a checked end state.

Disarm: drop the `platform` bound in `_find_chat_by_name` → the mail opens again (red).
"""
import time

import pytest

ANNA_MAIL = "anna@example.org"
ANNA_WA = "34600000001@s.whatsapp.net"


@pytest.fixture
def md(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.mensajeria import data
    now = time.time()
    db = data.load_db()
    db["items"] = [{"n": 1, "platform": "email", "chatId": ANNA_MAIL, "name": "Anna Lopez", "text": "[Asunto: Factura]",
                    "ts": now - 30, "messageId": "m1"},
                   {"n": 2, "platform": "whatsapp", "chatId": ANNA_WA, "name": "Anna Lopez", "text": "¿Quedamos?",
                    "ts": now - 60, "messageId": "w1"}]
    db["threads"] = {f"email|{ANNA_MAIL}": {"name": "Anna Lopez", "msgs": [
                         {"id": "m1", "dir": "in", "who": "Anna Lopez", "body": "Factura", "ts": now - 30}]},
                     f"whatsapp|{ANNA_WA}": {"name": "Anna Lopez", "msgs": [
                         {"id": "w1", "dir": "in", "who": "Anna Lopez", "body": "¿Quedamos?", "ts": now - 60}]}}
    data.store.save(data.WIDGET_ID, db)
    return data


@pytest.mark.parametrize("said", ["whatsapp", "WhatsApp", "wasap"])
def test_the_channel_he_names_opens_that_conversation(md, said):
    md.apply_action("open", {"name": "Anna", "platform": said})
    assert md.load_db()["active_chat"] == {"platform": "whatsapp", "chatId": ANNA_WA}


@pytest.mark.parametrize("said", ["email", "correo", "mail"])
def test_the_mail_he_names_opens_the_mail(md, said):
    md.apply_action("open", {"name": "Anna", "platform": said})
    assert md.load_db()["active_chat"] == {"platform": "email", "chatId": ANNA_MAIL}


def test_with_no_channel_named_what_is_on_screen_first_still_wins(md):
    md.apply_action("open", {"name": "Anna"})
    assert md.load_db()["active_chat"]["platform"] == "email"


def test_open_declares_its_end_state_over_what_the_card_reports():
    from nucleo.circuit import spec
    got = spec.render("mensajeria", "open", {"name": "Anna", "platform": "whatsapp"})
    clauses = got["all"]
    assert {"widget": "mensajeria", "field": "report.thread_open", "has": "Anna"} in clauses
    assert {"widget": "mensajeria", "field": "report.thread_open", "has": "whatsapp"} in clauses
    assert spec.render("mensajeria", "open", {"n": 2}) is None, "by number: nothing named to check, unverifiable"


def test_the_model_is_shown_the_channel_field_with_the_apps_own_channels():
    """Sandbox 2026-11-14, ES and EN: «abre el whatsapp de Anna» / «open Anna's whatsapp» → `open {name: Anna}` → her
    mail. The field existed, but an on-screen card shows the model only the keys of acts that declare `how`, and `open`
    declared none — the model never saw `platform`. Now `open` declares it, and its channels are the app's own
    (`data._PLATFORMS`), never a list written twice. Disarm: drop `how` from `open` → `platform` vanishes → red."""
    import json
    from pathlib import Path
    from widgets import brief
    from widgets.mensajeria import data
    man = json.loads((Path(data.__file__).parent / "manifest.json").read_text(encoding="utf-8"))
    acts = man["actions"]
    line = brief._payload_keys(acts)
    assert "open: name·n·platform" in line, line
    said = {c.strip() for c in acts["open"]["payload"]["platform"].split("—")[0].split("|")}
    assert said == set(data._PLATFORMS), (said, data._PLATFORMS)
