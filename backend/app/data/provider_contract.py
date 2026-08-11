"""数据源统一元数据契约与能力清单。"""
from __future__ import annotations

from typing import Any


PROVIDER_CAPABILITIES = {
    "tencent": {"name": "腾讯", "access": "free", "requires_key": False, "kinds": ["quote", "bar", "minute"]},
    "eastmoney": {"name": "东方财富", "access": "free", "requires_key": False, "kinds": ["minute", "news"]},
    "sina": {"name": "新浪", "access": "free", "requires_key": False, "kinds": ["bar", "minute", "news"]},
    "akshare": {"name": "AKShare", "access": "free", "requires_key": False, "kinds": ["bar", "fundamental"]},
    "yfinance": {"name": "Yahoo Finance", "access": "free", "requires_key": False, "kinds": ["bar", "minute", "fundamental"]},
    "polygon": {"name": "Polygon.io", "access": "freemium", "requires_key": True, "kinds": ["minute"]},
}

_SOURCE_LABELS = {
    "tencent": ("tencent", "腾讯"),
    "tencent_quote": ("tencent", "腾讯"),
    "tencent_fqkline": ("tencent", "腾讯"),
    "akshare_tencent": ("akshare", "AKShare / 腾讯"),
    "akshare_sina": ("akshare", "AKShare / 新浪"),
    "akshare_ths": ("akshare", "AKShare / 同花顺"),
    "eastmoney": ("eastmoney", "东方财富"),
    "sina": ("sina", "新浪"),
    "sina_us_daily": ("sina", "新浪美股"),
    "yfinance": ("yfinance", "Yahoo Finance"),
    "polygon": ("polygon", "Polygon.io"),
}


def build_metadata(
    kind: str,
    source: str,
    *,
    as_of: str | None = None,
    delay: str = "unknown",
    adjustment: str = "none",
    fallback_used: bool = False,
    fallback_reason: str | None = None,
    rows_dropped: int = 0,
) -> dict[str, Any]:
    provider, provider_name = _SOURCE_LABELS.get(source, (source or "unknown", source or "未知"))
    return {
        "kind": kind,
        "source": source or "unknown",
        "provider": provider,
        "provider_name": provider_name,
        "as_of": as_of,
        "delay": delay,
        "adjustment": adjustment,
        "fallback_used": fallback_used,
        "fallback_reason": fallback_reason if fallback_used else None,
        "rows_dropped": rows_dropped,
    }


def news_metadata(items: list[dict[str, Any]]) -> dict[str, Any]:
    names = sorted({item.get("source") for item in items if item.get("source")})
    latest = max((item.get("published_at") or item.get("time") or "" for item in items), default="")
    meta = build_metadata("news", "mixed" if len(names) > 1 else (names[0] if names else "unknown"), as_of=latest or None, delay="delayed")
    meta["provider_name"] = " / ".join(names) if names else "未知"
    return meta
