"""LLM 客户端：基于 LangChain 的 ChatOpenAI，OpenAI 兼容协议。

用户配置的 provider/base_url/api_key/model 从这里生效。
无 api_key 时降级为本地模拟输出（用于开发调试和演示）。

支持任意 OpenAI 兼容端点：DeepSeek、OpenAI、通义千问、Moonshot、
Ollama(本地)、vLLM 等。
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from .config import get_config

logger = logging.getLogger(__name__)


def friendly_llm_error(error: Exception) -> str:
    """把供应商原始错误转换为可直接展示给用户的提示。"""
    text = str(error).lower()
    if '401' in text or 'authentication' in text or 'api key' in text or 'invalid_request_error' in text:
        return '模型服务认证失败，请到个人中心 → 模型配置检查 API Key 和接口地址。'
    if '403' in text or 'permission' in text or 'forbidden' in text:
        return '模型服务拒绝了当前请求，请检查账号权限、模型权限或接口配置。'
    if '429' in text or 'rate limit' in text or 'too many requests' in text:
        return '模型服务当前请求过多，请稍后再试。'
    if 'timeout' in text or 'timed out' in text or 'time out' in text:
        return '模型服务响应超时，请稍后重试；如果持续出现，请检查接口地址。'
    return '模型服务暂时不可用，请检查个人中心的模型配置后重试。'


class LLMClient:
    def __init__(self, config: dict[str, Any] | None = None, user_id: int | None = None):
        """初始化LLM客户端。

        优先用传入的config，其次用per-user配置（如果user_id给定），
        最后用全局默认配置。
        """
        if config:
            self.config = config
        elif user_id is not None:
            # 从per-user存储读取（key已解密）
            from .auth import get_effective_llm_config
            self.config = get_effective_llm_config(user_id)
        else:
            self.config = get_config()

    def _build_model(self) -> ChatOpenAI | None:
        api_key = (self.config.get("api_key") or "").strip()
        if not api_key:
            return None
        base_url = (self.config.get("base_url") or "").strip()
        kwargs: dict[str, Any] = {
            "model": self.config.get("model", "deepseek-chat"),
            "api_key": api_key,
            "temperature": float(self.config.get("temperature", 0.3)),
            "max_tokens": int(self.config.get("max_tokens", 4096)),
            "timeout": 120,
        }
        if base_url:
            kwargs["base_url"] = base_url
        return ChatOpenAI(**kwargs)

    def chat(self, system: str, user: str, temperature: float | None = None) -> str:
        """调用 LLM 返回文本；无 api_key 时返回模拟输出。

        网络类异常自动重试（最多 3 次，指数退避），全部失败才返回错误占位。
        """
        model = self._build_model()
        if model is None:
            return self._mock(system, user)
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                resp = model.invoke(
                    [SystemMessage(content=system), HumanMessage(content=user)]
                )
                return resp.content or ""
            except Exception as e:
                last_err = e
                logger.warning(
                    "LLM call failed provider=%s model=%s attempt=%s error_type=%s",
                    self.config.get("provider", "unknown"),
                    self.config.get("model", "unknown"),
                    attempt + 1,
                    type(e).__name__,
                )
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
        return f"[LLM调用失败: {friendly_llm_error(last_err or RuntimeError('unknown'))}]"

    def chat_json(self, system: str, user: str) -> dict[str, Any]:
        """调用 LLM 并解析 JSON 输出；解析失败自动追问一次。"""
        text = self.chat(system, user)
        data = self._parse_json(text)
        if "error" not in data:
            return data
        # JSON 解析失败：把原始输出回传给模型要求修正（一次机会）
        retry = self.chat(
            system + " 你只能输出一个合法的 JSON 对象，不要有任何其他文字。",
            f"你之前的输出不是合法JSON：\n{text[:800]}\n\n请重新输出正确的JSON。",
        )
        return self._parse_json(retry)

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        """容错解析：剥离 markdown 代码块后解析 JSON。"""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            start, end = cleaned.find("{"), cleaned.rfind("}")
            if start != -1 and end != -1:
                try:
                    return json.loads(cleaned[start : end + 1])
                except json.JSONDecodeError:
                    pass
            return {"error": "无法解析JSON", "raw": text[:500]}

    def _mock(self, system: str, user: str) -> str:
        """无 API key 时的模拟输出，保证流水线可跑通。"""
        return json.dumps(
            {
                "summary": "（模拟输出：未配置 API Key，此为占位结论）",
                "score": 0,
                "evidence": ["未配置 LLM API Key，请在前端设置页填写"],
                "risk_points": ["演示模式无实际分析"],
            },
            ensure_ascii=False,
        )
