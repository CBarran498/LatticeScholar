from __future__ import annotations

import asyncio
import hashlib
import html
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urldefrag, urljoin, urlparse

import httpx

from ..config import Settings
from ..db import Database
from ..models import PolicySource
from .policies import PolicyService

POLICY_MARKERS = (
    "政策",
    "通知",
    "意见",
    "办法",
    "规划",
    "方案",
    "指南",
    "公告",
    "条例",
    "规定",
    "细则",
    "标准",
    "决定",
    "公示",
    "申报",
    "项目",
    "基金",
    "实施",
)
DATE_PATTERN = re.compile(r"(?P<year>20\d{2})[-/.年](?P<month>\d{1,2})[-/.月](?P<day>\d{1,2})")
STATE_COUNCIL_SEARCH_URL = "https://sousuo.www.gov.cn/search-gov/data"


class _LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._href: Optional[str] = None
        self._parts: List[str] = []
        self.links: List[tuple] = []

    def handle_starttag(self, tag: str, attrs: List[tuple]) -> None:
        if tag.lower() == "a" and self._href is None:
            attributes = dict(attrs)
            self._href = attributes.get("href")
            self._parts = [attributes.get("title", "")]

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href is not None:
            text = " ".join(part.strip() for part in self._parts if part.strip())
            self.links.append((self._href, text))
            self._href = None
            self._parts = []


def _clean_title(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip(" \t\r\n-|_·")


def _date_from_text(value: str) -> str:
    match = DATE_PATTERN.search(value)
    if not match:
        return ""
    try:
        return datetime(
            int(match.group("year")), int(match.group("month")), int(match.group("day"))
        ).date().isoformat()
    except ValueError:
        return ""


def _allowed_link(base_url: str, target_url: str) -> bool:
    base = urlparse(base_url)
    target = urlparse(target_url)
    if target.scheme not in {"http", "https"} or not target.hostname or not base.hostname:
        return False
    base_host = base.hostname.casefold()
    target_host = target.hostname.casefold()
    return (
        target_host == base_host
        or target_host.endswith("." + base_host)
        or base_host.endswith("." + target_host)
    )


def discover_policy_links(source: PolicySource, page_html: str) -> List[Dict[str, Any]]:
    collector = _LinkCollector()
    collector.feed(page_html)
    discovered: Dict[str, Dict[str, Any]] = {}
    for raw_href, raw_title in collector.links:
        title = _clean_title(raw_title)
        if not (8 <= len(title) <= 300) or not any(marker in title for marker in POLICY_MARKERS):
            continue
        url, _ = urldefrag(urljoin(str(source.portal_url), raw_href))
        if not _allowed_link(str(source.portal_url), url):
            continue
        external_id = hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
        published_at = _date_from_text(title + " " + raw_href)
        content_hash = hashlib.sha256(
            f"{title}\n{source.authority}\n{published_at}\n{url}".encode()
        ).hexdigest()
        discovered[external_id] = {
            "source_id": source.id,
            "external_id": external_id,
            "title": title,
            "issuer": source.authority,
            "published_at": published_at,
            "url": url,
            "summary": "自动发现的官方页面，发布前必须人工核验政策性质、日期、效力与适用范围。",
            "signals": [],
            "tags": list(dict.fromkeys([source.sector] + source.keywords))[:12],
            "content_hash": content_hash,
            "raw": {"portal": str(source.portal_url), "discovery_method": "official_index"},
        }
        if len(discovered) >= 200:
            break
    return list(discovered.values())


def discover_state_council_records(
    source: PolicySource, payload: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Normalize the official State Council policy-library JSON response."""
    search = payload.get("searchVO") or {}
    groups = search.get("catMap") or {}
    records: List[dict] = []
    if isinstance(search.get("listVO"), list):
        records.extend(search["listVO"])
    if isinstance(groups, dict):
        for group in groups.values():
            if isinstance(group, dict) and isinstance(group.get("listVO"), list):
                records.extend(group["listVO"])
    discovered: Dict[str, Dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        raw_title = str(record.get("title") or "")
        title = _clean_title(re.split(r"<br\s*/?>", raw_title, maxsplit=1, flags=re.I)[0])
        url, _ = urldefrag(str(record.get("url") or ""))
        if not (4 <= len(title) <= 300) or not _allowed_link(str(source.portal_url), url):
            continue
        issuer = _clean_title(str(record.get("puborg") or source.authority))
        published_at = _date_from_text(str(record.get("pubtimeStr") or ""))
        summary = _clean_title(re.sub(r"<[^>]+>", " ", str(record.get("summary") or "")))
        summary = summary[:1200] or "国务院政策文件库收录条目，发布前必须核验原文与现行效力。"
        official_id = str(record.get("id") or record.get("index") or "").strip()
        external_id = official_id or hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
        category = _clean_title(str(record.get("childtype") or ""))
        category_tags = [item.strip() for item in re.split(r"[\\/、]", category) if item.strip()]
        tags = list(dict.fromkeys([source.sector] + source.keywords + category_tags))[:12]
        content_hash = hashlib.sha256(
            f"{title}\n{issuer}\n{published_at}\n{url}\n{summary}".encode()
        ).hexdigest()
        discovered[external_id] = {
            "source_id": source.id,
            "external_id": external_id,
            "title": title,
            "issuer": issuer,
            "published_at": published_at,
            "url": url,
            "summary": summary,
            "signals": [],
            "tags": tags,
            "content_hash": content_hash,
            "raw": {
                "portal": str(source.portal_url),
                "discovery_method": "official_state_council_json",
                "document_number": record.get("pcode") or "",
                "category": category,
                "effect_status": record.get("shixiao") or "",
            },
        }
        if len(discovered) >= 200:
            break
    return list(discovered.values())


class PolicySyncService:
    def __init__(self, config: Settings, db: Database, policies: PolicyService):
        self.config = config
        self.db = db
        self.policies = policies

    async def sync(self, source_ids: Iterable[str]) -> List[dict]:
        results = []
        for source_id in list(dict.fromkeys(source_ids))[:5]:
            results.append(await self.sync_source(source_id))
        return results

    async def sync_source(self, source_id: str) -> dict:
        source = self.policies.source(source_id)
        if not source:
            raise ValueError(f"未知政策来源：{source_id}")
        started_at = datetime.now(timezone.utc).isoformat()
        discovered = 0
        changed = 0
        error = ""
        status = "ok"
        try:
            async with httpx.AsyncClient(
                timeout=self.config.request_timeout_seconds,
                follow_redirects=True,
                headers={
                    "User-Agent": "LatticeScholar-Policy-Monitor/0.6 (+open-source research tool)",
                    "Accept": "application/json,text/html,application/xhtml+xml",
                },
            ) as client:
                if source.id == "state-council":
                    response = await client.get(
                        STATE_COUNCIL_SEARCH_URL,
                        params={
                            "t": "zhengcelibrary",
                            "q": "",
                            "timetype": "",
                            "mintime": "",
                            "maxtime": "",
                            "sort": "score",
                            "sortType": 1,
                            "searchfield": "title",
                            "p": 1,
                            "n": 20,
                            "type": "gwyzcwjk",
                        },
                    )
                else:
                    response = await client.get(str(source.portal_url))
            response.raise_for_status()
            if not _allowed_link(str(source.portal_url), str(response.url)):
                raise ValueError("政策门户重定向到了未授权域名")
            if len(response.content) > 5 * 1024 * 1024:
                raise ValueError("政策门户页面超过 5 MB 安全上限")
            if source.id == "state-council":
                try:
                    payload = response.json()
                except ValueError as exc:
                    raise ValueError("国务院政策文件库没有返回有效 JSON") from exc
                if str(payload.get("code")) != "200":
                    raise ValueError("国务院政策文件库返回了非成功状态")
                candidates = discover_state_council_records(source, payload)
            else:
                content_type = response.headers.get("content-type", "")
                if "html" not in content_type.lower() and not response.text.lstrip().startswith("<"):
                    raise ValueError("政策门户没有返回 HTML 页面")
                candidates = discover_policy_links(source, response.text)
            if not candidates:
                raise ValueError("官方政策源未发现候选；门户结构可能已经变化")
            discovered = len(candidates)
            for candidate in candidates:
                if self.db.upsert_policy_candidate(candidate) in {"new", "changed"}:
                    changed += 1
        except (httpx.HTTPError, ValueError) as exc:
            status = "error"
            error = str(exc)
        return self.db.add_policy_sync_run(
            source.id, status, discovered, changed, error, started_at
        )


async def scheduled_policy_sync(
    service: PolicySyncService, source_ids: List[str], interval_hours: float
) -> None:
    await asyncio.sleep(60)
    while True:
        await service.sync(source_ids)
        await asyncio.sleep(max(0.25, interval_hours) * 3600)
