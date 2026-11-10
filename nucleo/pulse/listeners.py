"""nucleo/pulse/listeners.py — which inbound channels something is LISTENING to while nobody is there.

An engine that sleeps between uses must still be woken now and then to catch up a channel — but only when catching up
changes something. A mailbox that only fills a list he will read when he comes back loses nothing by waiting for him:
the connector's cursor delivers everything that arrived meanwhile at the next start. So a channel is a LISTENER only
when both hold:

  1. it RECEIVES and can be caught up later: a connected inbound connector whose server keeps what arrived while the
     engine was down (`CATCH_UP`: email, WhatsApp, Telegram). A real-time channel with no backlog (a MeshKore cluster
     relays to whoever is connected now) cannot be caught up by a periodic pass and is never a listener here;
  2. something REACTS to what arrives on it, declared as data the engine already keeps:
       · a standing rule subscribed to its topic (`rules.subscriptions` rows, matched by topic and declared platform),
         or a spoken note not yet read for a subscription whose scope could reach a message (global, a person, or
         the channel's own domain) — a note is read the first time an event arrives, so it must be able to arrive;
       · a task row that WAITS for its event (`waiting_for = event:<topic>[:<key>]`, the stream rows excepted: they
         exist because a rule subscribed, and the rule decides);
       · a live errand with a third party bound to a conversation there (an errand with no conversation yet waits on
         every channel it could be answered through);
       · his own explicit preference about arrivals there: a notify level other than `never`, or the autoresponder on.

The DEFAULT triage alone is not a listener: it sorts an inbox, and the next start sorts it just the same.

`decide()` is pure (every reading comes in as an argument); `active_listeners()` gathers the readings, each one
fail-soft — an unreadable source contributes nothing rather than waking a machine on a guess.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("zaelar.listeners")

#: Inbound channels whose server holds what arrived while the engine was down — a periodic pass catches them up.
CATCH_UP = ("email", "whatsapp", "telegram")
#: Fallback when the resources policy cannot be read (key `listen_every_min`).
_LISTEN_FALLBACK_MIN = 10.0


def _topic_channels(topic: str, key: str = "", platform: str = "") -> set[str]:
    """The channels an event topic (and its optional key or declared platform) arrives through."""
    from nucleo.events import vocabulary as voc
    if topic == voc.MAIL_IN:
        return {"email"}
    if topic == voc.CONNECTOR_MSG:
        named = (platform or key.partition(":")[0]).strip().lower()
        return {named} if named else {c for c in CATCH_UP if c != "email"}
    return set()


def decide(connected: set[str], *, subscriptions: list[dict] = (), note_scopes: list[str] = (),
           waits: list[str] = (), errand_threads: list[list[str]] = (), prefs: set[str] = (),
           channel_domains: dict[str, str] | None = None) -> set[str]:
    """The listening channels. Pure.

    `connected` — the catch-up channels that are connected; `subscriptions` — live `on_event` values (`{topic, match}`);
    `note_scopes` — scopes of his spoken notes not yet read for a subscription; `waits` — `waiting_for` of non-stream
    waiting rows; `errand_threads` — per live errand, the platforms it is bound to (empty = not bound yet); `prefs` —
    channels with an explicit arrival preference; `channel_domains` — channel → its consent-class domain."""
    live = {c for c in connected if c in CATCH_UP}
    if not live:
        return set()
    from nucleo.events import WAITING_PREFIX
    reacting: set[str] = set(prefs or ())
    for sub in subscriptions or ():
        match = dict((sub or {}).get("match") or {})
        reacting |= _topic_channels(str((sub or {}).get("topic") or ""), platform=str(match.get("platform") or ""))
    domains = channel_domains or {}
    for scope in note_scopes or ():
        s = str(scope or "").strip().lower()
        head = s.partition("/")[0]
        if s in ("", "global") or s.startswith("subject:"):
            reacting |= live
        else:
            reacting |= {c for c in live if domains.get(c) and head == domains[c]}
    for wf in waits or ():
        w = str(wf or "")
        if not w.startswith(WAITING_PREFIX):
            continue
        topic, _, key = w[len(WAITING_PREFIX):].partition(":")
        reacting |= _topic_channels(topic, key=key)
    for platforms in errand_threads or ():
        bound = {str(p or "").strip().lower() for p in platforms or () if p}
        reacting |= bound if bound else live
    return live & reacting


# ── the readings ─────────────────────────────────────────────────────────────────────────────────────────────────
def _connected() -> set[str]:
    out: set[str] = set()
    try:
        from config import connectors as cfg
        for c in CATCH_UP:
            if c == "email":
                from connectors.email import config as email_cfg
                if email_cfg.enabled() and email_cfg.has_credentials():
                    out.add(c)
            elif cfg.enabled(c):
                out.add(c)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"listeners: connector state unreadable: {e!r}")
    return out


def _subscriptions() -> tuple[list[dict], list[str]]:
    """(live subscription values, scopes of the notes not yet read for one)."""
    try:
        import rules
        from rules import cascade, subscriptions as subs
        values = [r["value"] for r in rules.all_rows(include_defaults=False)
                  if r["key"] == subs.KEY and isinstance(r.get("value"), dict) and cascade.live(r)
                  and not (r["value"].get("from_note") and rules.get(r["value"]["from_note"]) is None)]
        return values, [str(n.get("scope") or "") for n in subs.unread_notes()]
    except Exception as e:  # noqa: BLE001
        logger.debug(f"listeners: rules unreadable: {e!r}")
        return [], []


def _waits() -> list[str]:
    try:
        from nucleo.circuit import ledger
        return [str(r.get("waiting_for") or "") for r in
                ledger.store().tasks_where(states=("waiting",), visible_only=False, limit=500)
                if r.get("kind") != "stream"]
    except Exception as e:  # noqa: BLE001
        logger.debug(f"listeners: task rows unreadable: {e!r}")
        return []


def _errand_threads() -> list[list[str]]:
    try:
        from nucleo import errands
        return [[t.get("platform") for t in errands.threads(r["id"])] for r in errands.live_rows()]
    except Exception as e:  # noqa: BLE001
        logger.debug(f"listeners: errands unreadable: {e!r}")
        return []


def _prefs() -> set[str]:
    """Channels where he asked to hear about arrivals (notify level) or to answer them (autoresponder)."""
    try:
        from connectors.messaging import store
        from widgets.mensajeria import autorespond, policy
        db = store.load()
        return {c for c in CATCH_UP if policy.policy_for(db, c)["notify"] != "never"
                or autorespond.config_for(db, c)["enabled"]}
    except Exception as e:  # noqa: BLE001
        logger.debug(f"listeners: messaging preferences unreadable: {e!r}")
        return set()


def _channel_domains() -> dict[str, str]:
    """channel → the domain of its declared consent class (`messaging.send_new` → `messaging`), from the catalog."""
    try:
        from connectors import catalog
        return {m["id"]: str(m["consent_class"]).partition(".")[0] for m in catalog.load_manifests()
                if m.get("id") in CATCH_UP and m.get("consent_class")}
    except Exception as e:  # noqa: BLE001
        logger.debug(f"listeners: connector catalog unreadable: {e!r}")
        return {}


def active_listeners() -> set[str]:
    """The channels a periodic pass must catch up while nobody is there — empty when none."""
    connected = _connected()
    if not connected:
        return set()
    subs, notes = _subscriptions()
    return decide(connected, subscriptions=subs, note_scopes=notes, waits=_waits(),
                  errand_threads=_errand_threads(), prefs=_prefs(), channel_domains=_channel_domains())


def listen_every_s() -> float:
    """How often a listening engine is woken to catch its channels up (`listen_every_min`, resources policy)."""
    try:
        from nucleo.workers import envelope
        minutes = float(envelope.policy().get("listen_every_min", _LISTEN_FALLBACK_MIN))
    except Exception:  # noqa: BLE001 — an unreadable policy keeps the declared default
        minutes = _LISTEN_FALLBACK_MIN
    return max(1.0, minutes) * 60.0


def next_listen(now: float, every_s: float) -> float:
    """The next listen instant on a fixed grid: stable between passes, so one report covers a whole interval."""
    every = max(60.0, float(every_s))
    return (int(now // every) + 1) * every
