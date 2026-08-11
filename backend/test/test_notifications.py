from app import config, notifications


def test_notifications_are_persistent_and_user_scoped(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "notifications.db")
    notifications.create_notification(1, "alert", "预警", "A 已触发")
    notifications.create_notification(2, "feedback", "反馈", "已回复")

    first = notifications.list_notifications(1)

    assert first["unread"] == 1
    assert [item["message"] for item in first["items"]] == ["A 已触发"]
    notifications.mark_all_read(1)
    assert notifications.list_notifications(1)["unread"] == 0
    assert notifications.list_notifications(2)["unread"] == 1


def test_user_cannot_delete_another_users_notification(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "notifications.db")
    notification_id = notifications.create_notification(1, "alert", "预警", "A 已触发")

    assert notifications.delete_notification(notification_id, 2) is False
    assert notifications.delete_notification(notification_id, 1) is True
