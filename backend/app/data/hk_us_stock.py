"""港股/美股数据获取（新浪美股日K / yfinance分钟级 / 东财分时）。

仅含美股相关底层抓取函数；A股入口在 a_stock.py 中按 sym.startswith("us") 分发到此处。
"""
from __future__ import annotations

import json as _json
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

import pandas as pd
from .. import http_client


def _beijing_to_new_york(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=ZoneInfo("Asia/Shanghai")).astimezone(ZoneInfo("America/New_York"))


def _new_york_time_to_beijing(value: str, session_date: str) -> str:
    market_time = datetime.fromisoformat(f"{session_date} {value[:2]}:{value[2:4]}").replace(tzinfo=ZoneInfo("America/New_York"))
    return market_time.astimezone(ZoneInfo("Asia/Shanghai")).strftime("%H%M")


def _fetch_us_kline(sym: str, days: int) -> Optional[dict[str, Any]]:
    """美股日K线（新浪接口，1984年至今完整历史，国内直连）。

    返回 JSONP：var _=([{"d":"1984-09-07","o":"26.50","h":"26.87","l":"26.25","c":"26.50","v":...}, ...])
    """
    ticker = sym[2:]  # usAAPL -> AAPL
    url = (
        "https://stock.finance.sina.com.cn/usstock/api/jsonp_v2.php/"
        f"var%20_=/US_MinKService.getDailyK?symbol={ticker}"
    )
    try:
        r = http_client.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn"})
        text = r.text
        start, end = text.find("(["), text.rfind("]")
        if start == -1 or end == -1:
            return None
        data = _json.loads(text[start + 1 : end + 1])
        bars = []
        for row in data[-days:]:
            try:
                bars.append({
                    "date": str(row["d"]),
                    "open": float(row["o"]),
                    "close": float(row["c"]),
                    "high": float(row["h"]),
                    "low": float(row["l"]),
                    "volume": float(row.get("v", 0)),
                })
            except (KeyError, ValueError, TypeError):
                continue
        return {"bars": bars} if bars else None
    except Exception:
        return None


def _fetch_us_kline_aggregated(sym: str, period: str, count: int) -> Optional[dict[str, Any]]:
    """美股周K/月K：从新浪日K数据聚合。

    period: 'week' 或 'month'
    """
    # 多取数据确保聚合后有足够的周/月
    need_days = count * 7 if period == "week" else count * 31
    raw = _fetch_us_kline(sym, min(need_days, 5000))
    if raw is None or not raw.get("bars"):
        return None

    df = pd.DataFrame(raw["bars"])
    df["date"] = pd.to_datetime(df["date"])

    if period == "week":
        # 按周聚合：取每周第一天的日期，OHLC聚合
        df["period_key"] = df["date"].dt.to_period("W")
    else:
        df["period_key"] = df["date"].dt.to_period("M")

    agg = df.groupby("period_key").agg(
        date=("date", "first"),
        open=("open", "first"),
        close=("close", "last"),
        high=("high", "max"),
        low=("low", "min"),
        volume=("volume", "sum"),
    ).reset_index(drop=True)

    agg = agg.sort_values("date").tail(count)

    bars = []
    for _, row in agg.iterrows():
        bars.append({
            "date": row["date"].strftime("%Y-%m-%d"),
            "open": float(row["open"]),
            "close": float(row["close"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "volume": float(row["volume"]),
        })
    return {"bars": bars} if bars else None


def _fetch_us_minute_kline(ticker: str, m_param: str, count: int) -> Optional[dict[str, Any]]:
    """美股分钟级K线（yfinance，国内直连）。

    m_param: m5/m15/m30/m60
    时间转换为北京时间，并自动处理美股夏令时。
    """
    try:
        import yfinance as yf
        interval_map = {"m5": "5m", "m15": "15m", "m30": "30m", "m60": "60m"}
        interval = interval_map.get(m_param, "5m")
        period = "5d" if count <= 390 else "60d"
        df = yf.download(ticker, period=period, interval=interval, progress=False)
        if df is None or len(df) == 0:
            return None
        # yfinance返回MultiIndex列名，扁平化
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if df.index.tz is None:
            df.index = df.index.tz_localize("America/New_York")
        df.index = df.index.tz_convert("Asia/Shanghai")
        bars = []
        for idx, row in df.tail(count).iterrows():
            dt_str = idx.strftime("%Y-%m-%d %H:%M")
            try:
                bars.append({
                    "date": dt_str,
                    "open": round(float(row["Open"]), 4),
                    "close": round(float(row["Close"]), 4),
                    "high": round(float(row["High"]), 4),
                    "low": round(float(row["Low"]), 4),
                    "volume": int(float(row["Volume"])),
                })
            except (ValueError, TypeError):
                continue
        return {"bars": bars} if bars else None
    except Exception:
        return None


def _us_minute_from_em(symbol: str) -> Optional[dict[str, Any]]:
    """美股分时数据。多接口fallback：东财 → Polygon → 腾讯 → 新浪。

    返回与A股分时相同格式: {points, last_close, data_date, is_today}
    时间统一转换为北京时间，并自动处理美股夏令时。
    """
    import time as _time

    from ..logger import get_logger
    log = get_logger("hk_us_stock")

    started = _time.monotonic()
    deadline = 25.0  # fallback 全链路总耗时上限，避免串行超时叠加接近50秒

    # 接口1：东财trends2（curl_cffi）— 原始时间已是北京时间
    result = _us_minute_eastmoney(symbol)
    if result and result.get("points") and len(result["points"]) > 5:
        return result
    log.warning("us_minute fallback: eastmoney failed for %s (%.1fs)", symbol, _time.monotonic() - started)

    # 接口2：Polygon.io（5分钟K线聚合，稳定但延迟15分钟，转换为北京时间）
    try:
        from .polygon_us import polygon_get_minute
        result = polygon_get_minute(symbol)
        if result and result.get("points"):
            return result
    except Exception as e:
        log.warning("us_minute fallback: polygon error for %s: %s", symbol, e)

    # 接口3：腾讯分时（requests直连）— 美东时间转换为北京时间
    if _time.monotonic() - started < deadline:
        result = _us_minute_tencent(symbol)
        if result and result.get("points"):
            session_date = result.get("data_date") or datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
            for point in result["points"]:
                point["time"] = _new_york_time_to_beijing(point["time"], session_date)
            return result
        log.warning("us_minute fallback: tencent failed for %s (%.1fs)", symbol, _time.monotonic() - started)

    # 接口4：新浪5分钟K线聚合（requests）— 美东时间转换为北京时间
    if _time.monotonic() - started < deadline:
        result = _us_minute_sina(symbol)
        if result and result.get("points"):
            session_date = result.get("data_date") or datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
            for point in result["points"]:
                point["time"] = _new_york_time_to_beijing(point["time"], session_date)
            return result
        log.warning("us_minute fallback: sina failed for %s (%.1fs)", symbol, _time.monotonic() - started)

    log.warning("us_minute fallback: all sources failed for %s in %.1fs", symbol, _time.monotonic() - started)
    return None


def _us_minute_eastmoney(symbol: str) -> Optional[dict[str, Any]]:
    """东财trends2接口（curl_cffi）。push2his被封→自动用push2delay。"""
    sym = symbol.replace("us", "")
    nasdaq = {"AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "TSLA", "NVDA", "META", "NFLX",
              "AMD", "INTC", "CSCO", "ADBE", "PEP", "COST", "AVGO", "TXN", "QCOM",
              "TMUS", "CMCSA", "SBUX", "PYPL"}
    # 名单外的纳斯达克股票会被误判为 NYSE(106)，因此失败后尝试另一个市场 secid
    first = "105" if sym.upper() in {s.upper() for s in nasdaq} else "106"
    secid_candidates = [f"{first}.{sym}", f"{'106' if first == '105' else '105'}.{sym}"]

    params = {
        "fields1": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
        "iscr": "0",
        "ndays": "1",
    }
    try:
        from curl_cffi import requests as cffi_req
        d = None
        trends = []
        # 先试push2his，被封则fallback到push2delay；再换另一个市场的secid
        for secid in secid_candidates:
            if trends:
                break
            for host in ("push2his.eastmoney.com", "push2delay.eastmoney.com"):
                try:
                    r = cffi_req.get(f"https://{host}/api/qt/stock/trends2/get",
                                     params={**params, "secid": secid}, impersonate="chrome", timeout=10)
                    d = r.json()
                    trends = d.get("data", {}).get("trends", [])
                    if trends:
                        break
                except Exception:
                    continue
        if not trends:
            return None

        pre_close = d.get("data", {}).get("preClose", 0) or 0
        points = []
        market_dates = []
        total_vol = 0
        total_amount = 0
        for item in trends:
            parts = item.split(",")
            if len(parts) < 7:
                continue
            dt_str = parts[0]
            price = float(parts[2])
            vol = int(float(parts[5]))
            amount = float(parts[6])
            total_vol += vol
            total_amount += amount
            market_dt = _beijing_to_new_york(dt_str)
            time_part = dt_str.split(" ")[1].replace(":", "")[:4]
            market_dates.append(market_dt.strftime("%Y-%m-%d"))
            avg_price = total_amount / total_vol if total_vol > 0 else price
            points.append({"time": time_part, "price": round(price, 2), "avg": round(avg_price, 2), "vol": vol})

        if not points:
            return None
        last_date = market_dates[-1] if market_dates else ""
        return {
            "points": points,
            "last_close": round(pre_close, 2) if pre_close else None,
            "data_date": last_date,
            "is_today": True,
            "source": "eastmoney",
        }
    except Exception:
        return None


def _us_minute_tencent(symbol: str) -> Optional[dict[str, Any]]:
    """腾讯分时接口（requests直连，美股us前缀）。"""
    try:
        url = f"https://web.ifzq.gtimg.cn/appstock/app/minute/query?code={symbol}"
        r = http_client.get(url, timeout=12)
        d = r.json()
        node = d.get("data", {}).get(symbol, {})
        points_raw = node.get("data", {}).get("data", [])
        if not points_raw:
            return None

        # 昨收
        qt = node.get("qt", {})
        qt_arr = qt.get(symbol, []) if isinstance(qt, dict) else []
        last_close = None
        if isinstance(qt_arr, list) and len(qt_arr) > 4:
            try:
                last_close = float(qt_arr[4])
            except (ValueError, TypeError):
                pass

        # 数据日期
        data_date = node.get("data", {}).get("date", "")

        out = []
        for p in points_raw[:500]:
            try:
                parts = p.split() if isinstance(p, str) else p
                t = str(parts[0])
                if not t.isdigit():
                    continue
                price = float(parts[1])
                if price <= 0:
                    continue
                vol = float(parts[2]) if len(parts) > 2 and parts[2] else 0
                out.append({"time": t, "price": price, "avg": None, "vol": vol if vol else None})
            except (ValueError, IndexError, TypeError, AttributeError):
                continue

        if not out:
            return None

        # 计算分时均价：腾讯美股分时无成交额，用逐分钟成交量差分做 VWAP 近似
        cum_vol = 0.0
        prev_cum = 0.0
        vwap_amount = 0.0
        for i, pt in enumerate(out):
            cum = pt.get("vol") or 0
            # 腾讯返回的是累计成交量；首点或出现非累计数据时退化为当前分钟量
            minute_vol = max(cum - prev_cum, 0) if i > 0 and cum >= prev_cum else cum
            prev_cum = max(cum, prev_cum)
            cum_vol += minute_vol
            vwap_amount += pt["price"] * minute_vol
            pt["avg"] = round(vwap_amount / cum_vol, 2) if cum_vol > 0 else round(pt["price"], 2)

        return {
            "points": out,
            "last_close": last_close,
            "data_date": data_date,
            "is_today": True,
            "source": "tencent",
        }
    except Exception:
        return None


def _us_minute_sina(symbol: str) -> Optional[dict[str, Any]]:
    """新浪5分钟K线聚合为分时（最后兜底）。"""
    sym = symbol.replace("us", "")
    try:
        url = f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={sym}&scale=5&ma=no&datalen=48"
        r = http_client.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if not r.text.strip() or r.text.strip() == "null":
            return None
        data = _json.loads(r.text)
        if not data:
            return None

        out = []
        for item in data:
            dt = item.get("day", "")
            time_part = dt.split(" ")[1].replace(":", "")[:4] if " " in dt else "0000"
            close = float(item.get("close", 0))
            if close <= 0:
                continue
            vol = float(item.get("volume", 0))
            out.append({"time": time_part, "price": close, "avg": close, "vol": vol if vol else None})

        if not out:
            return None

        return {
            "points": out,
            "last_close": None,
            "data_date": data[-1].get("day", "").split(" ")[0],
            "is_today": True,
            "source": "sina",
        }
    except Exception:
        return None
