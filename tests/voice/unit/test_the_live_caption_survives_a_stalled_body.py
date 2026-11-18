"""His live caption survives a stalled body: the newest interim always lands, and nothing older after it (node 3.238).

Measured 2026-11-18 on a loaded, swapping host: the body stalled 1-8.7 s, ~90 batches failed in 18 min, and every
interim in a failed batch was dropped — the caption on the wall froze for exactly the seconds the machine was
busiest. An interim is LATEST-WINS (`body_link.caption_key`):
  (a) a newer interim replaces an older one still queued, and the newest one of a failed batch goes back to the
      front: once the body answers again it receives the LATEST words, once, and never an older caption after them;
  (b) his final words make every earlier caption stale: a caption is never delivered after the line it previewed;
  (c) while only a caption waits, the sender retries after `CAPTION_GAP_S`, not the full `RETRY_GAP_S`; any other
      fact queued keeps the E0 pace (node 3.203).

Disarms (each seen red): no re-queue of the caption in `_deliver` → (a); `_says_more` ignoring a final → (b);
`gap = RETRY_GAP_S` always in `_pace` → (c).
"""
from __future__ import annotations

import asyncio
import json

from voice.engine.pipeline import body_link


class _StalledBody:
    """An aiohttp session whose POST times out while `fail` is set; records every batch that lands."""
    def __init__(self):
        self.fail, self.attempts, self.landed = True, 0, []

    def post(self, url, data=None, headers=None, timeout=None):
        http = self

        class _Resp:
            status = 200

            async def __aenter__(self):
                http.attempts += 1
                if http.fail:
                    raise asyncio.TimeoutError()
                http.landed.extend(json.loads(data)["events"])
                return self

            async def __aexit__(self, *a):
                return False
        return _Resp()


def _link(monkeypatch, body):
    link = body_link.BodyLink(base="http://127.0.0.1:1", token="t")
    monkeypatch.setattr(link, "_http", lambda: body)
    monkeypatch.setattr(body_link, "RETRY_GAP_S", 0.4)
    monkeypatch.setattr(body_link, "CAPTION_GAP_S", 0.05)
    return link


def _interim(text, role="user"):
    return {"k": "emit", "kind": "interim", "label": "…", "text": text, "role": role, "extra": {}}


def _captions(events):
    return [ev["text"] for ev in events if body_link.caption_key(ev) is not None]


def test_the_newest_caption_lands_once_the_body_recovers_and_nothing_older_after_it(monkeypatch):
    body = _StalledBody()
    link = _link(monkeypatch, body)

    async def run():
        link.start()
        for words in ("quiero", "quiero que", "quiero que me", "quiero que me recuerdes"):
            link.send(_interim(words))
            await asyncio.sleep(0.07)          # the body is stalled through all of them
        body.fail = False                      # …and comes back
        await asyncio.sleep(0.3)
        await link.aclose()
    asyncio.run(run())
    assert body.attempts >= 2, "the stall was real"
    assert _captions(body.landed) == ["quiero que me recuerdes"], \
        f"the newest caption must land once, with nothing older after it: {_captions(body.landed)}"
    assert link.stats["coalesced"] >= 3, link.stats


def test_his_final_words_make_every_earlier_caption_stale(monkeypatch):
    body = _StalledBody()
    link = _link(monkeypatch, body)

    async def run():
        link.start()
        link.send(_interim("pon una alarma"))
        await asyncio.sleep(0.07)
        link.send({"k": "transcript", "final": True, "text": "pon una alarma a las siete"})
        link.send({"k": "emit", "kind": "transcript", "label": "🗣", "text": "pon una alarma a las siete",
                   "role": "user", "extra": {}})
        await asyncio.sleep(0.1)
        body.fail = False
        await asyncio.sleep(1.0)               # the queue holds real facts now: the E0 pace, one try a gap
        await link.aclose()
    asyncio.run(run())
    texts = [ev.get("text") for ev in body.landed]
    assert "pon una alarma a las siete" in texts, f"his final words reached the body: {body.landed}"
    assert _captions(body.landed) == [], f"a caption was delivered after the line it previewed: {body.landed}"


def test_a_waiting_caption_is_retried_sooner_than_the_other_facts(monkeypatch):
    body = _StalledBody()
    link = _link(monkeypatch, body)

    async def run():
        link.start()
        link.send(_interim("hola"))
        await asyncio.sleep(0.32)
        only_caption = body.attempts
        link.send({"k": "item", "role": "assistant", "text": "Hola."})
        await asyncio.sleep(0.05)
        before = body.attempts
        await asyncio.sleep(0.3)               # inside the E0 gap: a real fact waits, no caption pace
        mixed = body.attempts - before
        await link.aclose()
        return only_caption, mixed
    only_caption, mixed = asyncio.run(run())
    assert only_caption >= 4, f"a lone caption is retried every CAPTION_GAP_S ({only_caption} tries in 0.32 s)"
    assert mixed <= 1, f"with another fact queued the E0 pace holds ({mixed} tries inside one gap)"
