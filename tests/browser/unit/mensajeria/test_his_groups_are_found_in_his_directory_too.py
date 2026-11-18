"""V2-938 — «leave these two groups» finds them among ALL his groups: the messaging card's chat list AND the groups his
directory holds (a linked source feeds them). Measured in the sandbox replay of his session (2026-11-18): the chat list
had never been opened, the directory held both, and the act refused «not in your list of groups»."""
from __future__ import annotations


def test_a_group_only_the_directory_holds_is_found(monkeypatch):
    from widgets import directory
    from widgets.mensajeria import data  # noqa: F401 — the card first (its actions import it back)
    from widgets.mensajeria.actions import leave
    rows = [{"id": "g1", "name": "Book club", "kind": "group", "subtype": "group",
             "channels": [{"platform": "whatsapp", "chatId": "120363000000000101@g.us"}]},
            {"id": "p1", "name": "Odile Marsh", "kind": "person", "channels": [{"platform": "whatsapp", "chatId": "x"}]}]
    monkeypatch.setattr(directory, "_contacts", lambda: rows)
    found, refusal = leave.resolve({}, {"groups": ["Book club"]})
    assert refusal is None and found == [{"platform": "whatsapp", "chatId": "120363000000000101@g.us", "name": "Book club"}]
    _f, refused = leave.resolve({}, {"groups": ["Odile Marsh"]})
    assert refused, "a person is never a group to leave"


def test_disarmed_the_chat_list_alone_does_not_find_it(monkeypatch):
    from widgets import directory
    from widgets.mensajeria import data  # noqa: F401 — the card first (its actions import it back)
    from widgets.mensajeria.actions import leave
    monkeypatch.setattr(directory, "_contacts", lambda: [{"name": "Book club", "subtype": "group", "channels": [
        {"platform": "whatsapp", "chatId": "120363000000000101@g.us"}]}])
    monkeypatch.setattr(leave, "_directory_groups", lambda platform="": [])
    assert leave.resolve({}, {"groups": ["Book club"]})[1], "without the directory the group is not found"


def test_a_group_name_is_read_by_its_sound_and_all_of_them_is_an_answer(monkeypatch):
    """Measured live 2026-11-18: he said «Club Hípica», his groups are «Club Ípica» (a silent h) — twice, two
    chats of one name. It is found by sound; «all of them» (`every`) takes both; never a partial name."""
    from widgets import directory
    from widgets.mensajeria import data  # noqa: F401
    from widgets.mensajeria.actions import leave
    rows = [{"name": "Club Ípica", "subtype": "group", "channels": [{"platform": "whatsapp", "chatId": "120363000000000101@g.us"}]},
            {"name": "club ípica", "subtype": "group", "channels": [{"platform": "whatsapp", "chatId": "120363000000000102@g.us"}]},
            {"name": "Club Ípica 2", "subtype": "group", "channels": [{"platform": "whatsapp", "chatId": "120363000000000103@g.us"}]}]
    monkeypatch.setattr(directory, "_contacts", lambda: rows)
    _f, refused = leave.resolve({}, {"groups": ["Club Hípica"]})
    assert refused and len(refused["candidates"]["Club Hípica"]) == 2, refused
    found, no = leave.resolve({}, {"groups": ["Club Hípica"], "every": True})
    assert no is None and len(found) == 2 and all(r["name"].lower() == "club ípica" for r in found)
