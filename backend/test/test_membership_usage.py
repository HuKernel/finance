import pytest
from fastapi import HTTPException

from app import auth, config
from app.deps import require_membership
from app.llm import LLMClient
from app.routes import chat


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "membership-test.db"
    monkeypatch.setattr(config, "DB_PATH", db_path)
    monkeypatch.setattr(auth, "DB_PATH", db_path)
    auth._init_db()


def test_free_user_has_five_model_actions_per_month(isolated_db):
    user = {"id": 7, "is_admin": 0, "plan_code": "free", "membership_expires_at": None}

    for remaining in range(4, -1, -1):
        assert auth.consume_model_usage(user)["remaining"] == remaining

    with pytest.raises(PermissionError, match="每月可使用 5 次"):
        auth.consume_model_usage(user)


def test_member_and_admin_model_usage_is_unlimited(isolated_db):
    member = {"id": 8, "is_admin": 0, "plan_code": "pro", "membership_expires_at": None}
    admin = {"id": 9, "is_admin": 1, "plan_code": "free", "membership_expires_at": None}

    assert auth.consume_model_usage(member)["limit"] is None
    assert auth.consume_model_usage(admin)["limit"] is None


def test_model_config_requires_membership():
    with pytest.raises(HTTPException, match="模型配置仅限会员使用"):
        require_membership({"is_admin": 0, "plan_code": "free", "membership_expires_at": None})

    assert require_membership({"is_admin": 0, "plan_code": "pro", "membership_expires_at": None})["plan_code"] == "pro"


def test_invite_reward_increases_bonus_not_used(isolated_db):
    auth.create_user("inviter", "password")
    code = auth.create_invite_code(1)["code"]
    auth.create_user("invited", "password", code)
    usage = auth.get_model_usage({"id": 1, "is_admin": 0, "plan_code": "free", "membership_expires_at": None})
    assert usage["used"] == 0
    assert usage["bonus"] == 1
    assert usage["remaining"] == 6


def test_chat_rejects_more_than_200_characters_before_counting(monkeypatch):
    monkeypatch.setattr(chat, "consume_model_access", lambda user: pytest.fail("不应计次"))

    with pytest.raises(HTTPException, match="最多输入 200 个字符"):
        chat.chat_stream({"message": "a" * 201}, user={"id": 1})


def test_llm_client_falls_back_to_platform_model(monkeypatch):
    platform = {"provider": "deepseek", "api_key": "platform-key", "model": "deepseek-chat"}
    monkeypatch.setattr(auth, "get_effective_llm_config", lambda user_id: platform)

    assert LLMClient(user_id=7).config == platform
