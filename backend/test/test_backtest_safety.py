import pandas as pd

from app.backtest.engine import SignalGenerator, _affordable_shares, _execute_signals
from app.backtest_analysis import full_analysis


class CloseSignal(SignalGenerator):
    name = "test"

    def generate(self, df, i, position):
        return "BUY" if i == 1 and not position else "HOLD"


def test_signal_executes_at_next_open_without_negative_cash():
    df = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=4),
        "open": [10.0, 10.5, 11.0, 11.5],
        "close": [10.1, 10.6, 11.1, 11.6],
    })

    result = _execute_signals(
        CloseSignal(),
        df,
        10000,
        symbol="600519",
        slippage=0,
        enable_cost=True,
    )

    buy = result["trades_log"][0]
    assert buy["date"] == "2026-01-03"
    assert buy["price"] == 11
    assert buy["shares"] % 100 == 0
    assert result["final_value"] >= 0
    assert result["trades"] == 1
    assert _affordable_shares(10000, 99.99, "600519", True) == 0


def test_advanced_modules_include_runtime_dependencies():
    from app.backtest_analysis import layered, monte_carlo, pbo, sensitivity, walk_forward

    assert layered.datalayer
    assert monte_carlo.bt and monte_carlo.np
    assert sensitivity.bt and sensitivity.datalayer and sensitivity.np
    assert walk_forward.math and walk_forward.np
    assert pbo.math and pbo.datalayer


def test_recovery_factor_uses_drawdown_amount(monkeypatch):
    original = {
        "final_value": 110000,
        "total_return": 10,
        "max_drawdown": 10,
        "trades": 1,
        "trades_log": [
            {"action": "BUY", "price": 10, "shares": 100},
            {"action": "SELL", "price": 11, "shares": 100},
        ],
    }
    monkeypatch.setattr(full_analysis.bt, "run_backtest", lambda *args, **kwargs: original)
    monkeypatch.setattr(full_analysis, "run_monte_carlo", lambda *args, **kwargs: {})
    monkeypatch.setattr(full_analysis, "run_layered_test", lambda *args, **kwargs: {})
    monkeypatch.setattr(full_analysis, "run_parameter_sensitivity", lambda *args, **kwargs: {})

    result = full_analysis.run_full_analysis("600519")

    assert result["recovery_factor"] == 1
