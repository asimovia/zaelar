"""memory/vault.py — BÓVEDA DE SECRETOS del operador (V2-060, cifrado end-to-end).

Guarda los secretos del USUARIO (contraseña de Netflix, IBAN/tarjeta, nº de cuenta cripto, private key de un
wallet) de forma que **NUNCA estén en claro** — ni en local ni en la nube. Es una pieza AUTO-CONTENIDA del
substrato de memoria: depende solo de `pynacl`, `memory.db` y `memory.writer` (el escritor único). NO importa
`nucleo` ni toca la ruta caliente de voz.

## Modelo cripto (detalle en `zaelar-security.md` / iniciativa V2-060)

- **Asimétrico (sealed box de libsodium).** Un par de claves: la **pública `PK`** vive EN CLARO en `vault_meta`
  (sella secretos nuevos → **escribir NO pide desbloqueo**); la **privada `SK`** es secreta y solo hace falta para
  **LEER**.
- **`SK` se guarda ENVUELTA por N métodos de desbloqueo** (patrón sobre / key-wrapping): cada método cifra la MISMA
  `SK` por su lado. Hoy: **passphrase** (`Argon2id(passphrase, salt)` → `SecretBox`). Mañana (F3): **passkey**
  (WebAuthn PRF → misma envoltura). Añadir un método = un sobre nuevo, sin re-cifrar los secretos. Rotar la
  passphrase = re-cifrar SOLO su sobre.
- **Storage partido.** El VALOR va cifrado y opaco en `vault_secrets` (keyed por el id de una píldora-etiqueta); la
  ETIQUETA ("contraseña de Netflix") vive en claro y BUSCABLE en `memories` (`meta.vault=1`) → el recall la
  encuentra pero JAMÁS ve el valor.

## Invariantes duros

- La **passphrase** y la **clave privada `SK`** JAMÁS se persisten en claro, ni entran en un prompt de LLM, ni en
  un worker, ni en logs, ni en `state`, ni en una píldora. `SK` solo vive **desenvuelta en RAM** mientras la sesión
  está desbloqueada (modo cómodo) y se **borra** al bloquear / expirar / en modo estricto.
- **Escribir un secreto no requiere desbloqueo** (usa `PK`); **leerlo sí** (requiere `SK`).
- El `status()` para el frontend es **redactado**: expone presencia/estado, jamás material de clave.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from base64 import b64decode, b64encode

from nacl import pwhash, utils
from nacl.exceptions import CryptoError
from nacl.public import PrivateKey, PublicKey, SealedBox
from nacl.secret import SecretBox

from . import db as _db
from . import writer as _writer

# Parámetros del KDF (Argon2id). MODERATE = buen equilibrio interactivo (≈0.7s en un portátil) sin castigar el
# desbloqueo por voz. Se persisten por-sobre para poder subirlos en el futuro sin romper bóvedas viejas.
_OPS = pwhash.argon2id.OPSLIMIT_MODERATE
_MEM = pwhash.argon2id.MEMLIMIT_MODERATE
_SALTBYTES = pwhash.argon2id.SALTBYTES
_KEYBYTES = SecretBox.KEY_SIZE

# TTL de la clave desenvuelta en RAM (modo cómodo). En modo estricto el llamador usa hold=False (no se cachea).
import os as _os

_SESSION_TTL = float(_os.getenv("ZAELAR_VAULT_SESSION_TTL", "900"))   # s

_session_lock = threading.Lock()
_session: dict = {"sk": None, "exp": 0.0}


# ── errores ───────────────────────────────────────────────────────────────────────────────────────────────
class VaultError(Exception):
    """Fallo genérico de la bóveda."""


class VaultLocked(VaultError):
    """Se pidió leer un secreto pero la bóveda no está desbloqueada (falta la passphrase/passkey)."""


class WrongPassphrase(VaultError):
    """La passphrase (o el material de desbloqueo) no abre la clave privada."""


def _msg(key: str, default: str, **params) -> str:
    """An error text the vault modal shows VERBATIM, in the instance language (pack `ui`, English fallback).
    Resolved when raised, so the exception carries the sentence the screen will print."""
    from i18n import runtime as _rt
    out = _rt.text(key, default=default)
    for k, v in params.items():
        out = out.replace("{" + k + "}", str(v))
    return out


# ── helpers de KDF / envoltura ──────────────────────────────────────────────────────────────────────────────
def _derive_kek(passphrase: str, salt: bytes, ops: int, mem: int) -> bytes:
    """Argon2id(passphrase, salt) → clave de 32 bytes que envuelve/desenvuelve la privada."""
    return pwhash.argon2id.kdf(_KEYBYTES, passphrase.encode("utf-8"), salt, opslimit=ops, memlimit=mem)


def _passphrase_wrap(sk_bytes: bytes, passphrase: str) -> dict:
    """Crea un sobre 'passphrase' que envuelve `sk_bytes`."""
    salt = utils.random(_SALTBYTES)
    kek = _derive_kek(passphrase, salt, _OPS, _MEM)
    wrapped = SecretBox(kek).encrypt(sk_bytes)          # incluye nonce
    return {
        "method": "passphrase",
        "salt": b64encode(salt).decode(),
        "ops": _OPS,
        "mem": _MEM,
        "wrapped_sk": b64encode(bytes(wrapped)).decode(),
    }


def _unwrap_passphrase(wrap: dict, passphrase: str) -> bytes:
    """Desenvuelve `sk_bytes` de un sobre 'passphrase'. Lanza WrongPassphrase si no casa."""
    salt = b64decode(wrap["salt"])
    kek = _derive_kek(passphrase, salt, int(wrap.get("ops", _OPS)), int(wrap.get("mem", _MEM)))
    try:
        return SecretBox(kek).decrypt(b64decode(wrap["wrapped_sk"]))
    except CryptoError as e:  # MAC inválido = clave equivocada
        raise WrongPassphrase(_msg("vault.err.bad_passphrase", "Wrong passphrase")) from e


# ── metadatos de la bóveda (fila única) ───────────────────────────────────────────────────────────────────
def _load_meta() -> dict | None:
    row = _db.get_db().query_one("SELECT public_key, wraps FROM vault_meta WHERE id=1")
    if not row:
        return None
    return {"public_key": bytes(row["public_key"]), "wraps": json.loads(row["wraps"])}


def _save_meta(public_key: bytes, wraps: list[dict], *, create: bool) -> None:
    now = int(time.time())
    db = _db.get_db()
    payload = json.dumps(wraps, ensure_ascii=False)
    if create:
        db.execute("INSERT INTO vault_meta (id, public_key, wraps, created, updated) VALUES (1,?,?,?,?)",
                   (public_key, payload, now, now))
    else:
        db.execute("UPDATE vault_meta SET public_key=?, wraps=?, updated=? WHERE id=1",
                   (public_key, payload, now))


def exists() -> bool:
    """¿Hay una bóveda creada (con al menos un método de desbloqueo)?"""
    return _load_meta() is not None


# ── ciclo de vida: crear / desbloquear / bloquear ─────────────────────────────────────────────────────────
def create(passphrase: str) -> None:
    """Crea la bóveda: genera el par de claves, envuelve la privada con la passphrase, persiste. La privada NO se
    guarda en claro en ningún momento. Idempotencia dura: si ya existe, error (usar change_passphrase para rotar)."""
    if not passphrase or len(passphrase) < 4:
        raise VaultError(_msg("vault.err.short_passphrase", "The passphrase must be at least 4 characters long"))
    if exists():
        raise VaultError(_msg("vault.err.exists", "The vault already exists"))
    sk = PrivateKey.generate()
    pk_bytes = bytes(sk.public_key)
    wrap = _passphrase_wrap(bytes(sk), passphrase)
    _save_meta(pk_bytes, [wrap], create=True)


def _cache_sk(sk_bytes: bytes) -> None:
    with _session_lock:
        _session["sk"] = sk_bytes
        _session["exp"] = time.time() + _SESSION_TTL


def _cached_sk() -> bytes | None:
    with _session_lock:
        sk = _session["sk"]
        if sk is None:
            return None
        if time.time() > _session["exp"]:
            _session["sk"] = None
            return None
        return sk


def unlock(passphrase: str, *, hold: bool = True) -> bool:
    """Desbloquea la bóveda con la passphrase. Verifica desenvolviendo la privada y comprobando que su pública
    coincide con la almacenada (defensa en profundidad además del MAC del SecretBox). Si `hold` (modo cómodo),
    mantiene la privada en RAM `_SESSION_TTL` s; si no (modo estricto), la usa y descarta. Devuelve True/False;
    lanza VaultError si no hay bóveda."""
    meta = _load_meta()
    if not meta:
        raise VaultError(_msg("vault.err.no_vault", "No vault has been created"))
    for wrap in meta["wraps"]:
        if wrap.get("method") != "passphrase":
            continue
        try:
            sk_bytes = _unwrap_passphrase(wrap, passphrase)
        except WrongPassphrase:
            continue
        if bytes(PrivateKey(sk_bytes).public_key) != meta["public_key"]:
            continue  # sobre corrupto / no corresponde a esta bóveda
        if hold:
            _cache_sk(sk_bytes)
        return True
    return False


def lock() -> None:
    """Borra la clave privada de la RAM (bloquea la bóveda)."""
    with _session_lock:
        _session["sk"] = None
        _session["exp"] = 0.0


def is_unlocked() -> bool:
    return _cached_sk() is not None


# ── sellar / almacenar / abrir secretos ───────────────────────────────────────────────────────────────────
def seal(plaintext: str) -> bytes:
    """Cifra un texto a la clave PÚBLICA de la bóveda (NO requiere desbloqueo). Devuelve el ciphertext opaco."""
    meta = _load_meta()
    if not meta:
        raise VaultError(_msg("vault.err.no_vault", "No vault has been created"))
    return SealedBox(PublicKey(meta["public_key"])).encrypt(plaintext.encode("utf-8"))


def _open_with_sk(ciphertext: bytes, sk_bytes: bytes) -> str:
    _load_meta()   # kept for its read (fails the same way it always did); the binding was dead (F841)
    sk = PrivateKey(sk_bytes)
    return SealedBox(sk).decrypt(bytes(ciphertext)).decode("utf-8")


def store_secret(label: str, value: str, *, slot: str | None = None, sensitivity: str = "high",
                 kind: str = "fact") -> int:
    """Guarda un secreto: SELLA el valor (con la pública, sin desbloqueo) y escribe la píldora-ETIQUETA buscable
    por el escritor único. Devuelve el id de la píldora. La etiqueta va en claro (para el recall); el valor jamás.

    `slot` (p.ej. `secret:netflix:password`) permite SUPERSEDE: re-guardar la misma etiqueta reutiliza la píldora
    (mismo id) y REEMPLAZA el ciphertext → 'el más reciente manda', sin duplicar."""
    if not exists():
        raise VaultError(_msg("vault.err.no_vault_for_secrets", "No vault has been created — create it before saving secrets"))
    ciphertext = seal(value)
    meta = {"vault": 1, "sensitivity": sensitivity, "label": label}
    mid = _writer.insert_memory(
        label, level="long", kind=kind, importance=0.9, pinned=True, slot=slot, meta=meta)
    _db.get_db().execute(
        "INSERT OR REPLACE INTO vault_secrets (memory_id, ciphertext, created) VALUES (?,?,?)",
        (mid, bytes(ciphertext), int(time.time())))
    return mid


def is_sealed(memory_id: int) -> bool:
    """¿Esta píldora tiene un valor sellado en la bóveda?"""
    return _db.get_db().query_one(
        "SELECT 1 FROM vault_secrets WHERE memory_id=?", (memory_id,)) is not None


def open_secret(memory_id: int, *, passphrase: str | None = None) -> str:
    """Descifra el valor de un secreto. Usa la clave en RAM (modo cómodo) o, si se pasa `passphrase`, desbloquea de
    forma transitoria (modo estricto, sin cachear). Lanza VaultLocked si no hay forma de desbloquear, o VaultError
    si el secreto no existe."""
    row = _db.get_db().query_one("SELECT ciphertext FROM vault_secrets WHERE memory_id=?", (memory_id,))
    if not row:
        raise VaultError(_msg("vault.err.no_sealed_secret", "There is no sealed secret for item {id}", id=memory_id))
    ciphertext = bytes(row["ciphertext"])
    sk_bytes = _cached_sk()
    if sk_bytes is None and passphrase is not None:
        # desbloqueo transitorio (no cachea): desenvuelve, usa, descarta
        meta = _load_meta()
        if not meta:
            raise VaultError(_msg("vault.err.no_vault", "No vault has been created"))
        for wrap in meta["wraps"]:
            if wrap.get("method") != "passphrase":
                continue
            try:
                cand = _unwrap_passphrase(wrap, passphrase)
            except WrongPassphrase:
                continue
            if bytes(PrivateKey(cand).public_key) == meta["public_key"]:
                sk_bytes = cand
                break
        if sk_bytes is None:
            raise WrongPassphrase(_msg("vault.err.bad_passphrase", "Wrong passphrase"))
    if sk_bytes is None:
        raise VaultLocked(_msg("vault.err.locked", "The vault is locked — the passphrase is needed"))
    try:
        return _open_with_sk(ciphertext, sk_bytes)
    except CryptoError as e:
        raise VaultError(_msg("vault.err.decrypt_failed", "The secret could not be decrypted")) from e


def list_secrets() -> list[dict]:
    """Lista los secretos por su ETIQUETA (nunca el valor): [{memory_id, label, sensitivity, slot}]. Para el
    frontend / '¿qué contraseñas tienes guardadas?'."""
    rows = _db.get_db().query(
        "SELECT m.id AS id, m.text AS label, m.slot AS slot, m.meta AS meta "
        "FROM vault_secrets v JOIN memories m ON m.id = v.memory_id WHERE m.valid=1 ORDER BY m.updated DESC")
    out = []
    for r in rows:
        try:
            meta = json.loads(r["meta"]) if r["meta"] else {}
        except Exception:
            meta = {}
        out.append({"memory_id": int(r["id"]), "label": r["label"], "slot": r["slot"],
                    "sensitivity": meta.get("sensitivity", "high")})
    return out


# ── gestión de métodos de desbloqueo ──────────────────────────────────────────────────────────────────────
def change_passphrase(old: str, new: str) -> None:
    """Rota la passphrase: re-envuelve SOLO su sobre (los secretos y el par de claves NO se tocan)."""
    if not new or len(new) < 4:
        raise VaultError(_msg("vault.err.short_new_passphrase", "The new passphrase must be at least 4 characters long"))
    meta = _load_meta()
    if not meta:
        raise VaultError(_msg("vault.err.no_vault", "No vault has been created"))
    sk_bytes = None
    for wrap in meta["wraps"]:
        if wrap.get("method") != "passphrase":
            continue
        try:
            sk_bytes = _unwrap_passphrase(wrap, old)
            break
        except WrongPassphrase:
            continue
    if sk_bytes is None:
        raise WrongPassphrase(_msg("vault.err.bad_current_passphrase", "The current passphrase is wrong"))
    wraps = [w for w in meta["wraps"] if w.get("method") != "passphrase"]
    wraps.append(_passphrase_wrap(sk_bytes, new))
    _save_meta(meta["public_key"], wraps, create=False)


def status() -> dict:
    """Vista REDACTADA para el frontend: presencia/estado, NUNCA material de clave."""
    meta = _load_meta()
    if not meta:
        return {"exists": False, "unlocked": False, "methods": [], "secret_count": 0}
    count = _db.get_db().query_one("SELECT COUNT(*) AS n FROM vault_secrets")
    return {
        "exists": True,
        "unlocked": is_unlocked(),
        "methods": sorted({w.get("method") for w in meta["wraps"] if w.get("method")}),
        "secret_count": int(count["n"]) if count else 0,
    }


# ── PASSKEYS (WebAuthn PRF) — segundo método de desbloqueo (V2-060 F3) ────────────────────────────────────
# El navegador obtiene un secreto de 32 bytes del autenticador (Touch ID / Windows Hello) SOLO tras el gesto
# biométrico (extensión `prf`), y lo manda al server, que lo usa como KEK para envolver/desenvolver la MISMA clave
# privada (patrón sobre). El descifrado ocurre en el SERVER (modo cómodo, el default elegido). El salt del PRF se
# DERIVA de la clave pública (no secreto, estable) → sin schema nuevo ni estado extra.
def _prf_salt() -> bytes | None:
    meta = _load_meta()
    if not meta:
        return None
    return hashlib.blake2b(b"zaelar-vault-prf|" + meta["public_key"], digest_size=32).digest()


def _prf_kek(prf_secret: bytes) -> bytes:
    """Normaliza el secreto PRF (ya ~32B uniformes) a una clave de SecretBox de 32 bytes."""
    return hashlib.blake2b(bytes(prf_secret), digest_size=_KEYBYTES).digest()


def passkey_meta() -> dict:
    """Para el reto de WebAuthn del navegador: salt del PRF + ids de credenciales registradas (todo NO secreto)."""
    meta = _load_meta()
    if not meta:
        return {"prf_salt": None, "cred_ids": []}
    salt = _prf_salt()
    creds = [w.get("cred_id") for w in meta["wraps"] if w.get("method") == "passkey" and w.get("cred_id")]
    return {"prf_salt": b64encode(salt).decode() if salt else None, "cred_ids": creds}


def add_passkey(prf_secret: bytes, cred_id: str) -> None:
    """Registra un aparato: envuelve la clave privada bajo el PRF de la passkey. Requiere la bóveda DESBLOQUEADA
    (la privada en RAM) — así solo quien ya tiene acceso puede añadir un método. Dedup por `cred_id`."""
    meta = _load_meta()
    if not meta:
        raise VaultError(_msg("vault.err.no_vault", "No vault has been created"))
    sk_bytes = _cached_sk()
    if sk_bytes is None:
        raise VaultLocked(_msg("vault.err.unlock_before_passkey", "Unlock the vault before adding a passkey"))
    kek = _prf_kek(prf_secret)
    wrapped = SecretBox(kek).encrypt(sk_bytes)
    wraps = [w for w in meta["wraps"] if not (w.get("method") == "passkey" and w.get("cred_id") == cred_id)]
    wraps.append({"method": "passkey", "cred_id": cred_id, "wrapped_sk": b64encode(bytes(wrapped)).decode()})
    _save_meta(meta["public_key"], wraps, create=False)


def unlock_with_prf(prf_secret: bytes, *, hold: bool = True) -> bool:
    """Desbloquea con el secreto PRF de una passkey. Igual que `unlock` pero con KEK del PRF."""
    meta = _load_meta()
    if not meta:
        raise VaultError(_msg("vault.err.no_vault", "No vault has been created"))
    kek = _prf_kek(prf_secret)
    for wrap in meta["wraps"]:
        if wrap.get("method") != "passkey":
            continue
        try:
            sk_bytes = SecretBox(kek).decrypt(b64decode(wrap["wrapped_sk"]))
        except CryptoError:
            continue
        if bytes(PrivateKey(sk_bytes).public_key) != meta["public_key"]:
            continue
        if hold:
            _cache_sk(sk_bytes)
        return True
    return False


def remove_passkey(cred_id: str) -> None:
    """Revoca un aparato (quita su sobre). No toca los secretos ni los demás métodos."""
    meta = _load_meta()
    if not meta:
        raise VaultError(_msg("vault.err.no_vault", "No vault has been created"))
    wraps = [w for w in meta["wraps"] if not (w.get("method") == "passkey" and w.get("cred_id") == cred_id)]
    if not any(w.get("method") == "passphrase" for w in wraps) and \
            not any(w.get("method") == "passkey" for w in wraps):
        raise VaultError(_msg("vault.err.last_method", "You cannot remove the last unlock method"))
    _save_meta(meta["public_key"], wraps, create=False)
