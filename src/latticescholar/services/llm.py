from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx

from ..config import Settings
from .provider_vault import ProviderVault
from .providers import endpoint_for, provider_definition


class LLMUnavailable(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


DEEPSEEK_REASONING_TASKS = {"paper_analysis", "idea", "research_discussion"}


class LLMService:
    def __init__(self, config: Settings, vault: Optional[ProviderVault] = None):
        self.config = config
        self.vault = vault

    @property
    def enabled(self) -> bool:
        return self.config.llm_provider in {"ollama", "openai_compatible", "deepseek"}

    def available(self, owner_id: int = 0) -> bool:
        return bool((self.vault and self.vault.available(owner_id)) or self.enabled)

    @property
    def api_key_configured(self) -> bool:
        if self.config.llm_provider == "deepseek":
            return bool(self.config.deepseek_api_key or self.config.llm_api_key)
        if self.config.llm_provider == "openai_compatible":
            return bool(self.config.llm_api_key)
        return self.config.llm_provider == "ollama"

    def _base_url(self) -> str:
        return (
            self.config.deepseek_base_url
            if self.config.llm_provider == "deepseek"
            else self.config.llm_base_url
        )

    def _remote_allowed(self) -> bool:
        host = (urlparse(self._base_url()).hostname or "").lower()
        is_local = host in {"127.0.0.1", "localhost", "::1", "host.docker.internal"}
        return is_local or self.config.allow_remote_llm

    def model_for_task(self, task: str = "general") -> str:
        if self.config.llm_provider != "deepseek":
            return self.config.llm_model
        routing = self.config.deepseek_routing
        if routing == "quality":
            return self.config.deepseek_reasoning_model
        if routing == "economy":
            return self.config.deepseek_fast_model
        return (
            self.config.deepseek_reasoning_model
            if task in DEEPSEEK_REASONING_TASKS
            else self.config.deepseek_fast_model
        )

    def thinking_for_task(self, task: str, model: str) -> str:
        configured = self.config.deepseek_thinking
        if configured in {"enabled", "disabled"}:
            return configured
        if task in DEEPSEEK_REASONING_TASKS:
            return "enabled"
        return "disabled"

    def status(self, owner_id: int = 0) -> Dict[str, Any]:
        providers = self.vault.list_public(owner_id) if self.vault else []
        configured = [item for item in providers if item["configured"]]
        active = [item for item in configured if item["enabled"]]
        routing = self.vault.routing(owner_id) if self.vault else None
        return {
            "enabled": self.available(owner_id),
            "provider": active[0]["id"] if len(active) == 1 else (
                "smart-router" if active else self.config.llm_provider
            ),
            "api_key_configured": bool(configured) or self.api_key_configured,
            "remote_allowed": bool(active) or (self._remote_allowed() if self.enabled else False),
            "routing": routing["mode"] if routing else (
                self.config.deepseek_routing if self.config.llm_provider == "deepseek" else "single_model"
            ),
            "fast_model": self.model_for_task("query_strategy") if self.enabled else None,
            "reasoning_model": self.model_for_task("paper_analysis") if self.enabled else None,
            "thinking": self.config.deepseek_thinking
            if self.config.llm_provider == "deepseek"
            else None,
            "reasoning_effort": self.config.deepseek_reasoning_effort
            if self.config.llm_provider == "deepseek"
            else None,
            "configured_count": len(configured),
            "active_count": len(active),
            "providers": providers,
            "routing_settings": routing,
            "security": self.vault.security_status() if self.vault else {
                "encrypted_at_rest": False,
                "key_source": "environment",
                "plaintext_returned": False,
            },
        }

    async def json_completion(
        self,
        system: str,
        user: str,
        *,
        task: str = "general",
        user_id: Optional[str] = None,
        owner_id: int = 0,
        provider_id: str = "",
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        candidates = (
            self.vault.candidates(owner_id, task, provider_id)
            if self.vault and self.vault.available(owner_id)
            else []
        )
        if candidates:
            user = user[: self.config.llm_max_input_chars]
            started = time.perf_counter()
            errors: List[str] = []
            for index, candidate in enumerate(candidates):
                try:
                    content, usage = await self._provider_completion(
                        candidate, system, user, task, user_id
                    )
                except LLMUnavailable as exc:
                    errors.append(f"{provider_definition(candidate['provider_id']).name}：{exc}")
                    if not exc.retryable or index + 1 >= len(candidates):
                        raise LLMUnavailable("；".join(errors)) from exc
                    continue
                usage.update(
                    {
                        "task": task,
                        "latency_ms": int((time.perf_counter() - started) * 1000),
                        "source_chars": len(user),
                        "route_position": index + 1,
                        "fallback_used": index > 0,
                        "routing_mode": candidate.get("routing_mode", "balanced"),
                    }
                )
                return self._parse_json(content), usage
        if not self.enabled:
            raise LLMUnavailable("尚未配置可用的模型服务")
        if not self._remote_allowed():
            raise LLMUnavailable(
                "远程模型默认关闭（blocked）；阅读隐私说明后设置 LATTICE_ALLOW_REMOTE_LLM=true"
            )
        if self.config.llm_provider == "deepseek" and not self.api_key_configured:
            raise LLMUnavailable("DeepSeek API Key 尚未配置")
        user = user[: self.config.llm_max_input_chars]
        started = time.perf_counter()
        if self.config.llm_provider == "deepseek":
            content, usage = await self._deepseek_completion(system, user, task, user_id)
        elif self.config.llm_provider == "ollama":
            content, usage = await self._ollama_completion(system, user)
        else:
            content, usage = await self._openai_compatible_completion(system, user)
        usage.update(
            {
                "task": task,
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "source_chars": len(user),
            }
        )
        return self._parse_json(content), usage

    async def _provider_completion(
        self,
        candidate: Dict[str, Any],
        system: str,
        user: str,
        task: str,
        user_id: Optional[str],
    ) -> tuple[str, Dict[str, Any]]:
        protocol = candidate["protocol"]
        if protocol == "anthropic_messages":
            return await self._anthropic_completion(candidate, system, user)
        if protocol == "cohere_chat":
            return await self._cohere_completion(candidate, system, user)
        return await self._openai_provider_completion(candidate, system, user, task, user_id)

    async def _openai_provider_completion(
        self,
        candidate: Dict[str, Any],
        system: str,
        user: str,
        task: str,
        user_id: Optional[str],
    ) -> tuple[str, Dict[str, Any]]:
        provider_id = candidate["provider_id"]
        body: Dict[str, Any] = {
            "model": candidate["model"],
            "stream": False,
            "max_tokens": self.config.llm_max_output_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if provider_id in {"openai", "xai"}:
            body["max_completion_tokens"] = body.pop("max_tokens")
        if provider_id == "deepseek":
            thinking = "enabled" if task in DEEPSEEK_REASONING_TASKS else "disabled"
            body["thinking"] = {"type": thinking}
            body["reasoning_effort"] = "high"
            if thinking == "disabled":
                body["temperature"] = 0.2
        else:
            body["temperature"] = 0.2
        safe_user_id = re.sub(r"[^a-zA-Z0-9_-]", "_", user_id or "")[:512]
        if safe_user_id and provider_id in {"deepseek", "openai", "qianfan"}:
            body["user"] = safe_user_id
        response = await self._post_json(
            endpoint_for(candidate["base_url"], "openai_chat"),
            {"Authorization": "Bearer " + candidate["api_key"]},
            body,
            provider_definition(provider_id).name,
        )
        payload = response.json()
        choice = (payload.get("choices") or [{}])[0]
        finish_reason = choice.get("finish_reason")
        if finish_reason in {"length", "max_tokens"}:
            raise LLMUnavailable("输出达到长度上限，结构化结果可能不完整")
        content = (choice.get("message") or {}).get("content") or ""
        if isinstance(content, list):
            content = "".join(str(item.get("text") or "") for item in content if isinstance(item, dict))
        if not str(content).strip():
            raise LLMUnavailable("模型返回了空内容", retryable=True)
        raw_usage = payload.get("usage") or {}
        details = raw_usage.get("completion_tokens_details") or raw_usage.get("output_tokens_details") or {}
        usage = {
            **raw_usage,
            "provider": provider_id,
            "model": payload.get("model") or candidate["model"],
            "input_tokens": raw_usage.get("prompt_tokens") or raw_usage.get("input_tokens"),
            "output_tokens": raw_usage.get("completion_tokens") or raw_usage.get("output_tokens"),
            "cache_hit_tokens": (raw_usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0),
            "reasoning_tokens": details.get("reasoning_tokens", 0),
        }
        return str(content), usage

    async def _anthropic_completion(
        self, candidate: Dict[str, Any], system: str, user: str
    ) -> tuple[str, Dict[str, Any]]:
        response = await self._post_json(
            endpoint_for(candidate["base_url"], "anthropic_messages"),
            {"x-api-key": candidate["api_key"], "anthropic-version": "2023-06-01"},
            {
                "model": candidate["model"],
                "max_tokens": self.config.llm_max_output_tokens,
                "temperature": 0.2,
                "system": system + "\n最终响应必须是一个 JSON 对象，不要使用 Markdown 代码块。",
                "messages": [{"role": "user", "content": user}],
            },
            "Anthropic Claude",
        )
        payload = response.json()
        content = "".join(
            str(item.get("text") or "")
            for item in payload.get("content") or []
            if isinstance(item, dict) and item.get("type") == "text"
        )
        if not content.strip():
            raise LLMUnavailable("Claude 返回了空内容", retryable=True)
        raw_usage = payload.get("usage") or {}
        return content, {
            **raw_usage,
            "provider": candidate["provider_id"],
            "model": payload.get("model") or candidate["model"],
            "input_tokens": raw_usage.get("input_tokens"),
            "output_tokens": raw_usage.get("output_tokens"),
            "cache_hit_tokens": raw_usage.get("cache_read_input_tokens", 0),
        }

    async def _cohere_completion(
        self, candidate: Dict[str, Any], system: str, user: str
    ) -> tuple[str, Dict[str, Any]]:
        response = await self._post_json(
            endpoint_for(candidate["base_url"], "cohere_chat"),
            {"Authorization": "Bearer " + candidate["api_key"]},
            {
                "model": candidate["model"],
                "temperature": 0.2,
                "max_tokens": self.config.llm_max_output_tokens,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            "Cohere",
        )
        payload = response.json()
        message = payload.get("message") or {}
        content = "".join(
            str(item.get("text") or "")
            for item in message.get("content") or []
            if isinstance(item, dict)
        )
        if not content.strip():
            raise LLMUnavailable("Cohere 返回了空内容", retryable=True)
        billed = ((payload.get("usage") or {}).get("billed_units") or {})
        return content, {
            "provider": candidate["provider_id"],
            "model": candidate["model"],
            "input_tokens": billed.get("input_tokens"),
            "output_tokens": billed.get("output_tokens"),
        }

    async def _post_json(
        self, endpoint: str, headers: Dict[str, str], body: Dict[str, Any], provider_name: str
    ) -> httpx.Response:
        timeout = httpx.Timeout(180.0, connect=8.0)
        safe_headers = {"Content-Type": "application/json", **headers}
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(endpoint, headers=safe_headers, json=body)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise LLMUnavailable(f"{provider_name} 连接超时或网络不可用", retryable=True) from exc
        if response.status_code >= 400:
            if response.status_code in {401, 403}:
                raise LLMUnavailable(f"{provider_name} API Key 无效、权限不足或模型不可用")
            if response.status_code == 402:
                raise LLMUnavailable(f"{provider_name} 账户余额不足")
            if response.status_code in {408, 409, 429, 500, 502, 503, 504}:
                raise LLMUnavailable(
                    f"{provider_name} 暂时不可用（HTTP {response.status_code}）", retryable=True
                )
            raise LLMUnavailable(f"{provider_name} 请求失败（HTTP {response.status_code}）")
        return response

    async def _ollama_completion(self, system: str, user: str) -> tuple[str, Dict[str, Any]]:
        timeout = httpx.Timeout(120.0, connect=8.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                self.config.llm_base_url.rstrip("/") + "/api/chat",
                json={
                    "model": self.config.llm_model,
                    "stream": False,
                    "format": "json",
                    "options": {
                        "temperature": 0.2,
                        "num_predict": self.config.llm_max_output_tokens,
                    },
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
            )
            response.raise_for_status()
            payload = response.json()
        return (payload.get("message") or {}).get("content", ""), {
            "input_tokens": payload.get("prompt_eval_count"),
            "output_tokens": payload.get("eval_count"),
            "provider": "ollama",
            "model": self.config.llm_model,
        }

    async def _openai_compatible_completion(
        self, system: str, user: str
    ) -> tuple[str, Dict[str, Any]]:
        headers = {"Content-Type": "application/json"}
        if self.config.llm_api_key:
            headers["Authorization"] = "Bearer " + self.config.llm_api_key
        base = self.config.llm_base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            endpoint = base
        elif base.endswith("/v1"):
            endpoint = base + "/chat/completions"
        else:
            endpoint = base + "/v1/chat/completions"
        timeout = httpx.Timeout(120.0, connect=8.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                endpoint,
                headers=headers,
                json={
                    "model": self.config.llm_model,
                    "temperature": 0.2,
                    "max_tokens": self.config.llm_max_output_tokens,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
            )
            response.raise_for_status()
            payload = response.json()
        content = ((payload.get("choices") or [{}])[0].get("message") or {}).get("content", "")
        if not content:
            raise LLMUnavailable("模型返回了空内容")
        usage = payload.get("usage") or {}
        usage.update({"provider": "openai_compatible", "model": self.config.llm_model})
        return content, usage

    async def _deepseek_completion(
        self, system: str, user: str, task: str, user_id: Optional[str]
    ) -> tuple[str, Dict[str, Any]]:
        model = self.model_for_task(task)
        thinking = self.thinking_for_task(task, model)
        effort = self.config.deepseek_reasoning_effort
        if model == self.config.deepseek_reasoning_model and effort == "low":
            effort = "high"
        endpoint = self.config.deepseek_base_url.rstrip("/")
        if not endpoint.endswith("/chat/completions"):
            endpoint += "/chat/completions"
        key = self.config.deepseek_api_key or self.config.llm_api_key
        headers = {"Content-Type": "application/json", "Authorization": "Bearer " + key}
        request_body: Dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "max_tokens": self.config.llm_max_output_tokens,
            "response_format": {"type": "json_object"},
            "thinking": {"type": thinking},
            "reasoning_effort": effort,
        }
        if thinking == "disabled":
            request_body["temperature"] = 0.2
        safe_user_id = re.sub(r"[^a-zA-Z0-9_-]", "_", user_id or "")[:512]
        if safe_user_id:
            request_body["user_id"] = safe_user_id
        timeout = httpx.Timeout(self.config.deepseek_timeout_seconds, connect=8.0)
        attempts = max(1, self.config.deepseek_max_retries + 1)
        async with httpx.AsyncClient(timeout=timeout) as client:
            for attempt in range(attempts):
                try:
                    response = await client.post(endpoint, headers=headers, json=request_body)
                except (httpx.TimeoutException, httpx.NetworkError) as exc:
                    if attempt + 1 < attempts:
                        await asyncio.sleep(0.25 * (attempt + 1))
                        continue
                    raise LLMUnavailable("DeepSeek 连接超时或网络不可用") from exc
                if response.status_code in {429, 500, 502, 503, 504} and attempt + 1 < attempts:
                    await asyncio.sleep(0.25 * (attempt + 1))
                    continue
                if response.status_code >= 400:
                    raise self._deepseek_http_error(response.status_code)
                payload = response.json()
                choice = (payload.get("choices") or [{}])[0]
                finish_reason = choice.get("finish_reason")
                if finish_reason == "length":
                    raise LLMUnavailable("DeepSeek 输出达到长度上限，JSON 可能不完整")
                if finish_reason == "content_filter":
                    raise LLMUnavailable("DeepSeek 未返回内容：请求触发内容安全限制")
                if finish_reason == "insufficient_system_resource":
                    if attempt + 1 < attempts:
                        await asyncio.sleep(0.25 * (attempt + 1))
                        continue
                    raise LLMUnavailable("DeepSeek 当前资源不足，请稍后重试")
                content = (choice.get("message") or {}).get("content") or ""
                if not content.strip():
                    if attempt + 1 < attempts:
                        await asyncio.sleep(0.2)
                        continue
                    raise LLMUnavailable("DeepSeek 返回了空内容，请重试或调整提示")
                raw_usage = payload.get("usage") or {}
                details = raw_usage.get("completion_tokens_details") or {}
                usage = {
                    **raw_usage,
                    "input_tokens": raw_usage.get("prompt_tokens"),
                    "output_tokens": raw_usage.get("completion_tokens"),
                    "cache_hit_tokens": raw_usage.get("prompt_cache_hit_tokens", 0),
                    "cache_miss_tokens": raw_usage.get("prompt_cache_miss_tokens", 0),
                    "reasoning_tokens": details.get("reasoning_tokens", 0),
                    "provider": "deepseek",
                    "model": payload.get("model") or model,
                    "thinking": thinking,
                    "reasoning_effort": effort,
                }
                return content, usage
        raise LLMUnavailable("DeepSeek 请求未完成")

    @staticmethod
    def _deepseek_http_error(status_code: int) -> LLMUnavailable:
        messages = {
            400: "DeepSeek 请求参数无效",
            401: "DeepSeek API Key 无效或未授权",
            402: "DeepSeek 账户余额不足",
            422: "DeepSeek 无法处理当前请求",
            429: "DeepSeek 请求过于频繁，请稍后重试",
        }
        if status_code >= 500:
            return LLMUnavailable("DeepSeek 服务暂时不可用")
        return LLMUnavailable(messages.get(status_code, f"DeepSeek 请求失败（HTTP {status_code}）"))

    async def test_connection(
        self, user_id: Optional[str] = None, *, owner_id: int = 0, provider_id: str = ""
    ) -> Dict[str, Any]:
        payload, usage = await self.json_completion(
            "你是连接测试程序。只返回 JSON：{\"status\":\"ok\",\"message\":\"连接成功\"}。",
            "请执行一次最小连接测试并返回 JSON。",
            task="connection_test",
            user_id=user_id,
            owner_id=owner_id,
            provider_id=provider_id,
        )
        return {"ok": payload.get("status") == "ok", "message": payload.get("message", ""), "usage": usage}

    @staticmethod
    def _parse_json(content: str) -> Dict[str, Any]:
        clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.I)
        try:
            value = json.loads(clean)
        except json.JSONDecodeError as exc:
            match = re.search(r"\{.*\}", clean, flags=re.S)
            if not match:
                raise LLMUnavailable("模型没有返回有效 JSON") from exc
            value = json.loads(match.group(0))
        if not isinstance(value, dict):
            raise LLMUnavailable("模型响应必须是 JSON 对象")
        return value
