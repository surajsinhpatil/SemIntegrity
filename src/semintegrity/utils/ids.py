"""Deterministic identifiers.

Every id in SemIntegrity is a pure function of the thing it names. Re-running
the authoring pipeline on unchanged inputs reproduces the same ids, so a
constraint, probe or response can be traced across files, phases and machines
without a database.

Id grammar
----------
``family_id``     ``F-<domain_code>-<nn>``            e.g. ``F-GEO-03``
``schema_id``     ``S-<class>-<nn>``                  e.g. ``S-C4-02``
``constraint_id`` ``K-<class>-<domain_code>-<nn>``    e.g. ``K-C4-GEO-03``
``probe_id``      ``<constraint_id>-P<nn>``           e.g. ``K-C4-GEO-03-P07``
``pair_id``       ``<constraint_id>-<Pa>x<Pb>``       ordered, a < b
``response_id``   ``R-<12 hex>``  content hash of (run, model, probe, sample)
``run_id``        ``<experiment>-<YYYYmmddTHHMMSSZ>-<6 hex>``
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from .hashing import sha256_obj, short

DOMAIN_CODES: dict[str, str] = {
    "geography": "GEO",
    "history": "HIS",
    "biology": "BIO",
    "public_office": "POL",
    "science_technology": "SCI",
}

CLASSES: tuple[str, ...] = ("C1", "C2", "C3", "C4")

CONSTRAINT_RE = re.compile(r"^K-(C[1-4])-([A-Z]{3})-(\d{2})$")
PROBE_RE = re.compile(r"^K-(C[1-4])-([A-Z]{3})-(\d{2})-P(\d{2})$")
FAMILY_RE = re.compile(r"^F-([A-Z]{3})-(\d{2})$")
SCHEMA_RE = re.compile(r"^S-(C[1-4])-(\d{2})$")


class IdError(ValueError):
    """Raised when an id is malformed or its components are out of range."""


def domain_code(domain: str) -> str:
    try:
        return DOMAIN_CODES[domain]
    except KeyError as exc:  # pragma: no cover - defensive
        raise IdError(f"unknown domain {domain!r}; expected one of {sorted(DOMAIN_CODES)}") from exc


def _check_class(cls: str) -> str:
    if cls not in CLASSES:
        raise IdError(f"unknown class {cls!r}; expected one of {CLASSES}")
    return cls


def family_id(domain: str, index: int) -> str:
    """``index`` is 1-based within the domain (1..6 for the 120-constraint design)."""
    if not 1 <= index <= 99:
        raise IdError(f"family index out of range: {index}")
    return f"F-{domain_code(domain)}-{index:02d}"


def schema_id(cls: str, index: int) -> str:
    """``index`` is 1-based within the class (1..6 for the 120-constraint design)."""
    if not 1 <= index <= 99:
        raise IdError(f"schema index out of range: {index}")
    return f"S-{_check_class(cls)}-{index:02d}"


def constraint_id(cls: str, domain: str, index: int) -> str:
    """``index`` is 1-based within the (class, domain) cell (1..6)."""
    if not 1 <= index <= 99:
        raise IdError(f"constraint index out of range: {index}")
    return f"K-{_check_class(cls)}-{domain_code(domain)}-{index:02d}"


def probe_id(constraint: str, index: int) -> str:
    """``index`` is 1-based within the constraint (1..8 primary, 1..50 saturation)."""
    if not CONSTRAINT_RE.match(constraint):
        raise IdError(f"malformed constraint_id: {constraint!r}")
    if not 1 <= index <= 99:
        raise IdError(f"probe index out of range: {index}")
    return f"{constraint}-P{index:02d}"


def pair_id(probe_a: str, probe_b: str) -> str:
    """Unordered pair rendered canonically, so (A,B) and (B,A) give one id."""
    for p in (probe_a, probe_b):
        if not PROBE_RE.match(p):
            raise IdError(f"malformed probe_id: {p!r}")
    if probe_a == probe_b:
        raise IdError("a probe cannot be paired with itself")
    lo, hi = sorted((probe_a, probe_b))
    if lo.rsplit("-P", 1)[0] != hi.rsplit("-P", 1)[0]:
        raise IdError(f"probes belong to different constraints: {probe_a}, {probe_b}")
    constraint = lo.rsplit("-P", 1)[0]
    return f"{constraint}-{lo.rsplit('-', 1)[1]}x{hi.rsplit('-', 1)[1]}"


def constraint_of(probe: str) -> str:
    m = PROBE_RE.match(probe)
    if not m:
        raise IdError(f"malformed probe_id: {probe!r}")
    return probe.rsplit("-P", 1)[0]


def response_id(run_id: str, model_id: str, probe: str, sample_index: int) -> str:
    """Content-addressed response id.

    Deliberately excludes the timestamp: re-running the identical cell under the
    identical run yields the identical id, which is what makes append-only
    resume safe (a duplicate is detectable rather than silently doubled).
    """
    return "R-" + short(
        sha256_obj(
            {"run_id": run_id, "model_id": model_id, "probe_id": probe, "sample_index": sample_index}
        )
    )


def utc_stamp(when: datetime | None = None) -> str:
    """Compact UTC timestamp, e.g. ``20260911T143000Z``."""
    when = when or datetime.now(timezone.utc)
    return when.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def run_id(experiment: str, config_hash: str, when: datetime | None = None) -> str:
    """Identifies one execution of one experiment with one configuration."""
    if not experiment or " " in experiment:
        raise IdError(f"experiment must be a non-empty token without spaces: {experiment!r}")
    return f"{experiment}-{utc_stamp(when)}-{short(config_hash, 6)}"
