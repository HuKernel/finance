"""登录频率限制：5次失败后锁定15分钟（内存计数器，重启清零）。"""
from __future__ import annotations

import time
from typing import Any

# 登录频率限制：{ip_or_username: (fail_count, first_fail_time, lock_until)}
_login_attempts: dict[str, dict[str, Any]] = {}
MAX_LOGIN_FAILS = 5
LOCK_DURATION = 15 * 60  # 锁定15分钟


def check_rate_limit(identifier: str) -> tuple[bool, str]:
    """检查登录频率限制。返回(是否允许, 锁定提示)。"""
    now = int(time.time())
    rec = _login_attempts.get(identifier)

    if rec and rec.get("lock_until", 0) > now:
        remain = int((rec["lock_until"] - now) / 60)
        return False, f"登录失败次数过多，请{remain}分钟后再试"

    if rec and now - rec.get("first_fail", 0) > 3600:
        # 超过1小时重置
        del _login_attempts[identifier]

    return True, ""


def record_login_fail(identifier: str) -> None:
    """记录登录失败。"""
    now = int(time.time())
    rec = _login_attempts.get(identifier, {"count": 0, "first_fail": now, "lock_until": 0})
    rec["count"] += 1
    if rec["count"] >= MAX_LOGIN_FAILS:
        rec["lock_until"] = now + LOCK_DURATION
    _login_attempts[identifier] = rec


def record_login_success(identifier: str) -> None:
    """登录成功清除失败记录。"""
    _login_attempts.pop(identifier, None)
