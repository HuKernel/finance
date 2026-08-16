"""安全加固专项测试：密码策略 / pwd_version / MFA加密 / Cookie登录 / 密钥外移。"""
import pytest

from app import auth


@pytest.fixture()
def iso_db(tmp_path, monkeypatch):
    db_path = tmp_path / "sec-test.db"
    monkeypatch.setattr(auth, "DB_PATH", db_path)
    auth._init_db()
    return db_path


def test_password_policy(iso_db):
    with pytest.raises(ValueError):
        auth.create_user("u1", "short1")          # 不足8位
    with pytest.raises(ValueError):
        auth.create_user("u2", "qwerty123")      # 常见弱密码
    with pytest.raises(ValueError):
        auth.create_user("u3", "12345678")        # 纯数字
    user = auth.create_user("u4", "Str0ngPassw0rd")
    assert user["username"] == "u4"


def test_change_password_invalidates_old_tokens(iso_db):
    user = auth.create_user("alice", "Str0ngPassw0rd")
    token = auth.create_token(user["id"], "alice")
    payload = auth.decode_token(token)
    assert payload["pwd_version"] == auth.get_pwd_version(user["id"]) == 0

    assert auth.change_password(user["id"], "Str0ngPassw0rd", "NewStr0ngPass99") is True
    assert auth.get_pwd_version(user["id"]) == 1
    # 旧 token 的版本号与当前不一致 → deps.get_current_user 将拒绝
    assert auth.decode_token(token)["pwd_version"] != auth.get_pwd_version(user["id"])
    # 新 token 携带新版本，正常通过
    assert auth.decode_token(auth.create_token(user["id"], "alice"))["pwd_version"] == 1


def test_mfa_secret_encrypted_at_rest(iso_db):
    user = auth.create_user("bob", "Str0ngPassw0rd")
    auth.set_mfa(user["id"], "JBSWY3DPEHPK3PXP", True)
    # 存储的是 Fernet 密文，不是明文
    from app.auth._db import _connect
    with _connect() as conn:
        stored = conn.execute("SELECT mfa_secret FROM users WHERE id=?", (user["id"],)).fetchone()["mfa_secret"]
    assert stored and not stored.startswith("JBSWY3")
    assert stored.startswith("gAAAA")
    # 读取时自动解密
    assert auth.get_mfa_secret(user["id"]) == "JBSWY3DPEHPK3PXP"


def test_secrets_not_stored_in_database(iso_db):
    # JWT/Fernet 密钥必须不在数据库 app_config 里（在密钥文件/环境变量）
    from app.auth._db import _connect
    from app.auth import crypto
    crypto._get_secret()
    crypto._get_enc_key()
    with _connect() as conn:
        rows = conn.execute("SELECT key FROM app_config WHERE key IN ('jwt_secret','enc_key')").fetchall()
    assert rows == []


def test_cookie_login_and_me(iso_db):
    from fastapi.testclient import TestClient
    from app.main import app

    auth.create_user("carol", "Str0ngPassw0rd")
    with TestClient(app) as client:
        resp = client.post("/api/auth/login", json={"username": "carol", "password": "Str0ngPassw0rd"})
        assert resp.status_code == 200
        set_cookie = resp.headers.get("set-cookie", "")
        assert "fc_token=" in set_cookie and "HttpOnly" in set_cookie
        # TestClient 自动带 cookie：/me 应识别登录态
        me = client.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json()["user"]["username"] == "carol"
        # 登出清除 cookie
        out = client.post("/api/auth/logout")
        assert out.status_code == 200
        assert "fc_token=" in out.headers.get("set-cookie", "")
        me2 = client.get("/api/auth/me")
        assert me2.status_code == 401
