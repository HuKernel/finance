import pandas as pd

from app.graph import nodes


def test_report_evidence_separates_facts_calculations_and_ai(monkeypatch):
    history = pd.DataFrame({"close": range(1, 131)})
    history.attrs["data_meta"] = {
        "source": "test_kline", "as_of": "2026-08-11", "delay": "end_of_day",
        "adjustment": "qfq", "rows_dropped": 2,
    }
    monkeypatch.setattr(nodes.datalayer, "get_stock_brief", lambda ticker: {
        "name": "测试", "price": 130, "change_pct": 1, "pe": 12, "pb": 2,
    })
    monkeypatch.setattr(nodes.datalayer, "get_history", lambda ticker: history)
    monkeypatch.setattr(nodes.datalayer, "compute_tech_signals", lambda frame: {"price": 130})
    monkeypatch.setattr(nodes.datalayer, "get_financials", lambda ticker: {"period": "2026Q2", "roe": 15})
    monkeypatch.setattr(nodes.datalayer, "get_lhb", lambda ticker: None)
    monkeypatch.setattr(nodes.datalayer, "get_news", lambda ticker: [{
        "source": "测试源", "published_at": "2026-08-11 10:00",
    }])
    monkeypatch.setattr(nodes.datalayer, "get_industry_compare", lambda ticker: None, raising=False)
    monkeypatch.setattr(nodes.datalayer, "get_social_sentiment", lambda ticker: None, raising=False)
    monkeypatch.setattr("app.reflection_engine.settle_pending", lambda *args, **kwargs: 0)

    state = {
        "ticker": "600519", "topic": "估值", "raw_score": 3.0,
        "consensus_score": 3.6, "vote_adjustment": 0.6,
        "votes": {"bull": 3, "bear": 1, "neutral": 1},
    }
    state.update(nodes.collect_data(state, {"configurable": {}}))
    report = nodes._build_report_evidence(state, "2026-08-11T12:00:00")

    assert state["context"]["trend"]["ma5"] == 128
    assert report["schema_version"] == 2
    assert report["facts"]["history"]["source"] == "test_kline"
    assert report["facts"]["financials"]["values"]["roe"] == 15
    assert report["calculations"]["consensus_score"]["value"] == 3.6
    assert "consensus_verdict" in report["ai_judgments"]
