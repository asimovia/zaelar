"""widgets/state_adopt.py — his HAND on an app's own control becomes the order, and nothing else does (V2-884 C10 A1/A2).

A report field that declares `adopt` (the name of one of the app's INTERNAL actions) can move its order key — e.g. he
unmutes the video from the player's own speaker icon, and the card must stop saying «muted». Measured risks this rule
exists to close: the autoplay start reports `muted=true` with the order already `muted=false` (adopting it would turn
«the browser blocks the sound» into «he muted it»), and a late or unapplied report could undo what he just asked by
voice. So, per field and per mount, a settlement:

  · `unsettled` → `agreed` when a report that acks the CURRENT revision of the key it follows has the ordered value;
  · `unsettled` → `contradicted` when such a report has another value (it feeds facts, `audio_blocked`; never adopts);
  · ONLY `agreed` → a contrary report that acks the current revision AND says his hand was on the app's control (the
    player had the focus — an autoplay start or a browser that reverts a sound never says it) ADOPTS. The adoption
    runs the app's declared action (its own invariants, `mute_kept`); the field is then `hand`: while he keeps moving
    it (a volume drag) each settled report adopts the newest value, and agreeing with it ends there.

An agreement belongs to the order revision it was given at: a new order on that key, or a change of the keys the field
`settle_on` (the video, and the command counter — an order that leaves the value as it was counts too), or the surface
forgetting the field (a rebuilt player), puts it back to `unsettled`. A report that acks less than the current revision (a late phone,
a report queued offline, a player that has not applied the order yet) is an observation — it settles nothing. A new
mount starts unsettled. Nothing here reads a value's meaning.
"""
from __future__ import annotations

from widgets import state_decl as decl

AGREED, CONTRADICTED, UNSETTLED, HAND = "agreed", "contradicted", "unsettled", "hand"


def _anchor(data, order: dict, spec: dict) -> tuple:
    """The values of the order keys the field's agreement hangs on (`settle_on`: one name or a list — the video, and the
    command counter so that ANY order on the app, even one that leaves the value as it was, starts it over)."""
    on = spec.get("settle_on")
    names = [on] if isinstance(on, str) else list(on or [])
    return tuple(decl.order_value(data, order.get(n)) for n in names)


def settle(app: str, instance: str, clean: dict, ack, prior: dict, *, hand: bool = False,
           full: bool = False, forgot=()) -> tuple[dict, list]:
    """The new settlement of the mount's `adopt` fields, and the adoptions due: [(action, payload)].

    `hand` = the surface says his hand was on the app's own control (the player had the focus) when this changed: a
    browser that reverts a sound on its own, or an autoplay start, never says it — and never adopts (audit P2-4)."""
    st = decl.of(app)
    order = st.get("order") or {}
    spec_all = {f: s for f, s in decl.report_fields(st).items() if isinstance(s, dict) and s.get("adopt")}
    # a field the surface no longer vouches for (forgotten, or left out of a full snapshot) starts over (audit P1-1)
    out = {f: v for f, v in prior.items() if f in spec_all and f not in forgot
           and not (f in clean and clean[f] is None) and not (full and f not in clean)}
    fields = {f: s for f, s in spec_all.items() if clean.get(f) is not None}
    if not fields:
        return out, []
    from nucleo.runtime_ids import boot_id
    from widgets import state, store
    disk = state.disk_id(instance)
    if not store.has_state(disk):
        return out, []
    data, changed, epoch = store.load(disk, {}), state.changed(instance), boot_id()
    adopt = []
    for f, spec in fields.items():
        key, inverted = decl.follows(spec)
        anchor = _anchor(data, order, spec)
        ch = changed.get(key)
        at = (ch[0], ch[1]) if ch else (epoch, 0)
        was, was_anchor, was_at = out.get(f, (UNSETTLED, anchor, at))
        if was_anchor != anchor or (tuple(was_at) != at and was != HAND):
            was = UNSETTLED                       # another video, any new order: agreement starts over
        if not (ack and ack[0] == epoch and ack[1] >= at[1] and (ch is None or ack[0] == ch[0])):
            out[f] = (was, anchor, tuple(was_at) if was == HAND else at)   # acks less: an observation, nothing more
            continue
        ordered = decl.order_value(data, order.get(key))
        seen = clean[f]
        seen_as_order = (not seen) if inverted and isinstance(seen, bool) else seen
        if seen_as_order == ordered:
            out[f] = (AGREED, anchor, at)
        elif was in (AGREED, HAND) and hand:
            # the report had confirmed the order (or his hand is still moving it) and moved away under his hand
            adopt.append((str(spec["adopt"]), {"field": f, "order": key, "value": seen_as_order}))
            out[f] = (HAND, anchor, at)
        else:
            out[f] = (CONTRADICTED if was != HAND else HAND, anchor, at)
    return out, adopt


def problem(man: dict, name: str, spec: dict) -> str | None:
    """Why a field's `adopt` is wrong, or None: an INTERNAL action of the app, on a one-screen app only (the order is
    per app, the report per screen — two screens would adopt by turns, C10 A3), `settle_on` an order name."""
    from widgets import screen_policy
    act = spec.get("adopt")
    actions = (man or {}).get("actions") or {}
    if screen_policy.of(man) != screen_policy.SINGLE:
        return f"state.report.{name}: adopt is for a one-screen app only (screens: single)"
    if not isinstance(act, str) or not isinstance(actions.get(act), dict) or not actions[act].get("internal"):
        return f"state.report.{name}: adopt names an INTERNAL action of this app"
    on = spec.get("settle_on")
    names = [on] if isinstance(on, str) else list(on or [])
    if (bad := next((n for n in names if n not in ((man.get("state") or {}).get("order") or {})), None)) is not None:
        return f"state.report.{name}: settle_on «{bad}» is not in state.order"
    return None
