"""GitHub OAuth App 登录配置与授权码流程。"""
from __future__ import annotations

import base64
import hashlib
import os
import secrets
from typing import Any
from urllib.parse import urlencode

from . import http_client

from . import auth

FIELDS = {"site_url": False, "client_id": False, "client_secret": True}


def _get(key: str) -> str:
    auth._init_db()
    with auth._connect() as conn:
        row = conn.execute("SELECT value FROM app_config WHERE key=?", ("github_oauth." + key,)).fetchone()
    if not row:
        return os.getenv("GITHUB_OAUTH_" + key.upper(), "").strip()
    return auth.decrypt_key(row["value"]) if FIELDS[key] else row["value"]


def configured() -> bool:
    return all(_get(key) for key in FIELDS)


def admin_config() -> dict[str, Any]:
    return {
        "values": {"site_url": _get("site_url"), "client_id": _get("client_id"), "client_secret": ""},
        "client_secret_configured": bool(_get("client_secret")),
        "enabled": configured(),
    }


def save_admin_config(values: dict[str, Any]) -> dict[str, Any]:
    clean = {key: str(values.get(key, "")).strip() for key in FIELDS if key in values}
    site_url = clean.get("site_url")
    if site_url and not (site_url.startswith("https://") or site_url.startswith("http://localhost") or site_url.startswith("http://127.0.0.1")):
        raise ValueError("站点地址必须使用 HTTPS；仅本地开发可使用 HTTP")
    if site_url:
        clean["site_url"] = site_url.rstrip("/")
    stored = {key: auth.encrypt_key(value) if FIELDS[key] else value for key, value in clean.items() if not FIELDS[key] or value}
    auth._init_db()
    with auth._connect() as conn:
        for key, value in stored.items():
            conn.execute("INSERT OR REPLACE INTO app_config (key,value) VALUES (?,?)", ("github_oauth." + key, value))
    return admin_config()


def callback_url() -> str:
    return _get("site_url").rstrip("/") + "/api/auth/github/callback"


def authorize_url() -> tuple[str, str, str]:
    if not configured():
        raise RuntimeError("GitHub 登录尚未配置")
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    query = urlencode({
        "client_id": _get("client_id"), "redirect_uri": callback_url(), "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256", "scope": "",
    })
    return "https://github.com/login/oauth/authorize?" + query, state, verifier


def exchange_identity(code: str, verifier: str) -> dict[str, Any]:
    token_response = http_client.post(
        "https://github.com/login/oauth/access_token",
        json={"client_id": _get("client_id"), "client_secret": _get("client_secret"), "code": code, "redirect_uri": callback_url(), "code_verifier": verifier},
        headers={"Accept": "application/json"}, timeout=15,
    )
    token_response.raise_for_status()
    access_token = token_response.json().get("access_token")
    if not access_token:
        raise ValueError("GitHub 未返回访问令牌")
    user_response = http_client.get(
        "https://api.github.com/user",
        headers={"Accept": "application/vnd.github+json", "Authorization": "Bearer " + access_token, "X-GitHub-Api-Version": "2022-11-28"},
        timeout=15,
    )
    user_response.raise_for_status()
    profile = user_response.json()
    if not profile.get("id") or not profile.get("login"):
        raise ValueError("GitHub 用户身份不完整")
    return profile
