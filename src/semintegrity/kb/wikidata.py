"""Wikidata client (proposal §4.3).

Every call goes through :class:`~semintegrity.kb.cache.KBCache`, so a run on a
compute node with no network resolves from the frozen snapshot and a run on the
login node fills that snapshot. The client never bypasses the cache.

Wikidata is the primary source but is explicitly **not** treated as absolute
truth (§4.3): historical and temporal facts require a second, corroborating
source, which :mod:`semintegrity.kb.corroboration` tracks.
"""

from __future__ import annotations

import datetime as dt
import re
import time
from dataclasses import dataclass, field
from typing import Any

from ..utils.logging import get_logger
from .cache import CacheMiss, CacheMode, KBCache

log = get_logger(__name__)

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"

#: Temporal qualifiers the proposal requires for C4 (§4.3).
P_START_TIME = "P580"
P_END_TIME = "P582"
P_POINT_IN_TIME = "P585"

QID_RE = re.compile(r"^Q\d+$")

#: Identifies this project to the Wikidata API, as their etiquette requires.
USER_AGENT = "SemIntegrity/0.1 (academic research; BITS Pilani) python-requests"


class WikidataError(RuntimeError):
    pass


@dataclass(slots=True)
class EntityRecord:
    """A resolved Wikidata item."""

    qid: str
    label: str
    description: str = ""
    aliases: list[str] = field(default_factory=list)
    sitelinks: int = 0
    retrieved: dt.date | None = None

    @classmethod
    def from_api(cls, qid: str, payload: dict[str, Any], lang: str = "en") -> EntityRecord:
        ent = payload["entities"][qid]
        if ent.get("missing") is not None:
            raise WikidataError(f"{qid} does not exist on Wikidata")
        labels = ent.get("labels", {})
        descs = ent.get("descriptions", {})
        aliases = [a["value"] for a in ent.get("aliases", {}).get(lang, [])]
        return cls(
            qid=qid,
            label=labels.get(lang, {}).get("value", ""),
            description=descs.get(lang, {}).get("value", ""),
            aliases=aliases,
            sitelinks=len(ent.get("sitelinks", {})),
            retrieved=dt.date.today(),
        )


@dataclass(slots=True)
class TimeQualifiedClaim:
    """One statement with its P580/P582 validity interval (§4.3)."""

    property_id: str
    value_qid: str | None
    value_literal: str | None
    start_time: str | None
    end_time: str | None
    rank: str = "normal"


class WikidataClient:
    """Cache-mediated access to Wikidata.

    Parameters
    ----------
    cache:
        The snapshot to read from and (in LIVE mode) write to.
    lang:
        Label/alias language. English throughout; recorded so it is not implicit.
    min_interval_s:
        Politeness delay between live requests. Wikidata asks for modest rates
        and this project needs only a few hundred calls in total.
    """

    def __init__(self, cache: KBCache, *, lang: str = "en", min_interval_s: float = 1.0) -> None:
        self.cache = cache
        self.lang = lang
        self.min_interval_s = min_interval_s
        self._last_request = 0.0

    # -- transport ----------------------------------------------------------
    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.min_interval_s:
            time.sleep(self.min_interval_s - elapsed)
        self._last_request = time.monotonic()

    def _fetch(self, url: str, params: dict[str, Any]) -> Any:
        if self.cache.mode is CacheMode.FROZEN:  # pragma: no cover - guarded upstream
            raise RuntimeError("a FROZEN client must never reach the network")
        try:
            import requests
        except ImportError as exc:  # pragma: no cover
            raise WikidataError("requests is required for live Wikidata access") from exc
        self._throttle()
        resp = requests.get(
            url, params=params, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}, timeout=60
        )
        if resp.status_code != 200:
            raise WikidataError(f"{url} returned HTTP {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    def _cached(self, kind: str, request: dict[str, Any], url: str, params: dict[str, Any]) -> Any:
        """Cache-first fetch. In FROZEN mode a miss is an error, never a fetch."""
        if self.cache.mode is not CacheMode.REFRESH:
            entry = self.cache.get(kind, request)
            if entry is not None:
                return entry.payload
        if self.cache.mode is CacheMode.FROZEN:
            raise CacheMiss(
                f"frozen cache miss for {kind} {request}; snapshot it from a networked node first"
            )
        payload = self._fetch(url, params)
        self.cache.put(kind, request, payload, source=url)
        return payload

    # -- public API ---------------------------------------------------------
    def get_entity(self, qid: str) -> EntityRecord:
        """Resolve one item: label, description, aliases and sitelink count."""
        if not QID_RE.match(qid):
            raise ValueError(f"malformed QID {qid!r}")
        request = {"qid": qid, "lang": self.lang}
        payload = self._cached(
            "entity",
            request,
            WIKIDATA_API,
            {
                "action": "wbgetentities",
                "ids": qid,
                "props": "labels|descriptions|aliases|sitelinks|claims",
                "languages": self.lang,
                "format": "json",
            },
        )
        return EntityRecord.from_api(qid, payload, self.lang)

    def sitelink_count(self, qid: str) -> int:
        """Entity familiarity metric (§4.3).

        Sitelinks are preferred to pageviews because they are deterministic,
        available from the knowledge base directly, and not time-sensitive.
        """
        return self.get_entity(qid).sitelinks

    def get_claims(self, qid: str, property_id: str) -> list[TimeQualifiedClaim]:
        """Statements for one property, with their P580/P582 qualifiers."""
        request = {"qid": qid, "lang": self.lang}
        payload = self._cached(
            "entity",
            request,
            WIKIDATA_API,
            {
                "action": "wbgetentities",
                "ids": qid,
                "props": "labels|descriptions|aliases|sitelinks|claims",
                "languages": self.lang,
                "format": "json",
            },
        )
        ent = payload["entities"][qid]
        out: list[TimeQualifiedClaim] = []
        for statement in ent.get("claims", {}).get(property_id, []):
            main = statement.get("mainsnak", {}).get("datavalue", {}).get("value")
            value_qid = main.get("id") if isinstance(main, dict) and "id" in main else None
            value_literal = None
            if isinstance(main, dict) and "time" in main:
                value_literal = main["time"]
            elif isinstance(main, str):
                value_literal = main
            quals = statement.get("qualifiers", {})
            out.append(
                TimeQualifiedClaim(
                    property_id=property_id,
                    value_qid=value_qid,
                    value_literal=value_literal,
                    start_time=_qualifier_time(quals, P_START_TIME),
                    end_time=_qualifier_time(quals, P_END_TIME),
                    rank=statement.get("rank", "normal"),
                )
            )
        return out

    def sparql(self, query: str) -> dict[str, Any]:
        """Run a SPARQL query through the cache.

        The query text is the cache key, so whitespace changes create new
        entries. Queries are therefore kept in
        ``src/semintegrity/kb/queries/`` rather than composed inline.
        """
        request = {"query": query.strip()}
        return self._cached(
            "sparql", request, WIKIDATA_SPARQL, {"query": query.strip(), "format": "json"}
        )


def _qualifier_time(qualifiers: dict[str, Any], prop: str) -> str | None:
    for q in qualifiers.get(prop, []):
        value = q.get("datavalue", {}).get("value", {})
        if isinstance(value, dict) and "time" in value:
            return value["time"]
    return None


def parse_wikidata_time(value: str | None) -> dt.date | None:
    """Parse a Wikidata time literal (``+1901-01-01T00:00:00Z``) into a date.

    Wikidata uses ``00`` for unknown month/day, which ``date`` cannot represent;
    those are clamped to January / the 1st and the loss of precision is the
    caller's to record in ``TemporalValidity.precision``.
    """
    if not value:
        return None
    m = re.match(r"^([+-])(\d{4,})-(\d{2})-(\d{2})T", value)
    if not m:
        return None
    sign, year, month, day = m.groups()
    if sign == "-":
        return None  # BCE dates are out of scope for this benchmark
    return dt.date(int(year), max(int(month), 1), max(int(day), 1))
