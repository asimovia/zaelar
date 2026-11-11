"""The one door that decides whether a cluster frame may wake the brain — code only, no model call.

A MeshKore cluster is one of the engine's input interfaces (with voice, chat and connector events). What it may
wake depends on the subscription's attention flags (`store.ATTENTION_FLAGS`, defaults by kind in
`store.ATTENTION_DEFAULTS`):

  · `addressed`  — a message aimed at us (`to` set)        → `addressed_to_me`   (on for every cluster)
  · `general`    — the cluster's general traffic: broadcasts, a peer arriving, our intro → `general_messages`
  · `content`    — content the cluster produces (posts, shared items) → `generated_content` (no frame carries it yet)
  · `pulse`      — our own follow-up of a conversation already engaged: always passes here, because engagement is
                   itself gated (`bridge.note_objective`, `cluster.connect`) and only HIS send engages otherwise.

Every autonomous brain turn of the bridge goes through `_brain_turn(kind=…)`, which asks `wakes()` before opening
anything, so a new call site cannot bypass it.
"""
from __future__ import annotations

from connectors.meshkore import store

_FLAG = dict(addressed="addressed_to_me", general="general_messages", content="generated_content")   # kind → flag id


def classify(ev: dict) -> str:
    """`addressed` when the message frame names a recipient, else `general`. The relay delivers a directed frame only
    to its recipient, so any `to` other than empty/`*` is ours; a broadcast arrives with `to: null` (or without it)."""
    to = (ev or {}).get("to")
    return "addressed" if to and to != "*" else "general"


def flags(cluster: str, live_public: bool | None = None) -> dict:
    """Saved flags; for a cluster not saved yet (a frame racing its first save), the defaults of the live
    connection's kind; with nothing known at all, the private defaults (today's behaviour)."""
    a = store.get_attention(cluster)
    if a is not None:
        return a
    return store.attention_defaults(bool(live_public))


def wakes(cluster: str, kind: str, live_public: bool | None = None) -> bool:
    if kind == "pulse":
        return True
    flag = _FLAG.get(kind)
    if flag is None:
        return False                  # an unknown kind never wakes the brain
    try:
        return bool(flags(cluster, live_public).get(flag))
    except Exception:  # noqa: BLE001 — an unreadable config keeps the safe answer for an addressed message only
        return kind == "addressed"
