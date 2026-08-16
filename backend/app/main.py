"""FinanceCrew 后端 API 入口。

启动: uvicorn app.main:app --host 0.0.0.0 --port 8000

路由按功能拆分到 app/routes/ 目录，这里只保留：
- app 创建、中间件、CORS、生命周期
- 共享依赖（get_current_user / require_admin）
- 路由注册
- 前端静态托管
"""
from __future__ import annotations

import os
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import auth
from .logger import setup_logging, get_logger

# 初始化日志系统
setup_logging()
logger = get_logger("main")

@asynccontextmanager
async def lifespan(_app: FastAPI):
    # 同步路由跑在线程池里（外部行情请求耗时较长），调大缺省 40 线程上限
    import anyio.to_thread
    anyio.to_thread.current_default_thread_limiter().total_tokens = 100
    # 数据库索引迁移
    try:
        from .db_migrations import run_migrations
        run_migrations()
    except Exception as e:
        logger.warning("数据库迁移失败: %s", e)
    # 调度器
    try:
        from .scheduler import start_scheduler
        start_scheduler()
    except Exception as e:
        logger.warning("调度器启动失败: %s", e)
    yield
    try:
        from .scheduler import stop_scheduler
        stop_scheduler()
    except Exception:
        pass


app = FastAPI(title="FinanceCrew API", version="0.4.0", lifespan=lifespan)


# TrustedHost：部署时可用 TRUSTED_HOSTS=a.com,b.com 收紧 Host 头（防 DNS rebinding / host 注入）
_trusted = [h.strip() for h in os.environ.get("TRUSTED_HOSTS", "").split(",") if h.strip()]
if _trusted:
    from starlette.middleware.trustedhost import TrustedHostMiddleware
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=_trusted)

# CORS: 环境变量 CORS_ORIGINS（逗号分隔）可覆盖，默认只允许本机和局域网
_default_origins = [
    "http://localhost:8000", "http://127.0.0.1:8000",
    "http://localhost:5173", "http://127.0.0.1:5173",
]
_extra_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_default_origins + _extra_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
    allow_credentials=True,
)

# ---------- 请求频率限制中间件（反爬） ----------

_rate_map: dict[str, list[float]] = defaultdict(list)
RATE_WINDOW = 60      # 60秒窗口
RATE_MAX = 200        # 每窗口最多200次请求
RATE_MAX_AUTH = 20    # 登录/注册类接口每窗口最多20次（防爆破）
RATE_CLEANUP_EVERY = 600  # 至少每600秒全量清理一次惰性访问不到的IP
_last_cleanup = 0.0

_AUTH_PATHS = {
    "/api/auth/login", "/api/auth/register", "/api/auth/forgot-password",
    "/api/auth/reset-password", "/api/auth/verify-email",
    "/api/auth/mfa/setup", "/api/auth/mfa/enable", "/api/auth/mfa/disable",
}


def _client_ip(request: Request) -> str:
    """反代场景优先取 X-Forwarded-For 第一个地址。"""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """全局频率限制：每IP每60秒最多200次请求；登录类接口单独 20次/60秒。"""
    global _last_cleanup
    path = request.url.path
    if path == "/api/health":
        return await call_next(request)

    client_ip = _client_ip(request)
    now = time.time()
    # 周期性全量清理，避免长期运行时 _rate_map 无界增长
    if now - _last_cleanup > RATE_CLEANUP_EVERY:
        stale = [ip for ip, ts in _rate_map.items() if not ts or now - ts[-1] >= RATE_WINDOW]
        for ip in stale:
            _rate_map.pop(ip, None)
        _last_cleanup = now

    # 登录类接口与普通接口分桶计数：共享桶会导致普通浏览量高时误伤登录接口
    limit = RATE_MAX_AUTH if path in _AUTH_PATHS else RATE_MAX
    bucket_key = f"auth:{client_ip}" if path in _AUTH_PATHS else client_ip
    bucket = _rate_map[bucket_key]
    bucket[:] = [t for t in bucket if now - t < RATE_WINDOW]
    if len(bucket) >= limit:
        return JSONResponse(status_code=429, content={"detail": "请求过于频繁，请稍后再试"})
    bucket.append(now)
    return await call_next(request)


# ---------- 认证依赖（从 deps.py 导入，避免循环导入） ----------

from .deps import get_current_user, require_admin


# ---------- 注册路由模块 ----------

from .routes import (
    system, auth as auth_routes, analysis, market, portfolio,
    backtest, alerts, chat, scheduler, thesis, knowledge,
    reflection, market_data, feedback, notifications, payments,
)

app.include_router(system.router)
app.include_router(auth_routes.router)
app.include_router(analysis.router)
app.include_router(market.router)
app.include_router(portfolio.router)
app.include_router(backtest.router)
app.include_router(alerts.router)
app.include_router(chat.router)
app.include_router(scheduler.router)
app.include_router(thesis.router)
app.include_router(knowledge.router)
app.include_router(reflection.router)
app.include_router(market_data.router)
app.include_router(feedback.router)
app.include_router(notifications.router)
app.include_router(payments.router)


# ---------- 前端静态托管 ----------

FRONTEND_DIST = Path(os.environ.get(
    "FRONTEND_DIST",
    Path(__file__).resolve().parent.parent.parent / "frontend" / "dist",
))

if FRONTEND_DIST.exists():
    from starlette.middleware.base import BaseHTTPMiddleware

    class NoCacheHtmlMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            resp = await call_next(request)
            if request.url.path == '/' or request.url.path.endswith('.html'):
                resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            return resp

    app.add_middleware(NoCacheHtmlMiddleware)
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
