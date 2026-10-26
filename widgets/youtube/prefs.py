#
# youtube/prefs — the card's standing preferences are rows of the rules table (V2-806).
#
# An enforceable preference (`library._ENFORCEABLE`: minimum definition, captions, start volume) is a `pref` row
# at `widget:youtube` whose key the player applies; anything he asks for that the player cannot enforce is a
# `note` row at the same scope, which the model reads when the card is in play. The card still SHOWS both as
# `prefs` / `prefs_notes`: those two fields are a projection of the table, laid over the store on every load, so
# an edit in Settings reaches the card without a second copy to keep in step. The fields an older store holds are
# imported once.
#
import time

SCOPE = "widget:youtube"
_NOTES_MAX = 20


def _rules():
    import rules
    return rules


def migrate(db: dict) -> None:
    """Import the `prefs` / `prefs_notes` an older store holds, once per database."""
    from rules import store as _rstore
    marker = "migrated:youtube.prefs"
    if _rstore.once_done(marker):
        return
    for k, v in (db.get("prefs") or {}).items():
        _rstore.insert_new({"id": f"m_youtube_{k}", "scope": SCOPE, "kind": "pref", "key": str(k), "value": v,
                            "source": "user", "origin": f"youtube.prefs:{k}"})
    for i, n in enumerate(db.get("prefs_notes") or []):
        t = str((n or {}).get("text") or "").strip()
        if t:
            _rstore.insert_new({"id": f"m_youtube_note_{i}", "scope": SCOPE, "kind": "pref", "key": "note",
                                "value": t, "text": t, "source": "user",
                                "created_at": float((n or {}).get("added_at") or time.time()),
                                "origin": "youtube.prefs_notes"})
    _rstore.mark_done(marker)


def overlay(db: dict, keys) -> dict:
    """Lay the table's rows over the store: `prefs` (the enforceable keys his rows set) and `prefs_notes`."""
    migrate(db)
    r = _rules()
    rows = [x for x in r.all_rows(include_defaults=False) if x["scope"] == SCOPE and x["source"] == "user"]
    db["prefs"] = {x["key"]: x["value"] for x in rows if x["key"] in keys and x["active"]}
    db["prefs_notes"] = [{"text": x["text"] or str(x["value"]), "added_at": int(x["created_at"]), "id": x["id"]}
                         for x in sorted(rows, key=lambda x: x["created_at"]) if x["key"] == "note" and x["active"]]
    return db


def set_value(db: dict, key: str, value, text: str, keys) -> None:
    _rules().add(SCOPE, "pref", key, value, text=text)
    overlay(db, keys)


def add_note(db: dict, text: str, keys) -> None:
    r = _rules()
    r.add(SCOPE, "pref", "note", text, text=text)
    notes = [x for x in r.all_rows(include_defaults=False) if x["scope"] == SCOPE and x["key"] == "note"]
    for old in sorted(notes, key=lambda x: x["created_at"])[:max(0, len(notes) - _NOTES_MAX)]:
        r.remove(old["id"])
    overlay(db, keys)


def clear_value(db: dict, key: str, keys) -> bool:
    gone = _rules().clear(SCOPE, key)
    overlay(db, keys)
    return bool(gone)


def remove_note(db: dict, note_id: str, keys) -> None:
    _rules().remove(note_id)
    overlay(db, keys)
