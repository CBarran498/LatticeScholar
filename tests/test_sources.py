import httpx
import pytest

from latticescholar.config import Settings
from latticescholar.models import SearchRequest
from latticescholar.services.sources import ScholarlySources


@pytest.mark.asyncio
async def test_all_source_adapters_normalize_to_paper_model():
    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if host == "api.crossref.org":
            return httpx.Response(
                200,
                json={
                    "message": {
                        "items": [
                            {
                                "DOI": "10.1/CROSSREF",
                                "title": ["Crossref paper"],
                                "abstract": "<jats:p>A useful abstract.</jats:p>",
                                "author": [{"given": "Ada", "family": "Lovelace"}],
                                "published": {"date-parts": [[2025, 1, 1]]},
                                "container-title": ["Journal A"],
                                "URL": "https://doi.org/10.1/crossref",
                                "ISSN": ["1234-5678"],
                                "is-referenced-by-count": 7,
                            }
                        ]
                    }
                },
            )
        if host == "api.semanticscholar.org":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "paperId": "s2",
                            "title": "Semantic paper",
                            "abstract": "Semantic abstract",
                            "authors": [{"name": "Grace Hopper"}],
                            "year": 2024,
                            "venue": "Journal B",
                            "externalIds": {"DOI": "10.1/S2"},
                            "url": "https://example.org/s2",
                            "citationCount": 9,
                            "openAccessPdf": {"url": "https://example.org/s2.pdf"},
                            "fieldsOfStudy": ["Computer Science"],
                        }
                    ]
                },
            )
        if host == "api.openalex.org":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": "https://openalex.org/W1",
                            "doi": "https://doi.org/10.1/OA",
                            "title": "OpenAlex paper",
                            "publication_year": 2023,
                            "authorships": [{"author": {"display_name": "Katherine Johnson"}}],
                            "primary_location": {
                                "landing_page_url": "https://example.org/oa",
                                "source": {"display_name": "Journal C"},
                            },
                            "abstract_inverted_index": {"Hello": [0], "world": [1]},
                            "cited_by_count": 11,
                            "open_access": {"is_oa": True},
                            "topics": [{"display_name": "Machine learning"}],
                        }
                    ]
                },
            )
        if host == "export.arxiv.org":
            return httpx.Response(
                200,
                text="""<?xml version="1.0" encoding="UTF-8"?>
                <feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
                  <entry><id>http://arxiv.org/abs/2501.00001v1</id><title>arXiv paper</title>
                  <summary>An open preprint abstract.</summary><published>2025-01-01T00:00:00Z</published>
                  <author><name>Alan Turing</name></author><category term="cs.AI"/>
                  <arxiv:journal_ref>Journal D</arxiv:journal_ref></entry>
                </feed>""",
                headers={"content-type": "application/atom+xml"},
            )
        if host == "eutils.ncbi.nlm.nih.gov" and request.url.path.endswith("esearch.fcgi"):
            return httpx.Response(200, json={"esearchresult": {"idlist": ["12345"]}})
        if host == "eutils.ncbi.nlm.nih.gov" and request.url.path.endswith("efetch.fcgi"):
            return httpx.Response(
                200,
                text="""<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>12345</PMID>
                <Article><Journal><ISSN>2049-3630</ISSN><JournalIssue><PubDate><Year>2025</Year></PubDate></JournalIssue><Title>Medical Journal</Title></Journal>
                <ArticleTitle>PubMed paper</ArticleTitle><Abstract><AbstractText Label="BACKGROUND">Clinical evidence.</AbstractText></Abstract>
                <AuthorList><Author><ForeName>Tu</ForeName><LastName>Youyou</LastName></Author></AuthorList></Article>
                <MeshHeadingList><MeshHeading><DescriptorName>Medicine</DescriptorName></MeshHeading></MeshHeadingList></MedlineCitation>
                <PubmedData><ArticleIdList><ArticleId IdType="doi">10.1/PUBMED</ArticleId></ArticleIdList></PubmedData>
                </PubmedArticle></PubmedArticleSet>""",
            )
        if host == "api.clarivate.com":
            assert request.headers["X-ApiKey"] == "test-wos-key"
            return httpx.Response(
                200,
                json={"hits": [{"uid": "WOS:1", "title": "WoS paper", "source": {"sourceTitle": "Journal E", "publishYear": 2025}, "names": {"authors": [{"displayName": "Marie Curie"}]}, "identifiers": {"doi": "10.1/WOS", "issn": "1111-2222"}, "links": {"record": "https://www.webofscience.com/record/1"}, "citations": [{"db": "WOS", "count": 12}], "keywords": {"authorKeywords": ["physics"]}}]},
            )
        return httpx.Response(404)

    sources = ScholarlySources(Settings(wos_api_key="test-wos-key"))
    await sources.client.aclose()
    sources.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    request = SearchRequest(query="machine learning", limit=5, sources=["crossref"])
    try:
        crossref = await sources.search_crossref(request)
        semantic = await sources.search_semantic_scholar(request)
        openalex = await sources.search_openalex(request)
        arxiv = await sources.search_arxiv(request)
        pubmed = await sources.search_pubmed(request)
        wos = await sources.search_web_of_science(request)
    finally:
        await sources.close()

    assert crossref[0].doi == "10.1/crossref"
    assert crossref[0].issn == ["1234-5678"]
    assert semantic[0].open_access is True
    assert openalex[0].abstract == "Hello world"
    assert arxiv[0].topics == ["cs.AI"]
    assert pubmed[0].doi == "10.1/pubmed"
    assert pubmed[0].abstract == "BACKGROUND: Clinical evidence."
    assert wos[0].citation_count == 12
    assert wos[0].sources == ["Web of Science"]
