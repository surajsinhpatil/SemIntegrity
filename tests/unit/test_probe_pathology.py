"""PROBE-C pathology checks (ADR-0023 D2).

These replace a criterion that required human semantic-equivalence validation.
They audit the generator. The tests below pin what the checks catch, and — just
as importantly — that the module refuses to present the P04 hypothesis as an
explanation of Mistral's failure.
"""

from __future__ import annotations

import datetime as dt

import pytest

from semintegrity.benchmark.loader import load_split
from semintegrity.probes.pathology import (
    PATHOLOGIES,
    STEM_EMBEDS_GOLD_ANSWER,
    UPSTREAM_GUARANTEES,
    audit,
    check_constraint_probes,
)
from semintegrity.schemas.enums import AnswerType, ConstraintClass, Domain, Polarity
from semintegrity.schemas.probe import Probe
from semintegrity.utils.paths import data_path
from tests.fixtures.synthetic_benchmark import make_constraint

TEST_SPLIT = data_path("benchmark") / "test"
needs_split = pytest.mark.skipif(
    not (TEST_SPLIT / "constraints.jsonl").is_file(), reason="test split not built"
)


def _constraint(gold="1972", space=("1972", "1961", "1981"), at=AnswerType.DATE):
    c = make_constraint(ConstraintClass.C4, Domain.SCIENCE_TECHNOLOGY, 16)
    return c.model_copy(update={
        "gold_answer": gold, "answer_space": list(space), "answer_type": at,
    })


def _probe(c, text, expected, *, idx=1, syntax="cloze"):
    return Probe(
        probe_id=f"{c.constraint_id}-P{idx:02d}", constraint_id=c.constraint_id,
        probe_text=text, expected_answer=expected, answer_type=c.answer_type,
        polarity=Polarity.AFFIRMATIVE, syntax=syntax, directionality="direct",
        factor_cell_index=idx, logical_form="ended(x) = y", subject="apollo",
        predicate="ended", object="1972", quantifier="none",
        generated_at=dt.datetime(2026, 10, 1, tzinfo=dt.timezone.utc),
    )


# --- the pathology this was built for -----------------------------------

def test_a_polar_probe_whose_stem_embeds_the_gold_answer_is_flagged():
    """The P04 shape, taken from the observed K-C1-HIS-16-P04 failure."""
    c = _constraint()
    p = _probe(c, 'The statement "1972 is the year it ended" is ___.', "YES", idx=4)
    findings = check_constraint_probes(c, [p])
    assert [f.pathology for f in findings] == [STEM_EMBEDS_GOLD_ANSWER]
    assert findings[0].factor_cell == "04"
    assert "blank invites completion" in findings[0].detail


def test_a_nonpolar_probe_containing_the_answer_is_NOT_flagged():
    """A reverse-direction probe legitimately names the answer; only a POLAR
    probe is invited to echo it."""
    c = _constraint()
    p = _probe(c, "The year it ended is ___.", "1972", idx=1)
    assert check_constraint_probes(c, [p]) == []


def test_a_polar_probe_not_containing_the_answer_is_NOT_flagged():
    c = _constraint()
    p = _probe(c, "Did the Apollo program end in that year? ___", "YES", idx=5)
    assert check_constraint_probes(c, [p]) == []


def test_a_polar_INTERROGATIVE_containing_the_answer_is_NOT_flagged():
    """The correction that matters. A polar question MUST state the proposition
    it asks about, so "contains the gold answer" alone flagged 362 of 960
    probes spread evenly across all eight cells -- the normal structure of
    polar probes, not a defect. An interrogative cues a yes/no by its form; a
    cloze blank does not.
    """
    c = _constraint()
    p = _probe(c, "Is 1972 the year the Apollo program ended?", "YES",
               idx=2, syntax="interrogative")
    assert check_constraint_probes(c, [p]) == []


def test_a_polar_DECLARATIVE_containing_the_answer_is_NOT_flagged():
    c = _constraint()
    p = _probe(c, "The Apollo program ended in 1972.", "YES",
               idx=3, syntax="declarative")
    assert check_constraint_probes(c, [p]) == []


def test_containment_is_token_anchored_not_substring():
    """'1972' inside '11972' is not the gold answer, and 'Mir' inside 'Mirror'
    is not either."""
    c = _constraint()
    p = _probe(c, 'The statement "11972 is a number" is ___.', "YES", idx=4)
    assert check_constraint_probes(c, [p]) == []

    c2 = _constraint(gold="Mir", space=("Mir", "Salyut", "Skylab"), at=AnswerType.ENTITY)
    p2 = _probe(c2, 'The statement "the mirror is broken" is ___.', "YES", idx=4)
    assert check_constraint_probes(c2, [p2]) == []


# --- the three guarantees PROBE-C relies on but does not implement -------
#
# An earlier draft reimplemented these. Each is already a HARD failure upstream,
# so duplicating them would have created two definitions of one rule and made
# PROBE-C look like four checks when it is one. These tests pin that the
# upstream guarantees are real, so the `upstream_guarantees` report is not a
# claim about code that might have changed.

def test_a_cloze_without_a_blank_cannot_even_be_CONSTRUCTED():
    """Stronger than an audit finding: the Probe schema refuses it outright."""
    c = _constraint()
    with pytest.raises(ValueError, match="cloze probes must contain"):
        _probe(c, "The year it ended.", "1972", idx=1, syntax="cloze")


def test_duplicate_surfaces_are_a_hard_failure_upstream():
    from semintegrity.schemas.probe import assert_distinct_surfaces

    c = _constraint()
    a = _probe(c, "The year it ended is ___.", "1972", idx=1)
    b = _probe(c, "The year it ended is ___.", "1972", idx=2)
    with pytest.raises(ValueError):
        assert_distinct_surfaces([a, b])


def test_probe_c_does_not_reimplement_the_upstream_checks():
    """A duplicate surface is NOT a PROBE-C finding -- the loader already
    refuses to load it, and two definitions would drift."""
    c = _constraint()
    a = _probe(c, "The year it ended is ___.", "1972", idx=1)
    b = _probe(c, "The year it ended is ___.", "1972", idx=2)
    assert check_constraint_probes(c, [a, b]) == []
    assert PATHOLOGIES == (STEM_EMBEDS_GOLD_ANSWER,)


def test_the_upstream_guarantees_are_reported_with_attribution():
    c = _constraint()
    _, summary = audit([c], {c.constraint_id: []})
    guarantees = summary["upstream_guarantees"]
    assert len(guarantees) == len(UPSTREAM_GUARANTEES) == 3
    for g in guarantees:
        assert g["severity"].startswith("hard failure")
        assert "semintegrity" in g["enforced_by"]
    assert summary["checks_implemented_here"] == [STEM_EMBEDS_GOLD_ANSWER]


# --- the summary must not overclaim -------------------------------------

def test_the_summary_cross_tabulates_by_factor_cell():
    """A pathology concentrated in one cell is a template problem; one spread
    evenly is not. The cross-tab is what distinguishes them."""
    c = _constraint()
    probes = [
        _probe(c, 'The statement "1972 is it" is ___.', "YES", idx=4),
        _probe(c, 'Is 1972 the year? ___', "YES", idx=2),
    ]
    _, summary = audit([c], {c.constraint_id: probes})
    assert summary["counts"][STEM_EMBEDS_GOLD_ANSWER] == 2
    assert summary["by_factor_cell"][STEM_EMBEDS_GOLD_ANSWER] == {"02": 1, "04": 1}
    assert summary["passes_probe_c"] is False


def test_the_summary_states_that_p04_does_not_explain_mistral():
    c = _constraint()
    p = _probe(c, 'The statement "1972 is it" is ___.', "YES", idx=4)
    _, summary = audit([c], {c.constraint_id: [p]})
    status = summary["stem_embeds_gold_answer_status"]
    assert "HYPOTHESIS" in status
    assert "P02-P08" in status
    assert "does not account for" in status


def test_the_summary_states_it_is_not_semantic_validation():
    c = _constraint()
    _, summary = audit([c], {c.constraint_id: []})
    assert "not be called validated" in summary["scope"]
    assert "GENERATOR" in summary["scope"]


def test_findings_are_reported_never_rewritten():
    c = _constraint()
    p = _probe(c, 'The statement "1972 is it" is ___.', "YES", idx=4)
    before = p.probe_text
    _, summary = audit([c], {c.constraint_id: [p]})
    assert p.probe_text == before, "the audit must not mutate a probe"
    assert "frozen" in summary["remedy"]


@pytest.mark.parametrize("pathology", PATHOLOGIES)
def test_every_pathology_is_reported_even_at_zero(pathology):
    c = _constraint()
    p = _probe(c, "The year it ended is ___.", "1972", idx=1)
    _, summary = audit([c], {c.constraint_id: [p]})
    assert pathology in summary["counts"]


# --- against the real frozen benchmark ----------------------------------

@needs_split
def test_probe_c_runs_over_the_frozen_test_split():
    """Executed against the real 120 x 8. Whatever it finds is a measurement,
    and a non-zero count is reported rather than treated as a failure to fix."""
    cons, probe_list = load_split(TEST_SPLIT)
    by_constraint: dict[str, list] = {}
    for p in probe_list:
        by_constraint.setdefault(p.constraint_id, []).append(p)
    findings, summary = audit(cons, by_constraint)
    assert summary["n_constraints"] == 120
    assert summary["n_probes"] == 960
    # Recorded, not asserted to be zero: this is the measurement PROBE-C exists
    # to produce, and the P04 hypothesis is what it informs.
    assert isinstance(summary["counts"][STEM_EMBEDS_GOLD_ANSWER], int)
    # MEASURED 2026-10-15 on the frozen split: 43 of 960 probes, confined to
    # three factor cells. Cells 04 and 07 are exactly the ones observed failing
    # in the Mistral and Qwen2.5-14B/OLMo-2 diagnostics, which is why the
    # concentration matters. Pinned so a probe or template change is visible.
    cells = summary["by_factor_cell"].get(STEM_EMBEDS_GOLD_ANSWER, {})
    assert summary["counts"][STEM_EMBEDS_GOLD_ANSWER] == 43
    assert cells == {"04": 16, "06": 11, "07": 16}
    assert set(cells) < {f"{i:02d}" for i in range(1, 9)}, (
        "the pathology must be CONFINED to some cells, not spread over all "
        "eight -- a check that fires everywhere is detecting normal structure"
    )
    assert set(summary["counts"]) == set(PATHOLOGIES)


def test_gold_embedding_and_any_member_embedding_are_the_SAME_43():
    """Closes an alternative predicate by measurement, not assumption.

    The echo risk arguably applies to any embedded answer-space member, not
    only the gold one. On the frozen split the two predicates flag exactly the
    same probes, so the narrower one is not a restriction.
    """
    import re

    cons, probe_list = load_split(TEST_SPLIT)
    cmap = {c.constraint_id: c for c in cons}
    polar = {"YES", "NO", "TRUE", "FALSE"}

    def has(text, answer):
        return bool(answer) and re.search(
            rf"(?<!\w){re.escape(answer.lower())}(?!\w)", text.lower()
        )

    pce = [
        p for p in probe_list
        if str(p.expected_answer).upper() in polar
        and str(p.syntax).split(".")[-1].lower() == "cloze"
        and str(cmap[p.constraint_id].answer_type) in ("entity", "date")
    ]
    gold = {p.probe_id for p in pce if has(p.probe_text, cmap[p.constraint_id].gold_answer)}
    anym = {
        p.probe_id for p in pce
        if any(has(p.probe_text, m) for m in cmap[p.constraint_id].answer_space)
    }
    assert len(pce) == 60
    assert gold == anym, "a distractor-embedding polar cloze would break this"
    assert len(gold) == 43
