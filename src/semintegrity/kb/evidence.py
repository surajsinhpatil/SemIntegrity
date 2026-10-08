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
import re
from functools import lru_cache
from typing import Any

from ..schemas.constraint import Evidence
from ..utils.logging import get_logger
from .wikidata import WikidataClient, parse_wikidata_time

log = get_logger(__name__)

WD_ITEM = "https://www.wikidata.org/wiki/{qid}"
WDQS = "https://query.wikidata.org/"

SUPPORTED_KINDS = frozenset(
    {"claim", "claim_literal", "claim_time", "claim_interval", "claim_interval_end",
     "claim_point_in_time", "claim_qualifier_time", "claim_cardinality", "entity_exists",
     "sparql_count"}
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

    if kind == "claim_interval_end":
        # The P582 END qualifier. §4.3 requires BOTH date qualifiers of a temporal
        # constraint ("P580 start time, P582 end time"), and axis 6 is
        # "Interval boundary" — a TERMINATING date. `claim_interval` reads only
        # `start_time`, so until now no check could verify the very qualifier the
        # policy names. `TimeQualifiedClaim` already carries `end_time`; this adds
        # the reader, and introduces no new evidence requirement.
        value_qid = check["value_qid"]
        expect_year = int(check["expect_year"])
        ends = [parse_wikidata_time(c.end_time) for c in claims if c.value_qid == value_qid]
        years = [d.year for d in ends if d]
        return Evidence(**common, observed_value=", ".join(map(str, years)),
                        supports_gold=(expect_year in years),
                        comparison=(f"{qid} {prop}={value_qid} end year(s) {years}; "
                                    f"expected {expect_year}"))

    if kind == "claim_qualifier_time":
        # A time-valued qualifier named by the CHECK rather than by this module.
        # Wikidata dates some facts on qualifiers other than P580/P582/P585 —
        # P574 ("year of publication of taxon name") sits on P225 — so without
        # this the only date such a fact has is unreadable. Generalises
        # claim_interval_end and claim_point_in_time rather than adding a third
        # per-property reader; introduces NO new evidence requirement (ADR-0020).
        qual_prop = str(check["qualifier_property"])
        expect_year = int(check["expect_year"])
        want_qid = check.get("value_qid")
        want_lit = check.get("value_literal")
        selected = [
            c for c in claims
            if (want_qid is None or c.value_qid == want_qid)
            and (want_lit is None or str(c.value_literal or "").strip() == str(want_lit).strip())
        ]
        dates = [parse_wikidata_time(c.qualifier_times.get(qual_prop)) for c in selected]
        years = [d.year for d in dates if d]
        target = want_qid or want_lit or "(any value)"
        return Evidence(**common, observed_value=", ".join(map(str, years)),
                        supports_gold=(expect_year in years),
                        comparison=(f"{qid} {prop}={target} qualifier {qual_prop} "
                                    f"year(s) {years}; expected {expect_year}"))

    if kind == "claim_point_in_time":
        # The P585 POINT IN TIME qualifier. A statement that records an
        # assessment rather than a period — a conservation status, a
        # measurement, a census — carries P585 and no P580/P582, so until now no
        # declared check could read the only date such a fact has. Added for the
        # same reason and on the same terms as `claim_interval_end`: it reads a
        # qualifier that `TimeQualifiedClaim` now carries, and introduces NO new
        # evidence requirement. See ADR-0020.
        value_qid = check["value_qid"]
        expect_year = int(check["expect_year"])
        dates = [
            parse_wikidata_time(c.point_in_time) for c in claims if c.value_qid == value_qid
        ]
        years = [d.year for d in dates if d]
        return Evidence(**common, observed_value=", ".join(map(str, years)),
                        supports_gold=(expect_year in years),
                        comparison=(f"{qid} {prop}={value_qid} point-in-time year(s) {years}; "
                                    f"expected {expect_year}"))

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


class QueryRegistryError(ValueError):
    """Raised when a registered query cannot be resolved for the given parameters."""


@lru_cache(maxsize=1)
def _sparql_registry() -> dict[str, Any]:
    """The registered queries, from ``configs/kb/sparql_queries.yaml``.

    Held in configuration rather than in this module: a query that decides
    whether a benchmark fact reaches EVIDENCE_VERIFIED is part of the method and
    belongs beside the rest of it. This changes WHERE queries live, not the
    evidence methodology.
    """
    from ..utils.config import load_config

    return load_config("configs/kb/sparql_queries.yaml").data


def registered_queries() -> list[str]:
    return sorted(_sparql_registry()["queries"])


def resolve_query(name: str, params: dict[str, str] | None = None) -> str:
    """Return the deterministic text of a registered query.

    Substitution is by declared parameter name only, and every value must match
    the pattern its parameter type declares (``^Q[0-9]+$`` or ``^P[0-9]+$``). So
    query text cannot be assembled from arbitrary strings: a typo or an injected
    fragment is refused rather than silently queried.
    """
    reg = _sparql_registry()
    queries = reg["queries"]
    if name not in queries:
        raise QueryRegistryError(
            f"no SPARQL query registered as {name!r}; known: {sorted(queries)}. "
            "Register it in configs/kb/sparql_queries.yaml — never inline a query "
            "in authoring code."
        )
    entry = queries[name]
    declared: dict[str, str] = entry.get("parameters") or {}
    supplied = dict(params or {})

    missing = sorted(set(declared) - set(supplied))
    extra = sorted(set(supplied) - set(declared))
    if missing or extra:
        raise QueryRegistryError(
            f"query {name!r} declares parameters {sorted(declared)}; "
            f"missing={missing} unexpected={extra}"
        )

    patterns = reg["parameter_patterns"]
    text = str(entry["query"])
    for key, kind in declared.items():
        if kind not in patterns:
            raise QueryRegistryError(
                f"query {name!r} parameter {key!r} has unknown type {kind!r}; "
                f"known: {sorted(patterns)}"
            )
        value = str(supplied[key])
        if not re.fullmatch(patterns[kind], value):
            raise QueryRegistryError(
                f"query {name!r} parameter {key}={value!r} does not match the "
                f"{kind} pattern {patterns[kind]!r}"
            )
        text = text.replace("{" + key + "}", value)

    leftover = re.findall(r"\{(\w+)\}", text)
    if leftover:
        raise QueryRegistryError(
            f"query {name!r} still has unbound placeholders {sorted(set(leftover))}"
        )
    return text


def _sparql_count(client: WikidataClient, check: dict) -> tuple[int, str]:
    name = check["query_name"]
    text = resolve_query(name, check.get("query_params"))
    payload = client.sparql(text)
    rows = payload["results"]["bindings"]
    label_key = _sparql_registry()["queries"][name].get("count_label", "itemLabel")
    labels = [r.get(label_key, {}).get("value", "?") for r in rows]
    return len(rows), ", ".join(labels) or "no rows"
