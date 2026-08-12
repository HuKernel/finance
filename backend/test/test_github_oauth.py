import sqlite3

from app import auth, config, github_oauth


def setup_db(tmp_path, monkeypatch):
    db_path = tmp_path / "github-oauth.db"
    monkeypatch.setattr(config, "DB_PATH", db_path)
    monkeypatch.setattr(auth, "DB_PATH", db_path)
    auth._init_db()


def test_github_oauth_secret_is_encrypted(tmp_path, monkeypatch):
    setup_db(tmp_path, monkeypatch)
    result = github_oauth.save_admin_config({"site_url":"https://example.com/", "client_id":"client", "client_secret":"secret"})
    assert result["enabled"] is True
    assert result["values"]["client_secret"] == ""
    with auth._connect() as conn:
        stored = conn.execute("SELECT value FROM app_config WHERE key='github_oauth.client_secret'").fetchone()["value"]
    assert stored != "secret"


def test_oauth_user_is_stable_and_username_collision_is_safe(tmp_path, monkeypatch):
    setup_db(tmp_path, monkeypatch)
    auth.create_user("octocat", "password")
    first = auth.get_or_create_oauth_user("github", "123", "octocat")
    second = auth.get_or_create_oauth_user("github", "123", "renamed")
    assert first["id"] == second["id"]
    assert first["username"] == "octocat_1"


def test_authorize_url_uses_state_and_pkce(tmp_path, monkeypatch):
    setup_db(tmp_path, monkeypatch)
    github_oauth.save_admin_config({"site_url":"https://example.com", "client_id":"client", "client_secret":"secret"})
    url, state, verifier = github_oauth.authorize_url()
    assert "code_challenge_method=S256" in url
    assert "state=" in url and state and verifier
    assert "scope=" in url
