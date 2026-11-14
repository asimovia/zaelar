"""A2A identity: the agent's Ed25519 key, its network DID, MeshKore-Sig headers and end-to-end encryption.

The network DID is ``did:key:<pubkey_b64>`` (standard base64 of the raw 32-byte Ed25519 public key) — the form the
MeshKore people network uses. It is NOT the multibase ``did:key:z6Mk…`` that the work-cluster connector presents; both
come from the same key file.

E2E (D5): each Ed25519 key is mapped to its X25519 twin (RFC 7748 birational map for the public half, the RFC 8032
expanded scalar for the private half). Two agents derive the same shared secret from static-static ECDH; every
envelope gets a fresh random nonce and its own HKDF salt (the envelope id), so no key/nonce pair is ever reused.
"""
from __future__ import annotations

import base64
import hashlib
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

SIG_SKEW_S = 120          # MeshKore-Sig clock tolerance (server side is the same)
_P = 2 ** 255 - 19        # curve25519 field prime
_HKDF_INFO = b"a2a/1 envelope"


class BadSignature(Exception):
    pass


class BadCiphertext(Exception):
    pass


def b64e(b: bytes) -> str:
    return base64.b64encode(b).decode()


def b64d(s: str) -> bytes:
    s = s.replace("-", "+").replace("_", "/")
    return base64.b64decode(s + "=" * (-len(s) % 4))


def did_of(pub_raw: bytes) -> str:
    return "did:key:" + b64e(pub_raw)


def pubkey_of(did: str) -> bytes:
    """`did:key:<b64>` → raw 32-byte Ed25519 public key. Raises ValueError on anything else."""
    if not isinstance(did, str) or not did.startswith("did:key:"):
        raise ValueError("not a did:key")
    raw = b64d(did[len("did:key:"):])
    if len(raw) != 32:
        raise ValueError("did:key must carry a 32-byte Ed25519 key")
    return raw


def short(did: str) -> str:
    """The only form of a PEER's DID that observability may carry: 8 chars of the key."""
    return (did or "")[len("did:key:"):][:8] if (did or "").startswith("did:key:") else (did or "")[:8]


# ── Ed25519 → X25519 ─────────────────────────────────────────────────────────────────────────────────────────────

def _x25519_pub_from_ed(pub_raw: bytes) -> X25519PublicKey:
    y = int.from_bytes(pub_raw, "little") & ((1 << 255) - 1)
    u = (1 + y) * pow((1 - y) % _P, _P - 2, _P) % _P
    return X25519PublicKey.from_public_bytes(u.to_bytes(32, "little"))


def _x25519_priv_from_ed(seed: bytes) -> X25519PrivateKey:
    h = bytearray(hashlib.sha512(seed).digest()[:32])
    h[0] &= 248
    h[31] &= 127
    h[31] |= 64
    return X25519PrivateKey.from_private_bytes(bytes(h))


@dataclass
class Identity:
    """One agent's key. `sign`/`verify` for envelopes, `mk_sig` for HTTP, `seal`/`open` for E2E."""

    _priv: Ed25519PrivateKey

    # construction --------------------------------------------------------------------------------------------
    @classmethod
    def generate(cls) -> "Identity":
        return cls(Ed25519PrivateKey.generate())

    @classmethod
    def from_pem(cls, pem: bytes) -> "Identity":
        key = serialization.load_pem_private_key(pem, password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise ValueError("not an Ed25519 key")
        return cls(key)

    @classmethod
    def from_file(cls, path: Path) -> "Identity":
        return cls.from_pem(Path(path).read_bytes())

    @classmethod
    def engine_default(cls) -> "Identity":
        """The engine's own MeshKore key (one identity per install, shared with the cluster connector — I8: the only
        import from connectors/meshkore). `A2A_KEY_FILE` overrides it (two agents on one machine, the lab)."""
        env = os.getenv("A2A_KEY_FILE")
        if env:
            p = Path(env)
            if not p.exists():
                p.parent.mkdir(parents=True, exist_ok=True)
                k = Ed25519PrivateKey.generate()
                p.write_bytes(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                              serialization.NoEncryption()))
                os.chmod(p, 0o600)
            return cls.from_file(p)
        from connectors.meshkore import identity as mk_identity
        return cls(mk_identity._load_or_create())

    # public parts --------------------------------------------------------------------------------------------
    @property
    def pub_raw(self) -> bytes:
        return self._priv.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)

    @property
    def pub_b64(self) -> str:
        return b64e(self.pub_raw)

    @property
    def did(self) -> str:
        return did_of(self.pub_raw)

    # signatures ----------------------------------------------------------------------------------------------
    def sign(self, data: bytes) -> str:
        return b64e(self._priv.sign(data))

    def mk_sig(self, method: str, path: str, body: str = "", ts: int | None = None, nonce: str | None = None) -> str:
        """`MeshKore-Sig: v1 <pubkey_b64> <ts> <nonce> <sig_b64>` over `MK1\\nMETHOD\\npath\\nsha256hex(body)\\nts\\nnonce`.
        `path` is the URL path exactly as sent (DIDs percent-encoded), without the query string."""
        ts = int(time.time()) if ts is None else ts
        nonce = nonce or secrets.token_hex(16)
        return f"v1 {self.pub_b64} {ts} {nonce} {self.sign(mk_canonical(method, path, body, ts, nonce))}"

    # E2E -----------------------------------------------------------------------------------------------------
    def _x_priv(self) -> X25519PrivateKey:
        seed = self._priv.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                                        serialization.NoEncryption())
        return _x25519_priv_from_ed(seed)

    def _key_with(self, peer_did: str, salt: str) -> bytes:
        shared = self._x_priv().exchange(_x25519_pub_from_ed(pubkey_of(peer_did)))
        return HKDF(algorithm=hashes.SHA256(), length=32, salt=salt.encode(), info=_HKDF_INFO).derive(shared)

    def seal(self, peer_did: str, plaintext: bytes, salt: str, aad: bytes = b"") -> dict:
        nonce = os.urandom(12)
        ct = ChaCha20Poly1305(self._key_with(peer_did, salt)).encrypt(nonce, plaintext, aad)
        return {"alg": "x25519-chacha20poly1305", "n": b64e(nonce), "ct": b64e(ct)}

    def open(self, peer_did: str, sealed: dict, salt: str, aad: bytes = b"") -> bytes:
        try:
            return ChaCha20Poly1305(self._key_with(peer_did, salt)).decrypt(b64d(sealed["n"]), b64d(sealed["ct"]), aad)
        except (InvalidTag, KeyError, ValueError, TypeError) as e:
            raise BadCiphertext(str(e)) from None


def mk_canonical(method: str, path: str, body: str, ts: int, nonce: str) -> bytes:
    bh = hashlib.sha256(body.encode()).hexdigest()
    return f"MK1\n{method.upper()}\n{path}\n{bh}\n{ts}\n{nonce}".encode()


def verify(did_or_pub: str | bytes, data: bytes, sig_b64: str) -> None:
    raw = did_or_pub if isinstance(did_or_pub, bytes) else (
        pubkey_of(did_or_pub) if did_or_pub.startswith("did:key:") else b64d(did_or_pub))
    try:
        Ed25519PublicKey.from_public_bytes(raw).verify(b64d(sig_b64), data)
    except (InvalidSignature, ValueError) as e:
        raise BadSignature(str(e) or "bad signature") from None


def verify_mk_sig(header: str | None, method: str, path: str, body: str, expected_pub_b64: str | None = None,
                  now: int | None = None, seen_nonces=None) -> str:
    """Check a MeshKore-Sig header; returns the signer's pubkey (b64). `expected_pub_b64` pins the signer (the wake
    push must come from the network's key). Raises BadSignature."""
    parts = (header or "").split()
    if len(parts) != 5 or parts[0] != "v1":
        raise BadSignature("malformed MeshKore-Sig")
    _, pub, ts_s, nonce, sig = parts
    if expected_pub_b64 and pub != expected_pub_b64:
        raise BadSignature("unexpected signer")
    try:
        ts = int(ts_s)
    except ValueError:
        raise BadSignature("bad ts") from None
    if abs((int(time.time()) if now is None else now) - ts) > SIG_SKEW_S:
        raise BadSignature("stale signature")
    if seen_nonces is not None and nonce in seen_nonces:
        raise BadSignature("replayed nonce")
    verify(pub, mk_canonical(method, path, body, ts, nonce), sig)
    if seen_nonces is not None:                  # recorded only once the signature held: junk never fills the store
        remember = getattr(seen_nonces, "remember", None)
        remember(nonce, ts) if remember else seen_nonces.add(nonce)
    return pub


class NonceWindow:
    """The nonces of VERIFIED signatures, each kept exactly as long as its timestamp can still pass the skew check
    (`ts + SIG_SKEW_S`). Never cleared wholesale: at `cap` live entries a new signature is refused instead."""

    def __init__(self, clock=time.time, cap: int = 4096):
        self._by_nonce: dict[str, int] = {}
        self._clock, self._cap = clock, cap

    def _prune(self) -> None:
        cut = int(self._clock()) - SIG_SKEW_S
        for n in [n for n, ts in self._by_nonce.items() if ts < cut]:
            del self._by_nonce[n]

    def __contains__(self, nonce: str) -> bool:
        return nonce in self._by_nonce

    def __len__(self) -> int:
        return len(self._by_nonce)

    def remember(self, nonce: str, ts: int) -> None:
        self._prune()
        if len(self._by_nonce) >= self._cap:
            raise BadSignature("nonce window full")
        self._by_nonce[nonce] = int(ts)
