"""LLM 客户端：基于 LangChain 的 ChatOpenAI，OpenAI 兼容协议。

用户配置的 provider/base_url/api_key/model 从这里生效。
无 api_key 时降级为本地模拟输出（用于开发调试和演示）。

支持任意 OpenAI 兼容端点：DeepSeek、OpenAI、通义千问、Moonshot、
Ollama(本地)、vLLM 等。
"""
from __future__ import annotations

import json
import time
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from .config import get_config


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
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
        return f"[LLM调用失败: {last_err}]"

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
