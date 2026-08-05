from __future__ import annotations

import json
from typing import List, Optional

from ..config import Settings
from ..db import Database
from ..models import Policy, PolicySource
from ..text_utils import cosine_similarity


class PolicyService:
    def __init__(self, config: Settings, db: Optional[Database] = None):
        self.config = config
        self.db = db
        with config.policy_path.open("r", encoding="utf-8") as handle:
            self._policies = [Policy.model_validate(item) for item in json.load(handle)]
        with config.policy_sources_path.open("r", encoding="utf-8") as handle:
            self._sources = [PolicySource.model_validate(item) for item in json.load(handle)]

    def list(self, query: str = "", tag: Optional[str] = None) -> List[Policy]:
        policies = self._all_policies()
        if tag:
            policies = [p for p in policies if tag.lower() in {t.lower() for t in p.tags}]
        if query.strip():
            ranked = []
            for policy in policies:
                text = " ".join([policy.title, policy.summary] + policy.signals + policy.tags)
                score = cosine_similarity(query, text)
                if score > 0:
                    ranked.append((score, policy))
            policies = [policy for _, policy in sorted(ranked, key=lambda pair: pair[0], reverse=True)]
        return sorted(policies, key=lambda p: p.published_at, reverse=True) if not query else policies

    def get_many(self, ids: List[str]) -> List[Policy]:
        wanted = set(ids)
        return [p for p in self._all_policies() if p.id in wanted]

    def _all_policies(self) -> List[Policy]:
        if not self.db:
            return self._policies
        combined = {str(policy.url): policy for policy in self._policies}
        for record in self.db.approved_policies():
            try:
                policy = Policy(
                    id=f"dynamic-{record['id']}",
                    title=record["title"],
                    issuer=record["issuer"],
                    published_at=record["published_at"],
                    url=record["url"],
                    summary=record["summary"],
                    signals=record["signals"],
                    tags=record["tags"],
                    source_tier="official-reviewed",
                )
            except ValueError:
                continue
            combined[str(policy.url)] = policy
        return list(combined.values())

    def sources(self, query: str = "") -> List[PolicySource]:
        if not query.strip():
            return self._sources
        needle = query.casefold()
        return [
            source
            for source in self._sources
            if needle
            in " ".join(
                [source.sector, source.authority, source.portal_name, source.scope]
                + source.keywords
            ).casefold()
        ]

    def source(self, source_id: str) -> Optional[PolicySource]:
        return next((source for source in self._sources if source.id == source_id), None)
