"""D2 — NLI contradiction detection over declarative renderings (§4.8.4).

Implements exactly what `configs/detectors/d2_nli.yaml` specifies, and refuses
to go beyond it:

* **bidirectional** — NLI is asymmetric, so both orderings are scored.
* **aggregate: max_contradiction_probability** — the pair's score is the larger
  of the two contradiction probabilities.
* **threshold: calibrated per_class, `default_0_5_forbidden: true`** — so this
  module will NOT produce verdicts without calibrated thresholds. A bare 0.5 is
  not available even as a fallback.

The split that makes that workable:

``score_pair``   always available. Returns a contradiction probability. This is
                 what CALIBRATION consumes, and calibration is what produces the
                 thresholds, so scoring cannot require them.
``check_pair``   requires a calibrated threshold for the constraint's class and
                 raises without one. This is what ANALYSIS consumes.

So the detector can be run to gather scores today and can only emit verdicts
once thresholds exist. That ordering is the specification's, not a limitation of
the implementation.

**The checkpoint is not chosen here.** `d2_nli.yaml` records
`checkpoint_selection.status: EMPIRICAL_NOT_ASSUMED` with `selected: null` and
four candidates, to be chosen by best AUPRC against human-labelled dev pairs.
Selecting one in code would decide an empirical question by fiat, so the
checkpoint is a required argument with no default.

The scorer is injected behind :class:`NLIScorer`, so the detector's logic is
testable without a GPU or a 1.5 GB download, and so the pipeline can be
exercised end to end before any checkpoint is chosen.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from itertools import combinations
from typing import Protocol

from ...schemas.constraint import Constraint
from ...schemas.enums import DetectorId, Verdict
from ...schemas.response import CanonicalResponse
from ...utils.ids import pair_id
from .templates import render_claim


class NLIScorer(Protocol):
    """Anything that returns P(contradiction) for a premise/hypothesis pair."""

    name: str

    def contradiction_probability(self, premise: str, hypothesis: str) -> float:
        """Probability in [0, 1] that the hypothesis contradicts the premise."""
        ...


class ThresholdNotCalibrated(RuntimeError):
    """A verdict was requested without a calibrated per-class threshold."""


@dataclass(frozen=True, slots=True)
class D2Score:
    """The bidirectional scoring of one pair, before any threshold is applied."""

    pair_id: str
    probe_a: str
    probe_b: str
    claim_a: str | None
    claim_b: str | None
    p_forward: float | None
    p_backward: float | None
    scorer: str
    detector: str = DetectorId.D2.value

    @property
    def evaluable(self) -> bool:
        return self.p_forward is not None and self.p_backward is not None

    @property
    def contradiction_probability(self) -> float | None:
        """max over both directions — `aggregate: max_contradiction_probability`."""
        if not self.evaluable:
            return None
        return max(self.p_forward, self.p_backward)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class D2Result:
    pair_id: str
    probe_a: str
    probe_b: str
    verdict: Verdict
    score: float | None
    threshold: float | None
    detector: str = DetectorId.D2.value
    reason: str = ""

    @property
    def is_contradiction(self) -> bool:
        return self.verdict is Verdict.VIOLATION


@dataclass
class D2Detector:
    """NLI contradiction detection, per `configs/detectors/d2_nli.yaml`."""

    scorer: NLIScorer
    #: class value ("C1".."C4") -> calibrated threshold. Empty means uncalibrated.
    thresholds: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for cls, value in self.thresholds.items():
            if not 0.0 < value < 1.0:
                raise ValueError(f"threshold for {cls} must be in (0,1), got {value}")
            if value == 0.5:
                # d2_nli.yaml: "A bare 0.5 threshold is never used."
                raise ValueError(
                    f"threshold for {cls} is exactly 0.5, which "
                    "configs/detectors/d2_nli.yaml forbids as an uncalibrated default"
                )

    # -- scoring: always available -----------------------------------------
    def score_pair(
        self, constraint: Constraint, a: CanonicalResponse, b: CanonicalResponse
    ) -> D2Score:
        pid = pair_id(a.probe_id, b.probe_id)
        claim_a, claim_b = render_claim(constraint, a), render_claim(constraint, b)
        if claim_a is None or claim_b is None:
            return D2Score(pid, a.probe_id, b.probe_id, claim_a, claim_b,
                           None, None, self.scorer.name)
        return D2Score(
            pid, a.probe_id, b.probe_id, claim_a, claim_b,
            self.scorer.contradiction_probability(claim_a, claim_b),
            self.scorer.contradiction_probability(claim_b, claim_a),
            self.scorer.name,
        )

    def score_all_pairs(
        self, constraint: Constraint, responses: Sequence[CanonicalResponse]
    ) -> list[D2Score]:
        return [self.score_pair(constraint, a, b) for a, b in combinations(responses, 2)]

    # -- verdicts: require calibration --------------------------------------
    def threshold_for(self, constraint: Constraint) -> float:
        cls = constraint.constraint_class.value
        try:
            return self.thresholds[cls]
        except KeyError:
            raise ThresholdNotCalibrated(
                f"no calibrated D2 threshold for class {cls}. "
                "configs/detectors/d2_nli.yaml requires per-class thresholds "
                "calibrated on the development split and forbids a 0.5 default; "
                "run scripts/detectors/calibrate_d2.py first, or use score_pair() "
                "to gather the scores calibration needs."
            ) from None

    def check_pair(
        self, constraint: Constraint, a: CanonicalResponse, b: CanonicalResponse
    ) -> D2Result:
        threshold = self.threshold_for(constraint)
        s = self.score_pair(constraint, a, b)
        if not s.evaluable:
            return D2Result(
                s.pair_id, s.probe_a, s.probe_b, Verdict.NOT_APPLICABLE, None, threshold,
                reason=f"no declarative claim for {a.label.value}/{b.label.value}",
            )
        p = s.contradiction_probability
        assert p is not None
        verdict = Verdict.VIOLATION if p >= threshold else Verdict.SATISFIED
        return D2Result(
            s.pair_id, s.probe_a, s.probe_b, verdict, p, threshold,
            reason=f"max bidirectional P(contradiction)={p:.4f} vs threshold {threshold:.4f}",
        )

    def check_all_pairs(
        self, constraint: Constraint, responses: Sequence[CanonicalResponse]
    ) -> list[D2Result]:
        return [self.check_pair(constraint, a, b) for a, b in combinations(responses, 2)]


def coverage(results: Sequence[D2Result]) -> float:
    """Fraction of pairs D2 could evaluate — reported, never silently dropped."""
    if not results:
        return 0.0
    return sum(r.verdict is not Verdict.NOT_APPLICABLE for r in results) / len(results)


class HuggingFaceNLIScorer:
    """Real scorer. Constructed only where a GPU and the checkpoint exist.

    The checkpoint is REQUIRED and has no default: `d2_nli.yaml` records the
    selection as `EMPIRICAL_NOT_ASSUMED` with four candidates, to be chosen by
    best AUPRC against human-labelled dev pairs. Hard-coding one would settle an
    empirical question by import.
    """

    def __init__(self, checkpoint: str, *, device: str = "cpu", revision: str | None = None):
        if not checkpoint:
            raise ValueError(
                "D2 requires an explicit NLI checkpoint; d2_nli.yaml lists the "
                "candidates and records the choice as EMPIRICAL_NOT_ASSUMED"
            )
        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
        except ImportError as exc:  # pragma: no cover - GPU nodes only
            raise RuntimeError("torch and transformers are required for D2") from exc

        self.name = f"{checkpoint}@{revision}" if revision else checkpoint
        self._torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(checkpoint, revision=revision)
        self.model = AutoModelForSequenceClassification.from_pretrained(
            checkpoint, revision=revision
        ).to(device).eval()
        self.device = device
        labels = {v.lower(): k for k, v in self.model.config.id2label.items()}
        if "contradiction" not in labels:
            raise ValueError(
                f"{checkpoint} has no 'contradiction' label (id2label="
                f"{self.model.config.id2label}); it is not an NLI checkpoint"
            )
        self.contradiction_index = labels["contradiction"]

    def contradiction_probability(self, premise: str, hypothesis: str) -> float:  # pragma: no cover
        with self._torch.no_grad():
            enc = self.tokenizer(premise, hypothesis, return_tensors="pt",
                                 truncation=True).to(self.device)
            probs = self.model(**enc).logits.softmax(dim=-1)[0]
        return float(probs[self.contradiction_index])
