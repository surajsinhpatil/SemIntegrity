"""The concrete D2 and D4 scorers, and the guards around them.

Both detectors previously had only a Protocol and no implementation, so neither
could run. These tests pin the properties that matter without loading a model:
the refusals, the label-order verification, and the arithmetic.
"""

from __future__ import annotations

from typing import ClassVar

import pytest
import yaml

from semintegrity.detectors.d2.scorer import TransformersNLIScorer, from_config
from semintegrity.detectors.d4.scorer import TeacherForcedScorer
from semintegrity.utils.paths import project_root

D2_CFG = yaml.safe_load(
    (project_root() / "configs/detectors/d2_nli.yaml").read_text()
)


# --- pinned revisions are mandatory --------------------------------------

@pytest.mark.parametrize("bad", [None, "", "abc", "z" * 40, "a" * 39])
def test_d2_refuses_an_unpinned_revision(bad):
    with pytest.raises(ValueError, match="pinned 40-hex revision"):
        TransformersNLIScorer(
            model_id="m", revision=bad, contradiction_index=2
        )


@pytest.mark.parametrize("bad", [None, "", "abc", "a" * 39])
def test_d4_refuses_an_unpinned_revision(bad):
    with pytest.raises(ValueError, match="pinned 40-hex revision"):
        TeacherForcedScorer(model_id="m", revision=bad)


def test_d2_from_config_reads_every_parameter_from_the_config():
    """Nothing is defaulted in the builder, so a config change is the only way
    to change what runs."""
    s = from_config(D2_CFG)
    assert s.model_id == D2_CFG["checkpoint_selection"]["selected"]
    assert s.revision == D2_CFG["checkpoint_selection"]["revision"]
    assert s.contradiction_index == 2
    assert s.dtype == "float32"
    assert s.batch_size == 32
    assert s.max_length == 512
    assert s.expected_label_order[2] == "contradiction"
    assert s.name.startswith("MoritzLaurer/DeBERTa-v3-large-mnli")


def test_scoring_before_load_raises_rather_than_returning_a_number():
    s = from_config(D2_CFG)
    with pytest.raises(RuntimeError, match="call load"):
        s.contradiction_probability("a", "b")

    d4 = TeacherForcedScorer(model_id="m", revision="a" * 40)
    with pytest.raises(RuntimeError, match="call load"):
        d4.mean_token_logprobs("prompt", ["x"])


def test_d4_refuses_an_empty_candidate_set():
    d4 = TeacherForcedScorer(model_id="m", revision="a" * 40)
    d4._model = object()          # bypass load; the check must come first
    with pytest.raises(ValueError, match="empty candidate set"):
        d4.mean_token_logprobs("prompt", [])


# --- the label-order guard, which is the one silent-failure mode ---------

def test_the_label_order_guard_rejects_a_mismatched_checkpoint(monkeypatch):
    """If `contradiction` were index 0 and the code read index 2, every score
    would be an entailment probability and the ordering would invert. Nothing
    downstream could notice, so the scorer refuses at load time."""
    import semintegrity.detectors.d2.scorer as mod

    class _Cfg:
        id2label: ClassVar[dict[int, str]] = {
            0: "contradiction", 1: "neutral", 2: "entailment"
        }

    class _Model:
        config = _Cfg()
        def to(self, device): return self
        def eval(self): return self

    class _Auto:
        @staticmethod
        def from_pretrained(*a, **k): return _Model()

    class _Tok:
        @staticmethod
        def from_pretrained(*a, **k): return object()

    import sys
    import types
    fake = types.ModuleType("transformers")
    fake.AutoModelForSequenceClassification = _Auto
    fake.AutoTokenizer = _Tok
    monkeypatch.setitem(sys.modules, "transformers", fake)

    s = mod.TransformersNLIScorer(
        model_id="m", revision="a" * 40, contradiction_index=2,
    )
    with pytest.raises(ValueError) as exc:
        s.load()
    msg = str(exc.value)
    assert "REFUSING TO SCORE" in msg
    assert "invert every ordering" in msg


def test_the_config_label_order_matches_the_pinned_revisions_real_labels():
    """Recorded from config.json at revision b3546ea6…; a change to either the
    revision or the recorded order must break here, not at runtime."""
    assert D2_CFG["checkpoint_selection"]["revision"] == (
        "b3546ea6b0346eb6f8d5d68b13c7dc6d0376b3d7"
    )
    assert D2_CFG["scoring"]["label_order"] == {
        0: "entailment", 1: "neutral", 2: "contradiction"
    }
    assert D2_CFG["scoring"]["contradiction_index"] == 2


# --- D2 still has no verdict ---------------------------------------------

def test_d2_detector_built_without_thresholds_still_refuses_verdicts():
    """ADR-0023 D6 changed the estimand; it did not relax the guard."""
    from semintegrity.detectors.d2.nli import D2Detector, ThresholdNotCalibrated
    from semintegrity.schemas.enums import ConstraintClass, Domain
    from tests.fixtures.synthetic_benchmark import make_constraint

    detector = D2Detector(scorer=from_config(D2_CFG))
    c = make_constraint(ConstraintClass.C1, Domain.GEOGRAPHY, 1)
    with pytest.raises(ThresholdNotCalibrated):
        detector.threshold_for(c)


def test_the_d2_driver_never_calls_check_pair():
    """The verdict path must be unreachable from the driver, not merely unused."""
    import ast

    src = (project_root() / "scripts/detectors/run_d2_nli.py").read_text()
    tree = ast.parse(src)
    calls = {
        n.func.attr for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    }
    assert "check_pair" not in calls
    assert "threshold_for" not in calls
    assert "score_all_pairs" in calls


def test_the_d4_driver_refuses_a_config_code_temperature_disagreement():
    """Two definitions of a preregistered quantity is a refusal, not a warning."""
    src = (project_root() / "scripts/analysis/run_d4.py").read_text()
    assert "PRIMARY_TEMPERATURE" in src
    assert "Refusing to run with two definitions" in src


def test_the_d4_driver_requires_the_stored_rendered_prompt():
    src = (project_root() / "scripts/analysis/run_d4.py").read_text()
    assert "rendered_prompt" in src
    assert "re-rendering would change the conditioning" in src.lower()
