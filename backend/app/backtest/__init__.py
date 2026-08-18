"""策略回测系统：在历史K线上模拟交易策略，验证收益率。

支持策略：
  ma_cross    -- 快/慢均线交叉金叉买入、死叉卖出（周期可调，默认5/20）
  dual_ma     -- 双均线策略（与ma_cross同族，显式可调参别名）
  macd        -- MACD金叉买入/死叉卖出
  kdj         -- KDJ金叉买入/死叉卖出
  boll        -- 布林带突破：跌破下轨买入、突破上轨卖出
  rsi         -- RSI超买超卖：RSI<超卖线买入、RSI>超卖线卖出
  grid        -- 网格交易（按百分比间距挂单）
  hold        -- 买入持有（基准对照）
  ai          -- AI增强策略（大模型综合多维度信号决策买卖）

风险/收益指标（在 _calc_metrics 中统一计算）：
  sharpe_ratio / sortino_ratio / calmar_ratio
  annual_return / annual_volatility / max_consecutive_losses

本包从原单文件 app/backtest.py 拆分而来，所有公共接口通过 __init__.py
重导出，保持 `from app.backtest import run_backtest` 等现有导入不变。
"""
from __future__ import annotations

import hashlib
import pandas as pd
import json
from datetime import datetime, timezone
from typing import Any, Optional

from ..data import fetcher as datalayer

# ---- 技术指标 ----
from .indicators import (
    _calc_macd,
    _calc_kdj,
    _calc_boll,
    _calc_rsi,
)

# ---- 统计指标 ----
from .metrics import (
    RISK_FREE_RATE,
    TRADING_DAYS_PER_YEAR,
    _calc_metrics,
    _calc_max_dd_duration,
    _max_consecutive_losses,
)

# ---- 执行引擎（成本模型/滑点/涨跌停/执行器）----
from .engine import (
    STAMP_TAX_RATE,
    COMMISSION_RATE,
    COMMISSION_MIN,
    TRANSFER_FEE_RATE,
    calc_trade_cost,
    apply_buy_cost,
    apply_sell_cost,
    _buy_price,
    _sell_price,
    _is_limit_up,
    _is_limit_down,
    _can_buy,
    _can_sell,
    _equity_and_drawdown,
    SignalGenerator,
    _execute_signals,
)

# ---- 策略信号生成器与 _backtest_* 函数 ----
from .strategies import (
    MACrossSignal,
    DualMASignal,
    MACDSignal,
    KDJSignal,
    BOLLSignal,
    RSISignal,
    GridSignal,
    HoldSignal,
    _build_signal_generator,
    _backtest_ma_cross,
    _backtest_dual_ma,
    _backtest_macd,
    _backtest_kdj,
    _backtest_boll,
    _backtest_rsi,
    _empty_result,
    _backtest_grid,
    _backtest_hold,
    _build_market_context,
    _ai_decision,
    _backtest_ai,
)


__all__ = [
    # 主入口
    "run_backtest",
    # 技术指标
    "_calc_macd",
    "_calc_kdj",
    "_calc_boll",
    "_calc_rsi",
    # 统计指标
    "RISK_FREE_RATE",
    "TRADING_DAYS_PER_YEAR",
    "_calc_metrics",
    "_calc_max_dd_duration",
    "_max_consecutive_losses",
    # 成本/滑点/涨跌停
    "STAMP_TAX_RATE",
    "COMMISSION_RATE",
    "COMMISSION_MIN",
    "TRANSFER_FEE_RATE",
    "calc_trade_cost",
    "apply_buy_cost",
    "apply_sell_cost",
    "_buy_price",
    "_sell_price",
    "_is_limit_up",
    "_is_limit_down",
    "_can_buy",
    "_can_sell",
    "_equity_and_drawdown",
    # 执行引擎
    "SignalGenerator",
    "_execute_signals",
    # 策略信号生成器
    "MACrossSignal",
    "DualMASignal",
    "MACDSignal",
    "KDJSignal",
    "BOLLSignal",
    "RSISignal",
    "GridSignal",
    "HoldSignal",
    "_build_signal_generator",
    # _backtest_* 函数
    "_backtest_ma_cross",
    "_backtest_dual_ma",
    "_backtest_macd",
    "_backtest_kdj",
    "_backtest_boll",
    "_backtest_rsi",
    "_empty_result",
    "_backtest_grid",
    "_backtest_hold",
    # AI 策略
    "_build_market_context",
    "_ai_decision",
    "_backtest_ai",
]


# ==================== 主入口 ====================

def _build_run_manifest(
    df,
    result: dict[str, Any],
    symbol: str,
    strategy: str,
    generator,
    initial_capital: float,
    enable_cost: bool,
    percentage: float,
    slippage: float,
) -> dict[str, Any]:
    """生成可导出的回测运行记录，用于核对数据、参数和执行口径。"""
    data_columns = [c for c in ("date", "open", "high", "low", "close", "volume") if c in df.columns]
    data_json = df[data_columns].to_json(orient="records", date_format="iso", date_unit="s", double_precision=10)
    outcome = {
        "final_value": result.get("final_value"),
        "total_return": result.get("total_return"),
        "max_drawdown": result.get("max_drawdown"),
        "trades_log": result.get("trades_log", []),
        "equity_curve": result.get("equity_curve", []),
    }
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "strategy": {
            "name": strategy,
            "parameters": dict(vars(generator)) if generator is not None else {},
        },
        "execution": {
            "engine": "close_signal_next_open_v1",
            "initial_capital": initial_capital,
            "position_percentage": percentage,
            "slippage": slippage,
            "cost_enabled": enable_cost,
            "commission_rate": COMMISSION_RATE,
            "commission_min": COMMISSION_MIN,
            "stamp_tax_rate": STAMP_TAX_RATE,
            "transfer_fee_rate": TRANSFER_FEE_RATE,
            "signal_time": "previous_close",
            "fill_time": "next_open",
            "forced_close": "last_close",
        },
        "data": {
            "symbol": symbol,
            "start": df.iloc[0]["date"].strftime("%Y-%m-%d"),
            "end": df.iloc[-1]["date"].strftime("%Y-%m-%d"),
            "rows": len(df),
            "columns": data_columns,
            "fingerprint": hashlib.sha256(data_json.encode()).hexdigest(),
            "metadata": df.attrs.get("data_meta", {}),
        },
        "result_fingerprint": hashlib.sha256(
            json.dumps(outcome, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }

def run_backtest(
    symbol: str,
    strategy: str = "ma_cross",
    days: int = 120,
    initial_capital: float = 100000.0,
    record_signals: bool = False,
    enable_cost: bool = True,
    *,
    fast_period: int = 5,
    slow_period: int = 20,
    percentage: float = 100.0,
    slippage: float = 0.001,
    **kwargs: Any,
) -> Optional[dict[str, Any]]:
    """运行策略回测。

    通用可选参数（向后兼容，全部有默认值）：
        fast_period: 快均线周期（ma_cross/dual_ma 使用，默认5）
        slow_period: 慢均线周期（ma_cross/dual_ma 使用，默认20）
        percentage:  每次买入使用可用资金的百分比（默认100，即满仓）
        slippage:    滑点率（默认0.001）。买入价=收盘价*(1+slippage)，
                     卖出价=收盘价*(1-slippage)

    策略特定参数（通过 kwargs 透传）：
        grid:   grid_pct (默认0.05)
        macd:   fastperiod/slowperiod/signalperiod (默认12/26/9)
        kdj:    k_period/d_period (默认9/3/3)
        boll:   boll_period/boll_std (默认20/2)
        rsi:    rsi_period/rsi_oversold/rsi_overbought (默认14/30/70)

    风控退出参数（通过 kwargs 透传，对所有策略生效，0=关闭）：
        stop_loss_pct:     固定止损百分比（相对买入价，如 8 表示 -8% 止损）
        take_profit_pct:   固定止盈百分比（相对买入价，如 15 表示 +15% 止盈）
        atr_trailing_mult: ATR 追踪止损倍数（需 df 含 atr 列；如 2 表示
                           持仓期最高收盘价 - 2*ATR 作为移动止损）

    返回 dict 包含原有 key（strategy/symbol/period/initial_capital/final_value/
    total_return/benchmark_return/excess_return/max_drawdown/trades/win_rate/
    trades_log/equity_curve）以及新增 key（annual_return/annual_volatility/
    sharpe_ratio/sortino_ratio/calmar_ratio/max_consecutive_losses）。
    """
    sym = datalayer._norm_symbol(symbol)
    hist = datalayer.get_history(sym, days=min(max(days, 30), 500))
    if hist is None or len(hist) < 12:
        return None
    # 新股适配：上市不足30个交易日也能回测（自适应均线），但给出明确提示
    short_history = len(hist) < 30
    result_warnings: list[str] = []
    if short_history:
        result_warnings.append(
            f"该股上市时间较短（仅{len(hist)}个交易日），回测样本有限、"
            "均线按可用数据自适应计算，早期信号参考性有限，结果不具统计意义"
        )

    df = hist.copy()
    # 计算 ma5/ma20（兼容老逻辑与AI策略；短历史时自适应）
    minp = 1 if short_history else None
    df["ma5"] = df["close"].rolling(5, min_periods=minp).mean()
    df["ma20"] = df["close"].rolling(20, min_periods=minp).mean()
    # ATR（供 atr_trailing 移动止损使用）
    _prev_close = df["close"].shift(1)
    _tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - _prev_close).abs(),
        (df["low"] - _prev_close).abs(),
    ], axis=1).max(axis=1)
    df["atr"] = _tr.rolling(14).mean()

    # 不同策略需要不同的最小可用长度；统一以 ma20 是否就绪做下限
    df = df.dropna(subset=["ma5", "ma20"]).reset_index(drop=True)
    if len(df) < 10:
        return None

    # 统一 kwargs
    common = {
        "enable_cost": enable_cost,
        "percentage": percentage,
        "slippage": slippage,
    }

    signal_log: list[dict[str, Any]] = []
    result: Optional[dict[str, Any]] = None
    evaluation_df = df

    # ---- 优先走信号-执行解耦架构（AlphaModel 重构）----
    # 所有支持信号生成器的策略走统一执行器 _execute_signals；
    # 信号生成器构建失败（如 ai 策略）则 fallback 到原 _backtest_* 函数。
    gen_kwargs = dict(kwargs)
    gen_kwargs["fast_period"] = fast_period
    gen_kwargs["slow_period"] = slow_period

    generator = _build_signal_generator(strategy, **gen_kwargs)
    if generator is not None and short_history:
        generator.short_history = True

    if generator is not None:
        try:
            # 预计算指标（dropna）—— 对齐原 _backtest_* 各自的 dropna 行为
            df_prepared = generator.prepare(df)
            if len(df_prepared) < max(generator.min_rows(), 5):
                result = _empty_result()
            else:
                evaluation_df = df_prepared
                # 自定义执行（如 grid 多仓位策略）
                custom = generator.execute(
                    df_prepared, initial_capital,
                    symbol=symbol,
                    record_signals=record_signals,
                    signal_log=signal_log,
                    enable_cost=enable_cost,
                    percentage=percentage,
                    slippage=slippage,
                )
                if custom is not None:
                    result = custom
                else:
                    # 统一执行器（风控退出参数透传：止损/止盈/ATR追踪）
                    result = _execute_signals(
                        generator, df_prepared, initial_capital,
                        symbol=symbol,
                        record_signals=record_signals,
                        signal_log=signal_log,
                        enable_cost=enable_cost,
                        percentage=percentage,
                        slippage=slippage,
                        stop_loss_pct=kwargs.get("stop_loss_pct", 0),
                        take_profit_pct=kwargs.get("take_profit_pct", 0),
                        atr_trailing_mult=kwargs.get("atr_trailing_mult", 0),
                    )
        except Exception:
            # 不回退到旧的同K线成交实现，避免静默产生带未来偏差的结果
            result = None

    if generator is not None and result is None:
        return None

    # ---- Fallback：仅 ai 策略（无信号生成器）走专用实现 ----
    # 其余策略的旧 _backtest_* 同K线成交实现存在前视偏差（当日收盘信号+当日收盘成交），
    # 已全部改走上方"前收盘信号+次日开盘成交"的统一执行器，不再提供回退。
    if result is None:
        if strategy == "ai":
            result = _backtest_ai(
                df, initial_capital,
                sym=sym,
                symbol=symbol,
                record_signals=record_signals,
                signal_log=signal_log,
                **common,
            )
        else:
            return None

    # ---- 基准：买入持有 ----
    first_price = float(evaluation_df.iloc[0]["close"])
    last_price = float(evaluation_df.iloc[-1]["close"])
    benchmark_return = (last_price / first_price - 1) * 100

    total_return = float(result.get("total_return", 0.0))
    max_drawdown = float(result.get("max_drawdown", 0.0))

    result.update({
        "strategy": strategy,
        "symbol": sym,
        "period": f"{evaluation_df.iloc[0]['date'].strftime('%Y-%m-%d')} ~ {evaluation_df.iloc[-1]['date'].strftime('%Y-%m-%d')}",
        "initial_capital": initial_capital,
        "benchmark_return": round(benchmark_return, 2),
        "excess_return": round(total_return - benchmark_return, 2),
    })

    # ---- 统一计算风险/收益指标 ----
    metrics = _calc_metrics(
        equity_curve=result.get("equity_curve", []),
        trades_log=result.get("trades_log", []),
        total_return=total_return,
        max_drawdown=max_drawdown,
        initial_capital=initial_capital,
    )
    result.update(metrics)

    # ---- 信号记录 ----
    if record_signals and signal_log:
        from ..signal_features import fill_labels, save_signals_to_csv
        signal_log = fill_labels(signal_log, df)
        csv_path = save_signals_to_csv(signal_log)
        result["signal_log_count"] = len(signal_log)
        result["signal_csv_path"] = csv_path
        result["signal_sample"] = signal_log[:3]
    else:
        result["signal_log_count"] = 0

    result["run_manifest"] = _build_run_manifest(
        evaluation_df, result, sym, strategy, generator,
        initial_capital, enable_cost, percentage, slippage,
    )
    if result_warnings:
        result["warnings"] = result_warnings

    return result
