import json

import pandas as pd

from app import backtest as backtest_module
from app.backtest.engine import SignalGenerator, _affordable_shares, _execute_signals
from app.backtest import strategies
from app.backtest_analysis import cpcv, full_analysis, pbo


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


def test_ai_simulation_executes_decisions_at_next_open(monkeypatch):
    df = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=5),
        "open": [10.0, 11.0, 12.0, 13.0, 14.0],
        "close": [10.5, 11.5, 12.5, 13.5, 14.5],
        "volume": [1000] * 5,
        "ma5": [10.0] * 5,
        "ma20": [10.0] * 5,
    })

    def decide(context, _position):
        return ("BUY", "buy") if context["date"] == "2026-01-01" else ("SELL", "sell")

    monkeypatch.setattr(strategies, "_ai_decision", decide)
    result = strategies._backtest_ai(df, 10000, symbol="600519", slippage=0)

    buy, sell = result["trades_log"]
    assert (buy["signal_date"], buy["date"], buy["price"]) == ("2026-01-01", "2026-01-02", 11)
    assert (sell["signal_date"], sell["date"], sell["price"]) == ("2026-01-04", "2026-01-05", 14)
    assert buy["shares"] % 100 == 0
    assert result["trades"] == 1
    assert result["strict_backtest"] is False
    assert result["methodology"] == "ai_scenario_simulation"
    assert len(result["warnings"]) == 2


def test_grid_uses_prior_close_and_next_open_with_a_share_lots():
    df = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=4),
        "open": [10.0, 10.5, 9.0, 10.5],
        "close": [10.0, 9.0, 10.0, 10.5],
    })

    result = strategies._backtest_grid(
        df, 100000, 0.05, symbol="600519", slippage=0, enable_cost=True,
    )

    first_buy, grid_buy, grid_sell = result["trades_log"][:3]
    assert (first_buy["signal_date"], first_buy["date"], first_buy["price"]) == (
        "2026-01-01", "2026-01-02", 10.5,
    )
    assert (grid_buy["signal_date"], grid_buy["date"], grid_buy["price"]) == (
        "2026-01-02", "2026-01-03", 9,
    )
    assert (grid_sell["signal_date"], grid_sell["date"], grid_sell["price"]) == (
        "2026-01-03", "2026-01-04", 10.5,
    )
    assert all(t["shares"] % 100 == 0 for t in result["trades_log"])
    assert result["trades"] == 2  # 网格卖出 + 期末平仓
    assert result["win_rate"] == 100


def test_cpcv_evaluates_disjoint_ranges_as_independent_blocks(monkeypatch):
    df = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=100),
        "close": range(100),
    })
    seen = []

    def fake_run(block, *_args, **_kwargs):
        seen.append((int(block["close"].iloc[0]), int(block["close"].iloc[-1])))
        return {
            "trades": 1 if block["close"].iloc[0] == 0 else 0,
            "total_return": 10 if block["close"].iloc[0] == 0 else 0,
            "equity_curve": [{"value": 100}, {"value": 101}, {"value": 102}],
        }

    monkeypatch.setattr(cpcv, "_run_strategy_on_df", fake_run)
    stats = cpcv._evaluate_on_blocks(
        df, list(range(0, 40)) + list(range(60, 100)), "ma_cross", 100000, {},
    )

    assert seen == [(0, 39), (60, 99)]
    assert stats["blocks"] == 2
    assert stats["return"] == 5


def test_cpcv_reports_distribution_without_compounding_combinations(monkeypatch):
    hist = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=180),
        "close": range(180),
    })
    monkeypatch.setattr(cpcv.datalayer, "get_history", lambda *_args, **_kwargs: hist)
    monkeypatch.setattr(
        cpcv, "_evaluate_on_blocks",
        lambda _df, _idx, _strategy, _capital, params, **_execution: {
            "return": 10 if params["id"] == 1 else 5,
            "sharpe": 1,
            "blocks": 1,
        },
    )

    result = cpcv.run_cpcv(
        "600519", n_groups=3, n_test_groups=1,
        param_grid=[{"id": 1}, {"id": 2}],
    )

    assert [point["value"] for point in result["oos_distribution"]] == [110000] * 3
    assert "oos_equity_curve" not in result
    assert "total_oos_return" not in result["summary"]


def test_pbo_uses_oos_rank_percentile_logit(monkeypatch):
    hist = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=180),
        "close": range(180),
    })
    monkeypatch.setattr(pbo.datalayer, "get_history", lambda *_args, **_kwargs: hist)

    def fake_evaluate(_df, indices, _strategy, _capital, params, **_execution):
        returns = {1: 3, 2: 2, 3: 1} if len(indices) > 60 else {1: 1, 2: 3, 3: 2}
        return {"return": returns[params["id"]], "sharpe": 1, "blocks": 1}

    monkeypatch.setattr(pbo, "_evaluate_on_blocks", fake_evaluate)
    result = pbo.run_pbo(
        "600519", n_groups=3, n_test_groups=1,
        param_grid=[{"id": 1}, {"id": 2}, {"id": 3}],
    )

    assert result["pbo"] == 1
    assert all(item["oos_rank_percentile"] == 0.25 for item in result["combinations"])
    assert all(item["below_median"] for item in result["combinations"])


def test_backtest_run_manifest_records_reproducible_inputs(monkeypatch):
    closes = [10 + (i % 20) * 0.1 for i in range(80)]
    hist = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=80),
        "open": closes,
        "high": [price + 0.2 for price in closes],
        "low": [price - 0.2 for price in closes],
        "close": closes,
        "volume": [1000 + i for i in range(80)],
    })
    monkeypatch.setattr(backtest_module.datalayer, "get_history", lambda *_args, **_kwargs: hist)

    first = backtest_module.run_backtest("600519", fast_period=3, slow_period=10, slippage=0)
    second = backtest_module.run_backtest("600519", fast_period=3, slow_period=10, slippage=0)
    manifest = first["run_manifest"]

    assert manifest["strategy"] == {
        "name": "ma_cross", "parameters": {"fast_period": 3, "slow_period": 10},
    }
    assert manifest["execution"]["fill_time"] == "next_open"
    assert manifest["execution"]["engine"] == "close_signal_next_open_v1"
    assert manifest["execution"]["commission_min"] == 5
    assert manifest["data"]["rows"] > 0
    assert len(manifest["data"]["fingerprint"]) == 64
    assert manifest["data"]["fingerprint"] == second["run_manifest"]["data"]["fingerprint"]
    assert manifest["result_fingerprint"] == second["run_manifest"]["result_fingerprint"]
    json.dumps(first, ensure_ascii=False)


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
