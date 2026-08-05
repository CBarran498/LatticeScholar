import json
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from latticescholar.config import Settings
from latticescholar.db import Database
from latticescholar.main import create_app
from latticescholar.models import (
    DiscussionPoint,
    LibraryItem,
    ResearchDiscussionRequest,
    ResearchDiscussionResponse,
    SearchStrategyRequest,
    SearchStrategyResponse,
)
from latticescholar.services.llm import LLMService, LLMUnavailable
from latticescholar.services.research_assistant import (
    ResearchAssistantService,
    evidence_context,
)


class DeepSeekResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload


class DeepSeekClient:
    responses = []
    requests = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, url, **kwargs):
        self.__class__.requests.append((url, kwargs, self.kwargs))
        return self.__class__.responses.pop(0)


def deepseek_settings(**values):
    defaults = dict(
        llm_provider="deepseek",
        deepseek_api_key="secret-key",
        deepseek_base_url="https://api.deepseek.com",
        allow_remote_llm=True,
        deepseek_max_retries=1,
    )
    defaults.update(values)
    return Settings(**defaults)


@pytest.mark.asyncio
async def test_deepseek_routes_tasks_sends_safe_protocol_and_records_cache(monkeypatch):
    payload = {
        "model": "deepseek-v4-pro",
        "choices": [{"finish_reason": "stop", "message": {"content": '{"answer":"中文结论"}'}}],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "prompt_cache_hit_tokens": 80,
            "prompt_cache_miss_tokens": 20,
            "completion_tokens_details": {"reasoning_tokens": 12},
        },
    }
    DeepSeekClient.responses = [DeepSeekResponse(payload)]
    DeepSeekClient.requests = []
    monkeypatch.setattr("latticescholar.services.llm.httpx.AsyncClient", DeepSeekClient)
    service = LLMService(deepseek_settings())

    result, usage = await service.json_completion(
        "必须返回 JSON", "论文公开内容", task="paper_analysis", user_id="user@example.edu"
    )

    assert result == {"answer": "中文结论"}
    assert usage["model"] == "deepseek-v4-pro"
    assert usage["input_tokens"] == 100 and usage["cache_hit_tokens"] == 80
    assert usage["reasoning_tokens"] == 12 and usage["task"] == "paper_analysis"
    url, request, client_options = DeepSeekClient.requests[0]
    assert url == "https://api.deepseek.com/chat/completions"
    assert request["headers"]["Authorization"] == "Bearer secret-key"
    assert request["json"]["response_format"] == {"type": "json_object"}
    assert request["json"]["thinking"] == {"type": "enabled"}
    assert request["json"]["user_id"] == "user_example_edu"
    assert "temperature" not in request["json"]
    assert client_options["timeout"].read == 180


@pytest.mark.asyncio
async def test_deepseek_flash_retry_connection_test_and_failures(monkeypatch):
    empty = {"choices": [{"finish_reason": "stop", "message": {"content": ""}}]}
    ok = {
        "model": "deepseek-v4-flash",
        "choices": [{"finish_reason": "stop", "message": {"content": '{"status":"ok","message":"连接成功"}'}}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 4},
    }
    DeepSeekClient.responses = [DeepSeekResponse(empty), DeepSeekResponse(ok)]
    DeepSeekClient.requests = []
    monkeypatch.setattr("latticescholar.services.llm.httpx.AsyncClient", DeepSeekClient)
    monkeypatch.setattr("latticescholar.services.llm.asyncio.sleep", AsyncMock())
    service = LLMService(deepseek_settings())

    result = await service.test_connection("lattice_u_1")
    assert result["ok"] is True
    assert len(DeepSeekClient.requests) == 2
    assert DeepSeekClient.requests[-1][1]["json"]["model"] == "deepseek-v4-flash"
    assert DeepSeekClient.requests[-1][1]["json"]["temperature"] == 0.2

    for code, expected in [(400, "参数"), (401, "Key"), (402, "余额"), (422, "处理"), (429, "频繁"), (503, "暂时")]:
        assert expected in str(LLMService._deepseek_http_error(code))
    assert "HTTP 418" in str(LLMService._deepseek_http_error(418))

    no_key = LLMService(deepseek_settings(deepseek_api_key=""))
    with pytest.raises(LLMUnavailable, match="Key"):
        await no_key.json_completion("JSON", "test")
    blocked = LLMService(deepseek_settings(allow_remote_llm=False))
    with pytest.raises(LLMUnavailable, match="blocked"):
        await blocked.json_completion("JSON", "test")


class ResearchLLM:
    enabled = True

    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    async def json_completion(self, system, user, **kwargs):
        self.calls.append((system, json.loads(user), kwargs))
        return self.responses[kwargs["task"]], {
            "provider": "deepseek",
            "model": "deepseek-v4-pro",
            "input_tokens": 20,
            "output_tokens": 10,
        }


def evidence_item():
    return LibraryItem(
        id=9,
        kind="paper",
        external_id="10.1/demo",
        title="可信临床模型",
        payload={
            "abstract": "研究在两个公开中心验证了校准方法。",
            "key_questions": [{"answer": "外部验证仍然不足。"}],
        },
        note="需要核对样本表",
        project_id=1,
        created_at="2026-08-04T00:00:00+00:00",
    )


@pytest.mark.asyncio
async def test_research_assistant_builds_bilingual_strategy_and_grounded_discussion():
    llm = ResearchLLM(
        {
            "query_strategy": {
                "chinese_query": "低资源 AND 临床决策",
                "english_query": '("resource-efficient" OR lightweight) AND "clinical decision"',
                "chinese_keywords": ["低资源", "临床决策"],
                "english_keywords": ["resource-efficient", "clinical decision"],
                "exclusions": ["纯综述"],
                "explanation": ["保留资源约束与应用场景两个概念组。"],
            },
            "research_discussion": {
                "answer": "当前证据只能支持初步可行性，尚不足以证明跨机构泛化。",
                "points": [
                    {"title": "已支持", "detail": "两个公开中心提供了初步校准证据。"},
                    {"title": "仍缺失", "detail": "缺少独立机构和前瞻性外部验证。"},
                    {"title": "判断边界", "detail": "不能将题录或模型建议当作创新性证明。"},
                ],
                "evidence_refs": ["E9", "E999"],
                "uncertainties": ["样本构成是否一致仍需回看原文。"],
                "next_actions": ["本周补检三篇独立外部验证研究并记录 DOI。"],
            },
        }
    )
    service = ResearchAssistantService(llm)
    strategy = await service.search_strategy(
        SearchStrategyRequest(query="低资源临床决策", field="医学人工智能", project_id=1),
        {"name": "可信医学AI", "research_question": "如何验证跨机构泛化？"},
        "lattice_u_1",
    )
    assert "resource-efficient" in strategy.english_query
    assert llm.calls[0][2]["task"] == "query_strategy"

    item = evidence_item()
    context = evidence_context([item])
    assert context[0]["reference"] == "E9" and "外部验证" in context[0]["content"]
    result = await service.discuss(
        ResearchDiscussionRequest(project_id=1, question="这些证据足以支持跨机构泛化结论吗？"),
        {"name": "可信医学AI", "research_question": "如何验证跨机构泛化？", "description": "公开数据研究"},
        [item],
        [{"id": "p1", "title": "科研数据政策"}],
        "lattice_u_1",
    )
    assert result.evidence_refs == ["E9"]
    assert len(result.points) == 3 and result.next_actions
    sent = llm.calls[-1][1]
    assert sent["evidence"][0]["reference"] == "E9"
    assert sent["policies"][0]["id"] == "p1"


def test_llm_usage_metadata_is_aggregated_without_content(tmp_path):
    db = Database(tmp_path / "usage.db")
    db.record_llm_run(7, {})
    db.record_llm_run(
        7,
        {
            "provider": "deepseek",
            "model": "deepseek-v4-pro",
            "task": "paper_analysis",
            "input_tokens": 100,
            "output_tokens": 20,
            "cache_hit_tokens": 60,
            "cache_miss_tokens": 40,
            "reasoning_tokens": 15,
            "latency_ms": 900,
            "paper_text": "不得写入数据库",
        },
    )
    summary = db.llm_usage_summary(7)
    assert summary["calls"] == 1
    assert summary["input_tokens"] == 100 and summary["cache_hit_tokens"] == 60
    assert summary["average_latency_ms"] == 900
    assert "paper_text" not in summary["recent"][0]


def test_model_center_and_research_assistant_api_paths(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, llm_provider="none", auth_mode="open"))
    with TestClient(app) as client:
        app.state.research_assistant.search_strategy = AsyncMock(
            return_value=SearchStrategyResponse(
                chinese_query="可信 AI",
                english_query="trustworthy AI",
                english_keywords=["trustworthy AI"],
                usage={
                    "provider": "deepseek",
                    "model": "deepseek-v4-flash",
                    "input_tokens": 4,
                },
            )
        )
        app.state.research_assistant.discuss = AsyncMock(
            return_value=ResearchDiscussionResponse(
                answer="当前证据支持有限，需要继续补充外部验证。",
                points=[DiscussionPoint(title="证据边界", detail="只有公开数据结果。")],
                next_actions=["补检外部验证论文。"],
                usage={"provider": "deepseek", "model": "deepseek-v4-pro", "output_tokens": 8},
            )
        )
        status = client.get("/api/llm/status")
        assert status.status_code == 200 and status.json()["usage"]["calls"] == 0
        project = client.post(
            "/api/projects",
            json={"name": "可信AI课题", "research_question": "如何开展外部验证？"},
        ).json()
        strategy = client.post(
            "/api/search/strategy",
            json={"query": "可信人工智能", "project_id": project["id"]},
        )
        assert strategy.status_code == 200 and strategy.json()["english_query"] == "trustworthy AI"
        discussion = client.post(
            "/api/discussions",
            json={"project_id": project["id"], "question": "当前证据是否足以支撑外部验证结论？"},
        )
        assert discussion.status_code == 200
        assert client.get("/api/llm/status").json()["usage"]["calls"] == 2
        assert client.post("/api/llm/test", json={}).status_code == 409
        assert client.post(
            "/api/discussions",
            json={"project_id": 999, "question": "这个不存在的项目可以讨论吗？"},
        ).status_code == 404
