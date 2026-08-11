import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import config
from app.main import app
from app.routes import feedback


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "feedback-test.db"
    monkeypatch.setattr(config, "DB_PATH", db_path)
    return db_path


def test_feedback_requires_login():
    with TestClient(app) as client:
        response = client.post(
            "/api/feedback",
            json={"category": "bug", "content": "反馈内容足够长"},
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "未登录"}


def test_feedback_is_saved_for_current_user(isolated_db):
    result = feedback.create_feedback(
        feedback.FeedbackRequest(
            category="data",
            content="  港股行情时间显示不正确  ",
            page="行情",
        ),
        user={"id": 7},
    )

    with config._connect() as conn:
        row = conn.execute("SELECT * FROM user_feedback WHERE id = ?", (result["id"],)).fetchone()

    assert dict(row) | {"created_at": "ignored"} == {
        "id": result["id"],
        "user_id": 7,
        "category": "data",
        "content": "港股行情时间显示不正确",
        "page": "行情",
        "status": "new",
        "created_at": "ignored",
    }


def test_feedback_rejects_blank_content():
    with pytest.raises(ValidationError):
        feedback.FeedbackRequest(category="other", content="     ")
