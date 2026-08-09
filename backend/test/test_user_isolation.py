import json

import pytest

from app import config, memory, scheduler, thesis_tracker


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "financecrew-test.db"
    monkeypatch.setattr(config, "DB_PATH", db_path)
    monkeypatch.setattr(memory, "DB_PATH", db_path)
    config._init_db()
    return db_path


def test_fastapi_app_imports_all_routes():
    from fastapi.testclient import TestClient
    from app.main import app

    assert len(app.routes) >= 95
    with TestClient(app) as client:
        assert client.get("/api/config").status_code == 401
        assert client.get("/api/reflection/600519").status_code == 401


def test_health_reports_runtime_dependencies():
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "ok",
        "scheduler": "running",
    }


def test_health_fails_when_database_is_unavailable(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.routes import system

    def fail_to_connect():
        raise OSError("database unavailable")

    monkeypatch.setattr(system.config, "_connect", fail_to_connect)
    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 503
    assert response.json() == {"detail": "database unavailable"}


def test_analysis_lookup_is_scoped_to_user(isolated_db):
    analysis_id = memory.save_analysis("600519", {"status": "completed"}, user_id=1)

    assert memory.get_analysis(analysis_id, user_id=1) is not None
    assert memory.get_analysis(analysis_id, user_id=2) is None


def test_thesis_and_check_history_are_scoped_to_user(isolated_db):
    thesis = thesis_tracker.create_thesis(1, "600519", "茅台", "长期竞争力")
    with config._connect() as conn:
        conn.execute(
            """INSERT INTO thesis_checks
               (thesis_id, checked_at, status, checks_detail, price_at_check)
               VALUES (?, '2026-08-09', 'valid', '{}', 100)""",
            (thesis["id"],),
        )

    assert thesis_tracker.get_thesis(thesis["id"], 1) is not None
    assert thesis_tracker.get_thesis(thesis["id"], 2) is None
    assert len(thesis_tracker.list_thesis_checks(thesis["id"], 1)) == 1
    assert thesis_tracker.list_thesis_checks(thesis["id"], 2) == []


def test_thesis_drift_only_reads_current_users_analyses(isolated_db):
    result = {"consensus_score": 1, "trade_plan": {}, "analyst_views": []}
    memory.save_analysis("600519", result, user_id=1)
    result["consensus_score"] = 2
    memory.save_analysis("600519", result, user_id=1)
    memory.save_analysis("600519", result, user_id=2)

    assert thesis_tracker.detect_thesis_drift("600519", 1) is not None
    assert thesis_tracker.detect_thesis_drift("600519", 2) is None


def test_scheduled_results_are_scoped_to_user(isolated_db):
    scheduler._ensure_tables()
    with config._connect() as conn:
        task_id = conn.execute(
            """INSERT INTO scheduled_tasks
               (user_id, name, symbols, mode, created_at)
               VALUES (1, 'test', '[]', 'standard', '2026-08-09')"""
        ).lastrowid
        conn.execute(
            """INSERT INTO scheduled_results (task_id, user_id, run_at, results)
               VALUES (?, 1, '2026-08-09', ?)""",
            (task_id, json.dumps({"ok": True})),
        )

    assert len(scheduler.list_results(task_id, 1)) == 1
    assert scheduler.list_results(task_id, 2) == []


def test_reflection_records_are_scoped_to_user(isolated_db):
    from app import reflection_engine

    memo_id = reflection_engine.record_decision(
        "600519", "consensus", 5, "看多", user_id=1
    )
    with config._connect() as conn:
        conn.execute(
            """UPDATE reflection_memos
               SET status='settled', settled_at='2026-08-09'
               WHERE id=?""",
            (memo_id,),
        )

    assert len(reflection_engine.get_recent_memos("600519", 1)) == 1
    assert reflection_engine.get_recent_memos("600519", 2) == []
