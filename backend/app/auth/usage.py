"""免费额度与会员用量统计。"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from ._db import _connect, _init_db

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
