"""用户通知：持久化预警、反馈回复和定时任务结果。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from .config import _connect


def _ensure_table() -> None:
    with _connect() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                link TEXT NOT NULL DEFAULT '',
                read_at TEXT,
                created_at TEXT NOT NULL
            )"""
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, id DESC)"
        )


def create_notification(
    user_id: int,
    kind: str,
    title: str,
    message: str,
    link: str = "",
) -> int:
    _ensure_table()
    with _connect() as conn:
        return int(conn.execute(
            """INSERT INTO notifications (user_id, kind, title, message, link, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, kind, title, message, link, datetime.now().isoformat(timespec="seconds")),
        ).lastrowid)


def list_notifications(user_id: int, limit: int = 50) -> dict[str, Any]:
    _ensure_table()
    with _connect() as conn:
        unread = conn.execute(
            "SELECT COUNT(*) FROM notifications WHERE user_id=? AND read_at IS NULL",
            (user_id,),
        ).fetchone()[0]
        rows = conn.execute(
            "SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    return {"items": [dict(row) for row in rows], "unread": unread}


def mark_all_read(user_id: int) -> None:
    _ensure_table()
    with _connect() as conn:
        conn.execute(
            "UPDATE notifications SET read_at=? WHERE user_id=? AND read_at IS NULL",
            (datetime.now().isoformat(timespec="seconds"), user_id),
        )


def delete_notification(notification_id: int, user_id: int) -> bool:
    _ensure_table()
    with _connect() as conn:
        return conn.execute(
            "DELETE FROM notifications WHERE id=? AND user_id=?",
            (notification_id, user_id),
        ).rowcount > 0
