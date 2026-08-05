
import pytest

from latticescholar.config import Settings
from latticescholar.db import Database
from latticescholar.models import AnalyzeRequest, IdeaRequest, Paper, SearchRequest
from latticescholar.services.analyzer import AnalyzerService
from latticescholar.services.exporter import export_bibtex, export_ris
from latticescholar.services.ideas import IdeaService
from latticescholar.services.journals import JournalService
from latticescholar.services.literature import LiteratureService
from latticescholar.services.llm import LLMService, LLMUnavailable
from latticescholar.services.policies import PolicyService
from latticescholar.services.policy_sync import (
    discover_policy_links,
    discover_state_council_records,
)


class FakeSources:
    async def search_many(self, request):
        return (
            {
                "crossref": [
                    Paper(
                        id="c1",
                        title="Efficient Clinical Multimodal Learning",
                        abstract="We propose an efficient model for clinical prediction.",
                        doi="10.1/demo",
                        year=2024,
                        sources=["Crossref"],
                    )
                ],
                "semantic_scholar": [
                    Paper(
                        id="s1",
                        title="Efficient clinical multimodal learning",
                        abstract="We propose a model. Results show improved calibration in clinical prediction.",
                        doi="10.1/demo",
                        year=2024,
                        citation_count=12,
                        sources=["Semantic Scholar"],
                    )
                ],
            },
            {"crossref": "ok (1)", "semantic_scholar": "ok (1)"},
        )

    async def search_crossref(self, request):
        assert len(request.query) <= 500
        return [
            Paper(
                id="j1",
                title="Clinical multimodal model",
                abstract="A calibrated multimodal clinical prediction model",
                venue="Journal A",
                issn=["1234-5678"],
                doi="10.1/j1",
                year=2025,
                sources=["Crossref"],
            ),
            Paper(
                id="j2",
                title="Multimodal decision support",
                venue="Journal A",
                issn=["1234-5678"],
                doi="10.1/j2",
                year=2024,
                sources=["Crossref"],
            ),
        ]


@pytest.mark.asyncio
async def test_literature_deduplicates_and_caches(tmp_path):
    config = Settings(data_dir=tmp_path, llm_provider="none")
    service = LiteratureService(config, Database(config.database_path), FakeSources())
    request = SearchRequest(
        query="efficient clinical multimodal learning",
        sources=["crossref", "semantic_scholar"],
    )
    first = await service.search(request)
    second = await service.search(request)
    assert len(first.papers) == 1
    assert first.papers[0].citation_count == 12
    assert len(first.papers[0].sources) == 2
    assert second.cache_hit is True


@pytest.mark.asyncio
async def test_analyzer_extracts_claims_without_inventing():
    analyzer = AnalyzerService(LLMService(Settings(llm_provider="none")))
    result = await analyzer.analyze(
        AnalyzeRequest(
            title="Demo",
            abstract=(
                "We propose a novel lightweight framework for diagnosis. "
                "We evaluate the model on two datasets. Results show improved calibration. "
                "However, external validation remains future work."
            ),
        )
    )
    assert result.mode == "heuristic"
    assert any("novel" in item.lower() for item in result.innovations)
    assert any("external validation" in item.lower() for item in result.limitations)
    assert result.evidence


@pytest.mark.asyncio
async def test_idea_fallback_is_explicitly_hypothetical():
    config = Settings(llm_provider="none")
    policies = PolicyService(config)
    service = IdeaService(LLMService(config), policies)
    result = await service.generate(
        IdeaRequest(
            existing_work="我们已经完成临床多模态预测模型并在两个公开数据集上验证。",
            keywords=["多模态", "临床"],
            policy_ids=["cn-ai-education-2026"],
        )
    )
    assert result.mode == "structured-hypothesis"
    assert len(result.candidates) == 3
    assert all(candidate.first_validation for candidate in result.candidates)
    assert any("待证伪" in warning for warning in result.warnings)


@pytest.mark.asyncio
async def test_remote_llm_is_blocked_without_explicit_consent():
    config = Settings(
        llm_provider="openai_compatible",
        llm_base_url="https://example.com",
        allow_remote_llm=False,
    )
    with pytest.raises(LLMUnavailable, match="blocked"):
        await LLMService(config).json_completion("system", "user")


@pytest.mark.asyncio
async def test_journal_match_truncates_query_and_keeps_issn():
    class JournalFakeSources:
        async def search_crossref(self, request):
            return await FakeSources().search_crossref(request)

    service = JournalService(JournalFakeSources())
    from latticescholar.models import JournalMatchRequest

    result = await service.match(
        JournalMatchRequest(title="Clinical model", abstract="multimodal " * 1000, limit=5)
    )
    assert result[0].journal == "Journal A"
    assert result[0].issn == ["1234-5678"]
    assert result[0].evidence_count == 2


def test_policy_discovery_only_accepts_official_same_domain_links():
    source = PolicyService(Settings()).source("state-council")
    html = """
    <a href="/zhengce/content/2026-08/01/content_1.htm">关于推进科研数据开放的指导意见</a>
    <a href="https://malicious.example/notice">关于虚假政策的通知</a>
    <a href="/about">网站介绍</a>
    """
    items = discover_policy_links(source, html)
    assert len(items) == 1
    assert items[0]["published_at"] == "2026-08-01"
    assert items[0]["url"].startswith("https://sousuo.www.gov.cn/")


def test_state_council_official_json_is_normalized_for_review():
    source = PolicyService(Settings()).source("state-council")
    payload = {
        "searchVO": {
            "catMap": {
                "gongwen": {
                    "listVO": [
                        {
                            "id": "26426338",
                            "title": "国务院关于印发科研数据规划的通知<br/>科研数据规划",
                            "pubtimeStr": "2026.07.31",
                            "puborg": "国务院",
                            "url": "https://www.gov.cn/zhengce/zhengceku/202607/demo.htm",
                            "summary": "<em>科研数据</em>开放共享与安全治理。",
                            "childtype": "科技、教育\\知识产权",
                            "pcode": "国发〔2026〕30号",
                        },
                        {
                            "id": "outside",
                            "title": "虚假政策",
                            "url": "https://malicious.example/policy",
                        },
                    ]
                }
            }
        }
    }
    items = discover_state_council_records(source, payload)
    assert len(items) == 1
    assert items[0]["external_id"] == "26426338"
    assert "<br" not in items[0]["title"]
    assert items[0]["title"] == "国务院关于印发科研数据规划的通知"
    assert items[0]["published_at"] == "2026-07-31"
    assert "<em>" not in items[0]["summary"]
    assert items[0]["raw"]["document_number"] == "国发〔2026〕30号"


def test_bibliography_exports_are_reference_manager_ready():
    papers = [
        Paper(
            id="p1",
            title="Evidence-grounded research workflow",
            authors=["Ada Lovelace", "Tu Youyou"],
            year=2026,
            venue="Journal of Research Tools",
            doi="10.1000/demo",
            url="https://doi.org/10.1000/demo",
        )
    ]
    bibtex = export_bibtex(papers)
    ris = export_ris(papers)
    assert "@article{Lovelace2026Evidence" in bibtex
    assert "doi = {10.1000/demo}" in bibtex
    assert "AU  - Tu Youyou" in ris
    assert "DO  - 10.1000/demo" in ris
