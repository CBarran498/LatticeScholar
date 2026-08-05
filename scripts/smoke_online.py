"""Small, read-only online smoke test for scholarly source availability."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from latticescholar.config import Settings
from latticescholar.db import Database
from latticescholar.models import SearchRequest
from latticescholar.services.literature import LiteratureService
from latticescholar.services.sources import ScholarlySources


async def main() -> None:
    with tempfile.TemporaryDirectory(prefix="latticescholar-smoke-") as tmp:
        config = Settings(data_dir=Path(tmp), request_timeout_seconds=25)
        sources = ScholarlySources(config)
        try:
            service = LiteratureService(config, Database(config.database_path), sources)
            result = await service.search(
                SearchRequest(
                    query="resource efficient machine learning",
                    limit=5,
                    sources=["crossref", "semantic_scholar", "arxiv", "pubmed"],
                    year_from=2022,
                )
            )
            print("source_status:", result.source_status)
            print("papers:", len(result.papers))
            if not result.papers:
                raise SystemExit("Smoke test returned no papers")
            print("top_result:", result.papers[0].title)
        finally:
            await sources.close()


if __name__ == "__main__":
    asyncio.run(main())
