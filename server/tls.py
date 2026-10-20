"""server/tls.py — the per-install HTTPS certificate, read by the server (2026-10-20).

`scripts/tls_cert.py` (a stdlib-only launcher script, not a package) owns the decision and the renewal window; this
loads it by path so the server and the status read the SAME rules. The server opens its HTTPS listener only with a
certificate that has not expired: an expired one does not degrade to «less secure», it turns every visit into
the browser's full-page «connection is not private» — measured on the operator's machine, 2026-10-20 16:37, with
the shared certificate of the pre-mkcert era. Without a usable certificate the engine is plain HTTP on localhost,
which browsers treat as a secure context (microphone included) and which never leaves the machine.
"""
from __future__ import annotations

import importlib.util
import os
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load():
    spec = importlib.util.spec_from_file_location("tls_cert", os.path.join(ROOT, "scripts", "tls_cert.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def pair() -> tuple[str, str]:
    cert_dir = os.getenv("ZAELAR_TLS_CERT_DIR", os.path.join(ROOT, "certs", "local.zaelar.com"))
    return os.path.join(cert_dir, "fullchain.pem"), os.path.join(cert_dir, "privkey.pem")


def usable(certfile: str, keyfile: str, *, now: float | None = None, tls=None) -> bool:
    """Both files present and the certificate not past its notAfter. Unreadable counts as usable: the TLS layer is
    the authority on a broken file (same rule as `tls_cert._expired`)."""
    if not (os.path.isfile(certfile) and os.path.isfile(keyfile)):
        return False
    not_after = (tls or load()).expires_at(certfile)
    return not_after is None or not_after > (time.time() if now is None else now)
