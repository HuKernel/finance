"""风控经理：审查共识结论，输出风控意见（可一票否决）。"""
from __future__ import annotations

from typing import Any

from ..llm import LLMClient
from ..models import RiskReview


class RiskManager:
    role = "risk"
    title = "风控经理"

    def __init__(self, llm: LLMClient | None = None):
        self.llm = llm or LLMClient()

    def review(self, context: dict[str, Any], views: list, consensus_score: float,
               debate_summary: str | None = None,
               consensus_verdict: str | None = None) -> RiskReview:
        """输入：全部角色观点 + 共识评分（+辩论交锋与共识结论摘要）。输出：风控意见。"""
        brief = context.get("brief") or {}
        tech = context.get("tech") or {}
        views_block = "\n".join(
            f"- {v.title}: 评分 {v.score} | {v.summary[:80]}" for v in views
        )
        # 注入用户记忆（影响风控建议：偏保守则更严格）
        memories = context.get("user_memories") or []
        mem_block = ""
        if memories:
            mem_block = "\n用户偏好：" + "；".join(memories[:5]) + "\n"
        debate_block = f"\n辩论交锋摘要:\n{debate_summary[:400]}\n" if debate_summary else ""
        verdict_block = f"\n共识结论: {consensus_verdict[:200]}\n" if consensus_verdict else ""
        user_prompt = (
            f"标的: {context.get('ticker')} ({brief.get('name', '')})  现价: {brief.get('price', 'N/A')}\n"
            f"共识评分: {consensus_score}（-10看空 ~ +10看多）\n"
            f"各角色观点:\n{views_block}\n"
            f"60日低点: {tech.get('low_60d', 'N/A')}  60日高点: {tech.get('high_60d', 'N/A')}\n"
            f"{debate_block}{verdict_block}{mem_block}\n"
            "请输出JSON: {\"approved\": bool, \"verdict\": \"风控结论\", "
            "\"max_position_pct\": 建议最大仓位百分比, \"stop_loss_pct\": 建议止损百分比}\n"
            "规则：共识偏多(评分>=3)建议仓位不超过10%；中性(|评分|<3)仓位不超过5%；"
            "评分接近-10（强烈看空）应 approved=false；存在重大风险时 approved=false。"
        )
        system = (
            "你是风控经理，负责审查交易建议。你有最终否决权。"
            "只输出JSON，不要输出其他文字。"
        )
        data = self.llm.chat_json(system, user_prompt)
        # 解析失败不能静默一票否决：降级为保守的规则审查并明确标注
        if "error" in data:
            approved = consensus_score > -6
            return RiskReview(
                approved=approved,
                verdict=f"[风控降级] LLM输出解析失败，已按规则保守审查（共识评分{consensus_score}）。原始错误: {data.get('error', '')}",
                max_position_pct=5.0 if approved else 0.0,
                stop_loss_pct=8.0 if approved else 0.0,
            )
        approved = data.get("approved") is True
        position_limit = 10.0 if consensus_score >= 3 else 5.0
        return RiskReview(
            approved=approved,
            verdict=str(data.get("verdict", "")),
            max_position_pct=_clamp(data.get("max_position_pct"), position_limit) if approved else 0.0,
            stop_loss_pct=_clamp(data.get("stop_loss_pct"), 100.0) if approved else 0.0,
        )


def _clamp(value: Any, upper: float) -> float:
    try:
        number = float(value or 0)
        return max(0.0, min(upper, number)) if number == number else 0.0
    except (TypeError, ValueError):
        return 0.0
