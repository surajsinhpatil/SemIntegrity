"""The documentation contract: every number the docs state must be computable.

ADR-0023, ADR-0024, METHODOLOGY_REVISED.md and the audit all quote figures
derived from the benchmark and the code. Prose drifts; this suite makes drift a
test failure. It also pins the prohibitions, so a future change that reinstates
an accuracy claim or unfreezes CANON breaks here.

This is the mechanical half of "review all revised methodology claims against
the actual code". It cannot check an argument, only an assertion of fact.
"""

from __future__ import annotations

import json

import pytest
import yaml

from semintegrity.analysis.sensitivity import confound_report
from semintegrity.benchmark.loader import load_split
from semintegrity.detectors.d0.audit import mechanism_coverage
from semintegrity.detectors.d0.registry import default_registry
from semintegrity.probes.pathology import audit as probe_audit
from semintegrity.utils.paths import data_path, project_root

TEST_SPLIT = data_path("benchmark") / "test"
needs_split = pytest.mark.skipif(
    not (TEST_SPLIT / "constraints.jsonl").is_file(), reason="test split not built"
)
DOCS = (
    "docs/decisions/ADR-0023-no-human-validation-redesign.md",
    "docs/decisions/ADR-0024-d4-temperature-resolution.md",
    "docs/METHODOLOGY_REVISED.md",
    "docs/AUDIT_2026-10-15_no_human_validation.md",
)


def _doc(name: str) -> str:
    return (project_root() / name).read_text(encoding="utf-8")


def _all_docs() -> str:
    return "\n".join(_doc(d) for d in DOCS)


# --- benchmark facts the docs quote -------------------------------------

@needs_split
def test_81_draft_of_132_is_still_true():
    total_draft = 0
    for split in ("test", "dev"):
        cons, _ = load_split(data_path("benchmark") / split)
        total_draft += sum(1 for c in cons if str(c.verification_status) == "DRAFT")
    assert total_draft == 81, f"the docs say 81 DRAFT; the data says {total_draft}"
    assert "81" in _all_docs()


@needs_split
def test_no_constraint_claims_human_validation():
    """The one claim this project must never make."""
    for split in ("test", "dev", "pilot"):
        path = data_path("benchmark") / split / "constraints.jsonl"
        if not path.is_file():
            continue
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            assert not r.get("human_validated_at"), r["constraint_id"]
            assert not r.get("human_validated_by"), r["constraint_id"]
            assert str(r.get("verification_status")) != "HUMAN_VALIDATED"


@needs_split
def test_the_chance_balance_the_confirmatory_contrast_rests_on():
    """C1/C4 = 0.611, C2/C3 = 0.500, both H1 arms 0.5556, gap 0.0000."""
    from semintegrity.analysis.sensitivity import chance_pscr

    cons, _ = load_split(TEST_SPLIT)
    per_class = {
        k: [chance_pscr(c) for c in cons if c.constraint_class.value == k]
        for k in ("C1", "C2", "C3", "C4")
    }
    for k in ("C1", "C4"):
        assert sum(per_class[k]) / 30 == pytest.approx(0.6111, abs=5e-4)
    for k in ("C2", "C3"):
        assert sum(per_class[k]) / 30 == pytest.approx(0.5000, abs=1e-9)
    arm_a = per_class["C1"] + per_class["C2"]
    arm_b = per_class["C3"] + per_class["C4"]
    mean_a = sum(arm_a) / len(arm_a)
    mean_b = sum(arm_b) / len(arm_b)
    assert mean_a == pytest.approx(0.5556, abs=5e-4)
    assert mean_a - mean_b == pytest.approx(0.0, abs=1e-9)


@needs_split
def test_the_verified_subset_has_no_c4_and_the_docs_say_so():
    cf = confound_report(load_split(TEST_SPLIT)[0])
    assert cf["C4"].n_verified == 0
    assert cf["C1"].verdict == "CONFOUNDED_ANSWER_TYPE"
    assert cf["C2"].comparable and cf["C3"].comparable
    assert cf["C3"].chance_gap == pytest.approx(0.0, abs=1e-12)
    docs = _all_docs()
    assert "0.0417" in docs, "the S3 chance gap must be stated"
    assert "zero C4" in docs or "no EVIDENCE_VERIFIED C4" in docs or "C4 | 0" in docs


@needs_split
def test_probe_c_flags_43_probes_in_three_cells():
    cons, probe_list = load_split(TEST_SPLIT)
    by: dict[str, list] = {}
    for p in probe_list:
        by.setdefault(p.constraint_id, []).append(p)
    _, summary = probe_audit(cons, by)
    assert summary["n_flagged"] == 43
    assert summary["by_factor_cell"]["POLAR_CLOZE_STEM_EMBEDS_GOLD_ANSWER"] == {
        "04": 16, "06": 11, "07": 16
    }
    assert "43" in _all_docs()


def test_28_predicates_5_implementations_matches_the_docs():
    cov = mechanism_coverage(default_registry())
    assert cov["n_registered_predicates"] == 28
    assert cov["n_distinct_pairwise_implementations"] == 5
    assert "28" in _all_docs()


# --- configuration the docs describe ------------------------------------

def test_d2_is_pinned_to_a_40_hex_revision_with_a_label_order():
    cfg = yaml.safe_load((project_root() / "configs/detectors/d2_nli.yaml").read_text())
    rev = cfg["checkpoint_selection"]["revision"]
    assert isinstance(rev, str) and len(rev) == 40
    assert all(ch in "0123456789abcdef" for ch in rev)
    assert cfg["checkpoint_selection"]["selection_performed"] is False
    scoring = cfg["scoring"]
    assert scoring["contradiction_index"] == 2
    assert scoring["label_order"][2] == "contradiction"
    assert scoring["produces_verdict"] is False
    assert cfg["threshold"]["status"] == "WITHDRAWN"
    assert cfg["threshold"]["default_0_5_forbidden"] is True
    assert cfg["rank_concordance"]["is_accuracy"] is False


def test_d4_is_frozen_at_T_1_with_the_band_the_code_uses():
    from semintegrity.detectors.d4.distributional import (
        PRIMARY_TEMPERATURE,
        SENSITIVITY_TEMPERATURES,
    )

    cfg = yaml.safe_load(
        (project_root() / "configs/detectors/d4_distributional.yaml").read_text()
    )
    dc = cfg["method"]["distribution_construction"]
    assert dc["status"] == "RESOLVED"
    assert dc["temperature"] == PRIMARY_TEMPERATURE == 1.0
    assert tuple(dc["sensitivity_band"]) == SENSITIVITY_TEMPERATURES
    assert dc["cross_temperature_magnitude_comparison"] == "forbidden"


def test_the_canon_threshold_is_still_095_and_unchanged():
    """CANON is FROZEN. Nothing in the redesign may move it."""
    from semintegrity.analysis.evaluate import canon_threshold

    assert canon_threshold() == 0.95
    pilot = yaml.safe_load((project_root() / "configs/inference/pilot.yaml").read_text())
    canon = next(c for c in pilot["go_no_go"] if c["id"] == "CANON")
    assert ">= 95%" in canon["criterion"]
    assert canon["status"] == "RETAINED_AND_FROZEN"


def test_the_revised_go_no_go_matches_adr_0023():
    pilot = yaml.safe_load((project_root() / "configs/inference/pilot.yaml").read_text())
    ids = [c["id"] for c in pilot["go_no_go"]]
    assert ids == ["GT", "PROBE-C", "CANON", "D0AUDIT-A", "NONDEGEN", "ABSTAIN"]
    assert [c["id"] for c in pilot["removed_go_no_go"]] == ["IAA"]
    # the ORIGINAL preregistered wording must remain traceable
    superseded = {c["id"]: c["criterion"] for c in pilot["superseded_go_no_go"]}
    assert "human semantic-equivalence validation" in superseded["PROBE"]
    assert "three-instance schema audit" in superseded["D0AUDIT"]
    assert "inter-annotator agreement" in superseded["IAA"]


def test_nondegen_no_longer_conflicts_between_two_configs():
    """Checks the PARSED value, not the raw text.

    The amendment comment in `_judge.yaml` deliberately quotes the superseded
    wording so the preregistration history stays traceable, so a grep over the
    file would fail for the right reason stated the wrong way round.
    """
    judge = yaml.safe_load((project_root() / "configs/models/_judge.yaml").read_text())
    required = judge["primary_judge"]["verification_required"]
    nondegen = [r for r in required if "NONDEGEN" in r]
    assert len(nondegen) == 1, required
    assert "label distribution must be non-degenerate" in nondegen[0]
    assert "judge-vs-human" not in nondegen[0], (
        "the effective criterion must not require human labels"
    )
    # and the superseded wording survives as a comment, for traceability
    raw = (project_root() / "configs/models/_judge.yaml").read_text()
    assert "judge-vs-human agreement must be non-degenerate" in raw


# --- the prohibitions ----------------------------------------------------

def test_the_docs_state_every_withdrawn_claim():
    docs = _all_docs()
    for claim in ("precision", "recall", "AUPRC", "Krippendorff",
                  "inter-annotator agreement"):
        assert claim in docs, f"{claim} must be named as withdrawn, not omitted"
    assert "HUMAN_VALIDATED" in docs


def test_the_gold_gate_is_still_active_in_code():
    """detector_scores must keep refusing accuracy without human labels."""
    from semintegrity.analysis.detector_scores import (
        GoldStandardMissing,
        require_human_gold,
    )

    with pytest.raises(GoldStandardMissing):
        require_human_gold("D1")
    with pytest.raises(GoldStandardMissing):
        require_human_gold("D3")


def test_no_analysis_module_imports_the_gold_scoring_module():
    """The redesign's central prohibition, enforced structurally."""
    import ast

    root = project_root() / "src" / "semintegrity" / "analysis"
    offenders = []
    for path in root.glob("*.py"):
        if path.name in ("detector_scores.py", "__init__.py"):
            continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            mod = ""
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
            elif isinstance(node, ast.Import):
                mod = " ".join(a.name for a in node.names)
            if "detector_scores" in mod:
                offenders.append(path.name)
    assert not offenders, f"these modules reach the gold-scoring module: {offenders}"
