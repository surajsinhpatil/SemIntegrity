"""The frozen numbers in the proposal must be arithmetically self-consistent.

If any of these fail, either a config was edited without an ADR or the design
lattice no longer closes.
"""

import math

import pytest

from semintegrity.utils.config import load_config, project_config


@pytest.fixture(scope="module")
def cfg():
    return project_config().data


def test_benchmark_counts_close(cfg):
    b = cfg["benchmark"]
    assert b["constraints_per_class"] * 4 == b["total_constraints"] == 120
    assert b["constraints_per_domain_per_class"] * len(cfg["domains"]) == b["constraints_per_class"]
    assert b["families"] * 4 == b["total_constraints"]
    assert b["families_per_domain"] * len(cfg["domains"]) == b["families"]
    assert b["schemas_per_class"] * b["instances_per_schema"] == b["constraints_per_class"]


def test_primary_probe_counts_close(cfg):
    pr = cfg["probes"]["primary"]
    assert pr["k"] * cfg["benchmark"]["total_constraints"] == pr["total"] == 960
    assert math.comb(pr["k"], 2) == pr["pairs_per_constraint"] == 28


def test_saturation_counts_close(cfg):
    s = cfg["probes"]["saturation"]
    assert s["constraints_per_class"] * 4 == s["constraints"] == 24
    # The first 8 of the 50 are the primary probes, so only 42 are new.
    assert s["constraints"] * (s["k"] - cfg["probes"]["primary"]["k"]) == s["additional_probes"] == 1008
    assert s["evaluated_at_k"][-1] == s["k"]
    assert s["evaluated_at_k"] == sorted(s["evaluated_at_k"])


def test_classes_are_not_ordered(cfg):
    """Guards against anyone modelling class as an ordinal/continuous term."""
    assert cfg["constraint_classes"]["ordered"] is False


def test_modal_and_counterfactual_are_excluded(cfg):
    excluded = {e["id"] for e in cfg["constraint_classes"]["excluded"]}
    assert excluded == {"modal", "counterfactual"}


def test_primary_endpoint_is_pscr_and_triad_is_intact(cfg):
    assert cfg["metrics"]["primary_endpoint"] == "PSCR"
    assert cfg["metrics"]["key_secondary"] == "PCS"
    assert set(cfg["metrics"]["reliability_triad"]) == {
        "TruthAccuracy",
        "PSCR",
        "AbstentionRate",
    }


def test_independent_unit_is_the_constraint(cfg):
    st = cfg["statistics"]
    assert st["independent_unit"] == "constraint"
    assert st["confirmatory"]["arm_size"] * 2 == cfg["benchmark"]["total_constraints"]


def test_quantisation_is_not_selective(cfg):
    assert cfg["inference"]["dtype"] == "bfloat16"
    assert cfg["inference"]["quantisation"] == "none"


def test_d4_is_never_a_detector(cfg):
    assert "NOT a contradiction detector" in cfg["detectors"]["d4_disclaimer"]


def test_seven_models_are_configured():
    from semintegrity.utils.paths import p

    names = sorted(f.stem for f in p("configs/models").glob("*.yaml") if not f.stem.startswith("_"))
    assert len(names) == 7
    families = set()
    for n in names:
        families.add(load_config(f"configs/models/{n}.yaml").data["family"])
    assert families == {"llama", "mistral", "qwen", "gemma"}


def test_no_model_revision_is_fabricated():
    """A revision must be null (unpinned) or a real 40-char hex SHA."""
    from semintegrity.utils.paths import p

    for f in p("configs/models").glob("*.yaml"):
        if f.stem.startswith("_"):
            continue
        rev = load_config(f"configs/models/{f.stem}.yaml").data["revision"]
        assert rev is None or (isinstance(rev, str) and len(rev) == 40 and all(
            c in "0123456789abcdef" for c in rev
        )), f"{f.stem}: suspicious revision {rev!r}"


def test_judge_is_external_to_evaluated_families():
    judge = load_config("configs/models/_judge.yaml").data
    chosen = judge["primary_judge"]["model_id"]
    if chosen is not None:  # still UNRESOLVED at this phase
        lowered = chosen.lower()
        for banned in ("llama", "mistral", "qwen", "gemma"):
            assert banned not in lowered, f"judge {chosen} is inside an evaluated family"


def test_unresolved_scanner_finds_markers_and_ignores_literal_values():
    from semintegrity.utils.config import unresolved_decisions

    found = unresolved_decisions(
        {
            "splits": {"status": "UNRESOLVED"},
            "cluster": {"hostname": "UNKNOWN", "nested": {"gpu": "UNPROBED"}},
            "answer_types": {"abstain_token": "UNKNOWN"},  # literal model token, not a marker
            "fine": {"status": "ACCEPTED"},
        }
    )
    assert set(found) == {
        "splits.status = UNRESOLVED",
        "cluster.hostname = UNKNOWN",
        "cluster.nested.gpu = UNPROBED",
    }


def test_no_hand_written_revision_hashes_in_docs():
    """Every 40-hex SHA in the docs must match a pinned config revision.

    A hash typed by hand is a fabricated provenance claim even when it looks
    right, so the docs may only quote hashes that the pinning script resolved.
    """
    import re

    import yaml

    from semintegrity.utils.paths import p, project_root

    pinned = set()
    for f in p("configs/models").glob("*.yaml"):
        cfg = yaml.safe_load(f.read_text(encoding="utf-8"))
        for value in (cfg.get("revision"), *(
            (cfg.get(k) or {}).get("revision") for k in ("primary_judge", "reproducibility_judge")
        )):
            if isinstance(value, str):
                pinned.add(value)

    offenders = []
    for doc in p("docs").rglob("*.md"):
        for m in re.finditer(r"\b[0-9a-f]{40}\b", doc.read_text(encoding="utf-8")):
            if m.group() not in pinned:
                offenders.append(f"{doc.relative_to(project_root())}: {m.group()}")
    assert not offenders, (
        "documentation contains SHA-like strings that match no pinned revision — "
        f"these are fabricated unless resolved from the Hub: {offenders}"
    )
