"""Ed25519 signature VERIFICATION in pure Python (RFC 8032 §5.1.7) — verify only, never sign.

WHY IT IS WRITTEN OUT HERE AND NOT IMPORTED. The headless daemon is standard library only, and CI proves it on a
bare runner before anything is installed. The update client must work in every build the daemon ships — the
zipapp included — so it cannot lean on `cryptography` or `pynacl` (neither is in `daemon/requirements.txt`, and
adding a compiled dependency to check one signature a day is the wrong trade). Verification needs no secret and
no constant-time arithmetic: everything it handles is public (the key, the message, the signature), so the
textbook big-integer formulas are correct and sufficient. Speed is irrelevant at one check a day (~10 ms here).

What it does NOT do: generate keys or sign. Signing happens in CI with the reference `minisign` tool; this module
only answers "did the holder of this public key sign these bytes?". Its correctness is pinned by the RFC 8032
test vectors and by real `minisign` signatures in the test suite.
"""
from __future__ import annotations

import hashlib

_P = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_SQRT_M1 = pow(2, (_P - 1) // 4, _P)

# Points are extended homogeneous coordinates (X, Y, Z, T) with x = X/Z, y = Y/Z, x*y = T/Z.


def _add(a, b):
    x1, y1, z1, t1 = a
    x2, y2, z2, t2 = b
    aa = (y1 - x1) * (y2 - x2) % _P
    bb = (y1 + x1) * (y2 + x2) % _P
    cc = t1 * 2 * _D * t2 % _P
    dd = z1 * 2 * z2 % _P
    e, f, g, h = bb - aa, dd - cc, dd + cc, bb + aa
    return (e * f % _P, g * h % _P, f * g % _P, e * h % _P)


def _mul(s: int, point):
    q = (0, 1, 1, 0)   # the neutral element
    while s > 0:
        if s & 1:
            q = _add(q, point)
        point = _add(point, point)
        s >>= 1
    return q


def _equal(a, b) -> bool:
    x1, y1, z1, _ = a
    x2, y2, z2, _ = b
    return (x1 * z2 - x2 * z1) % _P == 0 and (y1 * z2 - y2 * z1) % _P == 0


def _recover_x(y: int, sign: int) -> int | None:
    if y >= _P:
        return None
    x2 = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P)
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P != 0:
        x = x * _SQRT_M1 % _P
    if (x * x - x2) % _P != 0:
        return None
    if (x & 1) != sign:
        x = _P - x
    return x


def _decompress(raw: bytes):
    if len(raw) != 32:
        return None
    y = int.from_bytes(raw, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    if x is None:
        return None
    return (x, y, 1, x * y % _P)


_GY = 4 * pow(5, _P - 2, _P) % _P
_G = (_recover_x(_GY, 0), _GY, 1, _recover_x(_GY, 0) * _GY % _P)


def verify(public_key: bytes, message: bytes, signature: bytes) -> bool:
    """True only when `signature` is a valid Ed25519 signature of `message` under `public_key`. Never raises on
    malformed input: anything that is not a well-formed key or signature is simply not a valid signature."""
    if not isinstance(public_key, (bytes, bytearray)) or not isinstance(signature, (bytes, bytearray)):
        return False
    if len(public_key) != 32 or len(signature) != 64:
        return False
    a = _decompress(bytes(public_key))
    if a is None:
        return False
    r_raw = bytes(signature[:32])
    r = _decompress(r_raw)
    if r is None:
        return False
    s = int.from_bytes(signature[32:], "little")
    if s >= _L:
        return False
    h = int.from_bytes(hashlib.sha512(r_raw + bytes(public_key) + bytes(message)).digest(), "little") % _L
    return _equal(_mul(s, _G), _add(r, _mul(h, a)))
