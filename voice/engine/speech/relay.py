"""The voice stand-ins' one record: who serves now, who produced a metric, and WHY a switch happened (V2-896).

LiveKit's `FallbackAdapter` names the provider that failed, never the error: the last error each child raised is kept
here and travels with the switch alert, so a defect of ours (a socket closed on silence) never passes for an outage.
Child metrics keep their plugin `label`, so each one is billed to the plugin that produced it. Pure bookkeeping.
"""
from __future__ import annotations

_STATE: dict[str, dict] = {}


def track(family: str, pairs) -> None:
    """Remember the providers of `family` ('stt' | 'tts'), titular first, and listen for each one's errors."""
    labels: dict[str, str] = {}
    clash: set[str] = set()
    for name, inst in pairs:
        label = str(getattr(inst, "label", "") or "")
        if label in labels and labels[label] != name:
            clash.add(label)                     # two providers on one plugin class: a label cannot tell them apart
        labels[label] = name
    st = {"active": pairs[0][0], "labels": {k: v for k, v in labels.items() if k and k not in clash}, "cause": {},
          "insts": {id(inst): name for name, inst in pairs}}
    _STATE[family] = st
    for name, inst in pairs:
        on = getattr(inst, "on", None)
        if callable(on):
            on("error", lambda err, _n=name: None if getattr(err, "recoverable", False)   # a retry that may succeed
               else st["cause"].__setitem__(_n, _describe(err)))


def note(family: str, inst, err) -> None:
    """An exception the adapter caught from `inst` (P1-2): a raw one (a refused socket, a 402 at the handshake) never
    reaches the plugin's `error` event. Kept only when the event left nothing more precise for this episode."""
    st = _STATE.get(family) or {}
    name = st.get("insts", {}).get(id(inst))
    if name and not st["cause"].get(name):
        st["cause"][name] = _describe(err)


def _describe(err) -> str:
    """Type, status and message. LiveKit's own `APIError` quotes its payload after a colon (`… for text: <the
    sentence>`): only what comes before it is kept — no words the agent was about to say in an alert."""
    e = getattr(err, "error", err)
    code = getattr(e, "status_code", None)
    code = code if code not in (None, -1) else getattr(e, "status", None)        # aiohttp names it `status`
    text = str(getattr(e, "message", "") or e or "").strip().replace("\n", " ")
    text = (text.split(":")[0] if type(e).__name__ == "APIError" else text)[:160]
    return f"{type(e).__name__}{f' {code}' if code not in (None, -1) else ''}: {text}" if text else type(e).__name__


def take_cause(family: str, name: str) -> str:
    """The last error `name` raised since its cause was last read, or ''. Reading clears it: a cause is one episode's."""
    return (_STATE.get(family) or {}).get("cause", {}).pop(name, "")


def set_active(family: str, name: str) -> None:
    st = _STATE.get(family)
    if st is not None:
        st["active"] = name


def active(family: str, default: str) -> str:
    return (_STATE.get(family) or {}).get("active") or default


def provider_for(family: str, metric, default: str) -> str:
    """Who produced `metric`: as named where it was made (the voice process), its plugin label, who serves, `default`."""
    if isinstance(named := getattr(metric, "provider", None), str) and named:
        return named
    st = _STATE.get(family) or {}
    return st.get("labels", {}).get(str(getattr(metric, "label", "") or "")) or st.get("active") or default


def forget(family: str) -> None:
    _STATE.pop(family, None)
