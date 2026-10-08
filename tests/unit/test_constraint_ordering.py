"""The canonical constraint ordering (ADR-0003's ``constraint_index``).

ADR-0003 makes probe syntax a function of each constraint's 0-based position
within its class, and ``factor_design`` requires that position to be stable once
the benchmark is frozen. Before this module the position came from the order
families happened to appear in ``candidates.yaml``, so re-ordering a YAML file
would have re-worded a third of the benchmark's probes.

These tests pin three things: the domain order matches §4.3, the ordering is a
pure function of the records, and switching the pilot to it changes nothing.
"""

from __future__ import annotations

import yaml

from semintegrity.benchmark.ordering import (
    DOMAIN_ORDER,
    canonical_key,
    constraint_indices,
    order_within_class,
    schema_index,
)
from semintegrity.benchmark.pilot_builder import build
from semintegrity.schemas.enums import ConstraintClass, Domain
from semintegrity.utils.paths import data_path


def _pilot():
    candidates = yaml.safe_load(
        (data_path("benchmark") / "pilot" / "candidates.yaml").read_text(encoding="utf-8")
    )
    return build(candidates)


def test_domain_order_matches_the_domain_enum():
    """A module-level assert would vanish under ``python -O``; pin it here."""
    assert tuple(Domain) == DOMAIN_ORDER


def test_domain_order_is_the_order_section_4_3_lists():
    assert [d.value for d in DOMAIN_ORDER] == [
        "geography",
        "history",
        "biology",
        "public_office",
        "science_technology",
    ]


def test_schema_index_reads_the_axis_number():
    assert schema_index("S-C1-01") == 1
    assert schema_index("S-C3-04") == 4
    assert schema_index("S-C4-06") == 6


def test_indices_are_zero_based_and_dense_within_each_class():
    constraints = _pilot().constraints
    indices = constraint_indices(constraints)
    assert len(indices) == len(constraints)
    for cls in ConstraintClass:
        in_class = [c for c in constraints if c.constraint_class is cls]
        positions = sorted(indices[c.constraint_id] for c in in_class)
        assert positions == list(range(len(in_class)))


def test_ordering_is_independent_of_source_file_order():
    """The point of the module: shuffle the input, get the same indices."""
    constraints = _pilot().constraints
    forward = constraint_indices(constraints)
    backward = constraint_indices(list(reversed(constraints)))
    assert forward == backward


def test_pilot_ordering_is_geography_public_office_science():
    """The pilot's three families are already in §4.3 order, which is why
    adopting the canonical ordering re-words no pilot probe."""
    constraints = _pilot().constraints
    for cls in ConstraintClass:
        ordered = order_within_class(constraints, cls)
        assert [c.domain.value for c in ordered] == [
            "geography",
            "public_office",
            "science_technology",
        ]


def test_canonical_key_sorts_domain_before_schema():
    constraints = {c.constraint_id: c for c in _pilot().constraints}
    geo = constraints["K-C1-GEO-01"]
    sci = constraints["K-C1-SCI-01"]
    assert canonical_key(geo) < canonical_key(sci)
    assert canonical_key(geo)[0] == 0
    assert canonical_key(sci)[0] == 4


def test_pilot_probe_syntax_is_unchanged_by_the_canonical_ordering():
    """Regression guard: the committed probe records must still be reproduced.

    If the ordering ever stops agreeing with what is on disk, every probe's
    syntax has silently moved and the recorded pilot responses no longer
    correspond to the probes that produced them.
    """
    import json

    on_disk = {
        rec["probe_id"]: rec
        for rec in (
            json.loads(line)
            for line in (data_path("benchmark") / "pilot" / "probes.jsonl")
            .read_text()
            .splitlines()
            if line.strip()
        )
    }
    rebuilt = {p.probe_id: p for p in _pilot().probes}
    assert set(on_disk) == set(rebuilt)
    for pid, record in on_disk.items():
        assert rebuilt[pid].syntax.value == record["syntax"], f"{pid} syntax moved"
        assert rebuilt[pid].probe_text == record["probe_text"], f"{pid} text moved"
