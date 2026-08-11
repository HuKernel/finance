"""用户通知 API。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from .. import notifications
from ..deps import get_current_user

router = APIRouter()


@router.get("/api/notifications")
def list_notifications_api(
    limit: int = Query(default=50, ge=1, le=100),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    return notifications.list_notifications(user["id"], limit)


@router.post("/api/notifications/read-all")
def mark_all_read_api(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, str]:
    notifications.mark_all_read(user["id"])
    return {"status": "ok"}


@router.delete("/api/notifications/{notification_id}")
def delete_notification_api(
    notification_id: int,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    ok = notifications.delete_notification(notification_id, user["id"])
    return {"status": "ok" if ok else "not_found"}
