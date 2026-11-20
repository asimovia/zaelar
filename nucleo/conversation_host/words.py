"""The `Words` port (V2-941, B7b): the few fixed lines the manager says itself, as they are, from the language pack of
the person's language (`i18n.langs`) — a figure it could not confirm (`unverified_fact`). The pack's line or nothing:
a key the pack does not carry is an empty line, and the manager then says nothing rather than a line of ours.
"""
from __future__ import annotations


class PackWords:
    def line(self, key: str) -> str:
        from i18n import langs
        v = getattr(langs.current_language(), str(key), "")
        return v.strip() if isinstance(v, str) else ""
