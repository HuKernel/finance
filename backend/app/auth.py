"""认证与用户画像：注册/登录/JWT/用户偏好、登录频率限制。

- 密码哈希：标准库 hashlib.pbkdf2_hmac（无额外依赖）
- Token：PyJWT，HS256，7 天有效期
- 登录频率限制：5次失败后锁定15分钟（内存计数器，重启清零）
- LLM Key 加密：AES-256-GCM（同机部署，防DB泄露后key被直接读取）
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
import base64
import struct
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any, Optional

import jwt
from cryptography.fernet import Fernet, InvalidToken

from .config import DB_PATH

JWT_ALGO = "HS256"
TOKEN_TTL = 7 * 24 * 3600  # 7 天

# 登录频率限制：{ip_or_username: (fail_count, first_fail_time, lock_until)}
_login_attempts: dict[str, dict[str, Any]] = {}
MAX_LOGIN_FAILS = 5
LOCK_DURATION = 15 * 60  # 锁定15分钟


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                created_at TEXT NOT NULL,
                is_admin INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                is_invited INTEGER DEFAULT 0,
                plan_code TEXT DEFAULT 'free',
                membership_expires_at TEXT
            )"""
        )
        cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
        for col, definition in [("email", "TEXT"), ("email_verified", "INTEGER DEFAULT 0"), ("mfa_secret", "TEXT"), ("mfa_enabled", "INTEGER DEFAULT 0")]:
            if col not in cols:
                conn.execute(f"ALTER TABLE users ADD COLUMN {col} {definition}")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS user_profiles (
                user_id INTEGER PRIMARY KEY,
                risk_preference TEXT DEFAULT 'balanced',
                watchlist TEXT DEFAULT '[]',
                analyst_config TEXT DEFAULT '',
                updated_at TEXT
            )"""
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS app_config (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        conn.execute("""CREATE TABLE IF NOT EXISTS auth_tokens (
            token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, kind TEXT NOT NULL,
            expires_at INTEGER NOT NULL, used INTEGER DEFAULT 0, created_at TEXT NOT NULL
        )""")
        # per-user LLM 配置
        conn.execute(
            """CREATE TABLE IF NOT EXISTS user_llm_config (
                user_id INTEGER PRIMARY KEY,
                provider TEXT DEFAULT 'deepseek',
                base_url TEXT DEFAULT 'https://api.deepseek.com/v1',
                api_key_enc TEXT DEFAULT '',
                model TEXT DEFAULT 'deepseek-chat',
                temperature REAL DEFAULT 0.3,
                max_tokens INTEGER DEFAULT 4096,
                updated_at TEXT
            )"""
        )
        # 邀请码
        conn.execute(
            """CREATE TABLE IF NOT EXISTS invite_codes (
                code TEXT PRIMARY KEY,
                created_by INTEGER NOT NULL,
                used_by INTEGER,
                created_at TEXT NOT NULL,
                used_at TEXT,
                note TEXT DEFAULT ''
            )"""
        )
        # 审计日志
        conn.execute(
            """CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                action TEXT NOT NULL,
                detail TEXT DEFAULT '',
                ip TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )"""
        )
        # 确保旧表升级（ALTER ADD COLUMN）
        cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
        for col, default in [("is_admin", "0"), ("is_active", "1"), ("is_invited", "0")]:
            if col not in cols:
                conn.execute(f"ALTER TABLE users ADD COLUMN {col} INTEGER DEFAULT {default}")
        if "plan_code" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN plan_code TEXT DEFAULT 'free'")
        if "membership_expires_at" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN membership_expires_at TEXT")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS monthly_model_usage (
                user_id INTEGER NOT NULL,
                month TEXT NOT NULL,
                usage_count INTEGER NOT NULL DEFAULT 0,
                bonus_count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, month)
            )"""
        )
        usage_cols = [r[1] for r in conn.execute("PRAGMA table_info(monthly_model_usage)").fetchall()]
        if "bonus_count" not in usage_cols:
            conn.execute("ALTER TABLE monthly_model_usage ADD COLUMN bonus_count INTEGER NOT NULL DEFAULT 0")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS invite_rewards (
                invite_code TEXT PRIMARY KEY,
                inviter_id INTEGER NOT NULL,
                invited_user_id INTEGER NOT NULL,
                month TEXT NOT NULL,
                reward_count INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS oauth_identities (
                provider TEXT NOT NULL,
                provider_user_id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (provider, provider_user_id),
                UNIQUE (provider, user_id)
            )"""
        )

        # 首个用户自动成为管理员
        count = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
        if count == 0:
            # 会在 create_user 里设置 is_admin
            pass
        else:
            # 如果没有管理员，将第一个用户设为管理员
            admin = conn.execute("SELECT COUNT(*) as c FROM users WHERE is_admin=1").fetchone()["c"]
            if admin == 0:
                first = conn.execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()
                if first:
                    conn.execute("UPDATE users SET is_admin=1 WHERE id=?", (first["id"],))


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


# ---------- 登录频率限制 ----------

def check_rate_limit(identifier: str) -> tuple[bool, str]:
    """检查登录频率限制。返回(是否允许, 锁定提示)。"""
    now = int(time.time())
    rec = _login_attempts.get(identifier)

    if rec and rec.get("lock_until", 0) > now:
        remain = int((rec["lock_until"] - now) / 60)
        return False, f"登录失败次数过多，请{remain}分钟后再试"

    if rec and now - rec.get("first_fail", 0) > 3600:
        # 超过1小时重置
        del _login_attempts[identifier]

    return True, ""


def record_login_fail(identifier: str) -> None:
    """记录登录失败。"""
    now = int(time.time())
    rec = _login_attempts.get(identifier, {"count": 0, "first_fail": now, "lock_until": 0})
    rec["count"] += 1
    if rec["count"] >= MAX_LOGIN_FAILS:
        rec["lock_until"] = now + LOCK_DURATION
    _login_attempts[identifier] = rec


def record_login_success(identifier: str) -> None:
    """登录成功清除失败记录。"""
    _login_attempts.pop(identifier, None)


# ---------- per-user LLM 配置 ----------

def get_user_llm_config(user_id: int) -> dict[str, Any]:
    """读取用户专属LLM配置（api_key已解密）。"""
    _init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM user_llm_config WHERE user_id=?", (user_id,)
        ).fetchone()
    if row is None:
        # 首次：返回默认配置
        return {
            "provider": "deepseek",
            "base_url": "https://api.deepseek.com/v1",
            "api_key": "",
            "model": "deepseek-chat",
            "temperature": 0.3,
            "max_tokens": 4096,
        }
    return {
        "provider": row["provider"],
        "base_url": row["base_url"],
        "api_key": decrypt_key(row["api_key_enc"]),
        "model": row["model"],
        "temperature": row["temperature"],
        "max_tokens": row["max_tokens"],
    }


def get_effective_llm_config(user_id: int) -> dict[str, Any]:
    """用户配置了 Key 就用用户模型，否则使用平台默认模型。"""
    user_config = get_user_llm_config(user_id)
    if (user_config.get("api_key") or "").strip():
        return user_config
    from .config import get_config
    return get_config()


def save_user_llm_config(user_id: int, cfg: dict[str, Any]) -> dict[str, Any]:
    """保存用户专属LLM配置（api_key加密存储）。"""
    _init_db()
    now = datetime.now().isoformat(timespec="seconds")

    # 如果新key为空，保留旧key
    old_cfg = get_user_llm_config(user_id)
    api_key = cfg.get("api_key", "").strip()
    if not api_key:
        api_key = old_cfg["api_key"]

    with _connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO user_llm_config
               (user_id, provider, base_url, api_key_enc, model, temperature, max_tokens, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                user_id,
                cfg.get("provider", old_cfg["provider"]),
                cfg.get("base_url", old_cfg["base_url"]),
                encrypt_key(api_key),
                cfg.get("model", old_cfg["model"]),
                float(cfg.get("temperature", old_cfg["temperature"])),
                int(cfg.get("max_tokens", old_cfg["max_tokens"])),
                now,
            ),
        )
    # 返回脱敏版
    result = get_user_llm_config(user_id)
    result["api_key"] = _mask_key(result["api_key"])
    return result


def _mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "****"
    return key[:4] + "****" + key[-4:]


# ---------- 密码 ----------

def hash_password(password: str) -> tuple[str, str]:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 100_000)
    return digest.hex(), salt


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 100_000)
    return hmac.compare_digest(digest.hex(), expected_hash)


# ---------- JWT ----------

def create_token(user_id: int, username: str) -> str:
    payload = {
        "sub": str(user_id),
        "username": username,
        "iat": int(time.time()),
        "exp": int(time.time()) + TOKEN_TTL,
    }
    return jwt.encode(payload, _get_secret(), algorithm=JWT_ALGO)


def decode_token(token: str) -> Optional[dict[str, Any]]:
    try:
        return jwt.decode(token, _get_secret(), algorithms=[JWT_ALGO])
    except jwt.PyJWTError:
        return None


# ---------- 用户 CRUD ----------

def create_user(username: str, password: str, invite_code: str = "") -> dict[str, Any]:
    """注册用户，返回用户信息；用户名重复抛 ValueError。

    invite_code: 如果系统中有邀请码表，需要提供有效邀请码（如果表非空）。
    首个注册用户自动成为管理员。
    """
    _init_db()
    # 邀请码校验：如果存在邀请码记录，则必须提供有效码
    with _connect() as conn:
        code_count = conn.execute("SELECT COUNT(*) as c FROM invite_codes").fetchone()["c"]
        if code_count > 0:
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


def set_user_email(user_id: int, email: str) -> None:
    _init_db()
    with _connect() as conn:
        conn.execute("UPDATE users SET email=?, email_verified=0 WHERE id=?", (email.strip().lower(), user_id))


def get_security_profile(user_id: int) -> dict[str, Any]:
    _init_db()
    with _connect() as conn:
        row = conn.execute("SELECT email,email_verified,mfa_enabled FROM users WHERE id=?", (user_id,)).fetchone()
    return dict(row) if row else {"email": None, "email_verified": 0, "mfa_enabled": 0}


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
        conn.execute("UPDATE auth_tokens SET used=1 WHERE token_hash=?", (digest,))
    return int(row["user_id"])


def set_email_verified(user_id: int) -> None:
    with _connect() as conn:
        conn.execute("UPDATE users SET email_verified=1 WHERE id=?", (user_id,))


def set_mfa(user_id: int, secret: Optional[str], enabled: bool) -> None:
    with _connect() as conn:
        conn.execute("UPDATE users SET mfa_secret=?, mfa_enabled=? WHERE id=?", (secret, 1 if enabled else 0, user_id))


def get_mfa_secret(user_id: int) -> Optional[str]:
    with _connect() as conn:
        row = conn.execute("SELECT mfa_secret,mfa_enabled FROM users WHERE id=?", (user_id,)).fetchone()
    return row["mfa_secret"] if row and row["mfa_enabled"] else None


def totp_code(secret: str, at: Optional[int] = None) -> str:
    counter = int((at or int(time.time())) // 30)
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 15
    return str((struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7fffffff) % 1000000).zfill(6)


def verify_totp(secret: str, code: str) -> bool:
    return any(hmac.compare_digest(totp_code(secret, int(time.time()) + delta), code.strip()) for delta in (-30, 0, 30))


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


FREE_MONTHLY_MODEL_LIMIT = 5


def _usage_month() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m")


def has_membership(user: dict[str, Any]) -> bool:
    if user.get("is_admin"):
        return True
    if user.get("plan_code") not in (None, "", "free"):
        expires = user.get("membership_expires_at")
        if not expires:
            return True
        try:
            return datetime.fromisoformat(str(expires)).date() >= datetime.now(ZoneInfo("Asia/Shanghai")).date()
        except ValueError:
            return False
    return False


def get_model_usage(user: dict[str, Any]) -> dict[str, Any]:
    _init_db()
    month = _usage_month()
    with _connect() as conn:
        row = conn.execute(
            "SELECT usage_count, bonus_count FROM monthly_model_usage WHERE user_id=? AND month=?",
            (user["id"], month),
        ).fetchone()
    used = int(row["usage_count"]) if row else 0
    bonus = int(row["bonus_count"]) if row else 0
    unlimited = has_membership(user)
    return {"month": month, "used": used, "limit": None if unlimited else FREE_MONTHLY_MODEL_LIMIT + bonus, "bonus": bonus, "remaining": None if unlimited else max(0, FREE_MONTHLY_MODEL_LIMIT + bonus - used)}


def consume_model_usage(user: dict[str, Any]) -> dict[str, Any]:
    _init_db()
    if has_membership(user):
        return get_model_usage(user)
    month = _usage_month()
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO monthly_model_usage (user_id, month, usage_count, bonus_count) VALUES (?, ?, 0, 0)",
            (user["id"], month),
        )
        bonus = conn.execute("SELECT bonus_count FROM monthly_model_usage WHERE user_id=? AND month=?", (user["id"], month)).fetchone()["bonus_count"]
        cursor = conn.execute(
            "UPDATE monthly_model_usage SET usage_count=usage_count+1 WHERE user_id=? AND month=? AND usage_count<?",
            (user["id"], month, FREE_MONTHLY_MODEL_LIMIT + bonus),
        )
        if cursor.rowcount == 0:
            raise PermissionError("免费用户每月可使用 5 次 AI 功能，本月次数已用完")
    return get_model_usage(user)


def is_admin(user_id: int) -> bool:
    """检查用户是否是管理员。"""
    with _connect() as conn:
        row = conn.execute("SELECT is_admin FROM users WHERE id=?", (user_id,)).fetchone()
    return bool(row and row["is_admin"])


# ---------- 管理员功能 ----------

def list_all_users(page: int = 1, page_size: int = 20) -> dict[str, Any]:
    """列出所有用户（管理员功能）。"""
    _init_db()
    with _connect() as conn:
        total = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
        rows = conn.execute(
            "SELECT u.id, u.username, u.created_at, u.is_admin, u.is_active, u.is_invited, u.plan_code, u.membership_expires_at, "
            "(SELECT COUNT(*) FROM analyses WHERE analyses.user_id = u.id) as analysis_count "
            "FROM users u ORDER BY u.id LIMIT ? OFFSET ?", (page_size, (page - 1) * page_size)
        ).fetchall()
    return {"items": [dict(r) for r in rows], "total": total, "page": page, "page_size": page_size}


def delete_user(user_id: int) -> bool:
    _init_db()
    with _connect() as conn:
        row = conn.execute("SELECT id FROM users WHERE id=?", (user_id,)).fetchone()
        if not row:
            return False
        for table, col in [("user_profiles", "user_id"), ("user_llm_config", "user_id"), ("monthly_model_usage", "user_id"), ("oauth_identities", "user_id")]:
            conn.execute(f"DELETE FROM {table} WHERE {col}=?", (user_id,))
        conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    return True


def toggle_user_active(user_id: int) -> bool:
    """启用/禁用用户。"""
    _init_db()
    with _connect() as conn:
        row = conn.execute("SELECT is_active FROM users WHERE id=?", (user_id,)).fetchone()
        if row is None:
            return False
        conn.execute("UPDATE users SET is_active=? WHERE id=?", (1 - row["is_active"], user_id))
    return True


def set_user_admin(user_id: int, is_admin_val: bool) -> bool:
    """设置/取消管理员。"""
    _init_db()
    with _connect() as conn:
        cur = conn.execute("UPDATE users SET is_admin=? WHERE id=?", (1 if is_admin_val else 0, user_id))
        return cur.rowcount > 0


def create_invite_code(created_by: int, note: str = "") -> dict[str, Any]:
    """生成邀请码。"""
    _init_db()
    code = secrets.token_urlsafe(8).replace("-", "").replace("_", "")[:8].upper()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO invite_codes (code, created_by, created_at, note) VALUES (?, ?, ?, ?)",
            (code, created_by, datetime.now().isoformat(timespec="seconds"), note),
        )
    return {"code": code, "created_by": created_by, "note": note}


def list_invite_codes() -> list[dict[str, Any]]:
    _init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT i.*, u.username as created_by_name FROM invite_codes i "
            "LEFT JOIN users u ON i.created_by = u.id "
            "ORDER BY i.created_at DESC"
        ).fetchall()
    result = [dict(r) for r in rows]
    with _connect() as conn:
        for item in result:
            if item.get("used_by"):
                row = conn.execute("SELECT username FROM users WHERE id=?", (item["used_by"],)).fetchone()
                item["used_by_name"] = row["username"] if row else None
    return result


def audit_log(user_id: int, username: str, action: str, detail: str = "", ip: str = "") -> None:
    """记录审计日志。"""
    _init_db()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO audit_log (user_id, username, action, detail, ip, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, username, action, detail, ip, datetime.now().isoformat(timespec="seconds")),
        )


def list_audit_logs(page: int = 1, page_size: int = 20) -> dict[str, Any]:
    _init_db()
    with _connect() as conn:
        total = conn.execute("SELECT COUNT(*) c FROM audit_log").fetchone()["c"]
        rows = conn.execute(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT ? OFFSET ?", (page_size, (page - 1) * page_size)
        ).fetchall()
    return {"items": [dict(r) for r in rows], "total": total, "page": page, "page_size": page_size}


def get_system_stats() -> dict[str, Any]:
    """系统统计信息（管理员面板用）。"""
    _init_db()
    import os
    db_size = os.path.getsize(DB_PATH) if DB_PATH.exists() else 0
    with _connect() as conn:
        user_count = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
        active_users = conn.execute("SELECT COUNT(*) as c FROM users WHERE is_active=1").fetchone()["c"]
        member_count = conn.execute(
            "SELECT COUNT(*) as c FROM users WHERE plan_code NOT IN ('', 'free') AND (membership_expires_at IS NULL OR membership_expires_at >= ?)",
            (datetime.now().isoformat(timespec="seconds"),),
        ).fetchone()["c"]
        analysis_count = conn.execute("SELECT COUNT(*) as c FROM analyses").fetchone()["c"]
        session_count = conn.execute("SELECT COUNT(*) as c FROM chat_sessions").fetchone() if conn.execute("SELECT name FROM sqlite_master WHERE name='chat_sessions'").fetchone() else {"c": 0}
        alert_count = conn.execute("SELECT COUNT(*) as c FROM alerts").fetchone()["c"] if conn.execute("SELECT name FROM sqlite_master WHERE name='alerts'").fetchone() else {"c": 0}
        portfolio_count = conn.execute("SELECT COUNT(*) as c FROM portfolio").fetchone()["c"] if conn.execute("SELECT name FROM sqlite_master WHERE name='portfolio'").fetchone() else {"c": 0}
    return {
        "db_size_mb": round(db_size / 1024 / 1024, 2),
        "users": {"total": user_count, "active": active_users, "members": member_count},
        "analyses": analysis_count,
        "chat_sessions": session_count.get("c", 0) if isinstance(session_count, dict) else 0,
        "alerts": alert_count.get("c", 0) if isinstance(alert_count, dict) else 0,
        "portfolios": portfolio_count,
    }


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
    if len(new_password) < 6:
        raise ValueError("新密码至少6位")
    new_hash, new_salt = hash_password(new_password)
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET password_hash=?, salt=? WHERE id=?",
            (new_hash, new_salt, user_id),
        )
    return True
