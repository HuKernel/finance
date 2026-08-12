"""最小 SMTP 邮件发送与管理员配置。"""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from typing import Any

from . import auth

FIELDS = {"host": False, "port": False, "username": False, "password": True, "from_email": False, "use_tls": False}


def _get(key: str) -> str:
    auth._init_db()
    with auth._connect() as conn:
        row = conn.execute("SELECT value FROM app_config WHERE key=?", ("smtp." + key,)).fetchone()
    if not row:
        return os.getenv("SMTP_" + key.upper(), "").strip()
    return auth.decrypt_key(row["value"]) if FIELDS[key] else row["value"]


def admin_config() -> dict[str, Any]:
    values = {k: ("" if FIELDS[k] else _get(k)) for k in FIELDS}
    return {"values": values, "password_configured": bool(_get("password")), "enabled": bool(_get("host") and _get("from_email"))}


def save_admin_config(values: dict[str, Any]) -> dict[str, Any]:
    clean = {k: str(values.get(k, "")).strip() for k in FIELDS if k in values}
    for key, value in clean.items():
        if FIELDS[key] and not value:
            continue
        stored = auth.encrypt_key(value) if FIELDS[key] else value
        with auth._connect() as conn:
            conn.execute("INSERT OR REPLACE INTO app_config(key,value) VALUES(?,?)", ("smtp." + key, stored))
    return admin_config()


def send_email(to: str, subject: str, body: str) -> None:
    host, sender = _get("host"), _get("from_email")
    if not host or not sender:
        raise RuntimeError("管理员尚未配置邮件服务")
    message = EmailMessage()
    message["From"], message["To"], message["Subject"] = sender, to, subject
    message.set_content(body)
    with smtplib.SMTP(host, int(_get("port") or 587), timeout=15) as server:
        if _get("use_tls").lower() not in ("0", "false", "no"):
            server.starttls()
        if _get("username"):
            server.login(_get("username"), _get("password"))
        server.send_message(message)
