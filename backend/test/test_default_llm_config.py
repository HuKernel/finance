from app import auth, config
from app.routes import system


def test_default_llm_api_key_is_encrypted(tmp_path, monkeypatch):
    db_path = tmp_path / "llm-config.db"
    monkeypatch.setattr(config, "DB_PATH", db_path)
    monkeypatch.setattr(auth, "DB_PATH", db_path)
    saved = config.save_config({"provider": "deepseek", "base_url": "https://example.com/v1", "api_key": "secret-key", "model": "model-1", "temperature": 0.2, "max_tokens": 1000})
    assert saved["api_key"] == "secret-key"
    with config._connect() as conn:
        assert conn.execute("SELECT value FROM app_config WHERE key='api_key'").fetchone() is None
        encrypted = conn.execute("SELECT value FROM app_config WHERE key='llm_api_key_enc'").fetchone()["value"]
    assert encrypted != "secret-key"
    assert config.get_config()["api_key"] == "secret-key"


def test_empty_default_llm_api_key_keeps_existing(tmp_path, monkeypatch):
    db_path = tmp_path / "llm-config.db"
    monkeypatch.setattr(config, "DB_PATH", db_path)
    monkeypatch.setattr(auth, "DB_PATH", db_path)
    config.save_config({"api_key": "secret-key"})
    config.save_config({"model": "model-2", "api_key": ""})
    assert config.get_config()["api_key"] == "secret-key"


def test_admin_config_never_returns_api_key(tmp_path, monkeypatch):
    db_path = tmp_path / "llm-config.db"
    monkeypatch.setattr(config, "DB_PATH", db_path)
    monkeypatch.setattr(auth, "DB_PATH", db_path)
    config.save_config({"api_key": "secret-key"})
    public = system._public_config()
    assert public["api_key"] == ""
    assert public["api_key_configured"] is True
