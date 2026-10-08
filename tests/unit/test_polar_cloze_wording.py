"""Regression test for the polar-cloze wording (CANON Variant A, approved 2026-10-06).

Pins all 28 polar-cloze probe texts as literals. If
:func:`semintegrity.probes.surface._polar_cloze` changes, this fails loudly
rather than silently re-wording 28 probes that have already been through
canonicalisation analysis.

Also pins the two properties the rewrite was approved on:

* §4.4.1 -- probe equivalence is defined on the formal representation, and the
  rewrite changes none of it;
* the rewrite does not make Stage 0 more permissive: the six responses observed
  as INVALID on pilot job 11969/12095 are still INVALID under the new wording.

No inference is run here and no raw output is read; the six strings are the ones
recorded in ``docs/Q21_polarity_mapping_spec.md`` and ``docs/PROBE_REWRITE_LOG.md``.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import yaml

from semintegrity.benchmark.pilot_builder import build
from semintegrity.canonicalization.canonicaliser import classify
from semintegrity.probes.surface import _polar_cloze
from semintegrity.schemas.enums import ResponseLabel, Syntax
from semintegrity.schemas.probe import EQUIVALENCE_KEY_FIELDS
from semintegrity.utils.paths import data_path

#: probe_id -> (exact probe text, expected answer). All 28 polar-cloze probes.
POLAR_CLOZE: dict[str, tuple[str, str]] = {
    'K-C1-GEO-01-P06': (
        'The statement "It is not the case that Canberra is the capital city of Australia" is ___.',
        'NO',
    ),
    'K-C2-GEO-01-P03': (
        'The statement "Canberra is Australia\'s capital and it sits in the ACT" is ___.',
        'YES',
    ),
    'K-C2-GEO-01-P06': (
        'The statement "It is not the case that the capital of Australia is Canberra, and the Australian Capital Territory is where it is located" is ___.',
        'NO',
    ),
    'K-C3-GEO-01-P03': (
        'The statement "Canberra is the capital of any country besides Australia" is ___.',
        'NO',
    ),
    'K-C3-GEO-01-P06': (
        'The statement "It is not the case that some sovereign state other than Australia has Canberra as its capital" is ___.',
        'YES',
    ),
    'K-C4-GEO-01-P06': (
        'The statement "It is not the case that 1927 is the year of the move of the Australian federal parliament to Canberra" is ___.',
        'NO',
    ),
    'K-C1-POL-01-P02': (
        'The statement "George Washington is the first President of the United States" is ___.',
        'YES',
    ),
    'K-C1-POL-01-P05': (
        'The statement "It is not the case that the first President of the United States is George Washington" is ___.',
        'NO',
    ),
    'K-C1-POL-01-P08': (
        'The statement "It is not the case that George Washington is the first president of the US" is ___.',
        'NO',
    ),
    'K-C2-POL-01-P02': (
        'The statement "The first President of the United States was George Washington, and the office was taken up by him before 1800" is ___.',
        'YES',
    ),
    'K-C2-POL-01-P05': (
        'The statement "It is not the case that George Washington was the first President of the United States and took office before 1800" is ___.',
        'NO',
    ),
    'K-C2-POL-01-P08': (
        'The statement "It is not the case that the first US president was George Washington, and he got the job before 1800" is ___.',
        'NO',
    ),
    'K-C3-POL-01-P02': (
        'The statement "The offices of President and Vice President of the United States have been held simultaneously by some person" is ___.',
        'NO',
    ),
    'K-C3-POL-01-P05': (
        'The statement "It is not the case that some person has simultaneously held the offices of President and Vice President of the United States" is ___.',
        'YES',
    ),
    'K-C3-POL-01-P08': (
        'The statement "It is not the case that the jobs of US president and vice president have ever been held by the same person at once" is ___.',
        'YES',
    ),
    'K-C4-POL-01-P02': (
        'The statement "1789 is the year of the first holder of the office of President of the United States taking office" is ___.',
        'YES',
    ),
    'K-C4-POL-01-P05': (
        'The statement "It is not the case that the year of the first holder of the office of President of the United States taking office is 1789" is ___.',
        'NO',
    ),
    'K-C4-POL-01-P08': (
        'The statement "It is not the case that 1789 is the year of the first US president taking office" is ___.',
        'NO',
    ),
    'K-C1-SCI-01-P04': (
        'The statement "Au is the symbol on the periodic table of gold" is ___.',
        'YES',
    ),
    'K-C1-SCI-01-P07': (
        'The statement "It is not the case that the symbol on the periodic table of gold is Au" is ___.',
        'NO',
    ),
    'K-C2-SCI-01-P01': (
        'The statement "The chemical symbol for gold is Au and its atomic number is 79" is ___.',
        'YES',
    ),
    'K-C2-SCI-01-P04': (
        'The statement "Au is gold\'s symbol, and 79 is its atomic number" is ___.',
        'YES',
    ),
    'K-C2-SCI-01-P07': (
        'The statement "It is not the case that gold\'s symbol is Au and its atomic number is 79" is ___.',
        'NO',
    ),
    'K-C3-SCI-01-P01': (
        'The statement "Gold has more than one atomic number" is ___.',
        'NO',
    ),
    'K-C3-SCI-01-P04': (
        'The statement "More than one atomic number is what gold has" is ___.',
        'NO',
    ),
    'K-C3-SCI-01-P07': (
        'The statement "It is not the case that gold comes with more than one atomic number" is ___.',
        'YES',
    ),
    'K-C4-SCI-01-P04': (
        'The statement "1901 is the year of the Nobel Prize in Physics first being given out" is ___.',
        'YES',
    ),
    'K-C4-SCI-01-P07': (
        'The statement "It is not the case that the year of the Nobel Prize in Physics first being given out is 1901" is ___.',
        'NO',
    ),
}

#: The four OPEN cloze probes are untouched by the rewrite -- they are not polar.
OPEN_CLOZE: dict[str, str] = {
    'K-C1-GEO-01-P03': 'The capital of Australia is ___.',
    'K-C4-GEO-01-P03': 'The year of parliament moving to Canberra is ___.',
    'K-C1-SCI-01-P01': 'The chemical symbol of gold is ___.',
    'K-C4-SCI-01-P01': 'The year of the first award of the Nobel Prize in Physics is ___.',
}

#: Responses observed as INVALID under canonicaliser v1.1 (6/96 = 93.75%).
OBSERVED_INVALID: dict[str, str] = {
    "K-C2-SCI-01-P01": "Au",
    "K-C2-SCI-01-P04": "Au",
    "K-C2-GEO-01-P03": "Canberra",
    "K-C2-GEO-01-P06": "CANBERRA",
    "K-C1-GEO-01-P06": "Melbourne",
    "K-C4-SCI-01-P04": "Albert Einstein",
}


@pytest.fixture(scope="module")
def pilot():
    candidates = yaml.safe_load(
        (data_path("benchmark") / "pilot" / "candidates.yaml").read_text(encoding="utf-8")
    )
    result = build(candidates)
    return (
        {c.constraint_id: c for c in result.constraints},
        {p.probe_id: p for p in result.probes},
    )


def test_frame_is_variant_a():
    assert _polar_cloze("X is Y") == 'The statement "X is Y" is ___.'


def test_counts(pilot):
    _, probes = pilot
    cloze = [p for p in probes.values() if p.syntax is Syntax.CLOZE]
    polar = [p for p in cloze if p.expected_answer in ("YES", "NO")]
    assert len(probes) == 96
    assert len(cloze) == 32
    assert len(polar) == 28
    assert len(POLAR_CLOZE) == 28


@pytest.mark.parametrize("probe_id", sorted(POLAR_CLOZE))
def test_polar_cloze_text_is_pinned(pilot, probe_id):
    _, probes = pilot
    text, expected = POLAR_CLOZE[probe_id]
    assert probes[probe_id].probe_text == text
    assert probes[probe_id].expected_answer == expected


@pytest.mark.parametrize("probe_id", sorted(OPEN_CLOZE))
def test_open_cloze_untouched(pilot, probe_id):
    _, probes = pilot
    assert probes[probe_id].probe_text == OPEN_CLOZE[probe_id]


def test_no_probe_uses_the_old_colon_blank_frame(pilot):
    """The frame that produced the six echoes must not survive anywhere."""
    _, probes = pilot
    offenders = [p.probe_id for p in probes.values() if p.probe_text.endswith(": ___")]
    assert offenders == []


def test_rewrite_preserves_the_formal_representation(pilot):
    """§4.4.1: equivalence is defined on the formal representation, not the text.

    Compared against the committed records, which are the pre-rewrite formal
    representation for the 68 untouched probes and must still match for the 28.
    """
    import json

    constraints, probes = pilot
    on_disk = [
        json.loads(line)
        for line in (data_path("benchmark") / "pilot" / "probes.jsonl")
        .read_text()
        .splitlines()
        if line.strip()
    ]
    assert len(on_disk) == 96
    for record in on_disk:
        probe = probes[record["probe_id"]]
        for field in ("constraint_id", "probe_id", "answer_type", *EQUIVALENCE_KEY_FIELDS):
            assert str(getattr(probe, field)) == str(record[field]), (
                f"{record['probe_id']}.{field} changed"
            )


def _stage0(text: str, constraint, probe):
    raw = SimpleNamespace(
        response_id="R-000000000000",
        constraint_id=constraint.constraint_id,
        probe_id=probe.probe_id,
        timed_out=False,
        raw_text=text,
    )
    return classify(raw, constraint, probe)


@pytest.mark.parametrize("probe_id", sorted(POLAR_CLOZE))
@pytest.mark.parametrize("reply", ["true", "false", "True.", "FALSE", "YES", "NO"])
def test_cued_replies_canonicalise(pilot, probe_id, reply):
    """"true"/"false" are already in the canonicaliser's token sets, so the new
    wording needs no alias-table change (§5.6)."""
    constraints, probes = pilot
    probe = probes[probe_id]
    result = _stage0(reply, constraints[probe.constraint_id], probe)
    assert result.label in (ResponseLabel.ANSWER, ResponseLabel.NEGATED)
    assert result.canonical_answer is not None


@pytest.mark.parametrize("probe_id", sorted(OBSERVED_INVALID))
def test_observed_failures_are_still_invalid(pilot, probe_id):
    """The rewrite must not make Stage 0 permissive toward the echoes."""
    constraints, probes = pilot
    probe = probes[probe_id]
    result = _stage0(OBSERVED_INVALID[probe_id], constraints[probe.constraint_id], probe)
    assert result.label is ResponseLabel.INVALID
