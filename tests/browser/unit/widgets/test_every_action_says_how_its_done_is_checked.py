"""Every action a card declares says how its «done» is checked: a `done_when` (its end state, judged by the circuit) or
an explicit `instant` with its reason (the op's own answer IS the end state: a view, the card's bookkeeping).

Desktop, 2026-11-14: `mensajeria:open` declared nothing, the circuit logged «sin condición declarada» and the turn said
«Hecho.» anyway. «Done» stands only on a checked end state, so an action with neither is refused here — for EVERY card,
every action, every manifest. The actions found undeclared on 2026-11-14 are listed in `_UNDECLARED`: the list only
SHRINKS (a listed action that now declares one fails until it leaves the list), and nothing new may join it.

Disarm: drop the `instant` of any view in a manifest → that action is undeclared and not listed → red.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[4]

#: Undeclared on 2026-11-14, the debt this guard was born with. Shrinks only (V2-903, «Session 2026-11-14 fixes»).
_UNDECLARED: dict[str, set[str]] = {
    "agenda": {"add_reminder", "dedupe_meetings", "restore_meeting", "done", "drop", "snooze", "not_now", "drop_project", "clear_all", "clear_range", "invite", "accept_proposal", "decline_proposal", "rsvp_meeting", "set_default_calendar", "update_task", "delete_task", "restore", "add_list", "rename_list", "clear_list", "delete_list"},
    "archivos": {"copy_file", "torrent_save", "torrent_remove", "torrent_poll"},
    "contactos": {"restore_contact", "set_favorite", "set_flag", "link_contact", "sync_source", "set_alias", "hide_contact", "set_auto", "add_phone", "add_email", "rename_group", "delete_group", "add_to_group", "set_agent"},
    "fotos": {"label_batch"},
    "imagenes": {"slideshow_stop", "clear", "wallpaper_clear"},
    "map": {"clear"},
    "mensajeria": {"read", "unread", "readchat", "dismiss", "clear", "archive", "trash", "hide", "unhide", "draft", "cancel_send", "create_group", "set_notify", "load_more", "chats_more", "set_media_days", "set_signature", "set_signature_line", "clear_signature", "fetch_now", "set_autoresponder", "clear_autoresponder", "chat_digest", "mail_sort", "mail_more", "discard_draft"},
    "musica": {"favorite_current", "remove_from_playlist", "rename_playlist", "delete_playlist", "move_track", "release", "next", "seek", "previous", "volume_up", "volume_down", "set_volume", "queue", "queue_remove", "queue_move", "queue_clear", "shuffle", "repeat", "refresh"},
    "navegador": {"close", "scroll", "click", "type", "press", "automate"},
    "results": {"present", "append", "sources", "rejected", "progress", "criteria", "auth_done"},
    "timer": {"start", "pause", "reset"},
    "youtube": {"add", "ended", "remove", "move", "sort_list", "filter_list", "clear_list", "sync_platforms", "block_channel", "unblock_channel", "name_list", "captions_on", "captions_off", "restart", "clear_history", "follow_channel", "unfollow_channel", "channel_videos", "open_channel", "channel_tab", "close_channel", "refresh_channel", "channel_more", "channel_playlist", "sync_channels", "save_list", "open_list", "delete_list", "set_preference", "clear_preference", "add_results", "queue_search", "clear_search"}
}


def _actions():
    for p in sorted((ENGINE / "widgets").glob("*/manifest.json")):
        if p.parent.name.startswith(("_", ".")):
            continue
        for name, spec in ((json.loads(p.read_text(encoding="utf-8")).get("actions") or {}).items()):
            if isinstance(spec, dict):
                yield p.parent.name, name, spec


_ALL = list(_actions())


@pytest.mark.parametrize("wid,action,spec", _ALL, ids=[f"{w}:{a}" for w, a, _s in _ALL])
def test_every_action_says_how_its_done_is_checked(wid, action, spec):
    instant = spec.get("instant")
    if "instant" in spec:
        assert isinstance(instant, str) and instant.strip(), f"{wid}:{action} — `instant` needs its reason, as a sentence"
    declared = "done_when" in spec or "instant" in spec
    listed = action in _UNDECLARED.get(wid, set())
    if declared:
        assert not listed, f"{wid}:{action} now declares how its done is checked — take it off `_UNDECLARED`"
    else:
        assert listed, (f"{wid}:{action} says «done» with nothing to check it: declare `done_when` (its end state) or "
                        f"`instant: \"<why the op's answer is the end state>\"`")


def test_the_debt_names_only_actions_that_exist():
    real = {(w, a) for w, a, _s in _ALL}
    gone = sorted((w, a) for w, acts in _UNDECLARED.items() for a in acts if (w, a) not in real)
    assert not gone, f"listed actions no manifest declares any more — take them off: {gone}"
