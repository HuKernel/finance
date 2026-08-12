"""数据层通用工具。

- akshare 可用性检测（AK_AVAILABLE）
- 符号归一化 / 数值解析 / 容错包装等基础函数

原 fetcher.py 顶部初始化逻辑迁移至此；导入本模块即生效。
"""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd

try:
    import akshare as ak
    AK_AVAILABLE = True
except Exception:  # pragma: no cover
    ak = None
    AK_AVAILABLE = False

from ..cache import TTL, cached  # noqa: E402


def _safe(fn, *args, **kwargs):
    """统一容错包装。"""
    try:
        return fn(*args, **kwargs)
    except Exception:
        return None


def data_available() -> bool:
    return AK_AVAILABLE


def _norm_symbol(symbol: str) -> str:
    """统一股票代码格式：A股6位 / 港股 hk+5位 / 美股 us+代码。

    规则：hk/us 前缀原样保留；6位数字=A股；5位数字（如 00700）=港股；
    更短数字=港股补零；其他按原样返回（公司名交给 resolve_symbol 处理）。
    """
    s = symbol.strip().lower()
    if s.startswith(("hk", "us")):
        code = s[2:]
        if code.isdigit():
            return s[:2] + code.zfill(5) if len(code) < 5 else s[:2] + code
        return s[:2] + code.upper()  # 美股代码大写（usAAPL）
    if s.isdigit():
        if len(s) == 5:
            return "hk" + s
        if len(s) <= 4:
            return "hk" + s.zfill(5)
        return s.zfill(6)
    return s


def _market_prefix(symbol: str) -> str:
    """腾讯接口的市场前缀：A股 sh/sz/bj，港股/美股无需前缀（代码自带 hk/us）。"""
    if symbol.startswith(("hk", "us")):
        return ""
    if symbol[0] in "69":
        return "sh"
    if symbol[0] in "48":
        return "bj"
    return "sz"


def _parse_num(v: Any) -> Optional[float]:
    """解析带单位数值：'54.27%'->54.27, '1.47亿'->147000000, False/None->None。"""
    if v is None or v is False:
        return None
    s = str(v).strip().replace("%", "")
    if s in ("", "--", "nan", "None", "False"):
        return None
    mult = 1.0
    if s.endswith("亿"):
        mult = 1e8
        s = s[:-1]
    elif s.endswith("万"):
        mult = 1e4
        s = s[:-1]
    try:
        f = float(s) * mult
        return f if f == f else None
    except ValueError:
        return None


def _to_float(v: Any) -> Optional[float]:
    try:
        f = float(v)
        return f if f == f else None  # NaN 过滤
    except (TypeError, ValueError):
        return None


def finalize_ohlcv(
    df: pd.DataFrame,
    *,
    source: str,
    delay: str,
    adjustment: str,
    fallback_used: bool = False,
    fallback_reason: str | None = None,
) -> pd.DataFrame:
    """清洗统一 OHLCV 字段，并附加可审计的数据元信息。"""
    required = ["date", "open", "high", "low", "close", "volume"]
    original_rows = len(df)
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    for column in required[1:]:
        out[column] = pd.to_numeric(out[column], errors="coerce")
    out = out.dropna(subset=required)
    out = out[
        (out[["open", "high", "low", "close"]] > 0).all(axis=1)
        & (out["volume"] >= 0)
        & (out["high"] >= out[["open", "close"]].max(axis=1))
        & (out["low"] <= out[["open", "close"]].min(axis=1))
    ]
    out = out.drop_duplicates(subset=["date"], keep="last").sort_values("date").reset_index(drop=True)
    from .provider_contract import build_metadata
    out.attrs["data_meta"] = build_metadata(
        "bar", source,
        as_of=out.iloc[-1]["date"].isoformat() if not out.empty else None,
        delay=delay,
        adjustment=adjustment,
        fallback_used=fallback_used,
        fallback_reason=fallback_reason,
        rows_dropped=original_rows - len(out),
    )
    return out
