"""多LLM模型对比：同一问题并行调用多个模型，对比回答。

用户在配置页保存多个LLM配置，对比功能用同样的prompt并行调用，
返回每个模型的回答+耗时+token数（如可用）。
"""
from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI


def compare_models(
    prompt: str,
    models: list[dict[str, Any]],
    system: str = "你是金融分析助手，请专业、简洁地回答问题。",
) -> list[dict[str, Any]]:
    """并行调用多个LLM对比回答。

    models: [{"name": "DeepSeek", "base_url": "...", "api_key": "...", "model": "..."}, ...]
    返回回答、耗时、真实 usage、可选成本和启发式证据指标；单模型失败互不影响。
    """
    if not models:
        return []
    results: list[dict[str, Any] | None] = [None] * len(models)
    with ThreadPoolExecutor(max_workers=min(len(models), 5)) as executor:
        futures = {
            executor.submit(_call_model, prompt, model, system): index
            for index, model in enumerate(models)
        }
        for future in as_completed(futures):
            results[futures[future]] = future.result()
    return [result for result in results if result is not None]


def _call_model(prompt: str, config: dict[str, Any], system: str) -> dict[str, Any]:
    name = str(config.get("name") or config.get("model") or "unknown")
    api_key = str(config.get("api_key") or "").strip()
    base_url = str(config.get("base_url") or "").strip()
    model_name = str(config.get("model") or "")
    base = {
        "name": name, "model": model_name, "response": "", "latency_ms": 0,
        "usage": None, "cost_usd": None, "cost_status": "usage_unavailable",
        "evidence": _evidence_metrics(""), "error": "",
    }
    if not api_key or not model_name:
        return {**base, "error": "未配置API Key或模型名"}

    kwargs: dict[str, Any] = {
        "model": model_name, "api_key": api_key,
        "temperature": 0.3, "max_tokens": 2048, "timeout": 60,
    }
    if base_url:
        kwargs["base_url"] = base_url

    start = time.perf_counter()
    try:
        response = ChatOpenAI(**kwargs).invoke([
            SystemMessage(content=system), HumanMessage(content=prompt),
        ])
        text = str(response.content or "")
        usage = _extract_usage(response)
        cost, cost_status = _calculate_cost(usage, config)
        return {
            **base,
            "response": text,
            "latency_ms": int((time.perf_counter() - start) * 1000),
            "usage": usage,
            "cost_usd": cost,
            "cost_status": cost_status,
            "evidence": _evidence_metrics(text),
        }
    except Exception as e:
        return {
            **base,
            "latency_ms": int((time.perf_counter() - start) * 1000),
            "error": str(e)[:200],
        }


def _extract_usage(response: Any) -> dict[str, int] | None:
    usage = getattr(response, "usage_metadata", None) or {}
    token_usage = (getattr(response, "response_metadata", None) or {}).get("token_usage", {})
    input_tokens = usage.get("input_tokens", token_usage.get("prompt_tokens"))
    output_tokens = usage.get("output_tokens", token_usage.get("completion_tokens"))
    total_tokens = usage.get("total_tokens", token_usage.get("total_tokens"))
    if input_tokens is None and output_tokens is None and total_tokens is None:
        return None
    return {
        "input_tokens": int(input_tokens or 0),
        "output_tokens": int(output_tokens or 0),
        "total_tokens": int(total_tokens or (input_tokens or 0) + (output_tokens or 0)),
    }


def _calculate_cost(usage: dict[str, int] | None, config: dict[str, Any]) -> tuple[float | None, str]:
    if usage is None:
        return None, "usage_unavailable"
    try:
        input_rate = float(config["input_cost_per_million"])
        output_rate = float(config["output_cost_per_million"])
    except (KeyError, TypeError, ValueError):
        return None, "pricing_not_configured"
    cost = (
        usage["input_tokens"] * input_rate
        + usage["output_tokens"] * output_rate
    ) / 1_000_000
    return round(cost, 8), "calculated"


def _evidence_metrics(text: str) -> dict[str, Any]:
    citations = len(set(re.findall(r"https?://[^\s)\]]+", text)))
    numeric_claims = len(re.findall(r"(?<!\w)[+-]?\d+(?:\.\d+)?%?", text))
    score = min(100, round(citations / numeric_claims * 100)) if numeric_claims else None
    return {
        "citation_count": citations,
        "numeric_claim_count": numeric_claims,
        "completeness_score": score,
        "status": "scored" if numeric_claims else "not_applicable",
        "method": "启发式：引用链接数/数值主张数；不验证来源真实性",
    }
