"""密码哈希、加密与 TOTP。"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import struct
import time
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from ._db import _connect, _init_db

# ---------- 密钥存储 ----------
# 安全要求：加密密钥（JWT secret / Fernet enc_key）不得与密文同库存储，
# 否则拿到数据库文件即可解密全部 LLM API Key 并伪造任意用户 token。
# 优先级：环境变量 > 密钥文件（DB 同目录 .secret_keys.json）> 从旧库迁移。
# 环境变量: FC_JWT_SECRET（hex/utf-8 字符串）、FC_ENC_KEY（64位hex）


def _secret_file_path() -> Path:
    env = os.environ.get("FC_SECRET_FILE")
    if env:
        return Path(env)
    # 跟随 _db 模块的 DB_PATH（测试会 monkeypatch），密钥文件与库同目录
    from . import DB_PATH
    return Path(str(DB_PATH)).parent / ".secret_keys.json"


def _load_secrets() -> dict[str, str]:
    keys: dict[str, str] = {}
    # 1) 环境变量（部署推荐：密钥完全脱离磁盘上的数据库目录）
    env_jwt = os.environ.get("FC_JWT_SECRET", "").strip()
    env_enc = os.environ.get("FC_ENC_KEY", "").strip()
    if env_jwt:
        keys["jwt_secret"] = env_jwt
    if env_enc:
        keys["enc_key"] = env_enc
    if "jwt_secret" in keys and "enc_key" in keys:
        return keys

    # 2) 密钥文件
    path = _secret_file_path()
    if path.exists():
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
            keys.setdefault("jwt_secret", str(stored.get("jwt_secret", "")))
            keys.setdefault("enc_key", str(stored.get("enc_key", "")))
        except (json.JSONDecodeError, OSError):
            pass
    if keys.get("jwt_secret") and keys.get("enc_key"):
        return keys

    # 3) 从旧版本数据库迁移（首次升级），迁移后从库里删除
    _init_db()
    migrated = False
    with _connect() as conn:
        for key_name in ("jwt_secret", "enc_key"):
            if keys.get(key_name):
                continue
            row = conn.execute(
                "SELECT value FROM app_config WHERE key=?", (key_name,)
            ).fetchone()
            if row and row["value"]:
                keys[key_name] = row["value"]
                conn.execute("DELETE FROM app_config WHERE key=?", (key_name,))
                migrated = True

    # 4) 仍然缺失则生成新密钥
    changed = False
    if not keys.get("jwt_secret"):
        keys["jwt_secret"] = secrets.token_hex(32)
        changed = True
    if not keys.get("enc_key"):
        keys["enc_key"] = secrets.token_bytes(32).hex()
        changed = True

    # 持久化到密钥文件（环境变量提供的不落盘）
    file_keys = {k: v for k, v in keys.items()}
    if env_jwt:
        file_keys.pop("jwt_secret", None)
    if env_enc:
        file_keys.pop("enc_key", None)
    if file_keys and (changed or migrated or not path.exists()):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(file_keys), encoding="utf-8")
            os.chmod(path, 0o600)  # POSIX 下限制读取；Windows 上无操作
        except OSError:
            pass
    return keys


# ---------- JWT secret ----------

def _get_secret() -> str:
    return _load_secrets()["jwt_secret"]


# ---------- LLM Key 加密/解密 ----------

def _get_enc_key() -> bytes:
    """获取加密密钥（与JWT secret不同，单独存储）。"""
    return bytes.fromhex(_load_secrets()["enc_key"])


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
