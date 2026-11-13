"""widgets/state_adopt.py — his HAND on an app's own control becomes the order, and nothing else does (V2-884 C10 A1/A2).

A report field that declares `adopt` (the name of one of the app's INTERNAL actions) can move its order key — e.g. he
unmutes the video from the player's own speaker icon, and the card must stop saying «muted». Measured risks this rule
exists to close: the autoplay start reports `muted=true` with the order already `muted=false` (adopting it would turn
«the browser blocks the sound» into «he muted it»), and a late or unapplied report could undo what he just asked by
voice. So, per field and per mount, a settlement:

  · `unsettled` → `agreed` when a report that acks the CURRENT revision of the key it follows has the ordered value;
  · `unsettled` → `contradicted` when such a report has another value (it feeds facts, `audio_blocked`; never adopts);
  · ONLY `agreed` → a contrary report that acks the current revision ADOPTS: the report had confirmed the order and
    then moved — that is a hand. The adoption runs the app's declared action (its own invariants, `mute_kept`), and it
    moves the revision like any order, so the field is `unsettled` again until the next ack.

An agreement belongs to the order revision it was given at: a new order on that key, or a change of the key the field
`settle_on` (the video), puts it back to `unsettled`. A report that acks less than the current revision (a late phone,
a report queued offline, a player that has not applied the order yet) is an observation — it settles nothing. A new
mount starts unsettled. Nothing here reads a value's meaning.
"""
from __future__ import annotations

from widgets import state_decl as decl

AGREED, CONTRADICTED, UNSETTLED = "agreed", "contradicted", "unsettled"


def settle(app: str, instance: str, clean: dict, ack, prior: dict) -> tuple[dict, list]:
    """The new settlement of the mount's `adopt` fields, and the adoptions due: [(action, payload)]."""
    st = decl.of(app)
    order = st.get("order") or {}
    fields = {f: s for f, s in decl.report_fields(st).items()
              if isinstance(s, dict) and s.get("adopt") and clean.get(f) is not None}
    if not fields:
        return prior, []
    from nucleo.runtime_ids import boot_id
    from widgets import state, store
    disk = state.disk_id(instance)
    if not store.exists(disk):
        return prior, []
    data, changed, epoch = store.load(disk, {}), state.changed(instance), boot_id()
    out, adopt = dict(prior), []
    for f, spec in fields.items():
        key, inverted = decl.follows(spec)
        on = str(spec.get("settle_on") or "")
        anchor = decl.order_value(data, order.get(on)) if on else None
        ch = changed.get(key)
        at = (ch[0], ch[1]) if ch else (epoch, 0)
        was, was_anchor, was_at = prior.get(f, (UNSETTLED, anchor, at))
        if was_anchor != anchor or tuple(was_at) != at:
            was = UNSETTLED                       # another video, or a new order on the key: agreement starts over
        if not (ack and ack[0] == epoch and ack[1] >= at[1] and (ch is None or ack[0] == ch[0])):
            out[f] = (was, anchor, at)            # acks less than the current order: an observation, nothing more
            continue
        ordered = decl.order_value(data, order.get(key))
        seen = clean[f]
        seen_as_order = (not seen) if inverted and isinstance(seen, bool) else seen
        if seen_as_order == ordered:
            out[f] = (AGREED, anchor, at)
        elif was == AGREED:
            adopt.append((str(spec["adopt"]), {"field": f, "order": key, "value": seen_as_order}))
            out[f] = (UNSETTLED, anchor, at)
        else:
            out[f] = (CONTRADICTED, anchor, at)
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
    if on is not None and on not in ((man.get("state") or {}).get("order") or {}):
        return f"state.report.{name}: settle_on «{on}» is not in state.order"
    return None
