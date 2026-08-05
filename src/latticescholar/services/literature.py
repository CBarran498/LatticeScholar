from __future__ import annotations

import hashlib
import json
import math
import re
import time
from typing import Dict, List

from ..config import Settings
from ..db import Database
from ..models import Paper, SearchRequest, SearchResponse
from ..text_utils import cosine_similarity, normalize_title
from .sources import ScholarlySources


class LiteratureService:
    def __init__(self, config: Settings, db: Database, sources: ScholarlySources):
        self.config = config
        self.db = db
        self.sources = sources

    @staticmethod
    def _cache_key(request: SearchRequest) -> str:
        payload = request.model_dump(mode="json")
        payload.pop("project_id", None)
        payload["sources"] = sorted(payload["sources"])
        payload["response_schema"] = 3
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return "search:" + hashlib.sha256(raw).hexdigest()

    async def search(self, request: SearchRequest) -> SearchResponse:
        started = time.perf_counter()
        key = self._cache_key(request)
        cached = self.db.get_cache(key)
        if cached:
            response = SearchResponse.model_validate(cached)
            response.cache_hit = True
            response.elapsed_ms = round((time.perf_counter() - started) * 1000)
            return response

        results_by_source, source_status = await self.sources.search_many(request)
        raw_count = sum(len(items) for items in results_by_source.values())
        merged = self._merge_and_rank(
            " ".join(filter(None, [request.query, request.english_query])), results_by_source
        )
        merged = self._filter_and_sort(request, merged)
        selected = merged[: request.limit]
        facets = self._facets(selected)
        quality = self._quality(selected, source_status, raw_count, len(merged))
        notices = [
            "引用量来自不同元数据源，只用于结果排序，不代表论文质量。",
            "平台只展示数据源实际返回的摘要；仅有题录的记录仍可收藏或前往来源页获取全文。",
        ]
        if self._contains_chinese(request.query) and not request.english_query:
            notices.insert(0, "当前只提供了中文检索式。建议补充英文关键词，以提高英文数据库的召回率。")
        if facets.get("citation_only", 0):
            notices.append(
                f"本轮合并结果中有 {facets['citation_only']} 条仅含题录；可开启“只看有摘要”或补充英文检索式。"
            )
        if not selected:
            notices.insert(0, "未获得结果。请检查网络、缩短关键词或更换数据源。")
        response = SearchResponse(
            papers=selected,
            source_status=source_status,
            elapsed_ms=round((time.perf_counter() - started) * 1000),
            facets=facets,
            notices=notices,
            quality=quality,
        )
        self.db.set_cache(key, response.model_dump(mode="json"), self.config.cache_ttl_seconds)
        return response

    @staticmethod
    def _merge_and_rank(query: str, source_results: Dict[str, List[Paper]]) -> List[Paper]:
        merged: Dict[str, Paper] = {}
        for papers in source_results.values():
            for paper in papers:
                key = "doi:" + paper.doi if paper.doi else "title:" + normalize_title(paper.title)
                if not key.split(":", 1)[1]:
                    key = "id:" + paper.id
                current = merged.get(key)
                if current is None:
                    merged[key] = paper.model_copy(deep=True)
                    continue
                if len(paper.abstract) > len(current.abstract):
                    current.abstract = paper.abstract
                if not current.doi and paper.doi:
                    current.doi = paper.doi
                if not current.url and paper.url:
                    current.url = paper.url
                if not current.venue and paper.venue:
                    current.venue = paper.venue
                current.issn = list(dict.fromkeys(current.issn + paper.issn))
                if not current.authors and paper.authors:
                    current.authors = paper.authors
                if paper.citation_count is not None:
                    current.citation_count = max(current.citation_count or 0, paper.citation_count)
                if paper.open_access is True:
                    current.open_access = True
                current.sources = list(dict.fromkeys(current.sources + paper.sources))
                current.topics = list(dict.fromkeys(current.topics + paper.topics))[:8]

        for paper in merged.values():
            paper.language = LiteratureService._paper_language(paper)
            topical = cosine_similarity(query, paper.title + " " + paper.abstract)
            citations = math.log1p(max(paper.citation_count or 0, 0)) / 10
            recency = 0.0
            if paper.year:
                recency = max(0.0, min(1.0, (paper.year - 2000) / 26))
            corroboration = min(1.0, len(paper.sources) / 3)
            completeness = 1.0 if len(paper.abstract.strip()) >= 80 else 0.35 if paper.abstract else 0.0
            paper.score = round(
                min(
                    1.0,
                    0.60 * topical
                    + 0.13 * citations
                    + 0.11 * recency
                    + 0.08 * corroboration
                    + 0.08 * completeness,
                ),
                4,
            )
        return sorted(merged.values(), key=lambda item: (item.score, item.year or 0), reverse=True)

    @staticmethod
    def _contains_chinese(value: str) -> bool:
        return bool(re.search(r"[\u4e00-\u9fff]", value))

    @staticmethod
    def _paper_language(paper: Paper) -> str:
        text = f"{paper.title} {paper.abstract}"
        chinese = len(re.findall(r"[\u4e00-\u9fff]", text))
        latin = len(re.findall(r"[A-Za-z]", text))
        if chinese >= 4 and latin >= 12:
            return "mixed"
        if chinese >= 4:
            return "zh"
        if latin >= 12:
            return "en"
        return paper.language if paper.language in {"zh", "en", "mixed"} else "unknown"

    @staticmethod
    def _facets(papers: List[Paper]) -> Dict[str, int]:
        return {
            "all": len(papers),
            "zh": sum(p.language == "zh" for p in papers),
            "en": sum(p.language == "en" for p in papers),
            "mixed": sum(p.language == "mixed" for p in papers),
            "with_abstract": sum(len(p.abstract.strip()) >= 20 for p in papers),
            "citation_only": sum(len(p.abstract.strip()) < 20 for p in papers),
            "open_access": sum(p.open_access is True for p in papers),
        }

    @staticmethod
    def _quality(
        papers: List[Paper], source_status: Dict[str, str], raw_count: int, merged_count: int
    ) -> Dict[str, object]:
        count = len(papers)
        successful = sum(str(value).startswith("ok") for value in source_status.values())
        abstract_coverage = sum(len(p.abstract.strip()) >= 20 for p in papers) / count if count else 0
        doi_coverage = sum(bool(p.doi) for p in papers) / count if count else 0
        corroborated = sum(len(p.sources) >= 2 for p in papers)
        deduplicated = max(0, raw_count - merged_count)
        mean_relevance = sum(p.score for p in papers) / count if count else 0
        score = (
            0.30 * min(1.0, successful / 3)
            + 0.27 * abstract_coverage
            + 0.18 * doi_coverage
            + 0.15 * min(1.0, mean_relevance / 0.65)
            + 0.10 * min(1.0, corroborated / max(1, count // 3 or 1))
        )
        label = "高" if score >= 0.75 else "中" if score >= 0.48 else "有限"
        return {
            "score": round(score, 3),
            "label": label,
            "successful_sources": successful,
            "requested_sources": len(source_status),
            "abstract_coverage": round(abstract_coverage, 3),
            "doi_coverage": round(doi_coverage, 3),
            "corroborated_records": corroborated,
            "deduplicated_records": deduplicated,
            "mean_relevance": round(mean_relevance, 3),
            "interpretation": "这是本轮元数据完整度与多源一致性指标，不是论文质量评分。",
        }

    @staticmethod
    def _filter_and_sort(request: SearchRequest, papers: List[Paper]) -> List[Paper]:
        filtered = [
            paper
            for paper in papers
            if (request.language == "any" or paper.language == request.language)
            and (
                request.has_abstract is None
                or (len(paper.abstract.strip()) >= 20) is request.has_abstract
            )
            and (not request.open_access_only or paper.open_access is True)
            and (paper.citation_count or 0) >= request.min_citations
        ]
        if request.sort_by == "newest":
            return sorted(filtered, key=lambda p: (p.year or 0, p.score), reverse=True)
        if request.sort_by == "citations":
            return sorted(filtered, key=lambda p: (p.citation_count or 0, p.score), reverse=True)
        if request.sort_by == "completeness":
            return sorted(
                filtered,
                key=lambda p: (bool(p.abstract), p.open_access is True, len(p.sources), p.score),
                reverse=True,
            )
        return filtered
