"""The validity invariant: a perfectly consistent model must score PSCR 0.

This runs the PRODUCTION Stage 0 and D1 over the real pilot benchmark. It is not
a unit test of a helper; it is the guard that would have caught the defect the
2026-09-25 pilot exposed.

A model answering every probe with that probe's own `expected_answer` is
perfectly self-consistent by definition, so every pair must be SATISFIED. Before
the Q21 polarity mapping it was not: an affirmative "YES" and a negated "NO" both
mean "the constraint holds" but were recorded as different canonical answers and
compared, so such a model scored

    entity/date  0.714      boolean  0.571      MEAN  0.643

That is a measurement artifact with no model involved, and it did not merely
inflate PSCR — it inverted the per-constraint ordering, so answers to RQ2 would
have been wrong in unpredictable directions rather than uniformly biased.

If this test ever fails again, the numbers it guards are not measuring model
inconsistency.
"""

import datetime as dt

import pytest

from semintegrity.benchmark.loader import load_split
from semintegrity.canonicalization.canonicaliser import canonicalise
from semintegrity.detectors.d1.exact_match import check_all_pairs
from semintegrity.schemas.enums import ResponseLabel, Verdict
from semintegrity.schemas.response import Provenance, RawResponse
from semintegrity.utils.paths import data_path

PILOT = data_path("benchmark") / "pilot"
pytestmark = pytest.mark.skipif(
    not (PILOT / "constraints.jsonl").is_file(), reason="pilot benchmark not built"
)


def _provenance() -> Provenance:
    return Provenance(
        model_id="perfect-model", hf_revision_hash="a" * 40, tokenizer_hash="t",
        chat_template_hash="c", transformers_version="4.57.6", vllm_version="0.11.2",
        torch_version="2.9.0", cuda_version="12.8", gpu_model="A100", dtype="bfloat16",
        quantisation="none", temperature=0.0, top_p=1.0, top_k=-1, repetition_penalty=1.0,
        max_new_tokens=24, stop_sequences=[], seed=1, rendered_prompt="p", batch_size=1,
        sample_index=0, timestamp=dt.datetime(2026, 9, 26, tzinfo=dt.timezone.utc),
    )


def _raw_for(probe, text: str) -> RawResponse:
    return RawResponse(
        response_id="R-" + "b" * 12, run_id="r", experiment_id="invariant",
        config_snapshot_sha256="0" * 64, constraint_id=probe.constraint_id,
        probe_id=probe.probe_id, tier="pilot", track="A",
        semantic_instruction_id="trackA.v1", raw_text=text, timed_out=False,
        retry_index=0, provenance=_provenance(),
    )


@pytest.fixture(scope="module")
def pilot():
    cons_list, probe_list = load_split(PILOT)
    by_constraint: dict[str, list] = {}
    for probe in probe_list:
        by_constraint.setdefault(probe.constraint_id, []).append(probe)
    return {c.constraint_id: c for c in cons_list}, by_constraint


def test_perfect_model_scores_pscr_zero_on_every_constraint(pilot):
    """The invariant, through the production canonicaliser and D1."""
    constraints, by_constraint = pilot
    assert len(by_constraint) == 12

    failures = []
    for cid, probe_list in sorted(by_constraint.items()):
        assert len(probe_list) == 8, f"{cid} has {len(probe_list)} probes, expected K=8"
        c = constraints[cid]
        canon = [
            canonicalise(_raw_for(probe, probe.expected_answer), c, probe)
            for probe in probe_list
        ]
        results = check_all_pairs(canon)
        evaluable = [r for r in results if r.verdict is not Verdict.NOT_APPLICABLE]
        violations = [r for r in results if r.verdict is Verdict.VIOLATION]
        if violations:
            failures.append(
                f"{cid}: {len(violations)}/{len(evaluable)} pairs contradict "
                f"for a PERFECTLY CONSISTENT model -- e.g. {violations[0].reason}"
            )
    assert not failures, "PSCR artifact has returned:\n" + "\n".join(failures)


def test_perfect_model_is_fully_evaluable(pilot):
    """A guard that always passes is worthless: the invariant only means something
    if the pairs it checks are actually being evaluated. Every probe of a
    perfectly answering model must canonicalise to a usable answer, so coverage
    must be 1.0 — otherwise zero violations could simply mean zero comparisons.
    """
    constraints, by_constraint = pilot
    for cid, probe_list in sorted(by_constraint.items()):
        c = constraints[cid]
        canon = [
            canonicalise(_raw_for(probe, probe.expected_answer), c, probe)
            for probe in probe_list
        ]
        not_usable = [x.probe_id for x in canon if not x.is_evaluable]
        assert not not_usable, (
            f"{cid}: {len(not_usable)} probes of a perfect model are not evaluable "
            f"({not_usable[:3]}); the invariant above would pass vacuously"
        )
        results = check_all_pairs(canon)
        assert len(results) == 28, f"{cid}: expected 28 pairs at K=8, got {len(results)}"


def test_a_deliberately_inconsistent_model_is_still_detected(pilot):
    """The complement: the mapping must not make everything look consistent.

    One probe is answered with a wrong-but-valid alternative. That must produce
    violations, or the invariant above is being satisfied by a rule that simply
    never fires.
    """
    constraints, by_constraint = pilot
    cid = "K-C1-GEO-01"
    c = constraints[cid]
    probe_list = by_constraint[cid]
    other = next(a for a in c.answer_space if a != c.gold_answer)

    canon = []
    for i, probe in enumerate(probe_list):
        # Flip the first OPEN probe to a different member of the answer space.
        if i == 0 and probe.expected_answer not in ("YES", "NO"):
            text = other
        else:
            text = probe.expected_answer
        canon.append(canonicalise(_raw_for(probe, text), c, probe))

    results = check_all_pairs(canon)
    violations = [r for r in results if r.verdict is Verdict.VIOLATION]
    assert violations, "a model contradicting itself produced no D1 violations"


def test_negated_label_is_reachable_and_evaluable(pilot):
    """A polar probe answered against the asserted candidate yields NEGATED."""
    constraints, by_constraint = pilot
    cid = "K-C1-GEO-01"
    c = constraints[cid]
    probe = next(p for p in by_constraint[cid]
                 if p.expected_answer in ("YES", "NO") and p.polarity.value == "affirmative")
    # "Is Canberra the capital?" -> "no"  =>  NOT Canberra
    res = canonicalise(_raw_for(probe, "no"), c, probe)
    assert res.label is ResponseLabel.NEGATED
    assert res.canonical_answer == c.gold_answer
    assert res.is_evaluable


# --- the same invariant, through D0 ------------------------------------------

def test_d0_also_scores_a_perfect_model_at_zero_violations(pilot):
    """D0 is a second, independent path to the same claim.

    D1 compares canonical strings; D0 evaluates a symbolic predicate against the
    frozen knowledge base. They can disagree -- that disagreement is a reportable
    result (§4.8.2) -- but neither may flag a perfectly self-consistent model.

    This also exercises the frozen KB offline, which is how every compute node
    runs it (ADR-0011).
    """
    from itertools import combinations

    from semintegrity.detectors.d0.registry import default_registry
    from semintegrity.kb.adapter import WikidataKB
    from semintegrity.kb.cache import CacheMode, KBCache
    from semintegrity.utils.paths import data_path

    constraints, by_constraint = pilot
    registry = default_registry()
    kb = WikidataKB(KBCache(data_path("wikidata_cache"), mode=CacheMode.FROZEN))

    uncovered, violations = [], []
    for cid, probe_list in sorted(by_constraint.items()):
        c = constraints[cid]
        assert registry.has(c.formal_predicate), f"{cid}: no predicate {c.formal_predicate}"
        pred = registry.get(c.formal_predicate)
        canon = [
            canonicalise(_raw_for(probe, probe.expected_answer), c, probe)
            for probe in probe_list
        ]
        usable = [x for x in canon if x.label is ResponseLabel.ANSWER]
        for a, b in combinations(usable, 2):
            r = pred.check_pair(c, a, b, kb)
            if not r.is_covered:
                uncovered.append(f"{cid}: {a.probe_id}/{b.probe_id} {r.reason}")
            if r.verdict is Verdict.VIOLATION:
                violations.append(f"{cid}: {a.probe_id}/{b.probe_id} {r.reason}")

    assert not violations, (
        "D0 flags a PERFECTLY CONSISTENT model as contradictory:\n"
        + "\n".join(violations[:5])
    )
    # Coverage is a reportable result, not a pass/fail gate -- but for a model
    # that answers every probe, a sudden collapse to zero would mean D0 stopped
    # running rather than that coverage legitimately shrank.
    assert not uncovered, (
        f"D0 reached no decision on {len(uncovered)} pairs of a fully answering "
        f"model; it may not be running at all:\n" + "\n".join(uncovered[:5])
    )


def test_d0_and_d1_agree_that_a_perfect_model_is_consistent(pilot):
    """Both detectors, same conclusion. If they ever diverge HERE it is a bug,
    not the interesting detector-disagreement result §4.8 anticipates."""
    from itertools import combinations

    from semintegrity.detectors.d0.registry import default_registry
    from semintegrity.kb.adapter import WikidataKB
    from semintegrity.kb.cache import CacheMode, KBCache
    from semintegrity.utils.paths import data_path

    constraints, by_constraint = pilot
    registry = default_registry()
    kb = WikidataKB(KBCache(data_path("wikidata_cache"), mode=CacheMode.FROZEN))

    for cid, probe_list in sorted(by_constraint.items()):
        c = constraints[cid]
        canon = [
            canonicalise(_raw_for(probe, probe.expected_answer), c, probe)
            for probe in probe_list
        ]
        d1_bad = sum(r.verdict is Verdict.VIOLATION for r in check_all_pairs(canon))
        pred = registry.get(c.formal_predicate)
        usable = [x for x in canon if x.label is ResponseLabel.ANSWER]
        d0_bad = sum(
            pred.check_pair(c, a, b, kb).verdict is Verdict.VIOLATION
            for a, b in combinations(usable, 2)
        )
        assert d1_bad == d0_bad == 0, f"{cid}: D1 {d1_bad}, D0 {d0_bad}, expected 0 and 0"
