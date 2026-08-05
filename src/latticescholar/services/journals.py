from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Dict, List

from ..models import JournalMatchRequest, JournalRecommendation, SearchRequest
from ..text_utils import cosine_similarity, median_int
from .sources import ScholarlySources


class JournalService:
    def __init__(self, sources: ScholarlySources):
        self.sources = sources

    async def match(self, request: JournalMatchRequest) -> List[JournalRecommendation]:
        query = (request.title + " " + request.abstract).strip()[:500]
        source_names = ["crossref", "semantic_scholar", "arxiv", "pubmed"]
        config = getattr(self.sources, "config", None)
        if config and config.openalex_api_key:
            source_names.append("openalex")
        if config and config.wos_api_key:
            source_names.append("web_of_science")
        search_request = SearchRequest(query=query, limit=50, sources=source_names)
        if hasattr(self.sources, "search_many"):
            results, statuses = await self.sources.search_many(search_request)
        else:
            results = {"crossref": await self.sources.search_crossref(search_request)}
            statuses = {"crossref": f"ok ({len(results['crossref'])})"}
        papers = [paper for items in results.values() for paper in items] + request.papers
        active_sources = sorted({source for paper in papers for source in paper.sources})
        groups: Dict[str, List[Any]] = defaultdict(list)
        for paper in papers:
            if paper.venue:
                groups[paper.venue].append(paper)
        recommendations = []
        for journal, items in groups.items():
            topical = sum(cosine_similarity(query, p.title + " " + p.abstract) for p in items) / len(items)
            evidence_signal = min(1.0, math.log1p(len(items)) / math.log(8))
            citations = [max(p.citation_count or 0, 0) for p in items]
            citation_signal = min(1.0, math.log1p(sum(citations) / len(citations)) / 8)
            years = [p.year for p in items if p.year]
            recency = 0.0
            if years:
                recency = max(0.0, min(1.0, (median_int(years) - 2010) / 16))
            score = min(1.0, 0.62 * topical + 0.2 * evidence_signal + 0.1 * recency + 0.08 * citation_signal)
            dois = [p.doi for p in items if p.doi][:5]
            recommendations.append(
                JournalRecommendation(
                    journal=journal,
                    issn=list(dict.fromkeys(code for paper in items for code in paper.issn)),
                    score=round(score, 4),
                    topical_fit=round(topical, 4),
                    evidence_count=len(items),
                    median_year=median_int(years) if years else None,
                    citation_signal=round(citation_signal, 4),
                    reasons=[
                        f"在多源证据样本中找到 {len(items)} 篇主题相关论文",
                        f"标题/摘要词汇匹配度为 {topical:.0%}",
                        "来源覆盖：" + "、".join(active_sources[:8]),
                        "每项推荐均保留样本 DOI，便于人工复核 scope",
                    ],
                    evidence_dois=dois,
                    caveats=[
                        "这不是录用概率预测，也不包含专有影响因子或审稿周期。",
                        "投稿前必须核验期刊官网的 scope、文章类型、费用与预警信息。",
                        "接口状态：" + "；".join(f"{k}={v}" for k, v in statuses.items()),
                    ],
                )
            )
        recommendations.sort(key=lambda item: (item.score, item.evidence_count), reverse=True)
        return recommendations[: request.limit]
