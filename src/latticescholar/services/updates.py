from __future__ import annotations

import re
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import httpx

from ..config import Settings
from ..db import Database


def _version_tuple(value: str) -> tuple:
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", value)
    return tuple(int(part) for part in match.groups()) if match else (0, 0, 0)


def _github_repository(value: str) -> Optional[str]:
    parsed = urlparse(value)
    if parsed.hostname not in {"github.com", "www.github.com"}:
        return None
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 2:
        return None
    owner, repo = parts[:2]
    repo = repo.removesuffix(".git")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", owner) or not re.fullmatch(
        r"[A-Za-z0-9_.-]+", repo
    ):
        return None
    return f"{owner}/{repo}"


class UpdateService:
    def __init__(self, config: Settings, db: Database):
        self.config = config
        self.db = db

    async def check(self) -> Dict[str, Any]:
        repository = _github_repository(self.config.repository_url)
        base = {
            "current_version": self.config.app_version,
            "configured": bool(repository),
            "update_available": False,
        }
        if not repository:
            return {**base, "status": "repository_not_configured"}
        cache_key = f"release:{repository}"
        cached = self.db.get_cache(cache_key)
        if cached:
            return {**base, **cached, "cache_hit": True}
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
                response = await client.get(
                    f"https://api.github.com/repos/{repository}/releases/latest",
                    headers={
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28",
                        "User-Agent": "LatticeScholar-Update-Check",
                    },
                )
            if response.status_code == 404:
                result = {"status": "no_release", "repository": repository}
            else:
                response.raise_for_status()
                data = response.json()
                latest = str(data.get("tag_name") or "")
                result = {
                    "status": "ok",
                    "repository": repository,
                    "latest_version": latest,
                    "release_url": data.get("html_url"),
                    "published_at": data.get("published_at"),
                    "update_available": _version_tuple(latest)
                    > _version_tuple(self.config.app_version),
                }
            self.db.set_cache(cache_key, result, 6 * 60 * 60)
            return {**base, **result, "cache_hit": False}
        except (httpx.HTTPError, ValueError) as exc:
            return {**base, "status": "error", "detail": str(exc)[:300]}
