"""路由模块: backtest"""
from __future__ import annotations
from typing import Any
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..auth import get_profile
from ..config import get_config, save_config, PROVIDER_PRESETS
from ..deps import consume_model_access, get_current_user, require_admin

router = APIRouter()

from .. import backtest
from ..backtest_analysis import run_full_analysis, run_walk_forward, run_cpcv, run_pbo
from ..ic_evaluator import evaluate_signal_ic
from ..data import fetcher as datalayer


@router.get("/api/ml-signal/{symbol}")
def ml_signal_api(
    symbol: str,
    days: int = 500,
    model: str = "auto",
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """单标的 ML 信号样本外诊断；只开放固定模型和时间切分。"""
    if model not in {"auto", "rf", "gb", "logit", "numpy"}:
        raise HTTPException(status_code=400, detail="model 仅支持 auto/rf/gb/logit/numpy")
    days = min(max(days, 200), 500)
    sym = datalayer._norm_symbol(symbol)
    hist = datalayer.get_history(sym, days=days)
    if hist is None or len(hist) < 100:
        raise HTTPException(status_code=422, detail="历史数据不足，至少需要100个有效交易日")

    from dataclasses import asdict
    from ..ml_signal import PipelineConfig, run_ml_pipeline

    result = run_ml_pipeline(hist, PipelineConfig(model=model))
    if result is None:
        raise HTTPException(status_code=422, detail="有效样本不足，无法完成时间序列切分")

    buy_precision = float(result.classification.get("buy_precision") or 0)
    excess_return = float(result.strategy.get("excess_return_pct") or 0)
    trades = int(result.strategy.get("n_trades") or 0)
    flags = []
    if result.split_sizes.get("test", 0) < 50:
        flags.append({"level": "warning", "code": "small_test", "message": "测试集少于50条，结论稳定性有限"})
    if buy_precision <= 0.36:
        flags.append({"level": "warning", "code": "weak_precision", "message": "买入精度接近三分类随机基线"})
    if excess_return <= 0:
        flags.append({"level": "warning", "code": "no_excess", "message": "样本外策略未跑赢买入持有"})
    if trades < 5:
        flags.append({"level": "warning", "code": "few_trades", "message": "样本外交易少于5次，统计意义不足"})

    promising = buy_precision > 0.4 and excess_return > 0 and trades >= 5
    return {
        "symbol": sym,
        "backend": result.backend,
        "n_raw_rows": len(hist),
        "n_samples": result.n_samples,
        "split_sizes": result.split_sizes,
        "split_ranges": result.split_ranges,
        "classification": result.classification,
        "strategy": result.strategy,
        "feature_importance": [
            {"name": name, "value": value}
            for name, value in sorted(result.feature_importance.items(), key=lambda item: -item[1])[:10]
        ],
        "config": asdict(result.config),
        "data_metadata": hist.attrs.get("data_meta", {}),
        "flags": flags,
        "verdict": "样本外结果初步有效，仍需跨标的和滚动验证" if promising else "当前样本未证明存在稳定 Alpha",
        "disclaimer": "该诊断是固定时间切分下的启发式结果，不代表统计显著性或未来收益。",
    }


@router.get("/api/ic-evaluate/{symbol}")
def ic_evaluate_api(symbol: str, forward_days: int = 5) -> dict[str, Any]:
    """IC/Rank IC信号评估：评估技术指标对未来收益的预测力。"""
    from ..ic_evaluator import evaluate_strategy_signals
    sym = datalayer._norm_symbol(symbol)
    hist = datalayer.get_history(sym, days=250)
    if hist is None or len(hist) < 60:
        return {"error": "数据不足"}
    df = hist.copy()
    # 构建常见指标
    df["ma_signal"] = (df["close"].rolling(5).mean() - df["close"].rolling(20).mean()) / df["close"]
    df["rsi"] = _calc_rsi(df["close"], 14)
    df["macd_hist"] = _calc_macd_hist(df["close"])
    df["volume_ratio"] = df["volume"] / df["volume"].rolling(20).mean()
    df["boll_position"] = (df["close"] - df["close"].rolling(20).mean()) / (df["close"].rolling(20).std() + 0.001)
    df = df.dropna()
    result = evaluate_strategy_signals(df, forward_days=forward_days)
    return result


def _calc_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(period).mean()
    rs = gain / (loss + 0.001)
    return 100 - (100 / (1 + rs))


def _calc_macd_hist(close: pd.Series) -> pd.Series:
    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9).mean()
    return dif - dea



@router.get("/api/backtest/analysis/{symbol}")
def backtest_analysis_api(
    symbol: str,
    strategy: str = "ma_cross",
    days: int = 120,
    analysis_type: str = "full",
) -> dict[str, Any]:
    """回测深度分析：PF/RF/综合评分 + 蒙特卡洛 + 分层测试 + 参数敏感度。

    analysis_type: full / monte_carlo / layered / sensitivity / score
    """
    from .. import backtest_analysis as ba
    sym = datalayer._norm_symbol(symbol)

    if analysis_type == "monte_carlo":
        return ba.run_monte_carlo(sym, strategy=strategy, days=days)
    elif analysis_type == "layered":
        return ba.run_layered_test(sym, days=days)
    elif analysis_type == "sensitivity":
        return ba.run_parameter_sensitivity(sym, strategy=strategy, days=days)
    elif analysis_type == "score":
        r = backtest.run_backtest(sym, strategy=strategy, days=days)
        if not r:
            return {"error": "数据不足"}
        pf = ba.calc_profit_factor(r["trades_log"])
        rf = ba.calc_recovery_factor(
            r["final_value"] - 100000,
            100000 * r["max_drawdown"] / 100,
        )
        score = ba.calc_comprehensive_score(r["total_return"], r["max_drawdown"], pf, rf, r["trades"])
        return {"profit_factor": pf, "recovery_factor": rf, "score": score}
    else:
        return ba.run_full_analysis(sym, strategy=strategy, days=days)



@router.get("/api/backtest/{symbol}")
def backtest_api(
    symbol: str,
    strategy: str = "ma_cross",
    days: int = 120,
    record_signals: int = 0,
    enable_cost: int = 1,
    fast_period: int = 0,
    slow_period: int = 0,
    grid_pct: float = 0,
    boll_period: int = 0,
    rsi_period: int = 0,
    rsi_oversold: int = 0,
    rsi_overbought: int = 0,
    slippage: float = 0,
    position_pct: float = 0,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """策略回测：在历史K线上模拟交易策略。
    strategy: ma_cross / dual_ma / macd / kdj / boll / rsi / grid / hold / ai
    可选参数: fast_period, slow_period, grid_pct, boll_period, rsi_period, rsi_oversold, rsi_overbought, slippage, position_pct
    record_signals: 1=记录ML信号特征快照
    enable_cost: 1=含A股交易成本
    """
    sym = datalayer._norm_symbol(symbol)
    if strategy == "ai":
        consume_model_access(user)
    # 构建策略参数（只传非零/非默认值）
    kwargs: dict[str, Any] = {}
    if fast_period > 0: kwargs["fast_period"] = fast_period
    if slow_period > 0: kwargs["slow_period"] = slow_period
    if grid_pct > 0: kwargs["grid_pct"] = grid_pct / 100  # 前端传5表示5%
    if boll_period > 0: kwargs["boll_period"] = boll_period
    if rsi_period > 0: kwargs["rsi_period"] = rsi_period
    if rsi_oversold > 0: kwargs["rsi_oversold"] = rsi_oversold
    if rsi_overbought > 0: kwargs["rsi_overbought"] = rsi_overbought
    if slippage > 0: kwargs["slippage"] = slippage / 1000  # 前端传1表示0.1%
    if position_pct > 0: kwargs["percentage"] = position_pct  # 前端传100表示满仓

    result = backtest.run_backtest(sym, strategy=strategy, days=days,
                                   record_signals=bool(record_signals), enable_cost=bool(enable_cost), **kwargs)
    return result or {"error": "回测数据不足（需要至少30个交易日）"}



@router.get("/api/backtest/walk-forward/{symbol}")
def walk_forward_api(
    symbol: str,
    strategy: str = "ma_cross",
    total_days: int = 500,
    train_window: int = 60,
    test_window: int = 20,
) -> dict[str, Any]:
    """Walk-Forward 滚动测试：用过去 train_window 天优化参数 → 交易未来 test_window 天 → 平移。

    评估策略防过拟合能力与样本外稳定性。
    返回每个窗口的 train/test 收益与 Sharpe，以及样本外累计权益曲线。
    """
    from .. import backtest_analysis as ba
    sym = datalayer._norm_symbol(symbol)
    try:
        return ba.run_walk_forward(
            sym, strategy=strategy,
            total_days=total_days,
            train_window=train_window,
            test_window=test_window,
        )
    except Exception as e:
        return {"error": f"Walk-Forward 测试失败：{e}"}



@router.get("/api/backtest/cpcv/{symbol}")
def backtest_cpcv_api(
    symbol: str,
    strategy: str = "ma_cross",
    days: int = 500,
    n_groups: int = 6,
    n_test_groups: int = 2,
    embargo_pct: float = 0.01,
) -> dict[str, Any]:
    """组合式清洗交叉验证 (CPCV)：防信息泄漏的组合式 OOS 测试。

    把数据按时间分成 n_groups 组，遍历 C(n_groups, n_test_groups) 种组合，
    每次在样本内做参数搜索、样本外测试，并用 embargo 隔离带防止泄漏。
    返回各组合 IS/OOS 表现、汇总统计与样本外累计权益曲线。
    """
    from .. import backtest_analysis as ba
    sym = datalayer._norm_symbol(symbol)
    try:
        return ba.run_cpcv(
            sym, strategy=strategy, days=days,
            n_groups=n_groups, n_test_groups=n_test_groups,
            embargo_pct=embargo_pct,
        )
    except Exception as e:
        return {"error": f"CPCV 测试失败：{e}"}



@router.get("/api/backtest/pbo/{symbol}")
def backtest_pbo_api(
    symbol: str,
    strategy: str = "ma_cross",
    days: int = 500,
    n_groups: int = 8,
    n_test_groups: int = 2,
) -> dict[str, Any]:
    """回测过拟合概率 (PBO)：Bailey & López de Prado 2017 方法。

    在 IS 上找最优策略，检查其在 OOS 的排名是否低于中位数。
    PBO = 低于中位数的组合比例（<0.5 为良好）。
    返回 PBO、logit 直方图、IS 排名频率与评级。
    """
    from .. import backtest_analysis as ba
    sym = datalayer._norm_symbol(symbol)
    try:
        return ba.run_pbo(
            sym, strategy=strategy, days=days,
            n_groups=n_groups, n_test_groups=n_test_groups,
        )
    except Exception as e:
        return {"error": f"PBO 测试失败：{e}"}


# ---------- 多LLM对比 ----------

