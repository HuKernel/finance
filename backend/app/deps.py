"""共享依赖：认证守卫。

从 main.py 拆出来避免循环导入（routes 模块需要 get_current_user，
但 main.py 又要导入 routes 模块来注册路由）。

认证来源（按优先级）：
1. Authorization: Bearer <token>（API 客户端 / 向后兼容）
2. HttpOnly Cookie fc_token（网页端，防 XSS 窃取 token）

token 携带 pwd_version，改密码后自增，所有旧 token 立即失效。
"""
from __future__ import annotations

from typing import Any

from fastapi import Depends, Header, HTTPException, Request

from . import auth

COOKIE_NAME = "fc_token"
COOKIE_MAX_AGE = 7 * 24 * 3600  # 7天，与 TOKEN_TTL 一致


def _extract_token(authorization: str, request: Request) -> str:
    if authorization.startswith("Bearer "):
        return authorization[7:].strip()
    cookie_token = request.cookies.get(COOKIE_NAME, "")
    return cookie_token.strip()


def get_current_user(request: Request, authorization: str = Header(default="")) -> dict[str, Any]:
    token = _extract_token(authorization, request)
    if not token:
        raise HTTPException(status_code=401, detail="未登录")
    payload = auth.decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    user = auth.get_user(int(payload["sub"]))
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    if not user.get("is_active"):
        raise HTTPException(status_code=403, detail="账号已被禁用")
    # 密码版本校验：改密码后旧 token 全部失效
    try:
        token_pwd_version = int(payload.get("pwd_version", 0))
    except (TypeError, ValueError):
        token_pwd_version = 0
    current_pwd_version = auth.get_pwd_version(int(payload["sub"]))
    if token_pwd_version != current_pwd_version:
        raise HTTPException(status_code=401, detail="密码已修改，请重新登录")
    return user


def require_admin(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """管理员守卫：非管理员返回403。"""
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


def require_membership(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    if not auth.has_membership(user):
        raise HTTPException(status_code=403, detail="模型配置仅限会员使用")
    return user


def consume_model_access(user: dict[str, Any]) -> None:
    try:
        auth.consume_model_usage(user)
    except PermissionError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc


def _resolve_ticker(ticker: str) -> str | None:
    """把用户输入（公司名/代码）解析为标准代码，复用 tools.resolve_symbol。"""
    from .tools import resolve_symbol
    resolved = resolve_symbol(ticker)
    if resolved.isdigit() and len(resolved) == 6:
        return resolved
    if resolved.startswith(("hk", "us")):
        return resolved
    return None
