"""`python -m a2a <command>` — drive one agent against the real network (or `--fake` for a dry run).

    whoami                                   our network DID and the pubkey to register
    publish-hashes --email E --phone P       publish our own identifier hashes (opt-in)
    lookup --email E --phone P [--cid C]     look up a contact; a mutual match is printed (nothing is sent)
    connect DID [--name N] [--cid C]         send connect.request
    accept DID | decline DID | disconnect WHO
    send WHO TEXT                            msg.text to an accepted contact (WHO = DID or contact id)
    grant WHO ITEM [--verbs see,…] [--ttl S] / revoke WHO ITEM
    ask WHO ITEM [--projection P] [--args JSON]  then `pull` and `answer QID`
    pull                                     pull + handle the mailbox once
    status | inbox
    live-open WHO [--item I] [--ttl S]       → share_id
    live-push SHARE JSON                     one sample
    live-read SHARE                          samples since the last read

Env: A2A_API_BASE, A2A_STATE_DIR, A2A_KEY_FILE (a second identity on the same machine).
Cards that need the owner (a request, a proposal) are printed and left pending; answer them with accept/decline/connect.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import events, from_network
from .discovery import hashes_for


def _print(obj) -> None:
    print(json.dumps(obj, indent=1, ensure_ascii=False, default=str))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m a2a")
    p.add_argument("--events", action="store_true", help="print every observability row to stderr")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("whoami")
    for name in ("publish-hashes", "lookup"):
        s = sub.add_parser(name)
        s.add_argument("--email", action="append", default=[])
        s.add_argument("--phone", action="append", default=[])
        s.add_argument("--cc", default="")
        s.add_argument("--cid", default="contact")
        s.add_argument("--name", default="")
    s = sub.add_parser("connect"); s.add_argument("did"); s.add_argument("--name", default=""); s.add_argument("--cid", default=""); s.add_argument("--note", default="")
    for name in ("accept", "decline", "disconnect"):
        sub.add_parser(name).add_argument("who")
    s = sub.add_parser("send"); s.add_argument("who"); s.add_argument("text")
    s = sub.add_parser("grant"); s.add_argument("who"); s.add_argument("item"); s.add_argument("--verbs", default="see"); s.add_argument("--ttl", type=int, default=0)
    s = sub.add_parser("revoke"); s.add_argument("who"); s.add_argument("item")
    s = sub.add_parser("ask"); s.add_argument("who"); s.add_argument("item"); s.add_argument("--projection", default="default"); s.add_argument("--args", default="{}")
    sub.add_parser("answer").add_argument("qid")
    for name in ("pull", "status", "inbox"):
        sub.add_parser(name)
    s = sub.add_parser("live-open"); s.add_argument("who"); s.add_argument("--item", default="activity.live"); s.add_argument("--ttl", type=int, default=7200)
    s = sub.add_parser("live-push"); s.add_argument("share"); s.add_argument("sample")
    sub.add_parser("live-read").add_argument("share")
    a = p.parse_args(argv)

    if a.events:
        events.add_sink(lambda row: print(json.dumps(row, ensure_ascii=False), file=sys.stderr))
    cards: list[dict] = []
    agent = from_network(asker=lambda card: cards.append(card) or None)

    if a.cmd == "whoami":
        _print({"did": agent.me.did, "pubkey_b64": agent.me.pub_b64, "api": agent.mailbox.http.base})
    elif a.cmd == "publish-hashes":
        _print({"published": agent.publish_hashes(a.email, a.phone, a.cc)})
    elif a.cmd == "lookup":
        hs = hashes_for(a.email, a.phone, a.cc)
        _print({"hashes": len(hs), "matches": agent.directory.lookup(list(hs))})
    elif a.cmd == "connect":
        _print({"status": agent.connect(a.did, contact_id=a.cid, name=a.name, note=a.note)})
    elif a.cmd in ("accept", "decline", "disconnect"):
        _print({"status": getattr(agent, a.cmd)(a.who)})
    elif a.cmd == "send":
        _print({"sent": agent.send(a.who, a.text)})
    elif a.cmd == "grant":
        g = agent.grant(a.who, a.item, a.verbs.split(","), ttl_s=a.ttl, how="cli")
        _print({"grant": g.id, "item": g.item, "verbs": g.verbs, "expires_at": g.expires_at})
    elif a.cmd == "revoke":
        _print({"revoked": agent.revoke(a.who, a.item)})
    elif a.cmd == "ask":
        _print({"qid": agent.ask(a.who, a.item, a.projection, json.loads(a.args))})
    elif a.cmd == "answer":
        _print(agent.answer(a.qid))
    elif a.cmd == "pull":
        _print({"handled": agent.pull(reason="owner"), "cards": cards})
    elif a.cmd == "status":
        _print(agent.status())
    elif a.cmd == "inbox":
        _print(agent.inbox())
    elif a.cmd == "live-open":
        _print({"share_id": agent.live_open(a.who, a.item, a.ttl)})
    elif a.cmd == "live-push":
        _print({"seq": agent.live_push(a.share, json.loads(a.sample))})
    elif a.cmd == "live-read":
        _print(agent.live_read(a.share))
    return 0


if __name__ == "__main__":
    sys.exit(main())
