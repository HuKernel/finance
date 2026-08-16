from types import SimpleNamespace
from threading import Barrier
import asyncio

from app import llm_compare
from app.routes import system


def test_compare_models_runs_in_parallel_and_preserves_order(monkeypatch):
    barrier = Barrier(3)

    class FakeModel:
        def __init__(self, **kwargs):
            self.model = kwargs["model"]

        def invoke(self, messages):
            barrier.wait(timeout=2)
            return SimpleNamespace(
                content=f"{self.model}：增长 10%，来源 https://example.com/{self.model}",
                usage_metadata={"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
                response_metadata={},
            )

    monkeypatch.setattr(llm_compare, "ChatOpenAI", FakeModel)
    models = [
        {"name": name, "model": name, "api_key": "secret", "input_cost_per_million": 1, "output_cost_per_million": 2}
        for name in ("a", "b", "c")
    ]

    results = llm_compare.compare_models("比较", models)

    assert [result["name"] for result in results] == ["a", "b", "c"]
    assert results[0]["usage"]["total_tokens"] == 30
    assert results[0]["cost_usd"] == 0.00005
    assert results[0]["evidence"]["completeness_score"] == 100
    assert "不验证来源真实性" in results[0]["evidence"]["method"]
    assert llm_compare._calculate_cost(results[0]["usage"], {}) == (None, "pricing_not_configured")


def test_compare_models_isolates_failure_and_does_not_estimate_missing_cost(monkeypatch):
    class FakeModel:
        def __init__(self, **kwargs):
            self.model = kwargs["model"]

        def invoke(self, messages):
            if self.model == "bad":
                raise RuntimeError("provider failed")
            return SimpleNamespace(
                content="无数值结论", usage_metadata=None, response_metadata={},
            )

    monkeypatch.setattr(llm_compare, "ChatOpenAI", FakeModel)
    results = llm_compare.compare_models("比较", [
        {"name": "bad", "model": "bad", "api_key": "secret"},
        {"name": "good", "model": "good", "api_key": "secret"},
    ])

    assert "provider failed" in results[0]["error"]
    assert results[1]["response"] == "无数值结论"
    assert results[1]["usage"] is None
    assert results[1]["cost_usd"] is None
    assert results[1]["cost_status"] == "usage_unavailable"
    assert "secret" not in str(results)


def test_compare_api_reports_parallel_wall_time(monkeypatch):
    class Request:
        async def json(self):
            return {"prompt": "比较", "models": [{"model": "a"}, {"model": "b"}]}

    monkeypatch.setattr(system, "compare_models", lambda prompt, models: [{"name": "a"}, {"name": "b"}])
    # 不消耗真实开发库里的月度免费额度
    monkeypatch.setattr(system, "consume_model_access", lambda _user: None)
    result = asyncio.run(system.llm_compare_api(Request(), user={"id": 1}))

    assert result["execution"]["mode"] == "parallel"
    assert result["execution"]["model_count"] == 2
    assert len(result["results"]) == 2
