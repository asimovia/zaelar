"""Read and verify `minisign` public keys and signatures (the format of https://jedisct1.github.io/minisign/).

THE FORMAT, as far as a verifier needs it:

    public key   "untrusted comment: …"  then  base64( "Ed" | key_id[8] | ed25519_public_key[32] )
    signature    "untrusted comment: …"
                 base64( "ED" | key_id[8] | ed25519_signature[64] )      over BLAKE2b-512(file)
                 "trusted comment: <text>"
                 base64( ed25519_signature[64] )                         over signature[64] | <text>

Only the PREHASHED algorithm ("ED", minisign's default since 0.10) is accepted: the release workflow always
produces it, and refusing the legacy "Ed" form removes a second code path nobody exercises. The trusted comment
is covered by the second signature, so it cannot be edited without the key; the untrusted comments can and are
never read.

Every failure is a `SignatureError` with a sentence a person can act on. Nothing here returns "probably fine".
"""
from __future__ import annotations

import base64
import binascii
import hashlib
from dataclasses import dataclass

from . import ed25519

_KEY_ALG = b"Ed"
_PREHASHED = b"ED"


class SignatureError(Exception):
    """The signature is missing, malformed, made by another key, or does not match the bytes."""


@dataclass(frozen=True)
class PublicKey:
    key_id: bytes
    key: bytes

    @property
    def key_id_hex(self) -> str:
        # minisign prints the id as the little-endian 64-bit number it is.
        return self.key_id[::-1].hex().upper()


def _b64(text: str, what: str) -> bytes:
    try:
        return base64.b64decode(text.strip(), validate=True)
    except (binascii.Error, ValueError) as e:
        raise SignatureError(f"{what} is not valid base64") from e


def parse_public_key(text: str) -> PublicKey:
    """A public key file (comment line + key line) or the bare base64 key line `minisign -P` takes."""
    lines = [ln.strip() for ln in str(text).splitlines() if ln.strip()]
    lines = [ln for ln in lines if not ln.lower().startswith("untrusted comment:")]
    if len(lines) != 1:
        raise SignatureError("the public key must be exactly one base64 line")
    raw = _b64(lines[0], "the public key")
    if len(raw) != 42 or raw[:2] != _KEY_ALG:
        raise SignatureError("the public key is not a minisign Ed25519 key")
    return PublicKey(key_id=raw[2:10], key=raw[10:])


def verify(data: bytes, signature_text: str, keys: list[PublicKey]) -> str:
    """Verify `data` against a `.minisig` text with any of the trusted `keys`; return the trusted comment.

    Raises `SignatureError` on anything short of a complete, valid signature by one of `keys`."""
    if not keys:
        raise SignatureError("no trusted public key to verify with")
    lines = str(signature_text or "").splitlines()
    if len(lines) < 4:
        raise SignatureError("the signature file is incomplete")
    if not lines[0].lower().startswith("untrusted comment:"):
        raise SignatureError("the signature file does not start with a comment line")
    raw = _b64(lines[1], "the signature")
    if len(raw) != 74:
        raise SignatureError("the signature has the wrong length")
    algorithm, key_id, signature = raw[:2], raw[2:10], raw[10:]
    if algorithm != _PREHASHED:
        raise SignatureError("only prehashed (ED) minisign signatures are accepted")
    prefix = "trusted comment: "
    if not lines[2].startswith(prefix):
        raise SignatureError("the signature file has no trusted comment")
    trusted_comment = lines[2][len(prefix):]
    global_signature = _b64(lines[3], "the comment signature")
    if len(global_signature) != 64:
        raise SignatureError("the comment signature has the wrong length")

    key = next((k for k in keys if k.key_id == key_id), None)
    if key is None:
        raise SignatureError(f"signed by an unknown key ({key_id[::-1].hex().upper()}), not by a trusted one")
    digest = hashlib.blake2b(bytes(data), digest_size=64).digest()
    if not ed25519.verify(key.key, digest, signature):
        raise SignatureError("the signature does not match the file")
    if not ed25519.verify(key.key, signature + trusted_comment.encode("utf-8"), global_signature):
        raise SignatureError("the trusted comment was altered")
    return trusted_comment
