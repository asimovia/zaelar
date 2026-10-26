"""V2-809 — files go into the chat: the 📎, paste and drop onto the composer, one fate per file, and the bubble
that keeps them. Rendered: the real ChatWall + store + stylesheet in Chromium, the engine's routes mocked.

What is measured, each as its own case:
  · the clip opens a MULTI-file picker; every file goes through the upload door as a RAW body (`?source=chat`,
    its name in `X-File-Name`) — the bytes travel to the door, never in the message;
  · several files, several fates: a type the chat refuses and a refusal from the server (disk full) end as
    their own translated row, and the others still go;
  · the sent bubble carries REFERENCES (id, name, kind, size, thumbnail URL) and shows them; the chat log keeps
    them, so a restored history shows the attachment again;
  · a cancel aborts the upload and removes the row; an upload that never answers ends in a visible outcome on
    its clock — nothing spins forever;
  · paste and drop onto the composer attach, exactly like the clip.
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from tests.waiting import until_sync

ENGINE = Path(__file__).resolve().parents[4]
_EN = json.loads((ENGINE / "i18n/genesis/en/ui.json").read_text(encoding="utf-8"))

pytest.importorskip("playwright.sync_api")

PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4"
       b"\x89\x00\x00\x00\rIDATx\x9cc\xf8\xcf\xc0\xf0\x1f\x00\x05\x00\x01\xff\x89\x99=\x1d\x00\x00\x00\x00IEND\xaeB`\x82")
LIMITS = {"max_file_bytes": 1048576, "max_files_per_message": 10, "max_message_bytes": 4194304,
          "upload_stall_s": 1, "process_timeout_s": 1}


def _listening(port: int) -> bool:
    try:
        socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
        return True
    except OSError:
        return False


@pytest.fixture(scope="module")
def browser_and_port():
    from playwright.sync_api import sync_playwright
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    until_sync(lambda: _listening(port), "the static server to accept connections", timeout_s=10)
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            yield b, port
            b.close()
    finally:
        srv.terminate(); srv.wait(timeout=10)


class Door:
    """The mocked upload door: records every request and answers by file name."""

    def __init__(self):
        self.seen: list[dict] = []
        self.held = []
        self.n = 0

    def __call__(self, route):
        req = route.request
        name = req.headers.get("x-file-name", "")
        self.seen.append({"url": req.url, "name": name, "ctype": req.headers.get("content-type", ""),
                          "len": len(req.post_data_buffer or b"")})
        if "hang" in name:
            self.held.append(route)          # never answered: the composer's clock must end it
            return
        if "full" in name:
            return route.fulfill(status=507, content_type="application/json",
                                 body=json.dumps({"ok": False, "reason": "disk_full"}))
        self.n += 1
        kind = "image" if name.endswith(".png") else "pdf" if name.endswith(".pdf") else "text"
        return route.fulfill(status=200, content_type="application/json", body=json.dumps({
            "ok": True, "name": name, "size": len(req.post_data_buffer or b""), "episode_id": 100 + self.n,
            "kind": kind, "thumb": f"/api/files/{100 + self.n}/thumb" if kind == "image" else None, "read": True}))


def _page(browser, port, *, clear=True, limits=LIMITS):
    """`browser` may be a context: two pages of ONE context share localStorage, which is what a reload is."""
    pg = browser.new_page(viewport={"width": 1280, "height": 800}) if hasattr(browser, "new_context") \
        else browser.new_page()
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    door = Door()
    # Catch-all FIRST: Playwright gives the last matching route priority.
    pg.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
    pg.route("**/api/files/*/thumb", lambda r: r.fulfill(status=200, content_type="image/png", body=PNG))
    pg.route("**/api/files/limits", lambda r: r.fulfill(status=200, content_type="application/json",
                                                         body=json.dumps(limits)))
    pg.route("**/api/files/upload**", door)
    pg.route("**/api/i18n/bundle/*", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps({"strings": _EN})))
    pg.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
    pg.evaluate("""async (clear) => {
        if (clear) localStorage.clear();
        for (const h of ['/frontend/app/core/palette.css', '/frontend/app/styles.css']) {
          const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = h; document.head.append(l); }
        const i18n = await import('/frontend/app/core/i18n.js?v=1');
        await i18n.loadBundle('en'); if (i18n.applyLang) await i18n.applyLang('en');
        const store = await import('/frontend/app/core/store.js?v=2');
        const wall = await import('/frontend/app/components/ChatWall.js?v=5');
        document.body.append(wall.ChatWall());
        window.__store = store;
        store.openChatFrom('orb'); store.setChatTab('chat');
    }""", clear)
    pg.wait_for_selector("#chatwall.open", timeout=5000)
    pg._errors, pg._door = errors, door
    return pg


def _chips(pg):
    return pg.evaluate("""() => [...document.querySelectorAll('#chatwall .cw-att-chip')].map(c => ({
        phase: c.dataset.phase, name: c.querySelector('.cw-att-name').textContent,
        sub: c.querySelector('.cw-att-sub').textContent }))""")


def _files(*specs):
    return [{"name": n, "mimeType": m, "buffer": b} for n, m, b in specs]


def test_the_clip_attaches_several_files_and_each_keeps_its_own_fate(browser_and_port):
    b, port = browser_and_port
    pg = _page(b, port)
    clip = pg.locator("#chatwall .cw-clip")
    assert clip.is_visible() and clip.locator("svg").count() == 1, "the 📎 must be on the composer"
    assert pg.get_attribute("#chatwall .cw-att-input", "multiple") is not None, "the picker takes several files"
    with pg.expect_file_chooser() as fc:
        clip.click()
    fc.value.set_files(_files(("photo.png", "image/png", PNG),
                              ("notes.txt", "text/plain", b"buy milk"),
                              ("setup.exe", "application/octet-stream", b"MZ\x90\x00"),
                              ("full.pdf", "application/pdf", b"%PDF-1.4 x")))
    until_sync(lambda: sorted(c["phase"] for c in _chips(pg)) == ["error", "error", "ready", "ready"],
               "two files ready and two refused, each in its own row", timeout_s=8)
    chips = {c["name"]: c for c in _chips(pg)}
    assert chips["setup.exe"]["sub"] == _EN["chat.attachType"].replace("{name}", "setup.exe")
    assert chips["full.pdf"]["sub"] == _EN["chat.attachDiskFull"].replace("{name}", "full.pdf")
    # The refused type never travelled; the three others did, each as a RAW body tagged for the chat.
    sent = {s["name"]: s for s in pg._door.seen}
    assert set(sent) == {"photo.png", "notes.txt", "full.pdf"}
    assert all("source=chat" in s["url"] and not s["ctype"].startswith("multipart") for s in sent.values())
    assert sent["photo.png"]["len"] == len(PNG)

    pg.fill("#chatwall .cw-input textarea", "what does this say?")
    pg.click("#chatwall .cw-send")
    until_sync(lambda: pg.locator("#chatwall .cw-msg.you .cw-msg-att").count() == 1, "the bubble with its files")
    msg = pg.evaluate("() => window.__store.chatMsgs().at(-1)")
    assert msg["text"] == "what does this say?"
    assert [(a["id"], a["name"], a["kind"]) for a in msg["att"]] == [(101, "photo.png", "image"), (102, "notes.txt", "text")]
    assert not any("buffer" in a or "data" in a for a in msg["att"]), "the message carries references, not bytes"
    assert pg.locator("#chatwall .cw-msg.you img.cw-att-img").get_attribute("src") == "/api/files/101/thumb"
    assert pg.locator("#chatwall .cw-msg.you .cw-att-file .cw-att-name").inner_text() == "notes.txt"
    assert _chips(pg) == [], "sending clears the tray, failed rows included"
    assert not pg._errors, pg._errors
    pg.close()


def test_a_restored_history_shows_the_attachment_again(browser_and_port):
    b, port = browser_and_port
    ctx = b.new_context(viewport={"width": 1280, "height": 800})
    pg = _page(ctx, port)
    pg.evaluate("""() => window.__store.pushChat({role: 'you', text: '',
        att: [{id: 7, name: 'ticket.png', kind: 'image', size: 2048, thumb: '/api/files/7/thumb'},
              {id: 8, name: 'contract.pdf', kind: 'pdf', size: 900000, thumb: null}]})""")
    until_sync(lambda: "ticket.png" in (pg.evaluate("() => localStorage.getItem('hb_chat_log')") or ""),
               "the chat log to persist the attachment")
    pg.close()
    pg2 = _page(ctx, port, clear=False)
    until_sync(lambda: pg2.locator("#chatwall .cw-msg.you .cw-msg-att").count() == 1, "the restored bubble")
    assert pg2.locator("#chatwall .cw-msg.you img.cw-att-img").get_attribute("src") == "/api/files/7/thumb"
    # PAINTED, not only present: a lazy image inside the scrolled wall never loaded (seen in a screenshot).
    until_sync(lambda: pg2.evaluate("""() => { const i = document.querySelector('#chatwall .cw-msg.you img.cw-att-img');
        return i.complete && i.naturalWidth > 0 && i.getBoundingClientRect().width > 0; }"""), "the thumbnail to paint")
    assert pg2.locator("#chatwall .cw-msg.you .cw-att-file .cw-att-name").inner_text() == "contract.pdf"
    ctx.close()


def test_a_cancel_aborts_the_upload_and_a_silent_door_ends_on_its_clock(browser_and_port):
    b, port = browser_and_port
    pg = _page(b, port)
    with pg.expect_file_chooser() as fc:
        pg.click("#chatwall .cw-clip")
    fc.value.set_files(_files(("hang-a.png", "image/png", PNG), ("hang-b.txt", "text/plain", b"x")))
    until_sync(lambda: len(_chips(pg)) == 2, "two rows in flight")
    assert pg.locator("#chatwall .cw-send").is_disabled(), "nothing is sent while a file is still on its way"
    pg.evaluate("""() => { window.__aborts = 0; const a = XMLHttpRequest.prototype.abort;
        XMLHttpRequest.prototype.abort = function () { window.__aborts++; return a.call(this); }; }""")
    pg.locator("#chatwall .cw-att-chip").first.locator(".cw-att-x").click()
    until_sync(lambda: [c["name"] for c in _chips(pg)] == ["hang-b.txt"], "the cancelled row to go")
    # The × ABORTS the request at once — well inside the 1 s stall clock, so this is the cancel, not the clock.
    until_sync(lambda: pg.evaluate("() => window.__aborts") == 1,
               "the cancelled upload to be aborted, not left running", timeout_s=0.8)
    # The other one never gets an answer: its clock (stall 1 s + reading 1 s here) must end it, visibly.
    until_sync(lambda: _chips(pg)[0]["phase"] == "error", "the silent upload to end in a visible outcome",
               timeout_s=10)
    assert _chips(pg)[0]["sub"] in (_EN["chat.attachStalled"].replace("{name}", "hang-b.txt"),
                                    _EN["chat.attachTimeout"].replace("{name}", "hang-b.txt"))
    assert not pg.locator("#chatwall .cw-send").is_disabled()
    for r in pg._door.held:
        try:
            r.abort()
        except Exception:
            pass
    pg.close()


def test_paste_and_drop_onto_the_composer_attach(browser_and_port):
    b, port = browser_and_port
    pg = _page(b, port)
    pg.evaluate("""() => {
        const ta = document.querySelector('#chatwall .cw-input textarea');
        const dt = new DataTransfer();
        dt.items.add(new File([new Uint8Array([137,80,78,71,13,10,26,10])], 'pasted.png', {type: 'image/png'}));
        ta.dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true}));
        const dt2 = new DataTransfer();
        dt2.items.add(new File(['# title'], 'dropped.md', {type: 'text/markdown'}));
        document.querySelector('#chatwall .cw-input').dispatchEvent(
            new DragEvent('drop', {dataTransfer: dt2, bubbles: true, cancelable: true}));
    }""")
    until_sync(lambda: sorted((c["name"], c["phase"]) for c in _chips(pg))
               == [("dropped.md", "ready"), ("pasted.png", "ready")], "the pasted and the dropped file attached")
    pg.close()


def test_the_limits_refuse_before_anything_travels(browser_and_port):
    b, port = browser_and_port
    pg = _page(b, port, limits={**LIMITS, "max_files_per_message": 1})
    with pg.expect_file_chooser() as fc:
        pg.click("#chatwall .cw-clip")
    fc.value.set_files(_files(("a.txt", "text/plain", b"a"), ("b.txt", "text/plain", b"b"),
                              ("huge.pdf", "application/pdf", b"%PDF" + b"x" * (LIMITS["max_file_bytes"] + 1))))
    until_sync(lambda: [c["phase"] for c in _chips(pg)] == ["ready", "error", "error"], "one in, two refused")
    subs = [c["sub"] for c in _chips(pg)]
    assert subs[1] == _EN["chat.attachTooMany"].replace("{name}", "b.txt").replace("{n}", "1")
    assert subs[2] == _EN["chat.attachTooLarge"].replace("{name}", "huge.pdf").replace("{max}", "1.0 MB")
    assert [s["name"] for s in pg._door.seen] == ["a.txt"], "a refused file never reaches the door"
    pg.close()
