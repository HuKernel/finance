"""用户反馈：登录用户提交，持久化到 SQLite。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator, model_validator

from ..config import _connect
from ..deps import get_current_user, require_admin

router = APIRouter()


class FeedbackRequest(BaseModel):
    category: Literal["suggestion", "bug", "data", "other"]
    content: str = Field(min_length=5, max_length=1000)
    page: str = Field(default="", max_length=80)

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 5:
            raise ValueError("反馈内容至少需要 5 个字")
        return value


class FeedbackUpdate(BaseModel):
    status: Literal["new", "processing", "resolved"] | None = None
    reply: str | None = Field(default=None, max_length=1000)

    @field_validator("reply")
    @classmethod
    def validate_reply(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("回复内容不能为空")
        return value

    @model_validator(mode="after")
    def validate_update(self) -> "FeedbackUpdate":
        if self.status is None and self.reply is None:
            raise ValueError("至少需要更新回复或状态")
        return self


def _ensure_table() -> None:
    with _connect() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS user_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                content TEXT NOT NULL,
                page TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'new',
                created_at TEXT NOT NULL
            )"""
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_feedback_user ON user_feedback(user_id, id)"
        )
        columns = {row[1] for row in conn.execute("PRAGMA table_info(user_feedback)")}
        if "admin_reply" not in columns:
            conn.execute("ALTER TABLE user_feedback ADD COLUMN admin_reply TEXT NOT NULL DEFAULT ''")


@router.post("/api/feedback")
def create_feedback(
    body: FeedbackRequest,
    user: dict = Depends(get_current_user),
) -> dict[str, int | str]:
    _ensure_table()
    with _connect() as conn:
        feedback_id = conn.execute(
            """INSERT INTO user_feedback
               (user_id, category, content, page, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                user["id"],
                body.category,
                body.content,
                body.page.strip(),
                datetime.now().isoformat(timespec="seconds"),
            ),
        ).lastrowid
    return {"id": int(feedback_id), "status": "received"}


@router.get("/api/feedback")
def list_own_feedback(
    user: dict = Depends(get_current_user),
) -> list[dict[str, Any]]:
    _ensure_table()
    with _connect() as conn:
        rows = conn.execute(
            """SELECT id, category, content, page, status, created_at, admin_reply
               FROM user_feedback WHERE user_id = ? ORDER BY id DESC""",
            (user["id"],),
        ).fetchall()
    return [dict(row) for row in rows]


@router.get("/api/admin/feedback")
def list_feedback(
    _admin: dict = Depends(require_admin),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, Any]]:
    _ensure_table()
    with _connect() as conn:
        rows = conn.execute(
            """SELECT f.*, COALESCE(u.username, '已删除用户') AS username
               FROM user_feedback f
               LEFT JOIN users u ON u.id = f.user_id
               ORDER BY f.id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


@router.patch("/api/admin/feedback/{feedback_id}")
def update_feedback(
    feedback_id: int,
    body: FeedbackUpdate,
    _admin: dict = Depends(require_admin),
) -> dict[str, str]:
    _ensure_table()
    with _connect() as conn:
        cursor = conn.execute(
            """UPDATE user_feedback
               SET status = COALESCE(?, status),
                   admin_reply = COALESCE(?, admin_reply)
               WHERE id = ?""",
            (body.status, body.reply, feedback_id),
        )
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="反馈不存在")
    return {"status": "updated"}


@router.delete("/api/admin/feedback/{feedback_id}")
def delete_feedback(
    feedback_id: int,
    _admin: dict = Depends(require_admin),
) -> dict[str, str]:
    _ensure_table()
    with _connect() as conn:
        cursor = conn.execute("DELETE FROM user_feedback WHERE id = ?", (feedback_id,))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="反馈不存在")
    return {"status": "deleted"}
