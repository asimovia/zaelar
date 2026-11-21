"""Linking a contacts source IS the ask: there is no switch for what comes in (2026-11-21, superseding 2026-10-04).

The operator: connecting a source (Google, WhatsApp, Telegram…) imports at once and keeps the inbound sync on by
default; no «Import contacts» button and no box to turn the inbound half on or off. What stays is ONE button that
sends what he changed here TO Google. (2026-10-04 had made every import wait to be asked: after a reset the
directory stayed empty while Telegram and WhatsApp refilled it and Google never did.)
"""
from __future__ import annotations

import json
from pathlib import Path


def test_the_google_sync_state_has_no_inbound_switch():
    from widgets.contactos import gcontacts
    assert "auto" not in gcontacts.sync_state({})


def test_the_card_declares_no_import_action_and_no_switch():
    actions = json.loads((Path(__file__).resolve().parents[4] / "widgets/contactos/manifest.json").read_text())["actions"]
    assert "sync_source" not in actions and "set_auto" not in actions and "sync_contacts" in actions
