"""投研运行追踪：记录节点、工具、模型和耗时，不保存敏感输入。"""
from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from time import perf_counter
from typing import Any
from uuid import uuid4


class AnalysisTrace:
    def __init__(self, ticker: str, mode: str, llm: Any = None):
        config = getattr(llm, "config", {}) or {}
        self.run_id = uuid4().hex
        self.ticker = ticker
        self.mode = mode
        self.provider = str(config.get("provider") or "unknown")
        self.model = str(config.get("model") or "unknown")
        self.started_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        self._started = perf_counter()
        self._finished_at: str | None = None
        self._duration_ms: int | None = None
        self._status = "running"
        self._error: str | None = None
        self._steps: list[dict[str, Any]] = []
        self._tools: list[dict[str, Any]] = []
        self._lock = Lock()

    @property
    def finished(self) -> bool:
        return self._finished_at is not None

    def step(self, name: str, label: str, detail: str | None = None) -> None:
        now = perf_counter()
        with self._lock:
            item: dict[str, Any] = {
                "name": name,
                "label": label,
                "status": "done",
                "at_ms": max(0, round((now - self._started) * 1000)),
            }
            if detail:
                item["detail"] = detail
            self._steps.append(item)

    def tool(self, name: str, preview: str = "", role: str | None = None) -> None:
        with self._lock:
            item: dict[str, Any] = {
                "name": name,
                "status": "done",
                "at_ms": max(0, round((perf_counter() - self._started) * 1000)),
            }
            if role:
                item["role"] = role
            self._tools.append(item)

    def finish(self, status: str = "completed", error: str | None = None) -> None:
        with self._lock:
            if self._finished_at is not None:
                return
            self._status = status
            self._error = error
            self._duration_ms = max(0, round((perf_counter() - self._started) * 1000))
            self._finished_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            out: dict[str, Any] = {
                "run_id": self.run_id,
                "ticker": self.ticker,
                "mode": self.mode,
                "provider": self.provider,
                "model": self.model,
                "status": self._status,
                "started_at": self.started_at,
                "finished_at": self._finished_at,
                "duration_ms": self._duration_ms if self._duration_ms is not None else max(0, round((perf_counter() - self._started) * 1000)),
                "steps": list(self._steps),
                "tools": list(self._tools),
            }
            if self._error:
                out["error"] = self._error
            return out


def attach_trace(result: dict[str, Any], trace: AnalysisTrace) -> dict[str, Any]:
    raw = dict(result.get("raw") or {})
    raw["trace"] = trace.snapshot()
    result["raw"] = raw
    result["run_id"] = trace.run_id
    return result
