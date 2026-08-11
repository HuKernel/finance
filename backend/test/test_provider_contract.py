from app.data.provider_contract import PROVIDER_CAPABILITIES, build_metadata, news_metadata
from app.routes import market


def test_metadata_contract_has_stable_fields():
    meta = build_metadata(
        "minute", "polygon", as_of="2026-08-11", delay="delayed",
        fallback_used=True, fallback_reason="主数据源不可用",
    )

    assert meta == {
        "kind": "minute",
        "source": "polygon",
        "provider": "polygon",
        "provider_name": "Polygon.io",
        "as_of": "2026-08-11",
        "delay": "delayed",
        "adjustment": "none",
        "fallback_used": True,
        "fallback_reason": "主数据源不可用",
        "rows_dropped": 0,
    }


def test_news_and_fundamental_use_same_metadata_contract(monkeypatch):
    news = news_metadata([
        {"source": "新浪", "published_at": "2026-08-11 09:00"},
        {"source": "东方财富", "published_at": "2026-08-11 10:00"},
    ])
    monkeypatch.setattr(market.datalayer, "get_financials", lambda symbol: {"period": "2026Q2", "roe": 15})
    fundamental = market.fundamentals("600519")

    assert news["kind"] == "news"
    assert news["as_of"] == "2026-08-11 10:00"
    assert fundamental["metadata"]["kind"] == "fundamental"
    assert fundamental["metadata"]["provider_name"] == "AKShare / 同花顺"


def test_provider_capability_matrix_declares_access_and_keys():
    result = market.data_providers()

    assert result["providers"] == PROVIDER_CAPABILITIES
    assert result["providers"]["polygon"]["access"] == "freemium"
    assert result["providers"]["polygon"]["requires_key"] is True
    assert result["providers"]["tencent"]["requires_key"] is False
