"""微信 Native 支付、支付宝电脑网站支付与会员订单。"""
from __future__ import annotations

import base64
import io
import json
import os
import secrets
import sqlite3
import time
from calendar import monthrange
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from . import auth, config

PLANS = {
    "monthly": {"name": "专业会员月卡", "amount_fen": 2900, "months": 1},
    "yearly": {"name": "专业会员年卡", "amount_fen": 19900, "months": 12},
}


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    auth._init_db()
    with _connect() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS payment_orders (
                order_no TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                plan_code TEXT NOT NULL,
                amount_fen INTEGER NOT NULL,
                channel TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                provider_trade_no TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                paid_at TEXT,
                membership_expires_at TEXT
            )"""
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_payment_orders_user ON payment_orders(user_id, created_at DESC)")


def channel_configured(channel: str) -> bool:
    if channel == "wechat":
        keys = ("WECHAT_APP_ID", "WECHAT_MCH_ID", "WECHAT_CERT_SERIAL_NO", "WECHAT_PRIVATE_KEY_PATH",
                "WECHAT_API_V3_KEY", "WECHAT_PAY_PUBLIC_KEY_ID", "WECHAT_PAY_PUBLIC_KEY_PATH", "PAYMENT_NOTIFY_BASE_URL")
    elif channel == "alipay":
        keys = ("ALIPAY_APP_ID", "ALIPAY_PRIVATE_KEY_PATH", "ALIPAY_PUBLIC_KEY_PATH", "PAYMENT_NOTIFY_BASE_URL")
    else:
        return False
    return all(os.getenv(key, "").strip() for key in keys)


def public_config() -> dict[str, Any]:
    return {
        "plans": [{"code": code, "name": plan["name"], "amount_fen": plan["amount_fen"]} for code, plan in PLANS.items()],
        "channels": {name: channel_configured(name) for name in ("wechat", "alipay")},
    }


def _private_key(path_env: str):
    path = Path(os.environ[path_env])
    return serialization.load_pem_private_key(path.read_bytes(), password=None)


def _public_key(path_env: str):
    raw = Path(os.environ[path_env]).read_bytes()
    try:
        return serialization.load_pem_public_key(raw)
    except ValueError:
        return x509.load_pem_x509_certificate(raw).public_key()


def _rsa_sign(message: str, path_env: str) -> str:
    signature = _private_key(path_env).sign(message.encode(), padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(signature).decode()


def _rsa_verify(message: str, signature: str, path_env: str) -> bool:
    try:
        _public_key(path_env).verify(base64.b64decode(signature), message.encode(), padding.PKCS1v15(), hashes.SHA256())
        return True
    except (InvalidSignature, ValueError):
        return False


def _new_order(user_id: int, plan_code: str, channel: str) -> dict[str, Any]:
    if plan_code not in PLANS or channel not in ("wechat", "alipay"):
        raise ValueError("无效的会员套餐或支付渠道")
    if not channel_configured(channel):
        raise RuntimeError("该支付渠道尚未配置")
    plan = PLANS[plan_code]
    order_no = datetime.now().strftime("FC%Y%m%d%H%M%S") + secrets.token_hex(5).upper()
    created_at = datetime.now().isoformat(timespec="seconds")
    with _connect() as conn:
        conn.execute(
            "INSERT INTO payment_orders (order_no,user_id,plan_code,amount_fen,channel,status,created_at) VALUES (?,?,?,?,?,'pending',?)",
            (order_no, user_id, plan_code, plan["amount_fen"], channel, created_at),
        )
    return {"order_no": order_no, "plan": plan, "created_at": created_at}


def create_order(user_id: int, plan_code: str, channel: str) -> dict[str, Any]:
    init_db()
    order = _new_order(user_id, plan_code, channel)
    if channel == "wechat":
        return _create_wechat_order(order)
    return _create_alipay_order(order)


def _create_wechat_order(order: dict[str, Any]) -> dict[str, Any]:
    path = "/v3/pay/transactions/native"
    body = json.dumps({
        "appid": os.environ["WECHAT_APP_ID"],
        "mchid": os.environ["WECHAT_MCH_ID"],
        "description": order["plan"]["name"],
        "out_trade_no": order["order_no"],
        "notify_url": os.environ["PAYMENT_NOTIFY_BASE_URL"].rstrip("/") + "/api/payments/wechat/notify",
        "amount": {"total": order["plan"]["amount_fen"], "currency": "CNY"},
    }, ensure_ascii=False, separators=(",", ":"))
    timestamp, nonce = str(int(time.time())), secrets.token_hex(16)
    signature = _rsa_sign(f"POST\n{path}\n{timestamp}\n{nonce}\n{body}\n", "WECHAT_PRIVATE_KEY_PATH")
    token = f'mchid="{os.environ["WECHAT_MCH_ID"]}",nonce_str="{nonce}",timestamp="{timestamp}",serial_no="{os.environ["WECHAT_CERT_SERIAL_NO"]}",signature="{signature}"'
    response = requests.post(
        "https://api.mch.weixin.qq.com" + path,
        data=body.encode(),
        headers={"Authorization": "WECHATPAY2-SHA256-RSA2048 " + token, "Accept": "application/json", "Content-Type": "application/json"},
        timeout=15,
    )
    if response.status_code != 200:
        raise RuntimeError(response.json().get("message", "微信支付下单失败"))
    _verify_wechat_message(response.headers, response.text)
    code_url = response.json()["code_url"]
    import qrcode
    image = qrcode.make(code_url)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return {"order_no": order["order_no"], "channel": "wechat", "status": "pending", "qr_code": "data:image/png;base64," + base64.b64encode(output.getvalue()).decode()}


def _create_alipay_order(order: dict[str, Any]) -> dict[str, Any]:
    base_url = os.environ["PAYMENT_NOTIFY_BASE_URL"].rstrip("/")
    params = {
        "app_id": os.environ["ALIPAY_APP_ID"], "method": "alipay.trade.page.pay", "format": "JSON",
        "charset": "utf-8", "sign_type": "RSA2", "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "version": "1.0", "notify_url": base_url + "/api/payments/alipay/notify",
        "return_url": base_url + "/?payment=return",
        "biz_content": json.dumps({"out_trade_no": order["order_no"], "total_amount": f'{order["plan"]["amount_fen"] / 100:.2f}', "subject": order["plan"]["name"], "product_code": "FAST_INSTANT_TRADE_PAY"}, ensure_ascii=False, separators=(",", ":")),
    }
    content = "&".join(f"{key}={params[key]}" for key in sorted(params))
    params["sign"] = _rsa_sign(content, "ALIPAY_PRIVATE_KEY_PATH")
    gateway = os.getenv("ALIPAY_GATEWAY", "https://openapi.alipay.com/gateway.do")
    return {"order_no": order["order_no"], "channel": "alipay", "status": "pending", "pay_url": gateway + "?" + urlencode(params)}


def _verify_wechat_message(headers: Any, body: str) -> None:
    timestamp = headers.get("Wechatpay-Timestamp", "")
    nonce = headers.get("Wechatpay-Nonce", "")
    signature = headers.get("Wechatpay-Signature", "")
    serial = headers.get("Wechatpay-Serial", "")
    if serial != os.environ["WECHAT_PAY_PUBLIC_KEY_ID"] or not timestamp.isdigit() or abs(time.time() - int(timestamp)) > 300:
        raise ValueError("微信支付签名信息无效")
    if not _rsa_verify(f"{timestamp}\n{nonce}\n{body}\n", signature, "WECHAT_PAY_PUBLIC_KEY_PATH"):
        raise ValueError("微信支付验签失败")


def handle_wechat_notify(headers: Any, body: str) -> dict[str, Any]:
    _verify_wechat_message(headers, body)
    resource = json.loads(body)["resource"]
    if resource.get("algorithm") != "AEAD_AES_256_GCM":
        raise ValueError("不支持的微信支付加密算法")
    key = os.environ["WECHAT_API_V3_KEY"].encode()
    if len(key) != 32:
        raise ValueError("WECHAT_API_V3_KEY 必须为 32 字节")
    plain = AESGCM(key).decrypt(
        resource["nonce"].encode(), base64.b64decode(resource["ciphertext"]), resource.get("associated_data", "").encode()
    )
    data = json.loads(plain)
    if data.get("trade_state") != "SUCCESS" or data.get("mchid") != os.environ["WECHAT_MCH_ID"] or data.get("appid") != os.environ["WECHAT_APP_ID"]:
        raise ValueError("微信支付结果无效")
    amount = data.get("amount") or {}
    if amount.get("currency", "CNY") != "CNY":
        raise ValueError("微信支付币种无效")
    return finalize_order(data["out_trade_no"], int(amount["total"]), "wechat", data.get("transaction_id", ""))


def handle_alipay_notify(params: dict[str, str]) -> dict[str, Any]:
    signature = params.get("sign", "")
    signed = {key: value for key, value in params.items() if key not in ("sign", "sign_type") and value != ""}
    content = "&".join(f"{key}={signed[key]}" for key in sorted(signed))
    if not _rsa_verify(content, signature, "ALIPAY_PUBLIC_KEY_PATH"):
        raise ValueError("支付宝验签失败")
    if params.get("app_id") != os.environ["ALIPAY_APP_ID"] or params.get("trade_status") not in ("TRADE_SUCCESS", "TRADE_FINISHED"):
        raise ValueError("支付宝支付结果无效")
    seller_id = os.getenv("ALIPAY_SELLER_ID", "").strip()
    if seller_id and params.get("seller_id") != seller_id:
        raise ValueError("支付宝收款账号不匹配")
    amount_fen = int(Decimal(params["total_amount"]) * 100)
    return finalize_order(params["out_trade_no"], amount_fen, "alipay", params.get("trade_no", ""))


def _add_months(value: datetime, months: int) -> datetime:
    month_index = value.month - 1 + months
    year, month = value.year + month_index // 12, month_index % 12 + 1
    return value.replace(year=year, month=month, day=min(value.day, monthrange(year, month)[1]))


def finalize_order(order_no: str, amount_fen: int, channel: str, provider_trade_no: str) -> dict[str, Any]:
    init_db()
    now = datetime.now()
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        order = conn.execute("SELECT * FROM payment_orders WHERE order_no=?", (order_no,)).fetchone()
        if not order or order["amount_fen"] != amount_fen or order["channel"] != channel:
            raise ValueError("支付订单、金额或渠道不匹配")
        if order["status"] == "paid":
            return dict(order)
        user = conn.execute("SELECT membership_expires_at FROM users WHERE id=?", (order["user_id"],)).fetchone()
        if not user:
            raise ValueError("支付订单用户不存在")
        current = None
        if user["membership_expires_at"]:
            try:
                current = datetime.fromisoformat(user["membership_expires_at"])
            except ValueError:
                current = None
        expires = _add_months(max(now, current) if current else now, PLANS[order["plan_code"]]["months"])
        expires_text = expires.isoformat(timespec="seconds")
        conn.execute("UPDATE users SET plan_code='pro', membership_expires_at=? WHERE id=?", (expires_text, order["user_id"]))
        conn.execute(
            "UPDATE payment_orders SET status='paid',provider_trade_no=?,paid_at=?,membership_expires_at=? WHERE order_no=?",
            (provider_trade_no, now.isoformat(timespec="seconds"), expires_text, order_no),
        )
    return get_order(order_no, order["user_id"])


def get_order(order_no: str, user_id: int) -> dict[str, Any]:
    init_db()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM payment_orders WHERE order_no=? AND user_id=?", (order_no, user_id)).fetchone()
    if not row:
        raise LookupError("订单不存在")
    return dict(row)
