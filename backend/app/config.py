"""LLM 配置管理：用户可配置 provider/base_url/api_key/model，持久化到 SQLite。

支持任意 OpenAI 兼容接口：DeepSeek、OpenAI、通义千问、Moonshot、
Ollama(本地)、vLLM 等。默认配置指向 DeepSeek。
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "financecrew.db"

DEFAULT_CONFIG: dict[str, Any] = {
    "provider": "deepseek",
    "base_url": "https://api.deepseek.com/v1",
    "api_key": "",
    "model": "deepseek-chat",
    "temperature": 0.3,
    "max_tokens": 4096,
}


def get_invite_required() -> bool:
    """读取邀请码注册开关；旧版本未配置时保持原有行为。"""
    _init_db()
    with _connect() as conn:
        row = conn.execute("SELECT value FROM app_config WHERE key='invite_required'").fetchone()
        if row is not None:
            try:
                return bool(json.loads(row["value"]))
            except json.JSONDecodeError:
                return row["value"].lower() == "true"
        return conn.execute("SELECT COUNT(*) FROM invite_codes").fetchone()[0] > 0 if _has_invite_table(conn) else False


def _has_invite_table(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='invite_codes'").fetchone() is not None


def set_invite_required(required: bool) -> bool:
    _init_db()
    with _connect() as conn:
        conn.execute("INSERT OR REPLACE INTO app_config (key, value) VALUES ('invite_required', ?)", (json.dumps(bool(required)),))
    return bool(required)

# 常见 provider 预设，用户选择后自动填充
PROVIDER_PRESETS: dict[str, dict[str, str]] = {
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
    },
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
    },
    "moonshot": {
        "base_url": "https://api.moonshot.cn/v1",
        "model": "moonshot-v1-8k",
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "model": "qwen2.5:14b",
    },
    "custom": {
        "base_url": "",
        "model": "",
    },
}


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    with _connect() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS app_config (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL,
                result TEXT
            )"""
        )
        # 交易后反思学习闭环：记录每次决策，N天后结算并反思
        conn.execute(
            """CREATE TABLE IF NOT EXISTS reflection_memos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                ticker TEXT NOT NULL,
                role TEXT NOT NULL,
                decision_date TEXT NOT NULL,
                decision_score REAL,
                decision_summary TEXT,
                raw_return REAL,
                alpha_return REAL,
                reflection TEXT,
                verdict TEXT,
                settled_at TEXT,
                status TEXT DEFAULT 'pending'
            )"""
        )
        cols = [r[1] for r in conn.execute("PRAGMA table_info(reflection_memos)").fetchall()]
        if "user_id" not in cols:
            conn.execute("ALTER TABLE reflection_memos ADD COLUMN user_id INTEGER")
        if "analysis_id" not in cols:
            conn.execute("ALTER TABLE reflection_memos ADD COLUMN analysis_id INTEGER")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_reflection_ticker ON reflection_memos(ticker, status)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_reflection_user ON reflection_memos(user_id, ticker, status)"
        )


def get_config() -> dict[str, Any]:
    """读取当前配置（数据库优先，缺失字段用默认值补齐）。"""
    _init_db()
    cfg = dict(DEFAULT_CONFIG)
    with _connect() as conn:
        rows = conn.execute("SELECT key, value FROM app_config").fetchall()
    encrypted_key = ""
    for row in rows:
        key, value = row["key"], row["value"]
        if key == "llm_api_key_enc":
            encrypted_key = value
            continue
        if key in cfg:
            try:
                cfg[key] = json.loads(value)
            except json.JSONDecodeError:
                cfg[key] = value
    if encrypted_key:
        from .auth import decrypt_key
        cfg["api_key"] = decrypt_key(encrypted_key)
    return cfg


def save_config(new_cfg: dict[str, Any]) -> dict[str, Any]:
    """保存配置：只更新合法字段，api_key 为空字符串时保留旧值。"""
    _init_db()
    cur = dict(DEFAULT_CONFIG)
    cur.update({k: v for k, v in new_cfg.items() if k in cur})

    old = get_config()
    if not cur.get("api_key") and old.get("api_key"):
        cur["api_key"] = old["api_key"]

    from .auth import encrypt_key
    encrypted_key = encrypt_key(str(cur.pop("api_key", "")))
    with _connect() as conn:
        conn.execute("DELETE FROM app_config WHERE key='api_key'")
        conn.execute("INSERT OR REPLACE INTO app_config (key, value) VALUES ('llm_api_key_enc', ?)", (encrypted_key,))
        for k, v in cur.items():
            conn.execute(
                "INSERT OR REPLACE INTO app_config (key, value) VALUES (?, ?)",
                (k, json.dumps(v, ensure_ascii=False)),
            )
    cur["api_key"] = old.get("api_key", "") if not new_cfg.get("api_key") else new_cfg["api_key"]
    return cur


def apply_preset(provider: str) -> dict[str, Any]:
    """应用 provider 预设的 base_url 和 model（不覆盖用户已填的 api_key）。"""
    preset = PROVIDER_PRESETS.get(provider, PROVIDER_PRESETS["custom"])
    cur = get_config()
    cur["provider"] = provider
    cur["base_url"] = preset["base_url"]
    cur["model"] = preset["model"]
    return cur
