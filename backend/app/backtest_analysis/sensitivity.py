"""回测深度分析 - sensitivity模块"""
from __future__ import annotations
from typing import Any
import pandas as pd
import numpy as np

from .. import backtest as bt
from ..data import fetcher as datalayer
from .scoring import calc_profit_factor


def run_parameter_sensitivity(
    symbol: str,
    strategy: str = "ma_cross",
    days: int = 120,
    initial_capital: float = 100000.0,
) -> dict[str, Any]:
    """参数敏感性分析：测试关键参数上下浮动后的表现。

    找"稳定平台"而非"最高点"——
    健康的参数是周围参数变化后仍然能盈利的参数。
    """
    sym = datalayer._norm_symbol(symbol)

    # 按策略选择真实生效的参数轴与网格（参数名必须与 strategies.py 的构造参数一致，
    # 否则网格会被静默忽略，20 组"不同参数"实际产出完全相同的结果）
    grid = _param_grid_for(strategy)
    if grid is None:
        return {"error": f"策略 {strategy} 无可调参数（或不支持敏感性分析）"}

    p1_name, p2_name, p1_label, p2_label, combos = grid

    results = []
    for p1, p2 in combos:
        kwargs: dict[str, Any] = {p1_name: p1}
        if p2_name:
            kwargs[p2_name] = p2
        if strategy == "rsi":
            kwargs["rsi_overbought"] = 100 - p1  # 对称阈值：超卖30 ↔ 超买70
        r = bt.run_backtest(sym, strategy=strategy, days=days,
                            initial_capital=initial_capital, **kwargs)
        if r and r.get("trades_log"):
            pf = calc_profit_factor(r["trades_log"])
            results.append({
                "fast": p1,  # 兼容前端字段名：fast/slow 泛指参数1/参数2
                "slow": p2,
                "total_return": r["total_return"],
                "max_drawdown": r["max_drawdown"],
                "trades": r["trades"],
                "pf": pf,
            })

    if not results:
        return {"error": "无有效结果"}

    # 分析稳定性
    returns = [r["total_return"] for r in results]
    dds = [r["max_drawdown"] for r in results]
    pfs = [r["pf"] for r in results]

    # 找稳定平台：收益标准差小、中位数收益正的区域
    median_return = float(np.median(returns))
    std_return = float(np.std(returns))
    profitable_count = sum(1 for r in returns if r > 0)

    # 找最优参数（不是最高收益，是综合最好的）
    best = max(results, key=lambda x: x["total_return"])
    worst = min(results, key=lambda x: x["total_return"])

    return {
        "symbol": sym,
        "strategy": strategy,
        "param_grid": f"{p1_label} x {p2_label}" if p2_label else p1_label,
        "p1_label": p1_label,
        "p2_label": p2_label,
        "combos_tested": len(results),
        "results": results,
        "median_return": round(median_return, 2),
        "std_return": round(std_return, 2),
        "profitable_ratio": round(profitable_count / len(results) * 100, 1),
        "best": best,
        "worst": worst,
        "stability_verdict": _verdict_stability(returns, dds, pfs),
    }


def _param_grid_for(strategy: str):
    """返回 (参数1名, 参数2名|None, 参数1标签, 参数2标签|None, 组合列表)。"""
    if strategy in ("ma_cross", "dual_ma"):
        return "fast_period", "slow_period", "MA快线", "MA慢线", [
            (3, 10), (3, 15), (3, 20),
            (5, 10), (5, 15), (5, 20), (5, 25),
            (7, 15), (7, 20), (7, 25), (7, 30),
            (10, 20), (10, 25), (10, 30), (10, 40),
            (12, 26), (15, 30), (15, 40), (20, 40), (20, 60),
        ]
    if strategy == "macd":
        return "fastperiod", "slowperiod", "DIF快线", "DEA慢线", [
            (6, 13), (6, 19), (8, 17), (8, 21), (10, 20), (10, 26),
            (12, 26), (12, 32), (15, 30), (16, 34), (19, 39),
        ]
    if strategy == "kdj":
        return "k_period", "d_period", "K周期", "D周期", [
            (5, 2), (5, 3), (6, 3), (9, 2), (9, 3), (9, 4),
            (12, 3), (14, 3), (18, 3), (20, 5),
        ]
    if strategy == "boll":
        return "boll_period", "boll_std", "布林周期", "标准差倍数", [
            (10, 1.5), (10, 2.0), (15, 1.5), (15, 2.0), (15, 2.5),
            (20, 1.5), (20, 2.0), (20, 2.5), (26, 2.0), (26, 2.5),
        ]
    if strategy == "rsi":
        # 对称阈值：overbought = 100 - oversold
        return "rsi_oversold", "rsi_period", "超卖阈值", "RSI周期", [
            (25, 7), (25, 14), (30, 7), (30, 10), (30, 14), (30, 21),
            (35, 10), (35, 14), (35, 21), (40, 14),
        ]
    return None




def _verdict_stability(returns: list[float], dds: list[float], pfs: list[float]) -> str:
    """判断参数稳定性。"""
    profitable = sum(1 for r in returns if r > 0) / len(returns)
    std = float(np.std(returns))

    if profitable > 0.7 and std < 10:
        return "STABLE: 多数参数组合盈利且波动小，策略稳健"
    elif profitable > 0.5:
        return "MODERATE: 一半参数组合盈利，策略有一定依赖性"
    elif profitable > 0.3:
        return "SENSITIVE: 少数参数组合盈利，策略对参数敏感"
    else:
        return "UNSTABLE: 大多数参数组合亏损，策略不稳健"


# ==================== 5. 一键完整分析 ====================

