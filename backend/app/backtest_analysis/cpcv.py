"""回测深度分析 - cpcv模块"""
from __future__ import annotations
from typing import Any
import numpy as np
from .full_analysis import _run_strategy_on_df
from .walk_forward import _CPCV_PARAM_GRID, param_grid_for_strategy
from .full_analysis import _sharpe_from_equity
from ..data import fetcher as datalayer


def _cpcv_split_groups(n_rows: int, n_groups: int) -> list[tuple[int, int]]:
    """把连续的 n_rows 行均分为 n_groups 组，返回 [(start, end), ...] 半开区间。

    不足整除时余数依次分配到前若干组，保证各组连续且覆盖全部行。
    """
    base = n_rows // n_groups
    rem = n_rows % n_groups
    bounds = []
    start = 0
    for i in range(n_groups):
        size = base + (1 if i < rem else 0)
        bounds.append((start, start + size))
        start += size
    return bounds




def _apply_embargo(
    train_idx: list[int],
    test_idx: list[int],
    n_rows: int,
    embargo_pct: float,
) -> list[int]:
    """从 train 索引中删除与 test 紧邻的 embargo 带，防止信息泄漏。

    embargo 带长度 = round(n_rows * embargo_pct)，从 train 侧剥离与 test
    边界相邻的若干行。
    """
    if embargo_pct <= 0 or not train_idx or not test_idx:
        return train_idx
    embargo_len = max(1, int(round(n_rows * embargo_pct)))
    test_set = set(test_idx)
    # 标记需要 embargo 的行：train 中与任意 test 行距离 < embargo_len 的行
    embargo_set = set()
    for t in test_idx:
        for d in range(1, embargo_len + 1):
            if t - d >= 0:
                embargo_set.add(t - d)
            if t + d < n_rows:
                embargo_set.add(t + d)
    embargo_set &= set(train_idx)  # 只清 train 内的
    return [i for i in train_idx if i not in embargo_set]


def _contiguous_ranges(indices: list[int]) -> list[tuple[int, int]]:
    """把索引拆成连续半开区间，避免跨越被清洗或留出的数据。"""
    ordered = sorted(set(indices))
    if not ordered:
        return []
    ranges = []
    start = previous = ordered[0]
    for current in ordered[1:]:
        if current != previous + 1:
            ranges.append((start, previous + 1))
            start = current
        previous = current
    ranges.append((start, previous + 1))
    return ranges


def _evaluate_on_blocks(
    df,
    indices: list[int],
    strategy: str,
    capital: float,
    params: dict,
    **execution,
) -> dict[str, float] | None:
    """独立回测每个连续块，按块长度汇总统计量。"""
    returns = []
    sharpes = []
    weights = []
    has_trade = False
    for start, end in _contiguous_ranges(indices):
        block = df.iloc[start:end].reset_index(drop=True)
        result = _run_strategy_on_df(block, strategy, capital, **execution, **params)
        if not result:
            continue
        has_trade = has_trade or result.get("trades", 0) > 0
        returns.append(float(result.get("total_return", 0.0)))
        sharpes.append(_sharpe_from_equity(result.get("equity_curve", [])))
        weights.append(end - start)
    if not returns or not has_trade:
        return None
    return {
        "return": float(np.average(returns, weights=weights)),
        "sharpe": float(np.average(sharpes, weights=weights)),
        "blocks": len(returns),
    }




def run_cpcv(
    symbol: str,
    strategy: str = "ma_cross",
    days: int = 500,
    n_groups: int = 6,
    n_test_groups: int = 2,
    embargo_pct: float = 0.01,
    **kwargs,
) -> dict[str, Any]:
    """组合式清洗交叉验证 (Combinatorial Purged Cross-Validation)。

    防止金融时序数据信息泄漏的交叉验证：
    1. 把数据按时间均分成 n_groups 组
    2. 遍历 C(n_groups, n_test_groups) 种组合，每次取 n_test_groups 组作为样本外(OOS)
    3. 在样本内(IS)上做参数网格搜索找最优参数，在样本外(OOS)上用该参数测试
    4. 用 embargo 在 train/test 边界加隔离带防止泄漏
    5. 汇总所有组合的 IS/OOS 表现，评估样本外一致性

    参数:
        symbol: 股票代码
        strategy: 策略名（仅对支持 fast_period/slow_period 的 ma_cross/dual_ma 生效）
        days: 数据拉取范围（交易日）
        n_groups: 分组数（建议 6~10）
        n_test_groups: 每次作为样本外的组数（< n_groups）
        embargo_pct: 隔离带占比（占数据总行数的比例，默认 1%）
        **kwargs: 透传 enable_cost/percentage/slippage；param_grid 覆盖默认网格

    返回:
        {
            combinations: [{combo_idx, test_groups, best_params,
                             train_return, test_return, train_sharpe, test_sharpe}, ...],
            summary: {n_combinations, avg_oos_return, oos_win_rate,
                      oos_sharpe_mean, oos_sharpe_std, consistency},
            oos_distribution: [{combo, return, value}, ...],
        }
    """
    from itertools import combinations

    sym = datalayer._norm_symbol(symbol)
    param_grid = kwargs.pop("param_grid", None) or param_grid_for_strategy(strategy) or _CPCV_PARAM_GRID
    enable_cost = kwargs.pop("enable_cost", True)
    percentage = kwargs.pop("percentage", 100.0)
    slippage = kwargs.pop("slippage", 0.001)
    capital = 100000.0

    if n_groups < 3 or n_test_groups < 1 or n_test_groups >= n_groups:
        return {"error": f"参数无效：需 2 ≤ n_test_groups < n_groups（got n_groups={n_groups}, n_test_groups={n_test_groups}）"}

    fetch_days = min(max(days, 90), 1000)
    hist = datalayer.get_history(sym, days=fetch_days)
    if hist is None or len(hist) < 60:
        return {"error": "历史数据不足（需 ≥60 行）"}

    df = hist.copy().reset_index(drop=True)
    n = len(df)

    # 分组
    bounds = _cpcv_split_groups(n, n_groups)

    combos = list(combinations(range(n_groups), n_test_groups))
    results: list[dict] = []
    oos_values: list[dict] = []
    execution = {
        "enable_cost": enable_cost,
        "percentage": percentage,
        "slippage": slippage,
        "symbol": sym,
    }

    for ci, test_groups in enumerate(combos):
        test_idx = []
        train_idx = []
        for gi, (gs, ge) in enumerate(bounds):
            block = list(range(gs, ge))
            if gi in test_groups:
                test_idx.extend(block)
            else:
                train_idx.extend(block)
        if not test_idx or not train_idx:
            continue

        # embargo 清洗 train
        train_idx_purged = _apply_embargo(train_idx, test_idx, n, embargo_pct)
        if len(train_idx_purged) < 30:
            continue

        best_params = None
        train_stats = None
        for params in param_grid:
            stats = _evaluate_on_blocks(
                df, train_idx_purged, strategy, capital, params, **execution,
            )
            if stats and (train_stats is None or stats["return"] > train_stats["return"]):
                best_params = dict(params)
                train_stats = stats
        if best_params is None or train_stats is None:
            continue

        test_stats = _evaluate_on_blocks(
            df, test_idx, strategy, capital, best_params, **execution,
        )
        if test_stats is None:
            continue

        oos_values.append({
            "combo": ci,
            "return": round(test_stats["return"], 2),
            "value": round(capital * (1.0 + test_stats["return"] / 100.0), 2),
        })

        results.append({
            "combo_idx": ci,
            "test_groups": list(test_groups),
            "best_params": best_params,
            "train_return": round(train_stats["return"], 2),
            "test_return": round(test_stats["return"], 2),
            "train_sharpe": round(train_stats["sharpe"], 3),
            "test_sharpe": round(test_stats["sharpe"], 3),
            "train_blocks": int(train_stats["blocks"]),
            "test_blocks": int(test_stats["blocks"]),
        })

    if not results:
        return {"error": "无有效组合结果（数据或参数不足）"}

    oos_returns = [r["test_return"] for r in results]
    oos_sharpes = [r["test_sharpe"] for r in results]
    avg_oos_return = float(np.mean(oos_returns))
    oos_win_rate = float(np.mean([1 if r > 0 else 0 for r in oos_returns]) * 100.0)
    oos_sharpe_mean = float(np.mean(oos_sharpes))
    oos_sharpe_std = float(np.std(oos_sharpes))
    # 一致性：OOS 收益为正且 Sharpe 标准差小 → 高一致性
    consistency = round(
        oos_win_rate * (1.0 - min(oos_sharpe_std / 2.0, 0.5)) if oos_sharpe_std > 0 else oos_win_rate,
        1,
    )

    summary = {
        "n_combinations": len(results),
        "avg_oos_return": round(avg_oos_return, 2),
        "oos_win_rate": round(oos_win_rate, 1),
        "oos_sharpe_mean": round(oos_sharpe_mean, 3),
        "oos_sharpe_std": round(oos_sharpe_std, 3),
        "consistency": round(consistency, 1),
    }

    return {
        "symbol": sym,
        "strategy": strategy,
        "n_groups": n_groups,
        "n_test_groups": n_test_groups,
        "embargo_pct": embargo_pct,
        "combinations": results,
        "summary": summary,
        "methodology": "independent_contiguous_blocks",
        "oos_distribution": oos_values,
    }


# ==================== 8. PBO 回测过拟合概率 ====================

