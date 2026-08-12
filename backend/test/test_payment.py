from datetime import datetime

import pytest

from app import auth, config, payment


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "payment-test.db"
    monkeypatch.setattr(config, "DB_PATH", db_path)
    monkeypatch.setattr(auth, "DB_PATH", db_path)
    auth._init_db()
    with auth._connect() as conn:
        conn.execute("INSERT INTO users (id,username,password_hash,salt,created_at) VALUES (1,'buyer','x','x',?)", (datetime.now().isoformat(),))
    payment.init_db()
    with payment._connect() as conn:
        conn.execute("INSERT INTO payment_orders (order_no,user_id,plan_code,amount_fen,channel,status,created_at) VALUES ('MONTH1',1,'monthly',2900,'wechat','pending',?)", (datetime.now().isoformat(),))


def test_paid_order_opens_membership_once(isolated_db):
    first = payment.finalize_order("MONTH1", 2900, "wechat", "WX1")
    second = payment.finalize_order("MONTH1", 2900, "wechat", "WX1")
    assert first["membership_expires_at"] == second["membership_expires_at"]
    assert auth.get_user(1)["plan_code"] == "pro"


def test_wrong_amount_does_not_open_membership(isolated_db):
    with pytest.raises(ValueError, match="金额"):
        payment.finalize_order("MONTH1", 1, "wechat", "WX1")
    assert auth.get_user(1)["plan_code"] == "free"


def test_unconfigured_channels_are_not_available(monkeypatch):
    for key in ("WECHAT_APP_ID", "ALIPAY_APP_ID", "PAYMENT_NOTIFY_BASE_URL"):
        monkeypatch.delenv(key, raising=False)
    assert payment.public_config()["channels"] == {"wechat": False, "alipay": False}


def test_forged_alipay_notify_is_rejected(monkeypatch):
    monkeypatch.setenv("ALIPAY_APP_ID", "app-1")
    monkeypatch.setattr(payment, "_rsa_verify", lambda *args: False)
    with pytest.raises(ValueError, match="验签失败"):
        payment.handle_alipay_notify({"sign": "forged", "app_id": "app-1", "trade_status": "TRADE_SUCCESS"})


def test_forged_wechat_notify_is_rejected(monkeypatch):
    monkeypatch.setenv("WECHAT_PAY_PUBLIC_KEY_ID", "PUB_KEY_ID_1")
    monkeypatch.setattr(payment, "_rsa_verify", lambda *args: False)
    headers = {
        "Wechatpay-Timestamp": str(int(datetime.now().timestamp())),
        "Wechatpay-Nonce": "nonce",
        "Wechatpay-Signature": "forged",
        "Wechatpay-Serial": "PUB_KEY_ID_1",
    }
    with pytest.raises(ValueError, match="验签失败"):
        payment._verify_wechat_message(headers, "{}")
