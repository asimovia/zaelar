"""The chat wall's actions from a session of the manager (V2-941, INI-042 #49; the wall plan §3): what the manager
hears and says, as actions with ids for the wall component (`frontend/chat-wall/`), one `wall` event each.

Every action names its writer — the component sets a line's owner from it and refuses another's hand:
  · `ear:<device>`      his spoken line, id = its intervention: `append` live at its first words, `update` while he
                        speaks (live, over the stream only, never stored: W-1), `update` final with the words the inbox
                        accepted, `delete` when the ear discards it before it was final;
  · `keyboard:<device>` his typed line, id = the screen's own `cid` (the component's id for it): the same line on the
                        screen that typed it and on every other; a repeated `cid` is one line;
  · `mouth`             our line, id = its say id, answering his (`re`): `append` live when its voice starts (or final
                        when shown), `update` final with what sounded; a line that never started is never said to
                        have sounded.
The package's telemetry carries no words: they come from the ear's own lane (`ear_in.receive` → `heard`), the inbox's
acceptance and the mouth.
"""
from __future__ import annotations

import threading

CID_MAX = 48
CID_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789_-")
KEPT = 512

_lock = threading.Lock()
_open: dict[str, str] = {}                  # device → the intervention its ear has open
_turns: dict[str, dict] = {}                # device → {provider turn: its words}, since that intervention opened
_lines: dict[str, str] = {}                 # a line on the wall → its writer (what this adapter appended)
_cid_of: dict[str, str] = {}                # a typed intervention → the screen's id for its line
_line_of: dict[str, str] = {}               # his intervention → its line's id on the wall (the `cid` of a typed one)
_env_iv: dict[str, str] = {}                # an envelope → its intervention
_run_ivs: dict[str, list] = {}              # a run → the interventions of his it answers (its batch, and absorbed)


def client_id_ok(cid) -> bool:
    """A screen's id for a line: `c_` and up to `CID_MAX` lowercase letters, digits, `_` or `-`. Never an owner."""
    c = str(cid or "")
    return 2 < len(c) <= CID_MAX and c.startswith("c_") and set(c) <= CID_CHARS


def _keep(d: dict, k: str, v) -> None:
    d[k] = v
    while len(d) > KEPT:
        d.pop(next(iter(d)))


def _say(writer: str, op: dict, *, live: bool = False) -> None:
    """One action on the stream. `live`: a line still being said — the stream only, never stored (W-1)."""
    from voice import observer
    observer.emit("wall", op["op"], extra={"writer": writer, "op": op, **({"live": True} if live else {})})


def heard(device: str, turn: int, text: str) -> None:
    """His words so far in one provider turn on `device` (the ear's lane): the open intervention's line, live."""
    device = str(device or "")
    with _lock:
        _turns.setdefault(device, {})[int(turn)] = str(text or "")
        iv = _open.get(device, "")
        words = " ".join(t for t in _turns[device].values() if t.strip())
        new = bool(iv) and iv not in _lines
        if new and words:
            _keep(_lines, iv, f"ear:{device}")
    if not iv or not words:
        return
    if new:
        _say(f"ear:{device}", {"op": "append", "id": iv, "role": "you", "state": "live", "text": words})
    else:
        _say(f"ear:{device}", {"op": "update", "id": iv, "text": words}, live=True)


def listen(kind: str, label: str, p: dict) -> None:
    """The conversation's telemetry, in its thread."""
    refs = p.get("refs") or {}
    iv, device = str(refs.get("iv") or ""), str(refs.get("endpoint") or "")
    if kind == "conv_ear" and label == "opened" and iv and refs.get("channel") == "voice":
        with _lock:
            _open[device], _turns[device] = iv, {}
    elif kind == "conv_ear" and label == "typed" and iv:
        cid = str((p.get("cause") or {}).get("ref") or "")
        if client_id_ok(cid):
            with _lock:
                _keep(_cid_of, iv, cid)
    elif kind == "conv_ear" and label == "discarded" and iv:
        with _lock:
            writer = _lines.pop(iv, "")
            if _open.get(device) == iv:
                _open.pop(device, None)
        if writer:
            _say(writer, {"op": "delete", "id": iv})
    elif kind == "conv_inbox" and label == "accepted" and iv and str(p.get("text") or "").strip():
        with _lock:
            _keep(_env_iv, str(refs.get("env") or ""), iv)
        _accepted(p.get("kind"), iv, device, str(p["text"]))
    elif kind == "conv_run" and (label == "started" or p.get("command") == "absorbed") and refs.get("run"):
        with _lock:                             # the lines our line answers: every intervention of its batch
            ivs = [_env_iv[e] for e in p.get("batch_envs") or () if e in _env_iv]
            _keep(_run_ivs, str(refs["run"]), list(dict.fromkeys(_run_ivs.get(str(refs["run"]), []) + ivs)))


def _accepted(kind, iv: str, device: str, text: str) -> None:
    if kind == "user.text":
        with _lock:
            cid = _cid_of.pop(iv, "") or iv
            _keep(_line_of, iv, cid)
        _say(f"keyboard:{device}", {"op": "append", "id": cid, "role": "you", "state": "final", "text": text})
        return
    if kind != "user.utterance":
        return
    with _lock:
        live = iv in _lines                              # its line was appended live, at its first words
        writer = _lines.get(iv) or f"ear:{device}"
        _keep(_lines, iv, writer)
        if _open.get(device) == iv:
            _open.pop(device, None)
            _turns.pop(device, None)
    if live:
        _say(writer, {"op": "update", "id": iv, "state": "final", "text": text})
    else:
        _say(writer, {"op": "append", "id": iv, "role": "you", "state": "final", "text": text})


def ours(order, event: str, heard_chars: int | None = None) -> None:
    """Our line (`WallMouth`): `shown` (final at once), `started` (live), `ended` (final, with what sounded)."""
    from nucleo.conversation_host import turns
    iv = turns.iv_of(str(order.request_id or ""))
    with _lock:                                 # every line of his it answers, by its id on the wall (W2-1)
        ivs = _run_ivs.get(str(getattr(order, "run_id", "") or ""), []) or ([iv] if iv.startswith("iv_") else [])
        re = [_line_of.get(i, i) for i in ivs]
    if event in ("shown", "started"):
        _say("mouth", {"op": "append", "id": order.say_id, "role": "agent", "re": re, "text": order.text,
                       "state": "final" if event == "shown" else "live"})
        return
    op = {"op": "update", "id": order.say_id, "state": "final"}
    if heard_chars is not None:
        op["heard"] = max(0, int(heard_chars))
    _say("mouth", op)


def _reset_for_tests() -> None:
    with _lock:
        _open.clear()
        _turns.clear()
        _lines.clear()
        _cid_of.clear()
        _line_of.clear()
        _env_iv.clear()
        _run_ivs.clear()
