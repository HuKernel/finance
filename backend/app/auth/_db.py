"""数据库连接与建表逻辑。"""
from __future__ import annotations

import sqlite3


def _connect() -> sqlite3.Connection:
    # 运行时从包属性读取 DB_PATH，保持对 auth.DB_PATH monkeypatch 的兼容
    from . import DB_PATH
    from ..db import connect
    return connect(DB_PATH)


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
        for col, definition in [("email", "TEXT"), ("email_verified", "INTEGER DEFAULT 0"), ("mfa_secret", "TEXT"), ("mfa_enabled", "INTEGER DEFAULT 0"), ("pwd_version", "INTEGER DEFAULT 0"), ("is_super", "INTEGER DEFAULT 0")]:
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
        for col, default in [("is_admin", "0"), ("is_active", "1"), ("is_invited", "0"), ("pwd_version", "0")]:
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
        conn.execute(
            """CREATE TABLE IF NOT EXISTS agreement_consents (
                user_id INTEGER NOT NULL,
                agreement TEXT NOT NULL,
                version TEXT NOT NULL,
                agreed_at TEXT NOT NULL,
                PRIMARY KEY (user_id, agreement, version)
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
