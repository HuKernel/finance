"""管理员功能。"""
from __future__ import annotations

import os
import secrets
from datetime import datetime
from typing import Any

from ._db import _connect, _init_db


def is_admin(user_id: int) -> bool:
    """检查用户是否是管理员。"""
    with _connect() as conn:
        row = conn.execute("SELECT is_admin FROM users WHERE id=?", (user_id,)).fetchone()
    return bool(row and row["is_admin"])


def list_all_users(page: int = 1, page_size: int = 20) -> dict[str, Any]:
    """列出所有用户（管理员功能）。"""
    _init_db()
    with _connect() as conn:
        total = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
        rows = conn.execute(
            "SELECT u.id, u.username, u.created_at, u.is_admin, u.is_super, u.is_active, u.is_invited, u.plan_code, u.membership_expires_at, "
            "(SELECT COUNT(*) FROM analyses WHERE analyses.user_id = u.id) as analysis_count "
            "FROM users u ORDER BY u.id LIMIT ? OFFSET ?", (page_size, (page - 1) * page_size)
        ).fetchall()
    return {"items": [dict(r) for r in rows], "total": total, "page": page, "page_size": page_size}


def delete_user(user_id: int) -> bool:
    _init_db()
    with _connect() as conn:
        row = conn.execute("SELECT id, is_super FROM users WHERE id=?", (user_id,)).fetchone()
        if not row:
            return False
        if row["is_super"]:
            raise ValueError("超级管理员不可删除")
        # 邀请奖励属于已删除用户的关系记录，也一并清理。
        conn.execute(
            "DELETE FROM invite_rewards WHERE inviter_id=? OR invited_user_id=?",
            (user_id, user_id),
        )
        # 删除邀请人时，未使用的邀请码没有保留价值；已使用的保留历史。
        conn.execute(
            "DELETE FROM invite_codes WHERE created_by=? AND used_by IS NULL",
            (user_id,),
        )
        for table, col in [("user_profiles", "user_id"), ("user_llm_config", "user_id"), ("monthly_model_usage", "user_id"), ("oauth_identities", "user_id")]:
            conn.execute(f"DELETE FROM {table} WHERE {col}=?", (user_id,))
        conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    return True


def toggle_user_active(user_id: int) -> bool:
    """启用/禁用用户。"""
    _init_db()
    with _connect() as conn:
        row = conn.execute("SELECT is_active, is_super FROM users WHERE id=?", (user_id,)).fetchone()
        if row is None:
            return False
        if row["is_super"]:
            raise ValueError("超级管理员不可禁用")
        conn.execute("UPDATE users SET is_active=? WHERE id=?", (1 - row["is_active"], user_id))
    return True


def set_user_admin(user_id: int, is_admin_val: bool) -> bool:
    """设置/取消管理员（超级管理员恒为管理员，不可取消）。"""
    _init_db()
    with _connect() as conn:
        if not is_admin_val:
            row = conn.execute("SELECT is_super FROM users WHERE id=?", (user_id,)).fetchone()
            if row and row["is_super"]:
                raise ValueError("超级管理员的管理员身份不可取消")
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
    from . import DB_PATH
    from .. import alert, config, portfolio
    config._init_db()
    alert._ensure_table()
    portfolio._ensure_tables()
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
