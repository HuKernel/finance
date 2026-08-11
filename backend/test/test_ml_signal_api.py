import numpy as np
import pandas as pd
import pytest
from fastapi import HTTPException

from app.routes import backtest as route


def synthetic_history(n: int = 500) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    returns = rng.normal(0.0003, 0.015, n)
    close = 100 * np.exp(np.cumsum(returns))
    df = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n, freq="B"),
        "open": close * (1 + rng.normal(0, 0.003, n)),
        "close": close,
        "high": close * (1 + np.abs(rng.normal(0, 0.006, n))),
        "low": close * (1 - np.abs(rng.normal(0, 0.006, n))),
        "volume": rng.lognormal(15, 0.4, n),
    })
    df.attrs["data_meta"] = {"source": "test", "as_of": "2025-11-28", "delay": "end_of_day"}
    return df


def test_ml_signal_api_returns_oos_diagnostics(monkeypatch):
    monkeypatch.setattr(route.datalayer, "get_history", lambda symbol, days: synthetic_history(days))

    result = route.ml_signal_api("600519", days=500, model="numpy", user={"id": 1})

    assert result["symbol"] == "600519"
    assert result["split_ranges"]["train"]["end"] < result["split_ranges"]["test"]["start"]
    assert "buy_precision" in result["classification"]
    assert "excess_return_pct" in result["strategy"]
    assert result["data_metadata"]["source"] == "test"
    assert result["verdict"]
    assert result["disclaimer"]


def test_ml_signal_api_rejects_unknown_model():
    with pytest.raises(HTTPException) as exc:
        route.ml_signal_api("600519", model="xgboost", user={"id": 1})
    assert exc.value.status_code == 400
