"""路由模块: system"""
from __future__ import annotations
from typing import Any
import asyncio
import time
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from .. import config, scheduler
from ..auth import get_profile
from ..config import get_config, save_config, PROVIDER_PRESETS
from ..deps import consume_model_access, get_current_user, require_admin

router = APIRouter()


def _mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "****"
    return key[:4] + "****" + key[-4:]


def _public_config() -> dict[str, Any]:
    from ..config import get_config
    cfg = get_config()
    out = dict(cfg)
    out["api_key_configured"] = bool(cfg.get("api_key"))
    out["api_key"] = ""
    return out


from datetime import date
from ..llm_compare import compare_models
from ..models import LLMConfig


@router.get("/api/health")
def health() -> dict[str, str]:
    try:
        with config._connect() as conn:
            conn.execute("SELECT 1")
    except Exception:
        raise HTTPException(status_code=503, detail="database unavailable")

    scheduler_status = "running" if scheduler.is_scheduler_running() else "stopped"
    return {
        "status": "ok" if scheduler_status == "running" else "degraded",
        "database": "ok",
        "scheduler": scheduler_status,
    }



@router.get("/api/providers")
def providers() -> dict[str, Any]:
    return PROVIDER_PRESETS



@router.get("/api/config")
def read_config(admin: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    return _public_config()



@router.put("/api/config")
def write_config(
    cfg: LLMConfig,
    admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    save_config(cfg.model_dump())
    from .. import auth
    auth.audit_log(admin["id"], admin["username"], "update_default_llm_config")
    return _public_config()


# ---------- 认证与用户画像 ----------


@router.post("/api/llm-compare")
async def llm_compare_api(request: Request, user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """多LLM模型对比：同一prompt调用多个模型，对比回答。需要登录。
    body: {prompt, models: [{name, base_url, api_key, model}]}
    """
    body = await request.json()
    prompt = body.get("prompt", "").strip()
    models = body.get("models", [])
    if not prompt or not isinstance(models, list) or not models:
        raise HTTPException(400, "请提供prompt和models列表")
    if len(models) > 5 or not all(isinstance(model, dict) for model in models):
        raise HTTPException(400, "models 必须是最多5项的对象列表")
    consume_model_access(user)
    started = time.perf_counter()
    results = await asyncio.to_thread(compare_models, prompt, models)
    return {
        "results": results,
        "execution": {
            "mode": "parallel",
            "model_count": len(models),
            "wall_latency_ms": int((time.perf_counter() - started) * 1000),
        },
    }


