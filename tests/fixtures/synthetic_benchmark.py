"""Structurally valid but FACTUALLY FICTIONAL constraints, for tests only.

**This is not benchmark content and must never be loaded as such.** Every gold
proposition here is invented. It exists so the design validator, the D0
framework and the probe generator can be exercised against a full 120-constraint
lattice without waiting for real authoring.

The guard: every constraint produced here carries ``split`` and a
``SYNTHETIC_MARKER`` in its notes, and `tests/unit/test_no_synthetic_leak.py`
asserts no file under `data/benchmark/` ever contains that marker.
"""

from __future__ import annotations

import datetime as dt

from semintegrity.schemas.constraint import Constraint, TemporalValidity
from semintegrity.schemas.enums import AnswerType, ConstraintClass, Domain, Split
from semintegrity.utils.ids import constraint_id, family_id, schema_id

SYNTHETIC_MARKER = "SYNTHETIC-TEST-FIXTURE-NOT-REAL-DATA"

_DOMAINS = list(Domain)
_CLASSES = list(ConstraintClass)


def make_constraint(
    cls: ConstraintClass,
    domain: Domain,
    index: int,
    *,
    family_index: int | None = None,
    schema_index: int | None = None,
    split: Split = Split.TEST,
    sitelinks: tuple[int, int] | None = None,
) -> Constraint:
    """One structurally valid, factually fictional constraint."""
    fam = family_index if family_index is not None else index
    sch = schema_index if schema_index is not None else index
    cid = constraint_id(cls.value, domain.value, index)
    if sitelinks is None:
        # Deterministic but non-degenerate spread, matched ACROSS classes: the
        # value depends on domain and index, never on the class. A Kruskal-Wallis
        # over classes therefore has real variance to work with and should fail
        # to reject equality — which is what a correctly matched design looks like.
        base = 40 + (index * 37 + _DOMAINS.index(domain) * 11) % 400
        sitelinks = (base, max(1, base - 25))
    temporal = (
        TemporalValidity(start=dt.date(1900, 1, 1), end=None, end_unknown=False, precision="day")
        if cls is ConstraintClass.C4
        else None
    )
    return Constraint.model_validate(
        {
            "constraint_id": cid,
            "family_id": family_id(domain.value, fam),
            "schema_id": schema_id(cls.value, sch),
            "domain": domain.value,
            "class": cls.value,
            "formal_predicate": f"{cls.value.lower()}_synthetic_{sch:02d}",
            "constraint_text": f"[{SYNTHETIC_MARKER}] fictional {cls.value} constraint {cid}",
            "entities": [f"EntityA-{cid}", f"EntityB-{cid}"],
            "entity_qids": [f"Q{9000000 + index}", f"Q{9500000 + index}"],
            "entity_sitelinks": list(sitelinks),
            "gold_proposition": f"[{SYNTHETIC_MARKER}] fictional proposition for {cid}",
            "gold_source": "SYNTHETIC",
            "gold_source_url": "https://example.invalid/synthetic",
            "gold_source_date": "2026-01-01",
            "temporal_validity": temporal.model_dump(mode="json") if temporal else None,
            "ambiguity_notes": "",
            "prerequisite_atomic_facts": [],
            "answer_type": AnswerType.ENTITY.value,
            "answer_space": [f"AnsX-{cid}", f"AnsY-{cid}", f"AnsZ-{cid}"],
            "gold_answer": f"AnsX-{cid}",
            "split": split.value,
            "notes": SYNTHETIC_MARKER,
        }
    )


def full_benchmark(*, split: Split = Split.TEST) -> list[Constraint]:
    """A complete, lattice-valid 120-constraint set.

    Layout follows ADR-0002: 30 families (6 per domain x 5 domains), each family
    contributing one constraint per class; schema index equals the family index
    within the domain, so schema x domain is fully crossed 6 x 5.
    """
    out: list[Constraint] = []
    for domain in _DOMAINS:
        for i in range(1, 7):  # 6 families per domain
            for cls in _CLASSES:
                out.append(
                    make_constraint(
                        cls, domain, i, family_index=i, schema_index=i, split=split
                    )
                )
    return out


def dev_set() -> list[Constraint]:
    """A 24-constraint development set, disjoint from :func:`full_benchmark`."""
    out: list[Constraint] = []
    for cls in _CLASSES:
        for j, domain in enumerate(_DOMAINS[:5], start=1):
            if j > 6:
                break
            out.append(
                make_constraint(
                    cls, domain, 20 + j, family_index=j, schema_index=j, split=Split.DEV
                )
            )
        out.append(
            make_constraint(cls, _DOMAINS[0], 26, family_index=1, schema_index=1, split=Split.DEV)
        )
    return out
