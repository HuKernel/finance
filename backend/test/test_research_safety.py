import pytest

from app import reflection_engine
from app.agents.risk import RiskManager
from app.agents.trader import Trader
from app.graph import nodes
from app.models import AnalystView, RiskReview


class StubLLM:
    def __init__(self, data=None):
        self.data = data or {}

    def chat(self, system, user):
        return "测试共识"

    def chat_json(self, system, user):
        return self.data


@pytest.mark.parametrize(
    ("score", "vote", "expected"),
    [(3, "bull", 3.3), (-3, "bear", -3.3)],
)
def test_consensus_preserves_direction(monkeypatch, score, vote, expected):
    monkeypatch.setattr(reflection_engine, "record_decision", lambda *args, **kwargs: 1)
    state = {
        "ticker": "600519",
        "views": [AnalystView(role="technical", title="技术", summary="测试", score=score)],
        "debate": [],
    }

    result = nodes.run_consensus(
        state,
        {"configurable": {"llm": StubLLM()}},
    )

    assert result["votes"] == {
        "bull": int(vote == "bull"),
        "bear": int(vote == "bear"),
        "neutral": 0,
    }
    assert result["consensus_score"] == expected


def test_analyst_profile_controls_fan_out(monkeypatch):
    from app import auth

    monkeypatch.setattr(auth, "get_profile", lambda user_id: {"analyst_config": ["technical"]})

    sends = nodes.fan_out_analysts({"context": {}, "user_id": 7, "mode": "standard"})

    assert len(sends) == 1
    assert sends[0].arg["role"] == "technical"


def test_risk_output_fails_closed_and_clamps_position():
    malformed = RiskManager(StubLLM({
        "approved": "false",
        "max_position_pct": 99,
        "stop_loss_pct": 8,
    })).review({}, [], 8)
    approved = RiskManager(StubLLM({
        "approved": True,
        "max_position_pct": 99,
        "stop_loss_pct": -2,
    })).review({}, [], 8)

    assert malformed.approved is False
    assert malformed.max_position_pct == 0
    assert approved.max_position_pct == 10
    assert approved.stop_loss_pct == 0


def test_trade_position_cannot_exceed_risk_limit():
    risk = RiskReview(
        approved=True,
        verdict="通过",
        max_position_pct=5,
        stop_loss_pct=3,
    )
    plan = Trader(StubLLM({
        "action": "买入",
        "position_pct": 50,
    })).plan({}, [], 4, "偏多", risk)

    assert plan.action == "买入"
    assert plan.position_pct == 5
