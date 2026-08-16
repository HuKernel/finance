"""JWT 与一次性认证 Token。"""
from __future__ import annotations

import hashlib
import secrets
import time
from datetime import datetime
from typing import Any, Optional

import jwt

from ._db import _connect
from .crypto import _get_secret

JWT_ALGO = "HS256"
TOKEN_TTL = 7 * 24 * 3600  # 7 天


def create_token(user_id: int, username: str) -> str:
    # pwd_version：改密码后自增，使所有已签发的 token 立即失效
    from . import users as _users
    payload = {
        "sub": str(user_id),
        "username": username,
        "pwd_version": _users.get_pwd_version(user_id),
        "iat": int(time.time()),
        "exp": int(time.time()) + TOKEN_TTL,
    }
    return jwt.encode(payload, _get_secret(), algorithm=JWT_ALGO)


def decode_token(token: str) -> Optional[dict[str, Any]]:
    try:
        return jwt.decode(token, _get_secret(), algorithms=[JWT_ALGO])
    except jwt.PyJWTError:
        return None


def issue_auth_token(user_id: int, kind: str, ttl: int = 900) -> str:
    raw = secrets.token_urlsafe(32)
    digest = hashlib.sha256(raw.encode()).hexdigest()
    with _connect() as conn:
        conn.execute("INSERT INTO auth_tokens(token_hash,user_id,kind,expires_at,created_at) VALUES(?,?,?,?,?)", (digest, user_id, kind, int(time.time()) + ttl, datetime.now().isoformat(timespec="seconds")))
    return raw


def consume_auth_token(raw: str, kind: str) -> Optional[int]:
    digest = hashlib.sha256(raw.encode()).hexdigest()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM auth_tokens WHERE token_hash=? AND kind=? AND used=0 AND expires_at>?", (digest, kind, int(time.time()))).fetchone()
        if not row:
            return None
        # 一次性 token：32字节随机数无爆破面，命中即作废
        conn.execute("UPDATE auth_tokens SET used=1 WHERE token_hash=?", (digest,))
    return int(row["user_id"])
