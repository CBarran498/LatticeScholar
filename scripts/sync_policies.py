"""Run incremental official-policy discovery for cron or manual maintenance."""

from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
from pathlib import Path

from latticescholar.config import Settings
from latticescholar.db import Database
from latticescholar.services.policies import PolicyService
from latticescholar.services.policy_sync import PolicySyncService


async def run() -> None:
    parser = argparse.ArgumentParser(
        description="Discover official policy links and place changes in the review queue"
    )
    parser.add_argument(
        "--source",
        action="append",
        dest="sources",
        help="Policy source id; repeat up to five times",
    )
    parser.add_argument("--dry-run", action="store_true", help="Use a temporary database")
    parser.add_argument("--json-report", help="Optional path for a machine-readable report")
    args = parser.parse_args()
    source_ids = args.sources or ["state-council"]
    if args.dry_run:
        temporary = tempfile.TemporaryDirectory(prefix="latticescholar-policy-")
        data_dir = Path(temporary.name)
    else:
        temporary = None
        data_dir = Settings().data_dir
    config = Settings(data_dir=data_dir)
    db = Database(config.database_path)
    policies = PolicyService(config, db)
    service = PolicySyncService(config, db, policies)
    results = await service.sync(source_ids)
    report = {"runs": results, "status": db.policy_sync_status(), "dry_run": args.dry_run}
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.json_report:
        Path(args.json_report).write_text(rendered + "\n", encoding="utf-8")
    if temporary:
        temporary.cleanup()
    if any(item["status"] == "error" for item in results):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(run())
