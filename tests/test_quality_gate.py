import hashlib
import hmac
import json
import sys
import time

import httpx
import pytest

from latticescholar.config import Settings, _env_bool
from latticescholar.db import Database
from latticescholar.models import (
    AnalyzeRequest,
    ExportRequest,
    IdeaCandidate,
    IdeaRequest,
    Paper,
    PaperAnalysis,
    Policy,
    SearchRequest,
)
from latticescholar.services.accounts import (
    AccountService,
    AuthenticationError,
    _parse_time,
    load_or_create_session_secret,
)
from latticescholar.services.analyzer import AnalyzerService, _select_evidence_window
from latticescholar.services.exporter import export_bibtex, export_markdown, export_ris
from latticescholar.services.ideas import IdeaService
from latticescholar.services.literature import LiteratureService
from latticescholar.services.llm import LLMService, LLMUnavailable
from latticescholar.services.policies import PolicyService
from latticescholar.services.policy_sync import PolicySyncService
from latticescholar.services.updates import UpdateService, _github_repository, _version_tuple


class FakeCompletionLLM:
    enabled = True

    def __init__(self, payload, max_chars=12000):
        self.payload = payload
        self.config = Settings(llm_provider="ollama", llm_max_input_chars=max_chars)

    async def json_completion(self, system, user, **kwargs):
        assert len(user) <= self.config.llm_max_input_chars + 200
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload, {"input_tokens": 20, "output_tokens": 30}


@pytest.mark.asyncio
async def test_analyzer_llm_success_long_selection_and_non_chinese_fallback():
    payload = {
        "core_problem": "现有模型在外部数据上的泛化能力不足。",
        "methods": ["作者采用多中心数据并比较三个基线。"],
        "innovations": ["创新点是引入跨中心校准步骤。"],
        "findings": ["结果显示校准误差下降，但仍需复核表格。"],
        "limitations": ["原文未披露独立前瞻性验证。"],
        "evidence": [{"claim": "结果证据", "quote": "Results improved.", "location": "第 4 页"}],
        "confidence": "medium",
        "warnings": ["关键数字需回到原文核验。"],
        "key_questions": [
            {"answer": "泛化不足。", "verdict": "原文有明确线索", "points": [
                {"title": "跨中心泛化", "detail": "现有模型在外部中心表现不稳定。", "locations": ["第 2 页"]}
            ], "evidence": []},
            {"answer": "增加校准。", "verdict": "作者有明确声明", "evidence": []},
            {"answer": "部分支持。", "verdict": "部分支持", "evidence": []},
            {"answer": "回看样本表。", "verdict": "建议回看原文", "evidence": []},
        ],
    }
    long_text = "Abstract current problem.\n\n" + ("Methods we propose a method. " * 700)
    result = await AnalyzerService(FakeCompletionLLM(payload, 7000)).analyze(
        AnalyzeRequest(title="Demo", abstract=long_text, use_llm=True)
    )
    assert result.mode == "llm"
    assert result.output_language == "zh-CN"
    assert result.usage["selection_strategy"] == "section_evidence_window"
    assert result.key_questions[0].points[0].locations == ["第 2 页"]
    assert result.key_questions[1].points[0].title == "核心结论"

    bad_questions = [
        {"answer": "English only", "verdict": "Unknown", "evidence": []}
        for _ in range(4)
    ]
    bad = {**payload, "core_problem": "Only English", "methods": ["English only"],
           "innovations": ["English"], "findings": ["English"], "limitations": ["English"],
           "key_questions": bad_questions}
    fallback = await AnalyzerService(FakeCompletionLLM(bad)).analyze(
        AnalyzeRequest(title="Demo", abstract="We propose a method. Results show an improvement. " * 4)
    )
    assert fallback.mode == "heuristic"
    assert "回退" in fallback.warnings[0]


def test_evidence_window_empty_and_short_paths():
    assert _select_evidence_window("short text", 100) == ("short text", False)
    selected, truncated = _select_evidence_window("x" * 200, 30)
    assert truncated and "系统说明" in selected


@pytest.mark.asyncio
async def test_idea_llm_success_and_failure_fallback():
    candidate = {
        "title": "可验证方向",
        "research_question": "跨中心是否稳定？",
        "hypothesis": "校准后更稳定。",
        "proposed_method": ["跨中心验证"],
        "novelty": ["待检索核验"],
        "policy_alignment": [],
        "evidence": ["用户工作"],
        "risks": ["样本偏差"],
        "first_validation": ["先复现实验"],
    }
    service = IdeaService(FakeCompletionLLM({"candidates": [candidate, candidate, candidate], "warnings": []}), PolicyService(Settings()))
    result = await service.generate(IdeaRequest(existing_work="我们已经完成足够长的前期模型和实验工作。", use_llm=True))
    assert result.mode == "llm-grounded" and result.candidates[0].title == "可验证方向"
    failed = IdeaService(FakeCompletionLLM(LLMUnavailable("offline")), PolicyService(Settings()))
    fallback = await failed.generate(IdeaRequest(existing_work="我们已经完成足够长的前期模型和实验工作。", use_llm=True))
    assert fallback.mode == "structured-hypothesis" and "回退" in fallback.warnings[0]


def test_llm_json_parsing_and_locality():
    assert LLMService._parse_json("```json\n{\"ok\": true}\n```") == {"ok": True}
    assert LLMService._parse_json("prefix {\"value\": 2} suffix") == {"value": 2}
    with pytest.raises(LLMUnavailable):
        LLMService._parse_json("not json")
    with pytest.raises(LLMUnavailable):
        LLMService._parse_json("[1, 2]")
    local = LLMService(Settings(llm_provider="ollama", llm_base_url="http://localhost:11434"))
    assert local.enabled and local._remote_allowed()


@pytest.mark.asyncio
async def test_llm_both_provider_protocols(monkeypatch):
    class Response:
        def __init__(self, payload): self.payload = payload
        def raise_for_status(self): return None
        def json(self): return self.payload

    class Client:
        payload = {}
        request = None
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return None
        async def post(self, url, **kwargs):
            Client.request = (url, kwargs)
            return Response(Client.payload)

    monkeypatch.setattr("latticescholar.services.llm.httpx.AsyncClient", Client)
    Client.payload = {"message": {"content": "{\"answer\": \"中文\"}"}, "prompt_eval_count": 4, "eval_count": 5}
    value, usage = await LLMService(Settings(llm_provider="ollama")).json_completion("系统", "用户")
    assert value["answer"] == "中文" and usage["provider"] == "ollama"
    Client.payload = {"choices": [{"message": {"content": "{\"answer\": \"中文\"}"}}], "usage": {"total_tokens": 9}}
    config = Settings(llm_provider="openai_compatible", llm_base_url="http://localhost:9000", llm_api_key="secret")
    value, usage = await LLMService(config).json_completion("系统", "用户")
    assert value["answer"] == "中文" and usage["provider"] == "openai_compatible"
    assert Client.request[1]["headers"]["Authorization"] == "Bearer secret"
    with pytest.raises(LLMUnavailable):
        await LLMService(Settings(llm_provider="none")).json_completion("s", "u")


@pytest.mark.asyncio
async def test_update_service_all_outcomes(tmp_path, monkeypatch):
    assert _version_tuple("v1.2.3") == (1, 2, 3)
    assert _version_tuple("bad") == (0, 0, 0)
    assert _github_repository("https://github.com/owner/repo.git") == "owner/repo"
    assert _github_repository("https://example.com/owner/repo") is None
    assert _github_repository("https://github.com/only-owner") is None

    class Response:
        status_code = 200
        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPStatusError(
                    "bad",
                    request=httpx.Request("GET", "https://x"),
                    response=httpx.Response(self.status_code),
                )
        def json(self): return {"tag_name": "v9.0.0", "html_url": "https://github.com/x", "published_at": "2026-01-01"}
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return None
        async def get(self, *args, **kwargs): return Response()
    monkeypatch.setattr("latticescholar.services.updates.httpx.AsyncClient", Client)
    config = Settings(data_dir=tmp_path, repository_url="https://github.com/owner/repo", app_version="0.6.0")
    service = UpdateService(config, Database(config.database_path))
    first = await service.check()
    second = await service.check()
    assert first["update_available"] and not first["cache_hit"] and second["cache_hit"]
    missing = UpdateService(Settings(data_dir=tmp_path / "none", repository_url="bad"), Database(tmp_path / "none.db"))
    assert (await missing.check())["status"] == "repository_not_configured"


def test_account_roles_and_login(tmp_path, monkeypatch):
    config = Settings(data_dir=tmp_path, auth_mode="accounts", dev_auth=True, admin_emails="admin@example.edu")
    db = Database(config.database_path)
    service = AccountService(config, db)
    code = service.request_code("admin@example.edu")
    with pytest.raises(AuthenticationError):
        service.request_code("admin@example.edu")
    with pytest.raises(AuthenticationError):
        service.verify_code("admin@example.edu", "000000" if code != "000000" else "999999")
    user = service.verify_code("admin@example.edu", code)
    assert service.entitlement(user)["plan"] == "admin"
    token = service.issue_session(user["id"])
    assert service.user_from_token(token)["email"] == "admin@example.edu"
    assert service.user_from_token("bad") is None

    regular = db.get_or_create_user("user@example.edu", 0)
    assert service.entitlement(regular)["plan"] == "user"
    assert service.entitlement(regular)["is_pro"] is True
    service.check_daily(regular, "search")
    service.require_pro(regular, "深度分析")
    service.validate_sources(regular, ["semantic_scholar"])
    service.check_library(regular)
    assert _parse_time("bad") is None and _parse_time(None) is None
    assert load_or_create_session_secret(config) == load_or_create_session_secret(config)


def test_export_markdown_and_duplicate_citation_keys():
    paper = Paper(id="1", title="A {study}", authors=["Ada Lovelace"], year=2026, venue="J", doi="10.1/x", url="https://x", abstract="Line one\nline two")
    analysis = PaperAnalysis(core_problem="问题", methods=["方法"], innovations=["创新"], findings=["结果"], limitations=["局限"], evidence=[], confidence="medium", mode="heuristic")
    idea = IdeaCandidate(title="方向", research_question="问题？", hypothesis="假设", proposed_method=[], novelty=[], policy_alignment=[], evidence=[], risks=[], first_validation=["验证"])
    policy = Policy(id="p", title="政策", issuer="部门", published_at="2026-01-01", url="https://www.gov.cn/demo", summary="足够长的政策摘要内容用于测试。", signals=[], tags=[])
    content = export_markdown(ExportRequest(title="简报", query="问题", papers=[paper], analyses=[analysis], ideas=[idea], policies=[policy]))
    assert "## Evidence set" in content and "## Paper analysis" in content and "## Policy evidence" in content
    bib = export_bibtex([paper, paper.model_copy(update={"id": "2"})])
    assert "Lovelace2026A2" in bib and "\\{study\\}" in bib
    assert "AB  - Line one line two" in export_ris([paper])


def test_literature_language_facets_and_advanced_filters():
    papers = [
        Paper(id="zh", title="中文论文", abstract="这是一个足够长的中文摘要，用于测试语言识别和筛选功能。", citation_count=3, open_access=True),
        Paper(id="en", title="English paper", abstract="This is a sufficiently long English abstract for filtering.", citation_count=30),
        Paper(id="record", title="Metadata only paper", abstract="", citation_count=100),
    ]
    merged = LiteratureService._merge_and_rank("论文 paper", {"demo": papers})
    facets = LiteratureService._facets(merged)
    assert facets["zh"] == 1 and facets["en"] == 2 and facets["citation_only"] == 1
    request = SearchRequest(query="论文", sources=["crossref"], language="en", has_abstract=True, min_citations=10, sort_by="citations")
    filtered = LiteratureService._filter_and_sort(request, merged)
    assert [paper.id for paper in filtered] == ["en"]
    assert LiteratureService._contains_chinese("论文")


def test_small_configuration_helpers(monkeypatch):
    monkeypatch.setenv("FLAG_FOR_TEST", "yes")
    assert _env_bool("FLAG_FOR_TEST") is True
    monkeypatch.setenv("FLAG_FOR_TEST", "no")
    assert _env_bool("FLAG_FOR_TEST", True) is False


@pytest.mark.asyncio
async def test_policy_sync_official_json_html_and_error(tmp_path, monkeypatch):
    class Response:
        def __init__(self, url, *, payload=None, text="", content_type="application/json"):
            self.url = httpx.URL(url)
            self._payload = payload
            self.text = text
            self.content = text.encode() if text else json.dumps(payload or {}).encode()
            self.headers = {"content-type": content_type}

        def raise_for_status(self):
            return None

        def json(self):
            if self._payload is None:
                raise ValueError("not json")
            return self._payload

    class Client:
        responses = []

        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, **kwargs):
            return Client.responses.pop(0)

    monkeypatch.setattr("latticescholar.services.policy_sync.httpx.AsyncClient", Client)
    config = Settings(data_dir=tmp_path)
    db = Database(config.database_path)
    policies = PolicyService(config, db)
    service = PolicySyncService(config, db, policies)
    payload = {
        "code": 200,
        "searchVO": {"listVO": [{
            "id": "official-1", "title": "关于科研数据开放的指导意见",
            "pubtimeStr": "2026-08-01", "puborg": "国务院",
            "url": "https://www.gov.cn/zhengce/zhengceku/202608/demo.htm",
            "summary": "推进科研数据依法合规开放共享并完善安全治理机制。",
        }]},
    }
    Client.responses = [Response("https://sousuo.www.gov.cn/search-gov/data", payload=payload)]
    run = await service.sync_source("state-council")
    assert run["status"] == "ok" and run["discovered"] == 1 and run["changed"] == 1

    html = '<a href="/demo/2026-08-02-policy.html">关于开展科研诚信项目申报工作的通知</a>'
    source = policies.source("most")
    Client.responses = [Response(str(source.portal_url), text=html, content_type="text/html")]
    run = await service.sync_source("most")
    assert run["status"] == "ok" and run["discovered"] == 1

    Client.responses = [Response(str(source.portal_url), text="<html>无候选</html>", content_type="text/html")]
    run = await service.sync_source("most")
    assert run["status"] == "error" and "未发现候选" in run["error"]
    with pytest.raises(ValueError):
        await service.sync_source("unknown-source")


def test_cli_starts_server_without_opening_browser(monkeypatch):
    import latticescholar.cli as cli

    called = {}
    monkeypatch.setattr(sys, "argv", ["latticescholar", "--host", "0.0.0.0", "--port", "9999", "--no-browser"])
    monkeypatch.setattr(cli.uvicorn, "run", lambda app, **kwargs: called.update(app=app, **kwargs))
    cli.main()
    from fastapi import FastAPI

    assert isinstance(called["app"], FastAPI) and called["port"] == 9999
