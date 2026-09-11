"""Knowledge-base adapters implementing the D0 :class:`KnowledgeBase` protocol.

Two implementations:

``WikidataKB``  backed by the frozen cache, so a Slurm job resolves facts with
                no network access.
``StaticKB``    an explicit in-memory dictionary, for predicate audits and tests
                where the point is to control the facts exactly.

Both are read-only. A predicate can never mutate the knowledge base, which is
what keeps D0's determinism claim honest.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from .cache import KBCache
from .wikidata import WikidataClient, parse_wikidata_time


class WikidataKB:
    """D0 knowledge base backed by the frozen Wikidata snapshot."""

    def __init__(self, cache: KBCache) -> None:
        self.client = WikidataClient(cache)
        self._facts_used: list[str] = []

    @property
    def facts_used(self) -> tuple[str, ...]:
        """Every lookup made, for the audit trail on a D0 verdict."""
        return tuple(self._facts_used)

    def entity_label(self, qid: str) -> str:
        self._facts_used.append(f"label({qid})")
        return self.client.get_entity(qid).label

    def sitelinks(self, qid: str) -> int:
        self._facts_used.append(f"sitelinks({qid})")
        return self.client.get_entity(qid).sitelinks

    def claim_values(self, qid: str, property_id: str) -> list[str]:
        self._facts_used.append(f"{property_id}({qid})")
        return [
            c.value_qid or c.value_literal or ""
            for c in self.client.get_claims(qid, property_id)
            if (c.value_qid or c.value_literal)
        ]

    def claim_interval(
        self, qid: str, property_id: str, value_qid: str
    ) -> tuple[dt.date | None, dt.date | None]:
        self._facts_used.append(f"{property_id}({qid}={value_qid}).interval")
        for c in self.client.get_claims(qid, property_id):
            if c.value_qid == value_qid:
                return parse_wikidata_time(c.start_time), parse_wikidata_time(c.end_time)
        return None, None


@dataclass(slots=True)
class StaticKB:
    """An explicit knowledge base. Used by predicate audits and unit tests."""

    labels: dict[str, str] = field(default_factory=dict)
    sitelink_counts: dict[str, int] = field(default_factory=dict)
    claims: dict[tuple[str, str], list[str]] = field(default_factory=dict)
    intervals: dict[tuple[str, str, str], tuple[dt.date | None, dt.date | None]] = field(
        default_factory=dict
    )

    def entity_label(self, qid: str) -> str:
        if qid not in self.labels:
            raise KeyError(f"StaticKB has no label for {qid}")
        return self.labels[qid]

    def sitelinks(self, qid: str) -> int:
        if qid not in self.sitelink_counts:
            raise KeyError(f"StaticKB has no sitelink count for {qid}")
        return self.sitelink_counts[qid]

    def claim_values(self, qid: str, property_id: str) -> list[str]:
        return list(self.claims.get((qid, property_id), []))

    def claim_interval(
        self, qid: str, property_id: str, value_qid: str
    ) -> tuple[dt.date | None, dt.date | None]:
        return self.intervals.get((qid, property_id, value_qid), (None, None))
