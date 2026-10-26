"""V2-809 — measures the chat-attachment limits declared in `config/attachments.default.json`.

Not a test: a MEASUREMENT you run when a limit changes. A real uvicorn serves the upload door; the largest file
of each kind the limits allow is uploaded through it (streamed, the way the composer sends it) while two probes
run beside it:

  · the server process's RSS, sampled every 20 ms (the delta over its idle RSS is what an upload costs);
  · an event-loop probe — a request to the same server every 50 ms — whose worst latency is how long the voice
    loop would have waited behind the upload and its processing.

Run:  ./.venv/bin/python tests/infrastructure/e2e/bench_chat_attachments.py [--keep DIR]

No model is called (the server runs with no image-reader rung): an image is still decoded and downscaled, which
is the bounded work being measured; the request to the reading model is network time, not RAM.
"""
from __future__ import annotations

import argparse
import http.client
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ENGINE))

from tests.waiting import port_listening  # noqa: E402

_APP = """
import sys; sys.path.insert(0, {engine!r})
import uvicorn
from fastapi import FastAPI
from server.memory_routes import router
from memory import db
from files import attachments
attachments._image_rungs = lambda: []     # no paid call from a bench: the decode and downscale are still measured
db.get_db()
app = FastAPI(); app.include_router(router)
uvicorn.run(app, host="127.0.0.1", port={port}, log_level="critical")
"""
MB = 1024 * 1024


def _limits() -> dict:
    return json.loads((ENGINE / "config" / "attachments.default.json").read_text())


def _pdf(path: Path, pages: int, pad_bytes: int) -> None:
    """A text PDF of `pages` pages, padded with an unreferenced binary stream up to the size cap."""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", None, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for i in range(pages):
        s = f"BT /F1 11 Tf 72 720 Td (Page {i}: the quarterly figures and the notes of the meeting) Tj ET"
        objs.append(f"<< /Length {len(s)} >>\nstream\n{s}\nendstream")
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {len(objs)} 0 R "
                    f"/Resources << /Font << /F1 3 0 R >> >> >>")
        kids.append(f"{len(objs)} 0 R")
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {pages} >>"
    with open(path, "wb") as out:
        offsets = []
        out.write(b"%PDF-1.4\n")
        for n, body in enumerate(objs, 1):
            offsets.append(out.tell())
            out.write(f"{n} 0 obj\n{body}\nendobj\n".encode())
        offsets.append(out.tell())
        out.write(f"{len(objs) + 1} 0 obj\n<< /Length {pad_bytes} >>\nstream\n".encode())
        left = pad_bytes
        while left > 0:
            n = min(left, 8 * MB)
            out.write(os.urandom(n))
            left -= n
        out.write(b"\nendstream\nendobj\n")
        xref = out.tell()
        out.write(f"xref\n0 {len(offsets) + 1}\n0000000000 65535 f \n".encode())
        for off in offsets:
            out.write(f"{off:010d} 00000 n \n".encode())
        out.write(f"trailer\n<< /Size {len(offsets) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())


def _image(path: Path, w: int, h: int, fmt: str) -> None:
    """Noise, so the file is as heavy as a real photo of that size (a flat colour compresses to nothing)."""
    from PIL import Image
    tile = Image.frombytes("RGB", (512, 512), os.urandom(512 * 512 * 3))
    im = Image.new("RGB", (w, h))
    for x in range(0, w, 512):
        for y in range(0, h, 512):
            im.paste(tile, (x, y))
    im.save(path, fmt, quality=92) if fmt == "JPEG" else im.save(path, fmt, compress_level=1)


def _make(d: Path, lim: dict) -> list[tuple[str, Path]]:
    cap = int(lim["max_file_bytes"])
    files = []
    p = d / "biggest.pdf"; _pdf(p, 3000, cap - 3 * MB); files.append(("pdf", p))
    p = d / "biggest.txt"
    with open(p, "wb") as fh:
        line = b"a line of a long export, with numbers 12345 and words\n"
        fh.write(line * ((cap - MB) // len(line)))
    files.append(("text", p))
    side = int((int(lim["max_image_pixels"]) * 0.96) ** 0.5)
    p = d / "biggest.jpg"; _image(p, side, side, "JPEG"); files.append(("image-jpeg", p))
    p = d / "biggest.png"; _image(p, side, side, "PNG"); files.append(("image-png", p))
    return files


def _upload(port: int, path: Path) -> tuple[int, float, dict]:
    size = path.stat().st_size
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=600)
    t0 = time.monotonic()
    c.putrequest("POST", "/api/files/upload?source=chat")
    c.putheader("Content-Type", "application/octet-stream")
    c.putheader("X-File-Name", path.name)
    c.putheader("Content-Length", str(size))
    c.endheaders()
    with open(path, "rb") as fh:
        while True:
            b = fh.read(MB)
            if not b:
                break
            c.send(b)
    t_sent = time.monotonic()
    r = c.getresponse()
    body = json.loads(r.read() or b"{}")
    return r.status, time.monotonic() - t0, {"sent_s": round(t_sent - t0, 2), **body}


class _Server:
    """A fresh server per scenario, so one scenario's retained allocations never hide the next one's cost."""

    def __init__(self, data: Path):
        import psutil
        s = socket.socket(); s.bind(("127.0.0.1", 0)); self.port = s.getsockname()[1]; s.close()
        env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")}
        env.update({"ZAELAR_DB": str(data / "zaelar.db"), "ZAELAR_EMBED_BACKEND": "hash"})
        self.proc = subprocess.Popen([sys.executable, "-c", _APP.format(engine=str(ENGINE), port=self.port)],
                                     cwd=ENGINE, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        port_listening(self.port, timeout_s=60)
        time.sleep(1.0)
        self.ps = psutil.Process(self.proc.pid)

    def close(self):
        self.proc.terminate()
        self.proc.wait(timeout=10)


def _measure(srv: _Server, paths: list[Path]) -> dict:
    """Upload `paths` at once (one thread each) while sampling RSS and probing the event loop."""
    import psutil
    idle = srv.ps.memory_info().rss
    peak, lat, stop = [idle], [], threading.Event()

    def sample():
        while not stop.is_set():
            try:
                peak.append(srv.ps.memory_info().rss)
            except psutil.Error:
                return
            time.sleep(0.02)

    def probe():
        while not stop.is_set():
            t = time.monotonic()
            try:
                c = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=30)
                c.request("GET", "/api/files/limits")
                c.getresponse().read()
                c.close()
            except OSError:
                pass
            lat.append(time.monotonic() - t)
            time.sleep(0.05)

    probes = [threading.Thread(target=sample, daemon=True), threading.Thread(target=probe, daemon=True)]
    for t in probes:
        t.start()
    outs: list = []
    t0 = time.monotonic()
    ups = [threading.Thread(target=lambda p=p: outs.append(_upload(srv.port, p)), daemon=True) for p in paths]
    for u in ups:
        u.start()
    for u in ups:
        u.join(timeout=600)
    took = time.monotonic() - t0
    stop.set()
    for t in probes:
        t.join(timeout=5)
    lat.sort()
    return {"status": sorted({o[0] for o in outs}), "read": [o[2].get("read") for o in outs],
            "total_s": round(took, 2), "rss_idle_mb": round(idle / MB),
            "rss_peak_delta_mb": round((max(peak) - idle) / MB),
            "loop_p95_ms": round(lat[max(0, int(len(lat) * 0.95) - 1)] * 1000) if lat else None,
            "loop_max_ms": round(lat[-1] * 1000) if lat else None, "probes": len(lat)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", default="")
    args = ap.parse_args()
    lim = _limits()
    work = Path(args.keep or tempfile.mkdtemp(prefix="zaelar-attach-bench-"))
    work.mkdir(parents=True, exist_ok=True)
    print(f"making the largest allowed files in {work} …", flush=True)
    files = _make(work, lim)
    scenarios = [(k, [p]) for k, p in files]
    # A message's files are uploaded IN PARALLEL by the composer: the worst message is every heavy file at once.
    worst = [p for _k, p in files] + [p for k, p in files if k.startswith("image")] * 2
    scenarios.append((f"parallel x{len(worst)}", worst))
    results = []
    for n, (kind, paths) in enumerate(scenarios):
        data = work / f"data-{n}"
        data.mkdir(exist_ok=True)
        srv = _Server(data)
        try:
            row = {"kind": kind, "file_mb": round(sum(p.stat().st_size for p in paths) / MB, 1),
                   **_measure(srv, paths)}
        finally:
            srv.close()
        results.append(row)
        print(json.dumps(row), flush=True)
    print(json.dumps({"limits": {k: lim[k] for k in ("max_file_bytes", "max_image_pixels", "max_pdf_pages",
                                                       "max_text_read_bytes", "chunk_bytes")},
                      "results": results}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
