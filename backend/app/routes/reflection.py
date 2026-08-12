"""路由模块: reflection"""
from __future__ import annotations
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..auth import get_profile
from ..config import get_config, save_config, PROVIDER_PRESETS
from ..deps import consume_model_access, get_current_user, require_admin

router = APIRouter()

from ..reflection_engine import get_recent_memos, settle_pending
from ..llm import LLMClient


@router.get("/api/reflection/{ticker}")
def reflection_api(
    ticker: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """获取某股票的历史决策反思记录（已结算）。"""
    return {"ticker": ticker, "memos": get_recent_memos(ticker, user["id"], limit=20)}



@router.post("/api/reflection/settle/{ticker}")
def settle_api(
    ticker: str,
    force: bool = False,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """手动触发某股票的 pending 决策结算（N 天后反思）。
    force=true 时立即结算（不等5天，用于测试/演示）。"""
    consume_model_access(user)
    settled = settle_pending(
        ticker,
        LLMClient(user_id=user["id"]),
        force=force,
        user_id=user["id"],
    )
    return {"ticker": ticker, "settled": settled}


# ==================== 定时/自动化分析 ====================


