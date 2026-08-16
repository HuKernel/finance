"""统一 HTTP 客户端：httpx 连接池 + 默认超时 + 失败日志。

全仓外部请求（除需要浏览器指纹的 curl_cffi 场景）统一走这里，
替换散落各处的 requests.get/post：
- 连接池复用，避免每请求新建 TCP/TLS 连接
- 默认超时（连接 5s / 读取 15s），调用方可覆盖
- 请求异常统一 warning 日志（原来静默吞掉，数据源挂了无从排查）
"""
from __future__ import annotations

from typing import Any

import httpx

from .logger import get_logger

log = get_logger("http")

# 模块级共享客户端；httpx.Client 线程安全，可供 AnyIO 线程池并发使用
_client = httpx.Client(
    timeout=httpx.Timeout(connect=5.0, read=15.0, write=15.0, pool=5.0),
    limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
    follow_redirects=True,
    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) FinanceCrew/0.4"},
)

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


def get(url: str, *, params: dict | None = None, headers: dict | None = None,
        timeout: float | httpx.Timeout | None = None) -> httpx.Response:
    merged = {**DEFAULT_HEADERS, **(headers or {})}
    try:
        return _client.get(url, params=params, headers=merged, timeout=timeout)
    except httpx.HTTPError as e:
        log.warning("GET %s failed: %s", url, e)
        raise


def post(url: str, *, params: dict | None = None, headers: dict | None = None,
         json: Any = None, data: Any = None,
         timeout: float | httpx.Timeout | None = None) -> httpx.Response:
    merged = {**DEFAULT_HEADERS, **(headers or {})}
    try:
        return _client.post(url, params=params, headers=merged, json=json, data=data, timeout=timeout)
    except httpx.HTTPError as e:
        log.warning("POST %s failed: %s", url, e)
        raise


def close() -> None:
    _client.close()
