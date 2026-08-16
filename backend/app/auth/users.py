"""用户 CRUD 与账号安全。"""
from __future__ import annotations

import json
import secrets
import sqlite3
from datetime import datetime
from typing import Any, Optional

from ._db import _connect, _init_db
from .crypto import hash_password, verify_password
from .usage import _usage_month

AGREEMENT_VERSION = "2026-08-12"


def create_user(username: str, password: str, invite_code: str = "") -> dict[str, Any]:
    """注册用户，返回用户信息；用户名重复抛 ValueError。

    invite_code: 如果系统中有邀请码表，需要提供有效邀请码（如果表非空）。
    首个注册用户自动成为管理员。
    """
    _init_db()
    validate_password_policy(password)
    # 邀请码校验：如果存在邀请码记录，则必须提供有效码
    with _connect() as conn:
        from ..config import get_invite_required
        if get_invite_required():
            if not invite_code:
                raise ValueError("当前需要邀请码注册")
            row = conn.execute("SELECT * FROM invite_codes WHERE code=? AND used_by IS NULL", (invite_code,)).fetchone()
            if row is None:
                raise ValueError("邀请码无效或已被使用")

    digest, salt = hash_password(password)
    try:
        with _connect() as conn:
            # 第一个用户自动管理员
            count = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
            is_admin = 1 if count == 0 else 0
            cur = conn.execute(
                "INSERT INTO users (username, password_hash, salt, created_at, is_admin, is_active, is_invited) VALUES (?, ?, ?, ?, ?, 1, ?)",
                (username, digest, salt, datetime.now().isoformat(timespec="seconds"), is_admin, 1 if invite_code else 0),
            )
            user_id = int(cur.lastrowid)
            conn.execute(
                "INSERT INTO user_profiles (user_id, risk_preference, watchlist) VALUES (?, 'balanced', '[]')",
                (user_id,),
            )
            # 消耗邀请码
            if invite_code:
                conn.execute(
                    "UPDATE invite_codes SET used_by=?, used_at=? WHERE code=?",
                    (user_id, datetime.now().isoformat(timespec="seconds"), invite_code),
                )
                inviter_id = conn.execute("SELECT created_by FROM invite_codes WHERE code=?", (invite_code,)).fetchone()["created_by"]
                month = _usage_month()
                conn.execute("INSERT INTO monthly_model_usage (user_id, month, bonus_count) VALUES (?, ?, 1) ON CONFLICT(user_id, month) DO UPDATE SET bonus_count=bonus_count+1", (inviter_id, month))
                conn.execute("INSERT INTO invite_rewards(invite_code, inviter_id, invited_user_id, month, created_at) VALUES(?,?,?,?,?)", (invite_code, inviter_id, user_id, month, datetime.now().isoformat(timespec="seconds")))
    except sqlite3.IntegrityError:
        raise ValueError("用户名已存在")
    return {"id": user_id, "username": username, "is_admin": is_admin}


def record_agreement_consent(user_id: int, agreement: str) -> None:
    _init_db()
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO agreement_consents(user_id, agreement, version, agreed_at) VALUES (?, ?, ?, ?)",
            (user_id, agreement, AGREEMENT_VERSION, datetime.now().isoformat(timespec="seconds")),
        )


def set_user_email(user_id: int, email: str) -> None:
    _init_db()
    with _connect() as conn:
        conn.execute("UPDATE users SET email=?, email_verified=0 WHERE id=?", (email.strip().lower(), user_id))


def get_security_profile(user_id: int) -> dict[str, Any]:
    _init_db()
    with _connect() as conn:
        row = conn.execute("SELECT email,email_verified,mfa_enabled FROM users WHERE id=?", (user_id,)).fetchone()
    return dict(row) if row else {"email": None, "email_verified": 0, "mfa_enabled": 0}


def set_email_verified(user_id: int) -> None:
    with _connect() as conn:
        conn.execute("UPDATE users SET email_verified=1 WHERE id=?", (user_id,))


def set_mfa(user_id: int, secret: Optional[str], enabled: bool) -> None:
    # TOTP 密钥用 Fernet 加密存储（拿到数据库文件也无法生成验证码）
    from .crypto import encrypt_key
    stored = encrypt_key(secret) if secret else None
    with _connect() as conn:
        conn.execute("UPDATE users SET mfa_secret=?, mfa_enabled=? WHERE id=?", (stored, 1 if enabled else 0, user_id))


def get_mfa_secret(user_id: int, only_enabled: bool = True) -> Optional[str]:
    """读取 MFA 密钥（自动解密）。

    only_enabled=True：仅在已启用时返回（登录校验用）；
    only_enabled=False：setup 后 enable 前也能读到（启用流程需要先验码）。
    """
    with _connect() as conn:
        row = conn.execute("SELECT mfa_secret,mfa_enabled FROM users WHERE id=?", (user_id,)).fetchone()
    if not row or not row["mfa_secret"]:
        return None
    if only_enabled and not row["mfa_enabled"]:
        return None
    stored = row["mfa_secret"]
    from .crypto import decrypt_key
    plain = decrypt_key(stored)
    if plain:
        return plain
    # 兼容旧版明文密钥（无法解密时按明文返回）
    return stored if stored and not stored.startswith("gAAAA") else None


def get_or_create_oauth_user(provider: str, provider_user_id: str, preferred_username: str) -> dict[str, Any]:
    """按第三方稳定 ID 登录；首次登录创建普通本地用户。"""
    _init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT u.* FROM oauth_identities o JOIN users u ON u.id=o.user_id WHERE o.provider=? AND o.provider_user_id=?",
            (provider, provider_user_id),
        ).fetchone()
        if row:
            if not row["is_active"]:
                raise PermissionError("账号已被禁用，请联系管理员")
            return {"id": row["id"], "username": row["username"], "is_admin": row["is_admin"]}

        base = "".join(char for char in preferred_username.strip() if char.isalnum() or char in "-_")[:20] or f"{provider}_user"
        username, suffix = base, 0
        while conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
            suffix += 1
            tail = f"_{suffix}"
            username = base[:20 - len(tail)] + tail
        digest, salt = hash_password(secrets.token_urlsafe(32))
        now = datetime.now().isoformat(timespec="seconds")
        cur = conn.execute(
            "INSERT INTO users (username,password_hash,salt,created_at,is_admin,is_active,is_invited) VALUES (?,?,?,?,0,1,0)",
            (username, digest, salt, now),
        )
        user_id = int(cur.lastrowid)
        conn.execute("INSERT INTO user_profiles (user_id,risk_preference,watchlist) VALUES (?,'balanced','[]')", (user_id,))
        conn.execute(
            "INSERT INTO oauth_identities (provider,provider_user_id,user_id,created_at) VALUES (?,?,?,?)",
            (provider, provider_user_id, user_id, now),
        )
    return {"id": user_id, "username": username, "is_admin": 0}


def authenticate(username: str, password: str) -> Optional[dict[str, Any]]:
    """校验登录，成功返回用户信息。"""
    _init_db()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    if row is None:
        return None
    if not verify_password(password, row["salt"], row["password_hash"]):
        return None
    if row["is_active"] == 0:
        return {"_disabled": True}
    return {"id": row["id"], "username": row["username"], "is_admin": row["is_admin"]}


def get_user(user_id: int) -> Optional[dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, username, created_at, is_admin, is_active, plan_code, membership_expires_at FROM users WHERE id=?",
            (user_id,),
        ).fetchone()
    return dict(row) if row else None


def get_profile(user_id: int) -> dict[str, Any]:
    _init_db()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM user_profiles WHERE user_id=?", (user_id,)).fetchone()
    if row is None:
        return {"risk_preference": "balanced", "watchlist": [], "analyst_config": {}}
    try:
        watchlist = json.loads(row["watchlist"])
    except (json.JSONDecodeError, TypeError):
        watchlist = []
    try:
        analyst_config = json.loads(row["analyst_config"]) if "analyst_config" in row.keys() and row["analyst_config"] else {}
    except (json.JSONDecodeError, TypeError):
        analyst_config = {}
    return {
        "risk_preference": row["risk_preference"],
        "watchlist": watchlist,
        "analyst_config": analyst_config,
        "updated_at": row["updated_at"],
    }


def update_profile(
    user_id: int,
    risk_preference: Optional[str] = None,
    watchlist: Optional[list[str]] = None,
    analyst_config: Optional[list[str]] = None,
) -> dict[str, Any]:
    _init_db()
    cur = get_profile(user_id)
    if risk_preference is not None:
        if risk_preference not in ("conservative", "balanced", "aggressive"):
            raise ValueError("无效的风险偏好")
        cur["risk_preference"] = risk_preference
    if watchlist is not None:
        cur["watchlist"] = [str(w).zfill(6) if str(w).isdigit() else str(w) for w in watchlist][:30]
    if analyst_config is not None:
        cur["analyst_config"] = analyst_config
    with _connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO user_profiles (user_id, risk_preference, watchlist, analyst_config, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, cur["risk_preference"], json.dumps(cur["watchlist"], ensure_ascii=False),
             json.dumps(cur.get("analyst_config", []), ensure_ascii=False),
             datetime.now().isoformat(timespec="seconds")),
        )
    return get_profile(user_id)


def change_password(user_id: int, old_password: str, new_password: str) -> bool:
    """修改密码。需验证旧密码。返回是否成功。"""
    _init_db()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if row is None:
        return False
    if not verify_password(old_password, row["salt"], row["password_hash"]):
        return False
    validate_password_policy(new_password)
    new_hash, new_salt = hash_password(new_password)
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET password_hash=?, salt=?, pwd_version=COALESCE(pwd_version,0)+1 WHERE id=?",
            (new_hash, new_salt, user_id),
        )
    return True


def get_pwd_version(user_id: int) -> int:
    """获取用户当前密码版本（改密码自增；token 中版本不匹配即失效）。"""
    _init_db()
    with _connect() as conn:
        row = conn.execute("SELECT pwd_version FROM users WHERE id=?", (user_id,)).fetchone()
    return int(row["pwd_version"]) if row and row["pwd_version"] is not None else 0


# 常见弱密码黑名单（前30）与策略校验
_WEAK_PASSWORDS = {
    "123456", "1234567", "12345678", "123456789", "1234567890",
    "password", "password1", "qwerty", "qwerty123", "abc123",
    "111111", "000000", "666666", "888888", "123123",
    "iloveyou", "admin", "admin123", "root", "letmein",
    "welcome", "monkey", "dragon", "sunshine", "princess",
    "a123456", "123qwe", "1q2w3e4r", "qwe123", "woaini",
    "password123", "password1234", "admin1234", "qwertyuiop",
    "1qaz2wsx", "abcd1234", "asd123456", "zxc123456", "520131400",
}


def validate_password_policy(password: str) -> None:
    """密码策略：至少8位，且不得是常见弱密码或纯数字/纯字母。"""
    if len(password) < 8:
        raise ValueError("密码至少8位")
    if password.lower() in _WEAK_PASSWORDS:
        raise ValueError("密码过于常见，请更换")
    if password.isdigit() or password.isalpha():
        raise ValueError("密码需同时包含字母和数字")
