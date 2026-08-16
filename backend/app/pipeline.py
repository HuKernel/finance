"""编排流水线：基于 LangGraph 状态图的薄封装。

完整流程由 app.graph 定义：
  collect_data -> [5×run_analyst 并行] -> aggregate_views -> debate
  -> consensus -> risk -> (批准: trader | 否决: abstain) -> finalize

对外保持 run_analysis(ticker, topic) 签名，API 层无需改动。
"""
from __future__ import annotations

import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from .analysis_trace import AnalysisTrace, attach_trace
from .graph.builder import build_graph
from .llm import LLMClient
from . import memory

logger = logging.getLogger(__name__)

# 编译一次，全局复用（LangGraph 图可被多次 invoke）
_GRAPH = build_graph()

# 同时运行的投研分析上限：每个分析要占一个线程 + 5 路 LLM 调用，
# 无限并发会把线程池和 LLM 配额同时打爆
ANALYSIS_MAX_CONCURRENT = int(os.environ.get("ANALYSIS_MAX_CONCURRENT", "3"))
# 单次分析的总超时（秒）：任一 LLM 供应商卡死时不再无限挂起
ANALYSIS_TIMEOUT = int(os.environ.get("ANALYSIS_TIMEOUT_SECONDS", "900"))

_analysis_semaphore = threading.BoundedSemaphore(ANALYSIS_MAX_CONCURRENT)
# 超时后后台图执行线程的宿主：与请求线程解耦，避免占死线程池
_deadline_executor = ThreadPoolExecutor(max_workers=ANALYSIS_MAX_CONCURRENT, thread_name_prefix="analysis-run")


class AnalysisTimeoutError(RuntimeError):
    """投研流水线总耗时超过 ANALYSIS_TIMEOUT。"""


def run_analysis(
    ticker: str,
    topic: str | None = None,
    llm: LLMClient | None = None,
    user_id: int | None = None,
    mode: str = "standard",
) -> dict[str, Any]:
    """执行完整投研流水线，返回 AnalysisResult 结构字典。

    llm 参数用于测试注入（如 mock 无 key 的客户端）；生产环境省略。
    mode: "standard"（默认，标准分析师）| "agentic"（自主调工具的 Agentic 分析师）。

    异常处理：单个分析师失败已被 graph/nodes.py 隔离（返回 score=0 的兜底视图）。
    此处捕获的是整个流水线的未预期异常（如 LLM 无 key、数据源全挂、序列化错误等），
    返回一个 error 状态的结果而不是让调用方崩溃。
    """
    if llm is None:
        llm = LLMClient(user_id=user_id) if user_id is not None else LLMClient()
    trace = AnalysisTrace(ticker, mode, llm)
    analysis_id: int | None = None
    try:
        initial = attach_trace({"ticker": ticker, "status": "running", "raw": {"topic": topic or ""}}, trace)
        analysis_id = memory.save_analysis(ticker, initial, status="running", user_id=user_id)
        config: dict[str, Any] = {"configurable": {"llm": llm}}
        state: dict[str, Any] = {
            "ticker": ticker,
            "topic": topic,
            "user_id": user_id,
            "mode": mode,
            "analysis_id": analysis_id,
            "run_id": trace.run_id,
            "trace": trace,
        }
        with _analysis_semaphore:
            started = time.monotonic()
            future = _deadline_executor.submit(_GRAPH.invoke, state, config=config)
            try:
                state = future.result(timeout=ANALYSIS_TIMEOUT)
            except TimeoutError as exc:
                future.cancel()
                raise AnalysisTimeoutError(
                    f"分析超过 {ANALYSIS_TIMEOUT} 秒未完成（已耗时 {time.monotonic() - started:.0f}s）"
                ) from exc
        trace.step("pipeline", "完整投研流水线")
        trace.finish()
        result = attach_trace(state["result"], trace)
        memory.update_analysis(analysis_id, result)
        return result
    except Exception as e:
        logger.exception("投研流水线异常 ticker=%s: %s", ticker, e)
        trace.finish("error", str(e))
        result = {
            "id": analysis_id,
            "ticker": ticker,
            "name": ticker,
            "status": "error",
            "consensus_score": 0.0,
            "consensus_verdict": f"分析流程异常: {e}",
            "analyst_views": [],
            "debate": [],
            "risk_review": None,
            "trade_plan": None,
            "disclaimer": "分析过程中出现错误，请稍后重试或检查 LLM 配置。",
            "error": str(e),
        }
        attach_trace(result, trace)
        if analysis_id is not None:
            memory.update_analysis(analysis_id, result, status="error")
        return result
