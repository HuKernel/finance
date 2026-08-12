"""会员购买与支付回调路由。"""
from __future__ import annotations

from urllib.parse import parse_qsl

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from .. import payment
from ..deps import get_current_user, require_admin

router = APIRouter()


@router.get("/api/admin/payment-config")
def get_admin_payment_config(admin: dict = Depends(require_admin)) -> dict:
    return payment.admin_config()


@router.put("/api/admin/payment-config")
def put_admin_payment_config(body: dict, admin: dict = Depends(require_admin)) -> dict:
    try:
        result = payment.save_admin_config(body)
    except (ValueError, OSError) as exc:
        raise HTTPException(400, f"支付配置无效：{exc}") from exc
    from .. import auth
    auth.audit_log(admin["id"], admin["username"], "update_payment_config")
    return result


@router.get("/api/payments/config")
def payment_config(user: dict = Depends(get_current_user)) -> dict:
    return payment.public_config()


@router.post("/api/payments/orders")
def create_payment_order(body: dict, user: dict = Depends(get_current_user)) -> dict:
    if not body.get("payment_agreement_accepted"):
        raise HTTPException(400, "请阅读并同意会员与支付协议")
    try:
        from .. import auth
        auth.record_agreement_consent(user["id"], "payment")
        return payment.create_order(user["id"], body.get("plan", ""), body.get("channel", ""))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc


@router.get("/api/payments/orders/{order_no}")
def payment_order(order_no: str, user: dict = Depends(get_current_user)) -> dict:
    try:
        return payment.get_order(order_no, user["id"])
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/api/payments/wechat/notify")
async def wechat_notify(request: Request) -> Response:
    try:
        payment.handle_wechat_notify(request.headers, (await request.body()).decode())
    except (ValueError, KeyError):
        return Response(status_code=400)
    return Response(status_code=200)


@router.post("/api/payments/alipay/notify")
async def alipay_notify(request: Request) -> Response:
    params = dict(parse_qsl((await request.body()).decode(), keep_blank_values=True))
    try:
        payment.handle_alipay_notify(params)
    except (ValueError, KeyError):
        return Response("failure", media_type="text/plain", status_code=400)
    return Response("success", media_type="text/plain")
