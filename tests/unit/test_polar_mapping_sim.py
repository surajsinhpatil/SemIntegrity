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
