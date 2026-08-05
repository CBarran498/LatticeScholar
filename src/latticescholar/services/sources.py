from __future__ import annotations

import asyncio
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import httpx

from ..config import Settings
from ..models import Paper, SearchRequest
from ..text_utils import clean_markup, stable_id


class SourceError(RuntimeError):
    pass


def _year_from_parts(value: Any) -> Optional[int]:
    try:
        return int(value[0][0])
    except (TypeError, ValueError, IndexError):
        return None


def _reconstruct_abstract(index: Any) -> str:
    if not isinstance(index, dict):
        return ""
    positioned = []
    for word, positions in index.items():
        for position in positions or []:
            positioned.append((position, word))
    return " ".join(word for _, word in sorted(positioned))


class ScholarlySources:
    def __init__(self, config: Settings):
        self.config = config
        headers = {
            "User-Agent": "LatticeScholar/0.6 (local-first scholarly research tool)",
            "Accept": "application/json, application/atom+xml;q=0.9, */*;q=0.8",
        }
        self.client = httpx.AsyncClient(
            headers=headers,
            timeout=httpx.Timeout(config.request_timeout_seconds),
            follow_redirects=True,
        )

    async def close(self) -> None:
        await self.client.aclose()

    @staticmethod
    def _query_for(request: SearchRequest, source: str) -> str:
        """Use the optional English expression for English-first indexes."""
        if request.english_query and source in {
            "semantic_scholar",
            "openalex",
            "arxiv",
            "pubmed",
            "web_of_science",
        }:
            return request.english_query
        return request.query

    async def search(self, source: str, request: SearchRequest) -> List[Paper]:
        method = getattr(self, "search_" + source, None)
        if method is None:
            raise SourceError("Unsupported source: " + source)
        try:
            return await method(request)
        except httpx.HTTPStatusError as exc:
            detail = f"HTTP {exc.response.status_code}"
            if exc.response.status_code == 429:
                detail += " rate limited"
            raise SourceError(detail) from exc
        except (httpx.RequestError, ET.ParseError, ValueError, KeyError) as exc:
            raise SourceError(type(exc).__name__ + ": " + str(exc)[:160]) from exc

    async def search_crossref(self, request: SearchRequest) -> List[Paper]:
        params: Dict[str, Any] = {
            "query.bibliographic": self._query_for(request, "crossref"),
            "rows": min(max(request.limit * 2, 20), 100),
            "select": "DOI,title,abstract,author,published,container-title,URL,is-referenced-by-count,ISSN,type",
        }
        filters = ["type:journal-article"]
        if request.year_from:
            filters.append(f"from-pub-date:{request.year_from}-01-01")
        if request.year_to:
            filters.append(f"until-pub-date:{request.year_to}-12-31")
        params["filter"] = ",".join(filters)
        if self.config.crossref_email:
            params["mailto"] = self.config.crossref_email
        response = await self.client.get("https://api.crossref.org/v1/works", params=params)
        response.raise_for_status()
        items = response.json().get("message", {}).get("items", [])
        papers = []
        for item in items:
            title = " ".join(item.get("title") or []).strip()
            if not title:
                continue
            doi = (item.get("DOI") or "").lower()
            authors = []
            for author in item.get("author") or []:
                name = " ".join(filter(None, [author.get("given", ""), author.get("family", "")]))
                if name:
                    authors.append(name)
            year = _year_from_parts((item.get("published") or {}).get("date-parts"))
            venue = " ".join(item.get("container-title") or []).strip()
            papers.append(
                Paper(
                    id=stable_id("crossref", doi or title),
                    title=title,
                    abstract=clean_markup(item.get("abstract", "")),
                    authors=authors,
                    year=year,
                    venue=venue,
                    issn=item.get("ISSN") or [],
                    doi=doi,
                    url=item.get("URL") or ("https://doi.org/" + doi if doi else ""),
                    citation_count=item.get("is-referenced-by-count"),
                    sources=["Crossref"],
                    topics=[],
                )
            )
        return papers

    async def search_semantic_scholar(self, request: SearchRequest) -> List[Paper]:
        headers = {}
        if self.config.semantic_scholar_api_key:
            headers["x-api-key"] = self.config.semantic_scholar_api_key
        params: Dict[str, Any] = {
            "query": self._query_for(request, "semantic_scholar"),
            "limit": min(request.limit * 2, 100),
            "fields": "paperId,title,abstract,authors,year,venue,externalIds,url,citationCount,openAccessPdf,fieldsOfStudy",
        }
        response = await self.client.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params=params,
            headers=headers,
        )
        response.raise_for_status()
        papers = []
        for item in response.json().get("data") or []:
            year = item.get("year")
            if request.year_from and year and year < request.year_from:
                continue
            if request.year_to and year and year > request.year_to:
                continue
            external = item.get("externalIds") or {}
            doi = (external.get("DOI") or "").lower()
            oa = item.get("openAccessPdf")
            papers.append(
                Paper(
                    id=stable_id("s2", item.get("paperId") or doi or item.get("title", "")),
                    title=item.get("title") or "Untitled",
                    abstract=clean_markup(item.get("abstract") or ""),
                    authors=[a.get("name", "") for a in item.get("authors") or [] if a.get("name")],
                    year=year,
                    venue=item.get("venue") or "",
                    doi=doi,
                    url=(oa or {}).get("url") or item.get("url") or "",
                    citation_count=item.get("citationCount"),
                    open_access=bool(oa) if oa is not None else None,
                    sources=["Semantic Scholar"],
                    topics=item.get("fieldsOfStudy") or [],
                )
            )
        return papers

    async def search_openalex(self, request: SearchRequest) -> List[Paper]:
        params: Dict[str, Any] = {
            "search": self._query_for(request, "openalex"),
            "per_page": min(request.limit * 2, 100),
            "select": "id,doi,title,publication_year,authorships,primary_location,abstract_inverted_index,cited_by_count,open_access,topics",
        }
        filters = []
        if request.year_from:
            filters.append(f"from_publication_date:{request.year_from}-01-01")
        if request.year_to:
            filters.append(f"to_publication_date:{request.year_to}-12-31")
        if request.has_abstract is True:
            filters.append("has_abstract:true")
        if request.open_access_only:
            filters.append("open_access.is_oa:true")
        if request.min_citations:
            filters.append(f"cited_by_count:>{max(0, request.min_citations - 1)}")
        if request.language in {"zh", "en"}:
            filters.append(f"language:{request.language}")
        if filters:
            params["filter"] = ",".join(filters)
        if self.config.openalex_api_key:
            params["api_key"] = self.config.openalex_api_key
        response = await self.client.get("https://api.openalex.org/works", params=params)
        response.raise_for_status()
        papers = []
        for item in response.json().get("results") or []:
            location = item.get("primary_location") or {}
            source = location.get("source") or {}
            doi_url = item.get("doi") or ""
            doi = re.sub(r"^https?://doi\.org/", "", doi_url, flags=re.I).lower()
            authors = []
            for authorship in item.get("authorships") or []:
                name = (authorship.get("author") or {}).get("display_name")
                if name:
                    authors.append(name)
            topics = [
                (topic.get("display_name") or "")
                for topic in (item.get("topics") or [])[:5]
                if topic.get("display_name")
            ]
            papers.append(
                Paper(
                    id=stable_id("openalex", item.get("id") or doi or item.get("title", "")),
                    title=item.get("title") or "Untitled",
                    abstract=_reconstruct_abstract(item.get("abstract_inverted_index")),
                    authors=authors,
                    year=item.get("publication_year"),
                    venue=source.get("display_name") or "",
                    doi=doi,
                    url=location.get("landing_page_url") or doi_url,
                    citation_count=item.get("cited_by_count"),
                    open_access=(item.get("open_access") or {}).get("is_oa"),
                    sources=["OpenAlex"],
                    topics=topics,
                )
            )
        return papers

    async def search_arxiv(self, request: SearchRequest) -> List[Paper]:
        query = quote(self._query_for(request, "arxiv"))
        url = (
            "https://export.arxiv.org/api/query?search_query=all:"
            + query
            + f"&start=0&max_results={min(request.limit * 2, 50)}&sortBy=relevance"
        )
        response = await self.client.get(url, headers={"Accept": "application/atom+xml"})
        response.raise_for_status()
        root = ET.fromstring(response.text)
        ns = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
        papers = []
        for entry in root.findall("a:entry", ns):
            title = clean_markup(entry.findtext("a:title", default="", namespaces=ns))
            published = entry.findtext("a:published", default="", namespaces=ns)
            year = int(published[:4]) if len(published) >= 4 else None
            if request.year_from and year and year < request.year_from:
                continue
            if request.year_to and year and year > request.year_to:
                continue
            entry_url = entry.findtext("a:id", default="", namespaces=ns)
            arxiv_id = entry_url.rsplit("/", 1)[-1]
            journal_ref = entry.findtext("arxiv:journal_ref", default="", namespaces=ns)
            categories = [c.attrib.get("term", "") for c in entry.findall("a:category", ns)]
            papers.append(
                Paper(
                    id=stable_id("arxiv", arxiv_id),
                    title=title,
                    abstract=clean_markup(entry.findtext("a:summary", default="", namespaces=ns)),
                    authors=[
                        a.findtext("a:name", default="", namespaces=ns)
                        for a in entry.findall("a:author", ns)
                    ],
                    year=year,
                    venue=journal_ref or "arXiv",
                    url=entry_url,
                    open_access=True,
                    sources=["arXiv"],
                    topics=categories,
                )
            )
        return papers

    async def search_pubmed(self, request: SearchRequest) -> List[Paper]:
        """Search PubMed through NCBI's supported ESearch + EFetch workflow."""
        term = self._query_for(request, "pubmed")
        if request.year_from or request.year_to:
            start = request.year_from or 1900
            end = request.year_to or 2100
            term += f" AND ({start}:{end}[dp])"
        if request.has_abstract is True:
            term += " AND hasabstract"
        if request.language == "en":
            term += " AND english[la]"
        elif request.language == "zh":
            term += " AND chinese[la]"
        common: Dict[str, Any] = {"tool": "LatticeScholar"}
        if self.config.ncbi_email:
            common["email"] = self.config.ncbi_email
        if self.config.ncbi_api_key:
            common["api_key"] = self.config.ncbi_api_key
        search_response = await self.client.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            params={
                **common,
                "db": "pubmed",
                "term": term,
                "retmode": "json",
                "retmax": min(request.limit * 2, 100),
                "sort": "relevance",
            },
        )
        search_response.raise_for_status()
        ids = search_response.json().get("esearchresult", {}).get("idlist", [])
        if not ids:
            return []
        fetch_response = await self.client.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
            params={**common, "db": "pubmed", "id": ",".join(ids), "retmode": "xml"},
            headers={"Accept": "application/xml"},
        )
        fetch_response.raise_for_status()
        root = ET.fromstring(fetch_response.text)
        papers: List[Paper] = []
        for article in root.findall(".//PubmedArticle"):
            citation = article.find("MedlineCitation")
            article_node = citation.find("Article") if citation is not None else None
            if article_node is None:
                continue
            pmid = citation.findtext("PMID", default="") if citation is not None else ""
            title_node = article_node.find("ArticleTitle")
            title = clean_markup("".join(title_node.itertext()) if title_node is not None else "")
            if not title:
                continue
            abstract_parts = []
            for part in article_node.findall("Abstract/AbstractText"):
                label = part.attrib.get("Label", "")
                value = clean_markup("".join(part.itertext()))
                abstract_parts.append(f"{label}: {value}" if label and value else value)
            journal = article_node.find("Journal")
            venue = journal.findtext("Title", default="") if journal is not None else ""
            issn = []
            if journal is not None and journal.findtext("ISSN"):
                issn.append(journal.findtext("ISSN", default=""))
            authors = []
            for author in article_node.findall("AuthorList/Author"):
                collective = author.findtext("CollectiveName", default="")
                name = collective or " ".join(
                    filter(None, [author.findtext("ForeName", default=""), author.findtext("LastName", default="")])
                )
                if name:
                    authors.append(name)
            year_text = ""
            if journal is not None:
                issue = journal.find("JournalIssue/PubDate")
                if issue is not None:
                    year_text = issue.findtext("Year", default="") or issue.findtext("MedlineDate", default="")[:4]
            if not year_text:
                year_text = article.findtext("PubmedData/History/PubMedPubDate[@PubStatus='pubmed']/Year", default="")
            year = int(year_text) if year_text.isdigit() else None
            article_ids = {
                node.attrib.get("IdType", ""): (node.text or "")
                for node in article.findall("PubmedData/ArticleIdList/ArticleId")
            }
            doi = article_ids.get("doi", "").lower()
            mesh = [
                clean_markup("".join(node.itertext()))
                for node in citation.findall("MeshHeadingList/MeshHeading/DescriptorName")
            ] if citation is not None else []
            papers.append(
                Paper(
                    id=stable_id("pubmed", pmid or doi or title),
                    title=title,
                    abstract=" ".join(filter(None, abstract_parts)),
                    authors=authors,
                    year=year,
                    venue=venue,
                    issn=issn,
                    doi=doi,
                    url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
                    sources=["PubMed"],
                    topics=mesh[:8],
                )
            )
        return papers

    async def search_web_of_science(self, request: SearchRequest) -> List[Paper]:
        """Use Clarivate's official Starter API when an API key is configured."""
        if not self.config.wos_api_key:
            raise SourceError("requires WOS_API_KEY from the Clarivate Developer Portal")
        query = self._query_for(request, "web_of_science").replace('"', " ").strip()
        params: Dict[str, Any] = {
            "db": "WOS",
            "q": f'TS=("{query}")',
            "limit": min(request.limit * 2, 50),
            "page": 1,
            "sortField": "RS+D",
        }
        if request.year_from or request.year_to:
            start = request.year_from or 1900
            end = request.year_to or 2100
            params["publishTimeSpan"] = f"{start}-01-01+{end}-12-31"
        response = await self.client.get(
            "https://api.clarivate.com/apis/wos-starter/v2/documents",
            params=params,
            headers={"X-ApiKey": self.config.wos_api_key},
        )
        response.raise_for_status()
        papers = []
        for item in response.json().get("hits") or []:
            source = item.get("source") or {}
            names = item.get("names") or {}
            identifiers = item.get("identifiers") or {}
            citations = item.get("citations") or []
            links = item.get("links") or {}
            keywords = (item.get("keywords") or {}).get("authorKeywords") or []
            doi = (identifiers.get("doi") or "").lower()
            papers.append(
                Paper(
                    id=stable_id("wos", item.get("uid") or doi or item.get("title", "")),
                    title=item.get("title") or "Untitled",
                    abstract=clean_markup(item.get("abstract") or ""),
                    authors=[
                        a.get("displayName", "")
                        for a in names.get("authors") or []
                        if a.get("displayName")
                    ],
                    year=source.get("publishYear"),
                    venue=source.get("sourceTitle") or "",
                    issn=list(filter(None, [identifiers.get("issn"), identifiers.get("eissn")])),
                    doi=doi,
                    url=links.get("record") or ("https://doi.org/" + doi if doi else ""),
                    citation_count=max(
                        (int(c.get("count") or 0) for c in citations), default=0
                    ),
                    sources=["Web of Science"],
                    topics=keywords[:8],
                )
            )
        return papers

    async def search_many(
        self, request: SearchRequest
    ) -> Tuple[Dict[str, List[Paper]], Dict[str, str]]:
        async def run(name: str) -> Tuple[str, List[Paper], str]:
            try:
                papers = await self.search(name, request)
                return name, papers, f"ok ({len(papers)})"
            except SourceError as exc:
                return name, [], "error: " + str(exc)

        results = await asyncio.gather(*(run(name) for name in request.sources))
        return (
            {name: papers for name, papers, _ in results},
            {name: status for name, _, status in results},
        )
