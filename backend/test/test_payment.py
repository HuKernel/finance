from datetime import datetime

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

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


def test_admin_payment_secrets_are_encrypted_and_not_returned(isolated_db):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    public_pem = private_key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    result = payment.save_admin_config({
        "PAYMENT_NOTIFY_BASE_URL": "https://pay.example.com",
        "WECHAT_APP_ID": "wx-app", "WECHAT_MCH_ID": "mch-1", "WECHAT_CERT_SERIAL_NO": "serial-1",
        "WECHAT_PRIVATE_KEY_PATH": private_pem, "WECHAT_API_V3_KEY": "1" * 32,
        "WECHAT_PAY_PUBLIC_KEY_ID": "PUB_KEY_ID_1", "WECHAT_PAY_PUBLIC_KEY_PATH": public_pem,
    })
    assert result["channels"]["wechat"] is True
    assert result["values"]["WECHAT_PRIVATE_KEY_PATH"] == ""
    with payment._connect() as conn:
        stored = conn.execute("SELECT value FROM app_config WHERE key='payment.WECHAT_API_V3_KEY'").fetchone()["value"]
    assert stored != "1" * 32
    assert payment._setting("WECHAT_API_V3_KEY") == "1" * 32


def test_admin_can_change_membership_prices(isolated_db):
    payment.save_admin_config({"MEMBERSHIP_MONTHLY_PRICE": "39.90", "MEMBERSHIP_YEARLY_PRICE": "299"})
    plans = {item["code"]: item["amount_fen"] for item in payment.public_config()["plans"]}
    assert plans == {"monthly": 3990, "yearly": 29900}


def test_membership_price_must_be_positive_money(isolated_db):
    with pytest.raises(ValueError, match="大于 0"):
        payment.save_admin_config({"MEMBERSHIP_MONTHLY_PRICE": "0"})


def test_alipay_raw_keys_without_pem_headers_are_accepted(isolated_db):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_raw = private_key.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    public_raw = private_key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    result = payment.save_admin_config({
        "ALIPAY_PRIVATE_KEY_PATH": __import__("base64").b64encode(private_raw).decode(),
        "ALIPAY_PUBLIC_KEY_PATH": __import__("base64").b64encode(public_raw).decode(),
    })
    assert result["configured"]["ALIPAY_PRIVATE_KEY_PATH"] is True
    assert result["configured"]["ALIPAY_PUBLIC_KEY_PATH"] is True


def test_alipay_raw_pkcs1_private_key_is_accepted(isolated_db):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_raw = private_key.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption())
    result = payment.save_admin_config({"ALIPAY_PRIVATE_KEY_PATH": __import__("base64").b64encode(private_raw).decode()})
    assert result["configured"]["ALIPAY_PRIVATE_KEY_PATH"] is True


def test_alipay_key_error_names_the_invalid_field(isolated_db):
    with pytest.raises(ValueError, match="支付宝应用私钥格式不正确"):
        payment.save_admin_config({"ALIPAY_PRIVATE_KEY_PATH": __import__("base64").b64encode(b"not-a-key").decode()})
