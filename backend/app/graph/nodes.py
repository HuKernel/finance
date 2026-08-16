"""LangGraph 节点：投研流水线的每一步。

- collect_data: 数据收集（容错，单项失败不阻塞）
- run_analyst: 单个分析师执行（由 Send API 并行扇出）
- aggregate_views: 汇总分析师观点
- debate / consensus / risk / trader / abstain / finalize
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.types import Send

from .. import data as datalayer
from ..data.provider_contract import build_metadata
from ..agents.analysts import ALL_ANALYSTS
from ..agents.risk import RiskManager
from ..agents.trader import Trader
from ..llm import LLMClient
from ..models import AnalystView, DebateRound, RiskReview, TradePlan
from .state import AgentState

DISCLAIMER = (
    "本报告由 AI 智能体自动生成，仅供参考，不构成任何投资建议。"
    "市场有风险，投资需谨慎，盈亏自负。"
)

# 分析师角色注册表：role -> 类
ROLE_REGISTRY = {cls.role: cls for cls in ALL_ANALYSTS}
ANALYST_ORDER = [cls.role for cls in ALL_ANALYSTS]


def _get_llm(config: RunnableConfig) -> LLMClient:
    """从 graph config 取 LLM（测试可注入 mock），缺省用真实配置。"""
    return config.get("configurable", {}).get("llm") or LLMClient()


# ---------- 1. 数据收集 ----------

def collect_data(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    ticker = state.get("ticker", "")
    user_id = state.get("user_id")
    # 惰性结算：分析新股票时触发旧决策的反思（失败不阻塞主流程）
    try:
        from ..reflection_engine import settle_pending

        settle_pending(ticker, _get_llm(config), user_id=user_id)
    except Exception:
        pass

    ctx: dict[str, Any] = {"ticker": ticker}
    ctx["brief"] = datalayer.get_stock_brief(ticker) or {}
    ctx["source_meta"] = {
        "quote": {
            **build_metadata("quote", "tencent_quote", delay="near_realtime"),
            "fetched_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        },
    }
    # 各外部数据源互相独立，并发拉取（原串行是分析耗时的主要来源）
    from concurrent.futures import ThreadPoolExecutor
    from ..chat import get_user_memories
    from .. import reflection_engine
    from ..knowledge_base import build_knowledge_context

    def _safe(fn, default):
        try:
            return fn()
        except Exception:
            return default

    def _get_history():
        h = datalayer.get_history(ticker)
        if h is None:
            raise RuntimeError("history unavailable")
        return h

    with ThreadPoolExecutor(max_workers=8, thread_name_prefix="collect") as pool:
        fut_history = pool.submit(_get_history)
        fut_financials = pool.submit(lambda: _safe(lambda: datalayer.get_financials(ticker) or {}, {}))
        fut_lhb = pool.submit(lambda: _safe(lambda: datalayer.get_lhb(ticker), None))
        fut_news = pool.submit(lambda: _safe(lambda: datalayer.get_news(ticker) or [], []))
        fut_industry = pool.submit(lambda: _safe(lambda: datalayer.get_industry_compare(ticker) or None, None))
        fut_sentiment = pool.submit(lambda: _safe(lambda: datalayer.get_social_sentiment(ticker) or None, None))
        # 宏观背景（让宏观分析师基于真实市场数据而非凭空推断；仅A股相关）
        def _macro_block() -> dict[str, Any] | None:
            if ticker.lower().startswith(("hk", "us")):
                return None
            macro: dict[str, Any] = {}
            try:
                from ..data.market_overview import get_market_sentiment
                macro["market_sentiment"] = get_market_sentiment()
            except Exception:
                pass
            try:
                from ..data.north_flow import get_north_flow_overview
                macro["north_flow"] = get_north_flow_overview()
            except Exception:
                pass
            return macro or None
        fut_macro = pool.submit(_macro_block)
        fut_memories = pool.submit(lambda: _safe(
            (lambda: get_user_memories(user_id)) if user_id else (lambda: []), []))
        fut_reflection = pool.submit(lambda: _safe(
            (lambda: reflection_engine.build_memory_block(ticker, user_id)) if user_id else (lambda: ""), ""))
        fut_knowledge = pool.submit(lambda: _safe(
            (lambda: build_knowledge_context(user_id, ticker)) if user_id else (lambda: ""), ""))

        history = _safe(fut_history.result, None)
        ctx["financials"] = fut_financials.result()
        ctx["lhb"] = fut_lhb.result()
        ctx["news"] = fut_news.result()
        ctx["industry"] = fut_industry.result()
        ctx["sentiment"] = fut_sentiment.result()
        ctx["macro"] = fut_macro.result()
        ctx["user_memories"] = fut_memories.result()
        ctx["reflection_memory"] = fut_reflection.result()
        ctx["knowledge_context"] = fut_knowledge.result()

    try:
        ctx["tech"] = datalayer.compute_tech_signals(history) if history is not None else {"error": "行情数据不可用"}
        if history is not None:
            ctx["source_meta"]["history"] = {
                **history.attrs.get("data_meta", {}), "rows": len(history),
            }
    except Exception:
        ctx["tech"] = {"error": "技术指标计算失败"}
    # 历史趋势摘要（让分析师有纵向参照，不只是最新快照）
    try:
        hist = history.tail(120) if history is not None else None
        if hist is not None and len(hist) >= 20:
            closes = hist["close"].dropna().astype(float).tolist()
            if len(closes) >= 20:
                import statistics
                ctx["trend"] = {
                    "ma5": round(sum(closes[-5:]) / 5, 2),
                    "ma20": round(sum(closes[-20:]) / 20, 2),
                    "ma60": round(sum(closes[-60:]) / 60, 2) if len(closes) >= 60 else None,
                    "high_120": round(max(closes), 2),
                    "low_120": round(min(closes), 2),
                    "latest": closes[-1],
                    "stdev": round(statistics.stdev(closes[-20:]) if len(closes) >= 21 else 0, 2),
                    "prev_month_close": closes[-21] if len(closes) >= 21 else None,
                }
    except Exception:
        ctx["trend"] = None
    return {"context": ctx}


# ---------- 2. 分析师并行（Send fan-out）----------

def fan_out_analysts(state: AgentState) -> list[Send]:
    """Map 阶段：为每个分析师角色分发一个 Send 任务（LangGraph 并行执行）。

    支持用户配置：从用户画像的 analyst_config 过滤，
    如果未配置则默认全部启用。
    mode（"standard"|"agentic"）透传给每个 run_analyst 任务，
    决定选用标准分析师还是自主调工具的 Agentic 变体。
    """
    ctx = state.get("context", {})
    mode = state.get("mode", "standard")
    enabled = None
    user_id = state.get("user_id")
    if user_id:
        try:
            from ..auth import get_profile

            enabled = get_profile(user_id).get("analyst_config")
        except Exception:
            pass
    if enabled and isinstance(enabled, list):
        roles = [r for r in ANALYST_ORDER if r in enabled]
    else:
        roles = ANALYST_ORDER
    return [
        Send("run_analyst", {"context": ctx, "role": role, "mode": mode, "trace": state.get("trace")})
        for role in roles
    ]


def run_analyst(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """单个分析师执行，产出 {role: AnalystView} 写入 view_map。

    根据 mode 选择分析师类：
    - "agentic": 用 AgenticXxxAnalyst（自主调工具循环）
    - 其他/缺省: 用标准 ROLE_REGISTRY 分析师（向后兼容）
    """
    role = state["role"]
    mode = state.get("mode", "standard")
    agent_cls = None
    if mode == "agentic":
        try:
            from ..agents.analysts import AGENTIC_ANALYSTS

            registry = {c.role: c for c in AGENTIC_ANALYSTS}
            agent_cls = registry.get(role)
        except Exception:
            agent_cls = None
    if agent_cls is None:
        agent_cls = ROLE_REGISTRY[role]
    agent = agent_cls(_get_llm(config))
    context = dict(state["context"])
    trace = state.get("trace")
    if trace:
        context["_on_tool_call"] = lambda name, result: trace.tool(name, result, role)
    try:
        view = agent.analyze(context)
    except Exception as e:
        view = AnalystView(role=role, title=agent_cls.title, summary=f"分析异常: {e}", score=0)
    return {"view_map": {role: view}}


def aggregate_views(state: AgentState) -> dict[str, Any]:
    """Reduce 阶段：按固定顺序汇总 view_map 为 views 列表。

    同时记录每个分析师的决策到反思引擎（pending 状态，N 天后结算）。
    记录失败不阻塞主流程。
    """
    view_map: dict[str, AnalystView] = state.get("view_map", {})
    views = [view_map[r] for r in ANALYST_ORDER if r in view_map]
    # 记录每个分析师的决策（供交易后反思）
    try:
        from ..reflection_engine import record_decision

        ticker = state.get("ticker", "")
        today = datetime.now().strftime("%Y-%m-%d")
        for view in views:
            try:
                record_decision(
                    ticker, view.role, view.score, view.summary, today,
                    user_id=state.get("user_id"),
                    analysis_id=state.get("analysis_id"),
                )
            except Exception:
                pass
    except Exception:
        pass
    return {"views": views}


# ---------- 3. 辩论 ----------

def run_debate(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    views = state["views"]
    llm = _get_llm(config)
    if len(views) < 2:
        return {"debate": []}
    sorted_views = sorted(views, key=lambda v: v.score)
    bear, bull = sorted_views[0], sorted_views[-1]
    if bull.score - bear.score < 1:
        return {"debate": [DebateRound(topic="观点一致性较高，未触发激烈辩论", positions=[])]}
    
    rounds: list[DebateRound] = []
    ctx = state.get("context", {})
    ticker = state.get('ticker', '')
    topic = state.get('topic') or '常规投研'
    other_views = ', '.join(v.title + '(' + str(v.score) + ')' for v in views if v.role not in (bear.role, bull.role))

    def _evidence_block(v, limit: int = 3) -> str:
        ev = [str(e) for e in (getattr(v, "evidence", None) or [])][:limit]
        return "；".join(ev) if ev else "（未提供具体证据）"

    prev_bear_arg = f"{bear.summary} 证据: {_evidence_block(bear)}"
    prev_bull_arg = f"{bull.summary} 证据: {_evidence_block(bull)}"

    # 多轮辩论：双方各自独立调用 LLM 陈述/反驳（真实对抗，而非主持人一人分饰两角），
    # 每轮结束后由主席调用一次总结交锋
    for rnd in range(2):
        label = "第一轮辩论" if rnd == 0 else "第二轮反驳"
        bear_system = (
            f"你是看空分析师（{bear.title}）。围绕标的与看多方辩论，第{rnd + 1}轮{label}。"
            "必须引用具体数据反驳对方，不得泛泛而谈。只输出JSON: "
            '{"argument": "你的本轮论点（120字内，需含数据）"}'
        )
        bull_system = (
            f"你是看多分析师（{bull.title}）。围绕标的与看空方辩论，第{rnd + 1}轮{label}。"
            "必须引用具体数据反驳对方，不得泛泛而谈。只输出JSON: "
            '{"argument": "你的本轮论点（120字内，需含数据）"}'
        )
        common = (
            f"标的: {ticker}  主题: {topic}\n"
            f"己方初始观点: {bear.summary if rnd == 0 else prev_bear_arg}\n"
            f"对方论点: {prev_bull_arg}\n"
            f"其他观点: {other_views}\n"
        )
        common_bull = (
            f"标的: {ticker}  主题: {topic}\n"
            f"己方初始观点: {bull.summary if rnd == 0 else prev_bull_arg}\n"
            f"对方论点: {prev_bear_arg}\n"
            f"其他观点: {other_views}\n"
        )
        bear_data = llm.chat_json(bear_system, common)
        bull_data = llm.chat_json(bull_system, common_bull)
        bear_arg = str(bear_data.get("argument") or prev_bear_arg)[:300]
        bull_arg = str(bull_data.get("argument") or prev_bull_arg)[:300]

        # 主席总结本轮交锋
        clash = llm.chat_json(
            "你是辩论主席。总结本轮多空交锋：双方最强论据各是什么、哪些点被有效反驳、分歧是否缩小。"
            '只输出JSON: {"conclusion": "交锋结论（80字内）"}',
            f"看空方: {bear_arg}\n看多方: {bull_arg}",
        )
        conclusion = str(clash.get("conclusion") or "")[:200]

        rounds.append(DebateRound(
            topic=f"[{label}] {ticker} 多空辩论",
            positions=[
                f"看空方({bear.title}): {bear_arg}",
                f"看多方({bull.title}): {bull_arg}",
                conclusion,
            ],
        ))
        prev_bear_arg, prev_bull_arg = bear_arg, bull_arg

    return {"debate": rounds}


# ---------- 4. 共识 ----------

def run_consensus(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """共识阶段：交叉质疑 + 投票决策。

    增强：
    1. 每个分析师对其他人的观点进行质疑（交叉质疑）
    2. 所有分析师对最终结论投票（多/空/中性）
    3. 投票结果影响共识评分
    """
    views = state["views"]
    score = round(sum(v.score for v in views) / len(views), 2) if views else 0.0
    views_block = "\n".join(f"- {v.title} ({v.score}): {v.summary[:120]}" for v in views)
    debate_ctx = ""
    if state.get("debate"):
        last_round = state["debate"][-1]
        debate_ctx = "\n辩论交锋: " + " | ".join(last_round.positions[:3])

    system = (
        "你是投研委员会主席，负责汇总各分析师观点形成最终共识结论。"
        "结论需包含：核心逻辑、主要分歧、风险提示、投票结果。100-150字，简洁专业。"
    )
    user = (
        f"标的: {state.get('ticker')}  主题: {state.get('topic') or '常规投研'}\n"
        f"综合评分: {score}/10\n观点:\n{views_block}{debate_ctx}\n\n"
        "请汇总共识，并在末尾附加分析师投票："
        "统计看多/看空/中性各几票，给出最终建议（买入/观望/卖出）。"
    )
    verdict = _get_llm(config).chat(system, user)

    # 投票统计：根据评分自动判定（仅展示，不参与计分）
    votes = {"bull": 0, "bear": 0, "neutral": 0}
    for v in views:
        if v.score >= 3:
            votes["bull"] += 1
        elif v.score <= -3:
            votes["bear"] += 1
        else:
            votes["neutral"] += 1

    # 分歧度折减（替代旧的"投票再加分"——那是对同一信号的双重计分）：
    # 分析师评分标准差越大，共识越不可信，分数向中性收缩；分歧小则保留原分。
    scores = [v.score for v in views]
    dispersion = round(float(__import__("statistics").pstdev(scores)), 2) if len(scores) > 1 else 0.0
    shrink = 1.0 - min(dispersion, 5.0) / 10.0  # 分歧5分以上最多打5折
    adjusted_score = round(max(-10, min(10, score * shrink)), 2)
    vote_adjustment = round(adjusted_score - score, 2)

    # 记录综合共识决策（供交易后反思）
    try:
        from ..reflection_engine import record_decision

        record_decision(
            state.get("ticker", ""),
            "consensus",
            adjusted_score,
            verdict[:500] if verdict else "",
            datetime.now().strftime("%Y-%m-%d"),
            user_id=state.get("user_id"),
            analysis_id=state.get("analysis_id"),
        )
    except Exception:
        pass

    return {
        "consensus_score": adjusted_score,
        "consensus_verdict": verdict,
        "votes": votes,
        "raw_score": score,
        "dispersion": dispersion,
        "vote_adjustment": vote_adjustment,
    }


# ---------- 5. 风控 ----------

def run_risk(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    # 把辩论交锋与共识结论一并交给风控（后段流程不再丢信息）
    debate_block = ""
    if state.get("debate"):
        last = state["debate"][-1]
        debate_block = "\n".join(p for p in last.positions[:2])
    review = RiskManager(_get_llm(config)).review(
        state.get("context", {}), state["views"], state["consensus_score"],
        debate_summary=debate_block or None,
        consensus_verdict=state.get("consensus_verdict"),
    )
    return {"risk_review": review}


# ---------- 6. 交易计划 / 避险（条件分支）----------

def route_after_risk(state: AgentState) -> str:
    """条件边：风控批准走正常交易计划，否决走避险节点。"""
    return "trader_node" if state.get("risk_review", RiskReview(approved=True, verdict="")).approved else "abstain"


def run_trader(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    plan = Trader(_get_llm(config)).plan(
        state.get("context", {}),
        state["views"],
        state["consensus_score"],
        state["consensus_verdict"],
        state["risk_review"],
    )
    return {"trade_plan": plan}


def run_abstain(state: AgentState) -> dict[str, Any]:
    """风控否决时的避险计划：不调 LLM，直接生成回避动作。"""
    plan = TradePlan(
        action="回避",
        target_price=None,
        stop_loss=None,
        position_pct=0.0,
        reasoning="风控经理否决了本次交易建议，强制规避以控制风险。",
        risk_warnings=["风控否决", "禁止开仓"],
    )
    return {"trade_plan": plan}


# ---------- 7. 组装与入库 ----------

def finalize(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    from ..memory import save_analysis

    brief = state.get("context", {}).get("brief") or {}
    created_at = datetime.now().isoformat(timespec="seconds")
    result = {
        "ticker": state.get("ticker", ""),
        "name": brief.get("name", ""),
        "price": brief.get("price"),
        "change_pct": brief.get("change_pct"),
        "created_at": created_at,
        "status": "completed",
        "consensus_score": state.get("consensus_score", 0.0),
        "consensus_verdict": state.get("consensus_verdict", ""),
        "analyst_views": [v.model_dump() for v in state.get("views", [])],
        "debate": [d.model_dump() for d in state.get("debate", [])],
        "risk_review": state.get("risk_review").model_dump() if state.get("risk_review") else None,
        "trade_plan": state.get("trade_plan").model_dump() if state.get("trade_plan") else None,
        "disclaimer": DISCLAIMER,
        "raw": {
            "topic": state.get("topic") or "",
            "report": _build_report_evidence(state, created_at),
        },
    }
    analysis_id = state.get("analysis_id")
    if analysis_id:
        from ..memory import update_analysis
        result["id"] = analysis_id
        update_analysis(analysis_id, result)
    else:
        result["id"] = save_analysis(result["ticker"], result, user_id=state.get("user_id"))
    return {"result": result}


def _build_report_evidence(state: AgentState, created_at: str) -> dict[str, Any]:
    """保存报告可核对的事实、计算口径与 AI 判断边界。"""
    context = state.get("context", {})
    brief = context.get("brief") or {}
    financials = context.get("financials") or {}
    news = context.get("news") or []
    sources = context.get("source_meta") or {}
    ticker = state.get("ticker", "")
    financial_source = "yfinance" if ticker.lower().startswith(("hk", "us")) else "akshare_ths"
    return {
        "schema_version": 2,
        "generated_at": created_at,
        "facts": {
            "quote": {
                "source": sources.get("quote", {}),
                "values": {key: brief.get(key) for key in (
                    "price", "change_pct", "market_cap", "pe", "pb", "turnover",
                )},
            },
            "history": sources.get("history", {}),
            "financials": {
                "source": financial_source,
                "period": financials.get("period"),
                "values": {key: financials.get(key) for key in (
                    "revenue", "revenue_yoy", "net_profit", "net_profit_yoy",
                    "roe", "gross_margin", "debt_ratio",
                )},
            },
            "news": {
                "count": len(news),
                "sources": sorted({item.get("source") for item in news if item.get("source")}),
                "latest_at": max(
                    (item.get("published_at") or item.get("time") or "" for item in news),
                    default="",
                ),
            },
        },
        "calculations": {
            "trend": {
                "method": "最近120个交易日收盘价；MA为简单移动平均，波动为最近20日样本标准差",
                "values": context.get("trend"),
            },
            "consensus_score": {
                "method": "分析师评分算术平均 + 0.3 × (看多票 - 看空票)，结果限制在[-10, 10]",
                "raw_score": state.get("raw_score"),
                "votes": state.get("votes") or {},
                "vote_adjustment": state.get("vote_adjustment"),
                "value": state.get("consensus_score", 0.0),
            },
        },
        "ai_judgments": ["analyst_views", "debate", "consensus_verdict", "risk_review", "trade_plan"],
        "assumptions": {
            "history_window": 120,
            "adjustment": sources.get("history", {}).get("adjustment"),
            "topic": state.get("topic") or "常规投研",
        },
    }
