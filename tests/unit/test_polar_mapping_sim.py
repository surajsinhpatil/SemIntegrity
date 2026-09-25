"""The Q21 polarity-mapping SIMULATION logic.

This covers `scripts/analysis/simulate_polar_mapping.py`, which is an offline
what-if and deliberately NOT production code. It is tested anyway, because its
output is going to inform a methodology decision: a truth table that is wrong in
one cell would misreport how many responses the mapping recovers, and the
double-negation row is exactly the kind of thing that is easy to get backwards.
"""

import importlib.util
import sys

import pytest

from semintegrity.utils.paths import p

spec = importlib.util.spec_from_file_location(
    "simulate_polar_mapping", p("scripts/analysis/simulate_polar_mapping.py")
)
sim = importlib.util.module_from_spec(spec)
assert spec.loader is not None
# @dataclass resolves annotations via sys.modules[cls.__module__], so the module
# has to be registered BEFORE exec_module or State's decorator raises.
sys.modules[spec.name] = sim
spec.loader.exec_module(sim)

State, contradicts, parse_yes_no = sim.State, sim.contradicts, sim.parse_yes_no


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("yes", True), ("YES", True), ("Yes.", True), ("true", True),
        ("no", False), ("NO", False), ("No,", False), ("false", False),
        ("Canberra", None), ("", None), ("1927", None),
        # Only a LEADING yes/no counts: a sentence merely containing the word is
        # not a polar answer, and treating it as one would invent data.
        ("The answer is yes", None),
        ("Paris, yes", None),
    ],
)
def test_parse_yes_no(text, expected):
    assert parse_yes_no(text) is expected


@pytest.mark.parametrize(
    ("polarity", "said_yes", "expect_definite"),
    [
        ("affirmative", True, True),    # "Is X the capital?" YES  -> X
        ("affirmative", False, False),  # "Is X the capital?" NO   -> not-X
        ("negated", True, False),       # "Is it false that X?" YES -> not-X
        ("negated", False, True),       # "Is it false that X?" NO  -> X  (double negation)
    ],
)
def test_polarity_truth_table(polarity, said_yes, expect_definite):
    """The rule is affirms = (polarity == affirmative) == (response == YES)."""
    affirms = (polarity == "affirmative") == said_yes
    assert affirms is expect_definite


def test_definite_vs_definite():
    assert contradicts(State("DEFINITE", "Canberra"), State("DEFINITE", "Sydney"))
    assert not contradicts(State("DEFINITE", "Canberra"), State("DEFINITE", "Canberra"))


def test_definite_contradicts_negation_of_itself():
    """The approved rule: not-X contradicts a definite X, either way round."""
    assert contradicts(State("DEFINITE", "Canberra"), State("NEGATED", "Canberra"))
    assert contradicts(State("NEGATED", "Canberra"), State("DEFINITE", "Canberra"))


def test_definite_is_compatible_with_negation_of_something_else():
    """'not Canberra' and 'Sydney' are jointly satisfiable, so not a contradiction."""
    assert not contradicts(State("DEFINITE", "Sydney"), State("NEGATED", "Canberra"))
    assert not contradicts(State("NEGATED", "Canberra"), State("DEFINITE", "Sydney"))


def test_two_negations_never_contradict():
    assert not contradicts(State("NEGATED", "Canberra"), State("NEGATED", "Canberra"))
    assert not contradicts(State("NEGATED", "Canberra"), State("NEGATED", "Sydney"))


def test_contradicts_is_symmetric():
    """PSCR counts unordered pairs, so an asymmetric rule would make the metric
    depend on iteration order."""
    kinds = ["DEFINITE", "NEGATED"]
    values = ["Canberra", "Sydney"]
    states = [State(k, v) for k in kinds for v in values]
    for a in states:
        for b in states:
            assert contradicts(a, b) == contradicts(b, a), f"{a} vs {b}"


def test_only_definite_and_negated_are_evaluable():
    assert State("DEFINITE", "X").evaluable
    assert State("NEGATED", "X").evaluable
    assert not State("ABSTAIN").evaluable
    assert not State("INVALID").evaluable


# --- boolean constraints are NOT exempt -------------------------------------

@pytest.mark.parametrize(
    ("polarity", "said_yes", "holds"),
    [
        ("affirmative", True, True),    # "Is Phi true?" YES        -> Phi holds
        ("affirmative", False, False),
        ("negated", True, False),       # "Is it false that Phi?" YES -> Phi fails
        ("negated", False, True),       # double negation            -> Phi holds
    ],
)
def test_boolean_polarity_normalisation(polarity, said_yes, holds):
    affirms = (polarity == "affirmative") == said_yes
    assert affirms is holds


def test_perfectly_consistent_model_scores_zero_on_the_real_benchmark():
    """The validity invariant, against the authored pilot benchmark.

    A model answering every probe with that probe's own `expected_answer` is by
    definition perfectly self-consistent, so PSCR MUST be 0. Under the current
    canonicaliser it is 0.643 on average -- 0.714 for entity/date constraints and
    0.571 for boolean ones -- because affirmative 'YES' and negated 'NO' are
    recorded as different canonical answers. That is a measurement artifact, and
    it is the reason this mapping exists.

    Needs no model output: it is a property of the benchmark and the mapping.
    """
    from itertools import combinations

    from semintegrity.benchmark.loader import load_split
    from semintegrity.utils.paths import data_path

    cons_list, probe_list = load_split(data_path("benchmark") / "pilot")
    constraints = {c.constraint_id: c for c in cons_list}
    by_constraint: dict[str, list] = {}
    for probe in probe_list:
        by_constraint.setdefault(probe.constraint_id, []).append(probe)

    assert len(by_constraint) == 12
    for cid, ps in by_constraint.items():
        assert len(ps) == 8, f"{cid} has {len(ps)} probes, expected K=8"
        c = constraints[cid]
        states = []
        for probe in ps:
            if probe.expected_answer in ("YES", "NO"):
                affirms = ((probe.polarity.value == "affirmative")
                           == (probe.expected_answer == "YES"))
                if c.answer_type.value == "boolean":
                    states.append(State("DEFINITE", "YES" if affirms else "NO"))
                else:
                    g = c.gold_answer
                    states.append(State("DEFINITE", g) if affirms else State("NEGATED", g))
            else:
                states.append(State("DEFINITE", probe.expected_answer))
        bad = [(a, b) for a, b in combinations(states, 2) if contradicts(a, b)]
        assert not bad, (
            f"{cid}: the proposed mapping scores a PERFECTLY CONSISTENT model as "
            f"having {len(bad)} contradictory pairs. The mapping is wrong."
        )
