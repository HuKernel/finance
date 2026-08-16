"""密码哈希、加密与 TOTP。"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from ._db import _connect, _init_db


# ---------- JWT secret ----------

def _get_secret() -> str:
    _init_db()
    with _connect() as conn:
        row = conn.execute("SELECT value FROM app_config WHERE key='jwt_secret'").fetchone()
    if row:
        return row["value"]
    secret = secrets.token_hex(32)
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO app_config (key, value) VALUES ('jwt_secret', ?)",
            (secret,),
        )
    return secret


# ---------- LLM Key 加密/解密 ----------

def _get_enc_key() -> bytes:
    """获取加密密钥（与JWT secret不同，单独存储）。"""
    _init_db()
    with _connect() as conn:
        row = conn.execute("SELECT value FROM app_config WHERE key='enc_key'").fetchone()
    if row:
        return bytes.fromhex(row["value"])
    key = secrets.token_bytes(32)
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO app_config (key, value) VALUES ('enc_key', ?)",
            (key.hex(),),
        )
    return key


def encrypt_key(plaintext: str) -> str:
    """使用 Fernet 认证加密存储 API key。"""
    if not plaintext:
        return ""
    key = _get_enc_key()
    f = Fernet(base64.urlsafe_b64encode(key))
    return f.encrypt(plaintext.encode()).decode()


def decrypt_key(ciphertext: str) -> str:
    """解密API key。"""
    if not ciphertext:
        return ""
    try:
        key = _get_enc_key()
        f = Fernet(base64.urlsafe_b64encode(key))
        return f.decrypt(ciphertext.encode()).decode()
    except (InvalidToken, ValueError):
        return ""


# ---------- 密码 ----------

def hash_password(password: str) -> tuple[str, str]:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 100_000)
    return digest.hex(), salt


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 100_000)
    return hmac.compare_digest(digest.hex(), expected_hash)


# ---------- TOTP ----------

def totp_code(secret: str, at: Optional[int] = None) -> str:
    counter = int((at or int(time.time())) // 30)
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 15
    return str((struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7fffffff) % 1000000).zfill(6)


def verify_totp(secret: str, code: str) -> bool:
    return any(hmac.compare_digest(totp_code(secret, int(time.time()) + delta), code.strip()) for delta in (-30, 0, 30))
