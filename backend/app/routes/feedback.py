"""用户反馈：登录用户提交，持久化到 SQLite。"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator

from ..config import _connect
from ..deps import get_current_user

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
