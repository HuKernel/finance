"""路由模块: auth"""
from __future__ import annotations
import secrets
import base64
from urllib.parse import quote
from typing import Any
import requests
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, StreamingResponse

from ..auth import get_profile
from ..config import get_config, save_config, PROVIDER_PRESETS
from ..deps import get_current_user, require_admin, require_membership

router = APIRouter()

from .. import auth
from ..models import LLMConfig

OAUTH_COOKIE_MAX_AGE = 600


@router.post("/api/auth/register")
def register(body: dict[str, str], request: Request) -> dict[str, Any]:
    client_ip = request.client.host if request.client else "unknown"
    allowed, msg = auth.check_rate_limit(f"register:{client_ip}")
    if not allowed:
        raise HTTPException(429, msg)
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    email = (body.get("email") or "").strip().lower()
    invite_code = body.get("invite_code", "").strip()
    if not body.get("agreements_accepted"):
        raise HTTPException(400, "请阅读并同意用户服务协议和隐私政策")
    if len(username) < 2 or len(username) > 20:
        raise HTTPException(400, "用户名需 2-20 个字符")
    if len(password) < 8:
        raise HTTPException(400, "密码至少 8 位")
    if email and ("@" not in email or "." not in email):
        raise HTTPException(400, "请输入有效邮箱")
    try:
        user = auth.create_user(username, password, invite_code)
        auth.record_agreement_consent(user["id"], "service")
        auth.record_agreement_consent(user["id"], "privacy")
        auth.set_user_email(user["id"], email)
        if email:
            try:
                from ..mail import send_email
                token = auth.issue_auth_token(user["id"], "email_verify")
                send_email(email, "验证邮箱", f"请打开以下链接完成邮箱验证（15分钟内有效）：\n/api/auth/verify-email?token={quote(token)}")
            except Exception:
                pass
    except ValueError as e:
        raise HTTPException(400, str(e))
    token = auth.create_token(user["id"], user["username"])
    auth.record_login_success(f"register:{client_ip}")
    auth.audit_log(user["id"], username, "register", f"invite_code={invite_code}", client_ip)
    return {"token": token, "user": user, "profile": auth.get_profile(user["id"])}



@router.post("/api/auth/login")
def login(body: dict[str, str], request: Request) -> dict[str, Any]:
    client_ip = request.client.host if request.client else "unknown"
    username = (body.get("username") or "").strip()
    for ident in [f"login_ip:{client_ip}", f"login_user:{username}"]:
        allowed, msg = auth.check_rate_limit(ident)
        if not allowed:
            raise HTTPException(429, msg)

    result = auth.authenticate(username, body.get("password") or "")
    if not result:
        for ident in [f"login_ip:{client_ip}", f"login_user:{username}"]:
            auth.record_login_fail(ident)
        auth.audit_log(None, username, "login_failed", "password", client_ip)
        raise HTTPException(401, "用户名或密码错误")
    if result.get("_disabled"):
        raise HTTPException(403, "账号已被禁用，请联系管理员")
    user = result
    secret = auth.get_mfa_secret(user["id"])
    if secret and not auth.verify_totp(secret, body.get("mfa_code", "")):
        auth.audit_log(user["id"], username, "login_failed", "mfa", client_ip)
        raise HTTPException(401, "请输入正确的 MFA 验证码")
    token = auth.create_token(user["id"], user["username"])
    for ident in [f"login_ip:{client_ip}", f"login_user:{username}"]:
        auth.record_login_success(ident)
    auth.audit_log(user["id"], username, "login", ip=client_ip)
    return {"token": token, "user": user, "profile": auth.get_profile(user["id"])}


@router.post("/api/auth/verify-email")
def verify_email(body: dict[str, str]) -> dict[str, str]:
    user_id = auth.consume_auth_token(body.get("token", ""), "email_verify")
    if not user_id:
        raise HTTPException(400, "验证链接无效或已过期")
    auth.set_email_verified(user_id)
    return {"status": "ok"}


@router.get("/api/auth/verify-email")
def verify_email_link(token: str = "") -> RedirectResponse:
    user_id = auth.consume_auth_token(token, "email_verify")
    if user_id:
        auth.set_email_verified(user_id)
    return RedirectResponse("/?email_verified=" + ("1" if user_id else "0"))


@router.post("/api/auth/forgot-password")
def forgot_password(body: dict[str, str]) -> dict[str, str]:
    email = (body.get("email") or "").strip().lower()
    with auth._connect() as conn:
        row = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
    if row:
        from ..mail import send_email
        token = auth.issue_auth_token(int(row["id"]), "password_reset")
        try:
            send_email(email, "重置密码", f"请使用以下链接重置密码（15分钟内有效）：\n/?reset_token={quote(token)}")
        except Exception:
            pass
    return {"status": "ok"}


@router.post("/api/auth/reset-password")
def reset_password(body: dict[str, str]) -> dict[str, str]:
    user_id = auth.consume_auth_token(body.get("token", ""), "password_reset")
    password = body.get("password", "")
    if not user_id or len(password) < 8:
        raise HTTPException(400, "链接无效或密码至少 8 位")
    digest, salt = auth.hash_password(password)
    with auth._connect() as conn:
        conn.execute("UPDATE users SET password_hash=?, salt=? WHERE id=?", (digest, salt, user_id))
    return {"status": "ok"}


@router.post("/api/auth/mfa/setup")
def mfa_setup(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, str]:
    secret = base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")
    auth.set_mfa(user["id"], secret, False)
    return {"secret": secret, "otpauth": f"otpauth://totp/FinanceCrew:{quote(user['username'])}?secret={secret}&issuer=FinanceCrew"}


@router.post("/api/auth/mfa/enable")
def mfa_enable(body: dict[str, str], user: dict[str, Any] = Depends(get_current_user)) -> dict[str, str]:
    secret = auth.get_mfa_secret(user["id"])
    if not secret or not auth.verify_totp(secret, body.get("code", "")):
        raise HTTPException(400, "验证码不正确")
    auth.set_mfa(user["id"], secret, True)
    return {"status": "ok"}


@router.post("/api/auth/mfa/disable")
def mfa_disable(body: dict[str, str], user: dict[str, Any] = Depends(get_current_user)) -> dict[str, str]:
    secret = auth.get_mfa_secret(user["id"])
    if not secret or not auth.verify_totp(secret, body.get("code", "")):
        raise HTTPException(400, "验证码不正确")
    auth.set_mfa(user["id"], None, False)
    return {"status": "ok"}


@router.get("/api/auth/providers")
def auth_providers() -> dict[str, bool]:
    from ..github_oauth import configured
    return {"github": configured()}


@router.get("/api/auth/github/start")
def github_start() -> RedirectResponse:
    from ..github_oauth import authorize_url
    try:
        url, state, verifier = authorize_url()
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    response = RedirectResponse(url)
    from ..github_oauth import _get
    secure = _get("site_url").startswith("https://")
    response.set_cookie("github_oauth_state", state, max_age=OAUTH_COOKIE_MAX_AGE, httponly=True, secure=secure, samesite="lax")
    response.set_cookie("github_oauth_verifier", verifier, max_age=OAUTH_COOKIE_MAX_AGE, httponly=True, secure=secure, samesite="lax")
    return response


@router.get("/api/auth/github/callback")
def github_callback(request: Request, code: str = "", state: str = "") -> RedirectResponse:
    from ..github_oauth import exchange_identity, _get
    site_url = _get("site_url").rstrip("/")
    expected_state = request.cookies.get("github_oauth_state", "")
    verifier = request.cookies.get("github_oauth_verifier", "")
    if not code or not state or not expected_state or not secrets.compare_digest(state, expected_state) or not verifier:
        return RedirectResponse(site_url + "/?oauth_error=state")
    try:
        profile = exchange_identity(code, verifier)
        user = auth.get_or_create_oauth_user("github", str(profile["id"]), str(profile["login"]))
        token = auth.create_token(user["id"], user["username"])
        auth.audit_log(user["id"], user["username"], "login_github", ip=request.client.host if request.client else "")
        response = RedirectResponse(site_url + "/#oauth_token=" + token)
    except (ValueError, PermissionError, requests.RequestException) as exc:
        auth.audit_log(None, "", "login_github_failed", type(exc).__name__ + ": " + str(exc)[:200], request.client.host if request.client else "")
        response = RedirectResponse(site_url + "/?oauth_error=github")
    except Exception as exc:
        auth.audit_log(None, "", "login_github_failed", type(exc).__name__ + ": " + str(exc)[:200], request.client.host if request.client else "")
        response = RedirectResponse(site_url + "/?oauth_error=github")
    response.delete_cookie("github_oauth_state")
    response.delete_cookie("github_oauth_verifier")
    return response


@router.get("/api/admin/github-oauth")
def get_admin_github_oauth(admin: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    from ..github_oauth import admin_config
    return admin_config()


@router.put("/api/admin/github-oauth")
def put_admin_github_oauth(body: dict[str, Any], admin: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    from ..github_oauth import save_admin_config
    try:
        result = save_admin_config(body)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    auth.audit_log(admin["id"], admin["username"], "update_github_oauth")
    return result


@router.get("/api/admin/mail")
def get_admin_mail(admin: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    from ..mail import admin_config
    return admin_config()


@router.put("/api/admin/mail")
def put_admin_mail(body: dict[str, Any], admin: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    from ..mail import save_admin_config
    result = save_admin_config(body)
    auth.audit_log(admin["id"], admin["username"], "update_mail_config")
    return result



@router.get("/api/auth/me")
def me(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    return {"user": user, "profile": auth.get_profile(user["id"])}


@router.get("/api/auth/capabilities")
def capabilities(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    return {
        "plan": user.get("plan_code") if auth.has_membership(user) else "free",
        "membership_expires_at": user.get("membership_expires_at"),
        "model_usage": auth.get_model_usage(user),
    }



@router.get("/api/auth/profile")
def get_profile(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    return auth.get_profile(user["id"])


@router.get("/api/auth/security")
def security(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    return auth.get_security_profile(user["id"])



@router.put("/api/auth/profile")
def put_profile(body: dict[str, Any], user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    try:
        return auth.update_profile(
            user["id"],
            risk_preference=body.get("risk_preference"),
            watchlist=body.get("watchlist"),
        )
    except ValueError as e:
        raise HTTPException(400, str(e))



@router.post("/api/auth/change-password")
async def change_password_api(request: Request, user: dict[str, Any] = Depends(get_current_user)) -> dict[str, str]:
    """修改密码。需提供旧密码。"""
    body = await request.json()
    old_pwd = body.get("old_password", "")
    new_pwd = body.get("new_password", "")
    if not old_pwd or not new_pwd:
        raise HTTPException(400, "请填写旧密码和新密码")
    try:
        ok = auth.change_password(user["id"], old_pwd, new_pwd)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not ok:
        raise HTTPException(400, "旧密码错误")
    return {"status": "ok"}


# ---------- per-user LLM 配置 ----------


@router.get("/api/auth/llm-config")
def get_llm_config_api(user: dict[str, Any] = Depends(require_membership)) -> dict[str, Any]:
    """获取当前用户的LLM配置（api_key脱敏）。"""
    return auth.get_user_llm_config(user["id"]) | {"api_key": auth._mask_key(auth.get_user_llm_config(user["id"])["api_key"])}



@router.put("/api/auth/llm-config")
async def save_llm_config_api(request: Request, user: dict[str, Any] = Depends(require_membership)) -> dict[str, Any]:
    """保存当前用户的LLM配置（api_key加密存储）。"""
    body = await request.json()
    return auth.save_user_llm_config(user["id"], body)


# ---------- 投研分析 ----------

def _resolve_ticker(ticker: str) -> str | None:
    """把用户输入（公司名/代码）解析为标准代码，复用 tools.resolve_symbol。"""
    from ..tools import resolve_symbol
    resolved = resolve_symbol(ticker)
    # 校验是否合法：A股6位数字 / hk+5位 / us+代码
    if resolved.isdigit() and len(resolved) == 6:
        return resolved
    if resolved.startswith(("hk", "us")):
        return resolved
    return None



@router.put("/api/auth/analyst-config")
def save_analyst_config(body: dict[str, Any], user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """保存用户分析师配置（启用哪些分析师）。"""
    enabled = body.get("enabled_analysts")
    if not isinstance(enabled, list):
        raise HTTPException(status_code=400, detail="enabled_analysts must be a list")
    from ..agents.analysts import ALL_ANALYSTS
    valid_roles = {cls.role for cls in ALL_ANALYSTS}
    enabled = [r for r in enabled if r in valid_roles]
    auth.update_profile(user["id"], analyst_config=enabled)
    return {"enabled_analysts": enabled}



@router.get("/api/admin/users")
def admin_list_users(admin: dict[str, Any] = Depends(require_admin), page: int = 1, page_size: int = 20) -> dict[str, Any]:
    return auth.list_all_users(max(1, page), min(100, max(1, page_size)))


@router.delete("/api/admin/users/{user_id}")
def admin_delete_user(user_id: int, admin: dict[str, Any] = Depends(require_admin)) -> dict[str, str]:
    if user_id == admin["id"]:
        raise HTTPException(400, "不能删除当前登录管理员")
    ok = auth.delete_user(user_id)
    auth.audit_log(admin["id"], admin["username"], "delete_user", f"target_id={user_id}")
    return {"status": "ok" if ok else "not_found"}



@router.post("/api/admin/users/{user_id}/toggle-active")
def admin_toggle_user(user_id: int, admin: dict[str, Any] = Depends(require_admin)) -> dict[str, str]:
    ok = auth.toggle_user_active(user_id)
    auth.audit_log(admin["id"], admin["username"], "toggle_user", f"target_id={user_id}")
    return {"status": "ok" if ok else "not_found"}



@router.post("/api/admin/users/{user_id}/set-admin")
async def admin_set_admin(user_id: int, request: Request, admin: dict[str, Any] = Depends(require_admin)) -> dict[str, str]:
    body = await request.json()
    ok = auth.set_user_admin(user_id, bool(body.get("is_admin", False)))
    auth.audit_log(admin["id"], admin["username"], "set_admin", f"target_id={user_id} value={body.get('is_admin')}")
    return {"status": "ok" if ok else "not_found"}



@router.post("/api/admin/invite-codes")
async def admin_create_invite(request: Request, admin: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    body = await request.json()
    note = body.get("note", "")
    code = auth.create_invite_code(admin["id"], note)
    auth.audit_log(admin["id"], admin["username"], "create_invite", f"code={code['code']}")
    return code


@router.post("/api/auth/invite-codes")
async def create_user_invite(request: Request, user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    body = await request.json()
    code = auth.create_invite_code(user["id"], str(body.get("note", "")))
    auth.audit_log(user["id"], user["username"], "create_invite", f"code={code['code']}")
    return code


@router.get("/api/auth/invite-codes")
def list_user_invites(user: dict[str, Any] = Depends(get_current_user)) -> list[dict[str, Any]]:
    return [item for item in auth.list_invite_codes() if item.get("created_by") == user["id"]]



@router.get("/api/admin/invite-codes")
def admin_list_invites(admin: dict[str, Any] = Depends(require_admin)) -> list[dict[str, Any]]:
    return auth.list_invite_codes()



@router.get("/api/admin/audit-logs")
def admin_audit_logs(admin: dict[str, Any] = Depends(require_admin), page: int = 1, page_size: int = 20) -> dict[str, Any]:
    return auth.list_audit_logs(max(1, page), min(100, max(1, page_size)))



@router.get("/api/admin/stats")
def admin_stats(admin: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    return auth.get_system_stats()



@router.get("/api/auth/is-admin")
def check_is_admin(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    return {"is_admin": bool(user.get("is_admin"))}
