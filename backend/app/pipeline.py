"""编排流水线：基于 LangGraph 状态图的薄封装。

完整流程由 app.graph 定义：
  collect_data -> [5×run_analyst 并行] -> aggregate_views -> debate
  -> consensus -> risk -> (批准: trader | 否决: abstain) -> finalize

对外保持 run_analysis(ticker, topic) 签名，API 层无需改动。
"""
from __future__ import annotations

import logging
from typing import Any

from .analysis_trace import AnalysisTrace, attach_trace
from .graph.builder import build_graph
from .llm import LLMClient
from . import memory

logger = logging.getLogger(__name__)

# 编译一次，全局复用（LangGraph 图可被多次 invoke）
_GRAPH = build_graph()


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
        state = _GRAPH.invoke(state, config=config)
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
