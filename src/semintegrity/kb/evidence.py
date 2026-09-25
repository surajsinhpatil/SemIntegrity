"""Machine-checked evidence against Wikidata (proposal §4.3).

Each authored constraint declares ``evidence_checks``; this module runs them and
returns :class:`~semintegrity.schemas.constraint.Evidence` records saying what
was asked, what came back, and whether it agrees with the gold answer.

Two properties matter more than coverage:

* **A failed check is a result, not an error.** A wrong QID, a missing property
  or a disagreeing value produces ``supports_gold=False`` with the observed
  value recorded, and the constraint simply stays DRAFT.
* **Nothing is inferred.** ``supports_gold`` is set by an explicit comparison
  that is written into the record in words, so a reviewer can re-check the
  judgement without re-running anything.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from ..schemas.constraint import Evidence
from ..utils.logging import get_logger
from .wikidata import WikidataClient, parse_wikidata_time

log = get_logger(__name__)

WD_ITEM = "https://www.wikidata.org/wiki/{qid}"
WDQS = "https://query.wikidata.org/"

SUPPORTED_KINDS = frozenset(
    {"claim", "claim_literal", "claim_time", "claim_interval", "claim_cardinality",
     "entity_exists", "sparql_count"}
)


def run_check(client: WikidataClient, check: dict[str, Any]) -> Evidence:
    """Run one declared evidence check. Never raises on a negative result."""
    kind = check.get("kind")
    if kind not in SUPPORTED_KINDS:
        raise ValueError(f"unknown evidence check kind {kind!r}; known: {sorted(SUPPORTED_KINDS)}")
    today = dt.date.today()
    desc = str(check.get("description", kind))

    try:
        return _dispatch(client, check, kind, desc, today)
    except Exception as exc:  # a lookup failure is evidence of absence, not a crash
        log.warning("evidence check failed", extra={"extra_fields": {"check": desc, "error": str(exc)}})
        return Evidence(
            source="wikidata", query=_query_label(check), url=_url(check), retrieved_at=today,
            observed_value="", supports_gold=False,
            comparison=f"lookup failed: {type(exc).__name__}: {exc}",
            note=desc,
        )


def _query_label(check: dict) -> str:
    if check.get("kind") == "sparql_count":
        return f"SPARQL:{check.get('query_name', 'unnamed')}"
    parts = [str(check.get("subject_qid", "")), str(check.get("property", ""))]
    if check.get("value_qid"):
        parts.append(str(check["value_qid"]))
    return " ".join(p for p in parts if p)


def _url(check: dict) -> str:
    qid = check.get("subject_qid")
    return WD_ITEM.format(qid=qid) if qid else WDQS


def _dispatch(client, check, kind, desc, today) -> Evidence:
    qid = check.get("subject_qid")
    prop = check.get("property")
    common = dict(source="wikidata", query=_query_label(check), url=_url(check),
                  retrieved_at=today, note=desc)

    if kind == "entity_exists":
        entity = client.get_entity(qid)
        return Evidence(**common, observed_value=entity.label, supports_gold=bool(entity.label),
                        comparison=f"{qid} resolves on Wikidata with label {entity.label!r}")

    if kind == "sparql_count":
        expected = int(check["expect_count"])
        n, sample = _sparql_count(client, check)
        return Evidence(**common, observed_value=f"count={n} ({sample})",
                        supports_gold=(n == expected),
                        comparison=f"SPARQL returned {n} row(s); expected exactly {expected}")

    claims = client.get_claims(qid, prop)
    if not claims:
        return Evidence(**common, observed_value="", supports_gold=False,
                        comparison=f"{qid} has no {prop} statement")

    if kind == "claim":
        expect = check["expect_qid"]
        values = [c.value_qid for c in claims if c.value_qid]
        return Evidence(**common, observed_value=", ".join(values), supports_gold=(expect in values),
                        comparison=f"{qid} {prop} -> {values}; expected to contain {expect}")

    if kind == "claim_literal":
        expect = str(check["expect_value"]).strip()
        values = [str(c.value_literal or c.value_qid or "").strip() for c in claims]
        normalised = [_num(v) for v in values]
        return Evidence(**common, observed_value=", ".join(values),
                        supports_gold=(_num(expect) in normalised),
                        comparison=f"{qid} {prop} -> {values}; expected {expect!r}")

    if kind == "claim_cardinality":
        expected = int(check["expect_count"])
        return Evidence(**common, observed_value=f"{len(claims)} statement(s)",
                        supports_gold=(len(claims) == expected),
                        comparison=f"{qid} {prop} has {len(claims)} statement(s); expected {expected}")

    if kind == "claim_time":
        expect_year = int(check["expect_year"])
        years = [d.year for d in (parse_wikidata_time(c.value_literal) for c in claims) if d]
        return Evidence(**common, observed_value=", ".join(map(str, years)),
                        supports_gold=(expect_year in years),
                        comparison=f"{qid} {prop} -> year(s) {years}; expected {expect_year}")

    # claim_interval
    value_qid = check["value_qid"]
    at_most = int(check["expect_year_at_most"])
    starts = [parse_wikidata_time(c.start_time) for c in claims if c.value_qid == value_qid]
    years = [d.year for d in starts if d]
    return Evidence(**common, observed_value=", ".join(map(str, years)),
                    supports_gold=bool(years) and min(years) <= at_most,
                    comparison=(f"{qid} {prop}={value_qid} start year(s) {years}; "
                                f"expected at least one <= {at_most}"))


def _num(value: str) -> str:
    """Compare 79 and '79' alike, without treating 'Au' as a number."""
    try:
        return str(int(float(value)))
    except (TypeError, ValueError):
        return value


_SPARQL_QUERIES: dict[str, str] = {
    # Sovereign states whose capital (P36) is Canberra (Q3114).
    "capitals_of_canberra": """
        SELECT ?country ?countryLabel WHERE {
          ?country wdt:P36 wd:Q3114 .
          ?country wdt:P31/wdt:P279* wd:Q3624078 .
          SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
        }
    """,
}


def _sparql_count(client: WikidataClient, check: dict) -> tuple[int, str]:
    name = check["query_name"]
    if name not in _SPARQL_QUERIES:
        raise KeyError(f"no SPARQL query registered as {name!r}")
    payload = client.sparql(_SPARQL_QUERIES[name])
    rows = payload["results"]["bindings"]
    labels = [r.get("countryLabel", {}).get("value", "?") for r in rows]
    return len(rows), ", ".join(labels) or "no rows"
