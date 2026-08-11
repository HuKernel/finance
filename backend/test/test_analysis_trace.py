from app.analysis_trace import AnalysisTrace, attach_trace
from app import pipeline


class FakeLLM:
    config = {"provider": "test-provider", "model": "test-model", "api_key": "secret"}


def test_trace_records_safe_runtime_metadata():
    trace = AnalysisTrace("600519", "agentic", FakeLLM())
    trace.step("collect_data", "数据收集")
    trace.tool("get_quote", "price=1500\napi_key=not-recorded", "fundamental")
    trace.finish()

    result = attach_trace({"ticker": "600519", "raw": {"topic": "估值"}}, trace)
    saved = result["raw"]["trace"]

    assert result["run_id"] == saved["run_id"]
    assert saved["provider"] == "test-provider"
    assert saved["model"] == "test-model"
    assert "api_key" not in saved
    assert "not-recorded" not in str(saved)
    assert saved["steps"][0]["name"] == "collect_data"
    assert saved["tools"][0]["role"] == "fundamental"


def test_pipeline_persists_running_and_completed_trace(monkeypatch):
    writes = []

    class FakeGraph:
        def invoke(self, state, config):
            assert state["analysis_id"] == 42
            assert state["trace"].run_id == state["run_id"]
            return {"result": {"id": 42, "ticker": state["ticker"], "raw": {"topic": state["topic"]}}}

    monkeypatch.setattr(pipeline, "_GRAPH", FakeGraph())
    monkeypatch.setattr(pipeline.memory, "save_analysis", lambda *args, **kwargs: 42)
    monkeypatch.setattr(pipeline.memory, "update_analysis", lambda analysis_id, result, status="completed": writes.append((analysis_id, result, status)))

    result = pipeline.run_analysis("600519", "估值", llm=FakeLLM(), user_id=7)

    assert result["raw"]["trace"]["status"] == "completed"
    assert result["raw"]["trace"]["steps"][0]["name"] == "pipeline"
    assert writes[-1][0] == 42
    assert writes[-1][2] == "completed"


def test_pipeline_returns_trace_when_history_storage_fails(monkeypatch):
    def fail_save(*args, **kwargs):
        raise OSError("database unavailable")

    monkeypatch.setattr(pipeline.memory, "save_analysis", fail_save)
    result = pipeline.run_analysis("600519", llm=FakeLLM())

    assert result["status"] == "error"
    assert result["id"] is None
    assert result["raw"]["trace"]["status"] == "error"
    assert "database unavailable" in result["raw"]["trace"]["error"]
