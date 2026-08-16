"""统一 SQLite 连接管理。

所有模块请通过 `connect()` 获取连接，统一开启 WAL 和 busy_timeout，
避免多线程并发写时出现 database is locked。
"""
from __future__ import annotations

import sqlite3


def connect(db_path: str | None = None) -> sqlite3.Connection:
    # 延迟导入避免与 config 循环依赖
    from .config import DB_PATH
    conn = sqlite3.connect(db_path or DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn
