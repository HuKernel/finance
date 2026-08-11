"""持仓与自选股的财报预约披露日历。"""
from __future__ import annotations

from datetime import date, datetime
from time import time
from typing import Any

from .auth import get_profile
from .config import _connect

_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def list_company_events(user_id: int) -> dict[str, Any]:
    symbols = _user_symbols(user_id)
    if not symbols:
        return {"items": [], "periods": [], "source": "东方财富", "as_of": datetime.now().isoformat(timespec="seconds")}

    periods = _report_periods(date.today())
    items: list[dict[str, Any]] = []
    for period in periods:
        items.extend(item for item in _load_period(period) if item["symbol"] in symbols)
    items.sort(key=lambda item: item["date"] or "9999-12-31")
    return {
        "items": items,
        "periods": periods,
        "source": "东方财富",
        "as_of": datetime.now().isoformat(timespec="seconds"),
    }


def _user_symbols(user_id: int) -> set[str]:
    with _connect() as conn:
        try:
            rows = conn.execute("SELECT symbol FROM portfolio WHERE user_id=?", (user_id,)).fetchall()
        except Exception:
            rows = []
    symbols = {str(row["symbol"]) for row in rows}
    symbols.update(str(symbol) for symbol in get_profile(user_id).get("watchlist", []))
    return {symbol for symbol in symbols if symbol.isdigit() and len(symbol) == 6}


def _report_periods(today: date) -> list[str]:
    if today.month <= 4:
        return [f"{today.year - 1}1231", f"{today.year}0331"]
    if today.month <= 8:
        return [f"{today.year}0630"]
    if today.month <= 10:
        return [f"{today.year}0930"]
    return [f"{today.year}1231"]


def _load_period(period: str) -> list[dict[str, Any]]:
    cached = _cache.get(period)
    if cached and time() - cached[0] < 21600:
        return cached[1]

    import akshare as ak

    frame = ak.stock_yysj_em(symbol="沪深A股", date=period)
    rows: list[dict[str, Any]] = []
    for record in frame.to_dict("records"):
        changed = next((record.get(column) for column in ("三次变更日期", "二次变更日期", "一次变更日期") if _date_text(record.get(column))), None)
        scheduled = changed or record.get("首次预约时间")
        actual = record.get("实际披露时间")
        rows.append({
            "symbol": str(record.get("股票代码", "")).zfill(6),
            "name": str(record.get("股票简称", "")),
            "period": period,
            "date": _date_text(actual) or _date_text(scheduled),
            "status": "已披露" if _date_text(actual) else ("已变更" if changed else "预约"),
        })
    _cache[period] = (time(), rows)
    return rows


def _date_text(value: Any) -> str:
    if value is None or str(value) in {"", "NaT", "None", "nan"}:
        return ""
    return str(value)[:10]
