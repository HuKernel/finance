"""市场情绪、全市场榜单与资讯雷达的数据聚合。"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from curl_cffi import requests as cq

from ..cache import TTL, cached
from .utils import AK_AVAILABLE, ak


_CLIST_URL = "https://push2delay.eastmoney.com/api/qt/clist/get"
_FS = "m:1+t:2,m:1+t:23,m:0+t:6,m:0+t:80,m:0+t:81"
_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}


def _number(value: Any) -> float | None:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def _pool(name: str, fn_name: str) -> dict[str, Any]:
    if not AK_AVAILABLE:
        return {"name": name, "items": [], "available": False, "source": "akshare_eastmoney"}
    try:
        df = getattr(ak, fn_name)(date=datetime.now().strftime("%Y%m%d"))
    except Exception:
        return {"name": name, "items": [], "available": False, "source": "akshare_eastmoney"}
    if df is None or df.empty:
        if name == "跌停":
            try:
                from .stock_screener import _fetch_all_stocks
                snapshot = _fetch_all_stocks()
                if snapshot is not None:
                    snapshot = snapshot[snapshot["change_pct"] <= -9.5].head(20)
                    items = [{
                        "code": str(row["code"]), "name": str(row["name"]),
                        "change_pct": _number(row["change_pct"]), "price": _number(row["price"]),
                        "reason": "全市场快照跌幅筛选", "boards": None,
                    } for _, row in snapshot.iterrows()]
                    return {"name": name, "items": items, "available": True, "source": "sina_snapshot"}
            except Exception:
                pass
        return {"name": name, "items": [], "available": True, "source": "akshare_eastmoney"}
    columns = {str(col) for col in df.columns}
    items = []
    for _, row in df.head(20).iterrows():
        code = str(row.get("代码", "")).zfill(6)
        items.append({
            "code": code,
            "name": str(row.get("名称", "")),
            "change_pct": _number(row.get("涨跌幅")),
            "price": _number(row.get("最新价")),
            "reason": str(row.get("涨停原因类别", row.get("所属行业", ""))),
            "boards": _number(row.get("连板数")) if "连板数" in columns else None,
        })
    return {"name": name, "items": items, "available": True, "source": "akshare_eastmoney"}


def _lhb() -> list[dict[str, Any]]:
    if not AK_AVAILABLE:
        return []
    try:
        end = datetime.now()
        df = ak.stock_lhb_detail_em(
            start_date=(end - timedelta(days=7)).strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
        )
    except Exception:
        return []
    items = []
    for _, row in df.head(20).iterrows():
        items.append({
            "code": str(row.get("代码", "")).zfill(6),
            "name": str(row.get("名称", "")),
            "date": str(row.get("上榜日", ""))[:10],
            "reason": str(row.get("上榜原因", "")),
            "net_buy": _number(row.get("龙虎榜净买额")),
        })
    return items


def get_market_sentiment() -> dict[str, Any]:
    """涨停、炸板、跌停、连板和近期龙虎榜。"""
    def fetch() -> dict[str, Any]:
        pools = [
            _pool("涨停", "stock_zt_pool_em"),
            _pool("炸板", "stock_zt_pool_zbgc_em"),
            _pool("跌停", "stock_zt_pool_dtgc_em"),
        ]
        ladder = sorted(
            (item for pool in pools[:1] for item in pool["items"] if item["boards"]),
            key=lambda item: item["boards"] or 0,
            reverse=True,
        )
        return {"pools": pools, "ladder": ladder[:20], "lhb": _lhb()}

    return cached("market:sentiment", 120, fetch)


def _ranking(sort_field: str, descending: bool) -> list[dict[str, Any]]:
    params = {
        "pn": 1, "pz": 20, "po": 1 if descending else 0, "np": 1,
        "fltt": 2, "invt": 2, "fid": sort_field, "fs": _FS,
        "fields": "f12,f14,f2,f3,f6,f8,f62,f184", "_": int(datetime.now().timestamp() * 1000),
    }
    try:
        rows = cq.get(_CLIST_URL, params=params, headers=_HEADERS, impersonate="chrome", timeout=8).json()["data"]["diff"]
    except Exception:
        return []
    return [{
        "code": str(row.get("f12", "")), "name": str(row.get("f14", "")),
        "price": _number(row.get("f2")), "change_pct": _number(row.get("f3")),
        "amount": _number(row.get("f6")), "turnover": _number(row.get("f8")),
        "main_net_inflow": _number(row.get("f62")),
    } for row in rows]


def get_market_rankings() -> dict[str, Any]:
    """东财延迟全市场涨幅、跌幅与成交额榜。"""
    def fetch() -> dict[str, Any]:
        return {
            "gainers": _ranking("f3", True),
            "losers": _ranking("f3", False),
            "turnover": _ranking("f6", True),
        }
    return cached("market:rankings", TTL["quote"], fetch)
