"""per-user LLM 配置。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from ._db import _connect, _init_db
from .crypto import decrypt_key, encrypt_key


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
    from ..config import get_config
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
