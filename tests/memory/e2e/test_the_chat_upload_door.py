"""V2-809 — the upload door as the chat uses it: refused by type, size and disk headroom; STREAMED to disk; a
cancel leaves nothing behind; several files are independent requests.

The refusals run in-process (the limits and the disk are monkeypatched). Streaming and cancel need a REAL
server: an in-process ASGI client hands the handler the whole body at once, so it cannot tell a streamed body
from one read whole — which is exactly the difference these two cases are about.
"""
from __future__ import annotations

import http.client
import io
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from files import attachments as att
from memory import db as memdb
from memory import embeddings as mememb
from server.memory_routes import router
from tests.waiting import port_listening, until_sync

ENGINE = Path(__file__).resolve().parents[3]


def _png(w=8, h=8) -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (200, 30, 30)).save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    mememb.reset()
    memdb.reset_db()
    memdb.get_db()
    att._reset_for_tests()
    att.limits()
    # No model is reached from a test: the image reader is replaced by what a model would have said.
    monkeypatch.setattr(att, "_read_image", lambda path: ("Stop sign. Text: ALTO", ""))
    app = FastAPI()
    app.include_router(router)
    yield TestClient(app)
    att._reset_for_tests()
    memdb.reset_db()
    mememb.reset()


def _raw(client, name: str, body: bytes, **headers):
    return client.post("/api/files/upload?source=chat", content=body,
                       headers={"Content-Type": "application/octet-stream", "X-File-Name": name, **headers})


def _inbox(tmp_path: Path) -> list[str]:
    d = tmp_path / "episodic" / ".incoming"
    return sorted(p.name for p in d.iterdir()) if d.exists() else []


def test_an_image_goes_in_with_its_kind_thumbnail_and_reading(client, tmp_path):
    r = _raw(client, "se%C3%B1al.png", _png(900, 600))
    assert r.status_code == 200, r.text
    body = r.json()
    # The name is the door's safe name (`_safe_name` keeps alphanumerics, so the ñ survives).
    assert body["kind"] == "image" and body["mime"] == "image/png" and body["name"] == "señal.png", body
    assert body["thumb"] == f"/api/files/{body['episode_id']}/thumb"
    thumb = client.get(body["thumb"])
    assert thumb.status_code == 200 and thumb.headers["content-type"] == "image/jpeg"
    from PIL import Image
    assert max(Image.open(io.BytesIO(thumb.content)).size) <= att.limits()["thumb_side"]
    assert att.reading_path(body["episode_id"]).read_text() == "Stop sign. Text: ALTO"
    assert [a["episode_id"] for a in att.current()] == [body["episode_id"]]
    assert _inbox(tmp_path) == [], "the streamed file is adopted, nothing stays in the inbox"


def test_the_kind_is_decided_by_the_bytes_not_the_name(client, tmp_path):
    for name, data in (("photo.png", b"MZ\x90\x00" + b"\x00" * 200),          # an executable named .png
                       ("notes.txt", b"plain\x00binary"),                    # a binary named .txt
                       ("script.py", b"print('hi')\n"),                      # text, but not a kind the chat takes
                       ("archive.zip", b"PK\x03\x04" + b"\x00" * 64)):
        r = _raw(client, name, data)
        assert r.status_code == 415 and r.json()["reason"] == "type", (name, r.status_code, r.text)
    for name, data in (("ok.txt", "café ☕".encode()), ("t.csv", b"a,b\n1,2\n"), ("r.md", b"# h"),
                       ("d.pdf", b"%PDF-1.4\n%%EOF")):
        assert _raw(client, name, data).status_code == 200, name
    assert _inbox(tmp_path) == []


def test_over_the_size_limit_is_refused_and_leaves_nothing(client, tmp_path, monkeypatch):
    monkeypatch.setitem(att._limits_cache, "max_file_bytes", 64 * 1024)
    r = _raw(client, "big.txt", b"a" * (64 * 1024 + 1))
    assert r.status_code == 413 and r.json() == {"ok": False, "reason": "too_large", "limit": 64 * 1024}
    # Without a declared length (a chunked body) it is refused while streaming, and the partial file goes.
    def gen():
        for _ in range(10):
            yield b"a" * 16384
    r = client.post("/api/files/upload?source=chat", content=gen(),
                    headers={"Content-Type": "application/octet-stream", "X-File-Name": "big.txt"})
    assert r.status_code == 413 and r.json()["reason"] == "too_large"
    assert _inbox(tmp_path) == []


def test_an_upload_that_would_eat_the_disk_headroom_is_refused_before_writing(client, tmp_path, monkeypatch):
    import shutil as _sh
    real = _sh.disk_usage
    total = 3 * 1024 ** 3
    # A small 3 GB data volume with 600 MB free: the headroom is max(512 MB, 15 % = 460 MB).
    monkeypatch.setattr(att.shutil, "disk_usage",
                        lambda p: real(p)._replace(total=total, free=600 * 1024 ** 2))
    r = client.post("/api/files/upload?source=chat", content=b"%PDF-1.4" + b"x" * (200 * 1024),
                    headers={"Content-Type": "application/octet-stream", "X-File-Name": "a.pdf"})
    assert r.status_code == 200, "200 KB on 600 MB free keeps the headroom"
    monkeypatch.setattr(att.shutil, "disk_usage",
                        lambda p: real(p)._replace(total=total, free=512 * 1024 ** 2 + 100 * 1024))
    r = client.post("/api/files/upload?source=chat", content=b"%PDF-1.4" + b"x" * (200 * 1024),
                    headers={"Content-Type": "application/octet-stream", "X-File-Name": "b.pdf"})
    assert r.status_code == 507 and r.json()["reason"] == "disk_full"
    assert _inbox(tmp_path) == []


def test_removing_the_chip_detaches_it_from_the_turn(client):
    eid = _raw(client, "n.txt", b"hello").json()["episode_id"]
    assert [a["episode_id"] for a in att.current()] == [eid]
    assert client.delete(f"/api/files/attached/{eid}").json() == {"ok": True, "detached": True}
    assert att.current() == []


def test_the_limits_the_composer_reads_are_the_declared_ones(client):
    got = client.get("/api/files/limits").json()
    declared = att.limits()
    assert got == {k: declared[k] for k in got} and set(got) >= {"max_file_bytes", "max_files_per_message",
                                                                "max_message_bytes", "upload_stall_s"}


def test_several_files_are_independent_one_refused_the_others_kept(client):
    out = [_raw(client, n, b).status_code for n, b in
           (("a.txt", b"one"), ("evil.png", b"not a png"), ("c.md", b"three"))]
    assert out == [200, 415, 200]
    assert [a["name"] for a in att.current()] == ["c.md", "a.txt"]


# ── a REAL server: streaming and cancel ──────────────────────────────────────────────────────────────────────
_APP = """
import sys; sys.path.insert(0, {engine!r})
import uvicorn
from fastapi import FastAPI
from server.memory_routes import router
from memory import db
db.get_db()
app = FastAPI(); app.include_router(router)
uvicorn.run(app, host="127.0.0.1", port={port}, log_level="critical")
"""


@pytest.fixture
def live(tmp_path):
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    env = {**os.environ, "ZAELAR_DB": str(tmp_path / "zaelar.db"), "ZAELAR_EMBED_BACKEND": "hash"}
    proc = subprocess.Popen([sys.executable, "-c", _APP.format(engine=str(ENGINE), port=port)], cwd=ENGINE,
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        port_listening(port, timeout_s=30)
        yield port, tmp_path / "episodic" / ".incoming"
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def _start(port, name, total):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    c.putrequest("POST", "/api/files/upload?source=chat")
    c.putheader("Content-Type", "application/octet-stream")
    c.putheader("X-File-Name", name)
    c.putheader("Content-Length", str(total))
    c.endheaders()
    return c


def _parts(inbox: Path) -> list[Path]:
    return list(inbox.glob("*.part")) if inbox.exists() else []


def test_the_body_reaches_the_disk_while_it_is_still_arriving(live):
    """STREAMED, not read whole: half the body is on disk while the other half has not been sent yet. A handler
    that awaited the whole body (or `UploadFile.read()`) would have written nothing at this point."""
    port, inbox = live
    chunk, n = 1024 * 1024, 8
    c = _start(port, "long.txt", chunk * n)
    for _ in range(n // 2):
        c.send(b"a" * chunk)
    until_sync(lambda: any(p.stat().st_size >= chunk * 2 for p in _parts(inbox)),
               "the first half of the body to be on disk before the second is sent", timeout_s=10)
    for _ in range(n // 2):
        c.send(b"a" * chunk)
    r = c.getresponse()
    assert r.status == 200, r.read()
    assert _parts(inbox) == []


def test_a_cancelled_upload_leaves_nothing_behind(live):
    port, inbox = live
    chunk = 1024 * 1024
    c = _start(port, "gone.txt", chunk * 10)
    c.send(b"a" * chunk * 2)
    until_sync(lambda: bool(_parts(inbox)), "the upload to start landing on disk", timeout_s=10)
    c.sock.close()                                      # what the composer's × does: the request goes away
    until_sync(lambda: _parts(inbox) == [], "the partial file to be removed once the client is gone",
               timeout_s=10)
    assert not list((inbox.parent).glob("gone*")), "a cancelled file must not be adopted"


def test_files_are_read_one_at_a_time(monkeypatch, tmp_path):
    """A message's files arrive in parallel; their READING does not. The worst bounded read (a PNG at the pixel
    cap) measured +266 MB of RSS, and eight at once +863 MB without this — serialized, +303 MB."""
    import threading
    live, worst = [0], [0]
    gate = threading.Lock()

    def slow_read(path, kind):
        with gate:
            live[0] += 1
            worst[0] = max(worst[0], live[0])
        import time as _t
        _t.sleep(0.05)
        with gate:
            live[0] -= 1
        return "ok", ""

    monkeypatch.setattr(att, "read", slow_read)
    ts = [threading.Thread(target=att.process, args=(tmp_path / f"{i}.txt", "text", tmp_path / f"{i}.jpg"))
          for i in range(6)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(timeout=10)
    assert worst[0] == 1, f"{worst[0]} files were read at the same time"


def test_an_upload_in_flight_counts_against_the_headroom_of_the_others(client, tmp_path, monkeypatch):
    """Free space only shows what is on disk: what another upload has announced and not written yet must count."""
    import shutil as _sh
    real = _sh.disk_usage
    monkeypatch.setattr(att.shutil, "disk_usage",
                        lambda p: real(p)._replace(total=3 * 1024 ** 3, free=600 * 1024 ** 2))
    other = att.Reservation(100 * 1024 ** 2)        # an upload still arriving, 100 MB to go
    try:
        r = _raw(client, "a.pdf", b"%PDF-1.4" + b"x" * (200 * 1024))
        assert r.status_code == 507 and r.json()["reason"] == "disk_full", (
            "600 MB free minus the 100 MB another upload still owes leaves less than the 512 MB headroom")
    finally:
        other.release()
    r = _raw(client, "a.pdf", b"%PDF-1.4" + b"x" * (200 * 1024))
    assert r.status_code == 200, "with the other upload done the same file fits"
    assert att.reserved_bytes() == 0, "a finished or refused upload must give its reservation back"


def test_a_reading_that_runs_out_of_time_leaves_no_thumbnail_behind(client, tmp_path, monkeypatch):
    import threading
    import time as _t
    done = threading.Event()
    left: list[Path] = []

    def slow_process(path, kind, thumb_dest):
        _t.sleep(0.6)                                # past the clock below
        thumb_dest.write_bytes(b"late thumbnail")
        left.append(thumb_dest)
        done.set()
        return "", "", True

    monkeypatch.setattr(att, "process", slow_process)
    monkeypatch.setitem(att._limits_cache, "process_timeout_s", 0.2)
    r = _raw(client, "slow.png", _png())
    assert r.status_code == 200 and r.json()["thumb"] is None
    until_sync(done.is_set, "the slow reader to finish", timeout_s=5)
    until_sync(lambda: left and not left[0].exists(), "the late thumbnail to be removed", timeout_s=5)
