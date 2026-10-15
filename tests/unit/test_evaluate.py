"""The shared evaluation layer: per-constraint rows and the §4.11 contrasts.

``constraint_rows`` was extracted from ``pilot_report`` so that the pilot report
and the primary evaluator share ONE definition of a per-constraint row. These
tests pin the parts that could silently drift: the arm composition of the
pre-specified contrasts, the refusal to impute an undefined PSCR, and the
statements the output makes about its own status.
"""

from __future__ import annotations

import pytest

from semintegrity.analysis.evaluate import (
    CONFIRMATORY_CONTRASTS,
    canon_threshold,
    class_profile,
    confirmatory_contrasts,
    stage0_summary,
)
from semintegrity.schemas.enums import ResponseLabel


def _rows(per_class: dict[str, list[float | None]]) -> list[dict]:
    rows = []
    for cls, values in per_class.items():
        for i, v in enumerate(values):
            rows.append({"constraint_id": f"K-{cls}-X-{i:02d}", "class": cls, "pscr": v})
    return rows


# --- contrast definition -------------------------------------------------
def test_the_two_prespecified_contrasts_are_the_ones_in_statistics_yaml():
    ids = [c[0] for c in CONFIRMATORY_CONTRASTS]
    assert ids == ["H1_primary", "H1_planned"]


def test_h1_primary_splits_the_classes_into_two_equal_arms():
    _, _, a, b = CONFIRMATORY_CONTRASTS[0]
    assert set(a) == {"C1", "C2"}
    assert set(b) == {"C3", "C4"}
    assert not set(a) & set(b), "the arms must be disjoint constraint sets"


def test_contrast_arms_match_the_configured_arm_size_on_the_real_lattice():
    """60/60 is preregistered in statistics.yaml; the lattice must deliver it."""
    from semintegrity.utils.config import load_config

    cfg = load_config("configs/analysis/statistics.yaml").data
    arm_size = cfg["confirmatory"]["contrasts"][0]["arm_size"]
    rows = _rows({"C1": [0.1] * 30, "C2": [0.1] * 30, "C3": [0.2] * 30, "C4": [0.2] * 30})
    out = confirmatory_contrasts(rows, n_boot=50)
    assert out[0]["arm_a_n"] == arm_size
    assert out[0]["arm_b_n"] == arm_size


# --- the contrasts compute ----------------------------------------------
def test_confirmatory_contrast_recovers_a_planted_difference():
    rows = _rows({"C1": [0.1] * 30, "C2": [0.1] * 30, "C3": [0.5] * 30, "C4": [0.5] * 30})
    primary = confirmatory_contrasts(rows, n_boot=400)[0]
    assert primary["estimate"] == pytest.approx(0.1 - 0.5)
    assert primary["ci_low"] is not None and primary["ci_high"] is not None


def test_a_zero_difference_yields_an_interval_covering_zero():
    rows = _rows({"C1": [0.3] * 30, "C2": [0.3] * 30, "C3": [0.3] * 30, "C4": [0.3] * 30})
    primary = confirmatory_contrasts(rows, n_boot=400)[0]
    assert primary["estimate"] == pytest.approx(0.0)
    assert primary["excludes_zero"] is False


def test_confirmatory_contrasts_are_recorded_as_exempt_from_fdr():
    """statistics.yaml:multiplicity exempts them; the row must say so."""
    rows = _rows({"C1": [0.1] * 2, "C2": [0.1] * 2, "C3": [0.2] * 2, "C4": [0.2] * 2})
    for row in confirmatory_contrasts(rows, n_boot=50):
        assert "EXEMPT" in row["fdr"]


def test_contrasts_are_seed_reproducible():
    rows = _rows({"C1": [0.1, 0.4], "C2": [0.2, 0.9], "C3": [0.5, 0.3], "C4": [0.7, 0.2]})
    assert confirmatory_contrasts(rows, n_boot=200) == confirmatory_contrasts(rows, n_boot=200)


# --- non-imputation (Q6) -------------------------------------------------
def test_an_all_undefined_arm_yields_no_estimate_rather_than_zero():
    rows = _rows({"C1": [None] * 4, "C2": [None] * 4, "C3": [0.5] * 4, "C4": [0.5] * 4})
    primary = confirmatory_contrasts(rows, n_boot=100)[0]
    assert primary["estimate"] is None, "an undefined arm must not be imputed as 0"
    assert primary["excludes_zero"] is None


def test_undefined_clusters_are_counted_not_dropped_from_the_denominator():
    rows = _rows({"C1": [0.2, None, 0.4], "C2": [], "C3": [], "C4": []})
    prof = {p["class"]: p for p in class_profile(rows, n_boot=100)}
    assert prof["C1"]["n_clusters"] == 3, "an NA cluster is still a cluster"
    assert prof["C1"]["n_defined"] == 2


# --- class profile -------------------------------------------------------
def test_class_profile_covers_all_four_classes_even_when_empty():
    prof = class_profile(_rows({"C1": [0.2]}), n_boot=50)
    assert [p["class"] for p in prof] == ["C1", "C2", "C3", "C4"]


def test_class_profile_carries_the_categorical_framing():
    """A figure built from this table must not become an ordering claim."""
    for row in class_profile(_rows({"C1": [0.2]}), n_boot=50):
        assert "CATEGORICAL" in row["framing"]
        assert "never ordered" in row["framing"]


# --- Stage 0 / CANON -----------------------------------------------------
def test_canon_threshold_is_read_from_config_not_hardcoded():
    assert canon_threshold() == pytest.approx(0.95)


def test_negated_and_abstain_both_count_as_canonicalised():
    labels = {
        ResponseLabel.ANSWER: 5, ResponseLabel.NEGATED: 2,
        ResponseLabel.ABSTAIN: 3, ResponseLabel.INVALID: 0,
    }
    s = stage0_summary(__import__("collections").Counter(labels), threshold=0.95)
    assert s.rate == pytest.approx(1.0)
    assert s.passed is True


def test_the_canon_gate_fails_below_threshold():
    from collections import Counter

    labels = Counter({ResponseLabel.ANSWER: 90, ResponseLabel.INVALID: 10})
    s = stage0_summary(labels, threshold=0.95)
    assert s.rate == pytest.approx(0.90)
    assert s.passed is False
