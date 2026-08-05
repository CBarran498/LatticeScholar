import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from latticescholar.config import Settings
from latticescholar.db import Database
from latticescholar.main import create_app
from latticescholar.services.llm import LLMService, LLMUnavailable
from latticescholar.services.provider_vault import ProviderVault, ProviderVaultError
from latticescholar.services.providers import PROVIDERS, endpoint_for, provider_definition


def make_vault(tmp_path: Path, **settings) -> ProviderVault:
    config = Settings(data_dir=tmp_path, **settings)
    return ProviderVault(config, Database(config.database_path))


def test_provider_registry_and_endpoints():
    assert {"deepseek", "qwen", "glm", "openai", "anthropic", "gemini"} <= set(PROVIDERS)
    assert provider_definition("openai").public()["quality_model"] == "gpt-5.6-sol"
    assert "official_hosts" not in provider_definition("openai").public()
    assert endpoint_for("https://api.openai.com/v1", "openai_chat").endswith(
        "/v1/chat/completions"
    )
    assert endpoint_for("https://api.anthropic.com/v1/messages", "anthropic_messages").endswith(
        "/v1/messages"
    )
    assert endpoint_for("https://api.cohere.com/v2", "cohere_chat").endswith("/v2/chat")
    with pytest.raises(ValueError, match="不支持"):
        provider_definition("missing")


def test_encrypted_provider_vault_lifecycle_and_routing(tmp_path, monkeypatch):
    monkeypatch.setattr(ProviderVault, "_reject_private_resolution", staticmethod(lambda *_: None))
    vault = make_vault(tmp_path)
    saved = vault.save(
        7,
        "deepseek",
        api_key="sk-super-secret",
        fast_model="fast-one",
        quality_model="quality-one",
        priority=5,
    )
    assert saved["configured"] and saved["key_hint"] == "••••cret"
    assert "super-secret" not in json.dumps(saved, ensure_ascii=False)
    row = vault.db.get_provider_credential(7, "deepseek")
    assert "super-secret" not in row["encrypted_api_key"]
    assert vault.resolved(7, "deepseek")["api_key"] == "sk-super-secret"
    assert vault.available(7) and not vault.available(8)
    assert vault.security_status()["key_source"] == "local-file"
    assert (tmp_path / "credential.key").exists()

    vault.save(7, "openai", api_key="openai-secret", priority=20)
    routing = vault.save_routing(7, "economy", "deepseek", True)
    assert routing["mode"] == "economy" and routing["primary_provider"] == "deepseek"
    candidates = vault.candidates(7, "paper_analysis")
    assert candidates[0]["provider_id"] == "deepseek"
    assert candidates[0]["model"] == "fast-one"
    vault.save_routing(7, "quality", "openai", False)
    candidates = vault.candidates(7, "paper_analysis")
    assert len(candidates) == 1 and candidates[0]["provider_id"] == "openai"
    assert candidates[0]["model"] == provider_definition("openai").quality_model

    unchanged = vault.save(7, "openai", api_key="", fast_model="fast-updated")
    assert unchanged["fast_model"] == "fast-updated"
    assert vault.delete(7, "openai")
    assert vault.routing(7)["primary_provider"] == ""
    assert not vault.delete(7, "openai")
    with pytest.raises(ProviderVaultError, match="尚未启用"):
        vault.resolved(7, "openai")


def test_provider_vault_validation_and_environment_key(tmp_path, monkeypatch):
    monkeypatch.setattr(ProviderVault, "_reject_private_resolution", staticmethod(lambda *_: None))
    vault = make_vault(tmp_path, credential_encryption_key="deployment-secret")
    assert vault.security_status()["key_source"] == "environment"
    with pytest.raises(ProviderVaultError, match="请输入"):
        vault.save(0, "openai", api_key="")
    with pytest.raises(ProviderVaultError, match="HTTPS"):
        vault.validate_base_url("openai", "http://api.openai.com/v1")
    with pytest.raises(ProviderVaultError, match="官方"):
        vault.validate_base_url("openai", "https://example.com/v1")
    with pytest.raises(ProviderVaultError, match="默认关闭"):
        vault.validate_base_url("custom", "https://models.example.edu/v1")
    assert vault.validate_base_url("custom", "http://localhost:11434/v1").startswith("http")
    with pytest.raises(ProviderVaultError, match="路由模式"):
        vault.save_routing(0, "turbo", "", True)
    with pytest.raises(ProviderVaultError, match="尚未配置"):
        vault.save_routing(0, "balanced", "openai", True)


class MockResponse:
    def __init__(self, payload=None, status_code=200):
        self.payload = payload or {}
        self.status_code = status_code

    def json(self):
        return self.payload


class MockClient:
    responses = []
    requests = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, url, **kwargs):
        self.__class__.requests.append((url, kwargs))
        return self.__class__.responses.pop(0)


@pytest.mark.asyncio
async def test_native_anthropic_cohere_and_openai_adapters(tmp_path, monkeypatch):
    monkeypatch.setattr(ProviderVault, "_reject_private_resolution", staticmethod(lambda *_: None))
    monkeypatch.setattr("latticescholar.services.llm.httpx.AsyncClient", MockClient)
    vault = make_vault(tmp_path)
    for provider in ("anthropic", "cohere", "openai"):
        vault.save(1, provider, api_key=f"{provider}-key")
    service = LLMService(Settings(data_dir=tmp_path), vault)

    MockClient.responses = [
        MockResponse(
            {
                "model": "claude-sonnet-5",
                "content": [{"type": "text", "text": '{"answer":"中文"}'}],
                "usage": {"input_tokens": 8, "output_tokens": 4, "cache_read_input_tokens": 2},
            }
        )
    ]
    value, usage = await service.json_completion(
        "返回JSON", "论文", owner_id=1, provider_id="anthropic", task="paper_analysis"
    )
    assert value["answer"] == "中文" and usage["provider"] == "anthropic"
    assert MockClient.requests[-1][1]["headers"]["x-api-key"] == "anthropic-key"

    MockClient.responses = [
        MockResponse(
            {
                "message": {"content": [{"type": "text", "text": '{"status":"ok"}'}]},
                "usage": {"billed_units": {"input_tokens": 3, "output_tokens": 2}},
            }
        )
    ]
    value, usage = await service.json_completion(
        "返回JSON", "测试", owner_id=1, provider_id="cohere"
    )
    assert value["status"] == "ok" and usage["output_tokens"] == 2

    MockClient.responses = [
        MockResponse(
            {
                "model": "gpt-5.6-sol",
                "choices": [{"finish_reason": "stop", "message": {"content": '{"ok":true}'}}],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "prompt_tokens_details": {"cached_tokens": 4},
                    "completion_tokens_details": {"reasoning_tokens": 3},
                },
            }
        )
    ]
    value, usage = await service.json_completion(
        "返回JSON", "测试", owner_id=1, provider_id="openai", task="paper_analysis"
    )
    assert value["ok"] is True and usage["reasoning_tokens"] == 3
    body = MockClient.requests[-1][1]["json"]
    assert "max_completion_tokens" in body and "max_tokens" not in body


@pytest.mark.asyncio
async def test_provider_failover_and_http_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(ProviderVault, "_reject_private_resolution", staticmethod(lambda *_: None))
    monkeypatch.setattr("latticescholar.services.llm.httpx.AsyncClient", MockClient)
    vault = make_vault(tmp_path)
    vault.save(2, "openai", api_key="one", priority=1)
    vault.save(2, "gemini", api_key="two", priority=2)
    service = LLMService(Settings(data_dir=tmp_path), vault)
    MockClient.responses = [
        MockResponse(status_code=503),
        MockResponse(
            {
                "choices": [{"finish_reason": "stop", "message": {"content": '{"ok":true}'}}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 1},
            }
        ),
    ]
    value, usage = await service.json_completion("JSON", "内容", owner_id=2)
    assert value["ok"] and usage["provider"] == "gemini" and usage["fallback_used"]

    for code, text in [(401, "Key"), (402, "余额"), (418, "HTTP 418")]:
        MockClient.responses = [MockResponse(status_code=code)]
        with pytest.raises(LLMUnavailable, match=text):
            await service.json_completion("JSON", "内容", owner_id=2, provider_id="openai")


def test_model_provider_api_never_returns_plaintext(tmp_path, monkeypatch):
    monkeypatch.setattr(ProviderVault, "_reject_private_resolution", staticmethod(lambda *_: None))
    app = create_app(Settings(data_dir=tmp_path, llm_provider="none", auth_mode="open"))
    with TestClient(app) as client:
        initial = client.get("/api/model-providers").json()
        assert len(initial["providers"]) >= 15
        saved = client.put(
            "/api/model-providers/deepseek",
            json={"api_key": "never-return-this", "fast_model": "fast", "quality_model": "pro"},
        )
        assert saved.status_code == 200
        assert "never-return-this" not in saved.text
        status = client.get("/api/llm/status").json()
        assert status["active_count"] == 1 and "never-return-this" not in json.dumps(status)
        routing = client.put(
            "/api/model-routing",
            json={"mode": "quality", "primary_provider": "deepseek", "fallback_enabled": False},
        )
        assert routing.status_code == 200 and routing.json()["mode"] == "quality"
        assert client.put(
            "/api/model-providers/unknown", json={"api_key": "x"}
        ).status_code == 422
        assert client.delete("/api/model-providers/deepseek").json()["deleted"] is True
