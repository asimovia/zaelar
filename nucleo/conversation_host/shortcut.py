"""The `Shortcut` port: a phrase of his the action map knows VERBATIM runs its direct act before any model (V2-942 A2,
INI-078 F2 step 7b).

`nucleo.actionmap` is its own module (V2-539): a per-language table of verified command phrases, an EXACT whole-utterance
lookup (a leading wake word aside, `match_spoken`), never a split, never an intent read — no exact hit, the model. Here
the manager only asks it, on the engine's loop where its canvas doors live, and says what the act left: a bulk close's
own receipt, a control's own line, or the language pack's short ack when his style allows one (`confirm_short_actions`)
— a control he cannot be heard after is always said. Its switches are the module's (`ZAELAR_ACTIONMAP`,
`actionmap.enabled`); the timeline says `origin: actionmap` and the run closes with that origin.
"""
from __future__ import annotations

import time

_last_ack = {"line": ""}


def _line(hit: dict) -> str:
    from i18n import langs
    from nucleo import style_policy
    from nucleo.acts import self_controls
    from nucleo.flash import bulk_close
    act = hit.get("action") or {}
    control = act if act.get("do") == "controls" else {}
    receipt = bulk_close.take_receipt() or (self_controls.said(control.get("act"), control.get("value")) if control else "")
    if receipt:
        return receipt
    if not (style_policy.confirm_short_actions() or (control and self_controls.one_way(control.get("act")))):
        return ""
    _last_ack["line"] = langs.pick_ack(_last_ack["line"])
    return _last_ack["line"]


def _run(text: str) -> str | None:
    from nucleo import actionmap
    from voice.observer import emit
    if not actionmap.enabled():
        return None
    t0 = time.perf_counter()
    hit = actionmap.match_spoken(text)
    if hit is None or not actionmap.execute(hit, emit, phrase=text):
        return None
    emit("actionmap", "⚡ action map: direct action (no model)", text=text[:160], role="user",
         extra={"cat": "flash", "action": actionmap.describe(hit), "entry": hit.get("id"),
                "source": hit.get("source"), "match_ms": round((time.perf_counter() - t0) * 1000, 2),
                "engine": "actionmap", "origin": "actionmap", "src": "actionmap"})
    return _line(hit)


class HostShortcut:
    async def take(self, account: str, text: str) -> str | None:
        from nucleo.conversation_host.acts_widget import _on_engine_loop

        async def run() -> str | None:          # on the engine's loop: a widget's act there needs its running loop
            return _run(text)
        return await _on_engine_loop(run())


# ── learning from use (V2-942 T8): a run whose only effect was ONE declared canvas act is a map candidate ─────────
#: the runs in course, by id: his words, the effects claimed and how each settled, whether the model read anything
_runs: dict[str, dict] = {}


def _canvas_ops() -> dict[str, str]:
    """The manager's declared canvas acts, tool → op (`declared.json`, door `canvas`)."""
    from nucleo.conversation_host.acts import ACTS
    return {name: a["op"] for name, a in ACTS.items() if a.get("door") == "canvas"}


def listen(kind: str, label: str, p: dict) -> None:
    """The conversation's telemetry: a run that ANSWERED him with exactly one declared canvas act, accepted by its door,
    and no read — what one entry of the action map would have done in silence — is handed to its watch as a candidate
    (`actionmap.watch.candidate`, origin `conversation`). The map's own runs are hits, never candidates."""
    run = str(((p or {}).get("refs") or {}).get("run") or "")
    if not run:
        return
    if kind == "conv_run" and label == "input":
        _runs[run] = {"said": " ".join(str(t).strip() for t in (p.get("text") or ()) if t), "tools": [], "states": [],
                      "reads": 0}
        return
    got = _runs.get(run)
    if got is None:
        return
    if kind == "conv_effect":
        if label == "read":
            got["reads"] += 1
        elif label == "submitted":
            got["tools"].append(str(p.get("tool") or ""))
        elif label in ("receipt", "unknown", "refused"):
            got["states"].append(str(p.get("state") or label))
        return
    if kind == "conv_run" and label == "command" and p.get("command") == "actionmap":
        got["reads"] += 1                       # the map served it: a hit, never a candidate
        return
    if kind == "conv_run" and label == "ended":
        _runs.pop(run, None)
        ops = _canvas_ops()
        if p.get("outcome") == "answered" and not got["reads"] and len(got["tools"]) == 1 \
                and got["tools"][0] in ops and got["states"] == ["provider_accepted"]:
            from nucleo.actionmap import watch
            watch.candidate(got["said"], f"canvas:{ops[got['tools'][0]]}", "conversation")
