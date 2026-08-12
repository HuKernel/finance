import pandas as pd

from app.cache import TTL
from app.data import stock_data
from app.routes import market


def test_minute_kline_keeps_requested_history(monkeypatch):
    requested = {}
    rows = 80
    frame = pd.DataFrame({
        "date": pd.date_range("2026-07-01 09:30", periods=rows, freq="30min"),
        "open": [10.0] * rows,
        "close": [10.1] * rows,
        "high": [10.2] * rows,
        "low": [9.9] * rows,
        "volume": [1000] * rows,
    })

    def fake_history(symbol, period, count):
        requested.update(symbol=symbol, period=period, count=count)
        return frame

    monkeypatch.setattr(market.datalayer, "get_history_multi", fake_history)

    result = market.kline_multi_period_api("600519", period="30min", count=100_000)

    assert requested == {"symbol": "600519", "period": "30min", "count": 100_000}
    assert len(result["bars"]) == rows


def test_minute_kline_uses_short_cache_ttl(monkeypatch):
    observed = {}

    def fake_cached(cache_key, ttl, fetch_fn):
        observed.update(cache_key=cache_key, ttl=ttl)
        return {"bars": [{
            "date": "2026-08-12 10:00", "open": 10, "close": 10.1,
            "high": 10.2, "low": 9.9, "volume": 1000,
        }]}

    monkeypatch.setattr(stock_data, "cached", fake_cached)

    result = stock_data.get_history_multi("600519", period="30min", count=100_000)

    assert result is not None
    assert observed == {
        "cache_key": "kline:600519:30min:100000",
        "ttl": TTL["minute_kline"],
    }
