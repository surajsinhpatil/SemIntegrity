"""Detector performance against human gold (§4.10 `detector_scores`).

**Nothing here can be reported yet.** The gold standard is human annotation and
none exists. This module is the interface those numbers will flow through, and
it is written now so the analysis is fixed before the labels arrive rather than
shaped by them.

Two guards make the absence loud rather than quiet:

* `DetectorScores.gold_source` is required, and `require_human_gold()` rejects
  anything not marked as adjudicated human annotation. A score computed against
  another detector's output is a detector-agreement statistic, not performance,
  and must never be labelled precision or recall.
* `auprc` refuses detectors without a continuous score. Q7 records that D0 and
  D1 are binary and have a single operating point; an AUPRC for them would be
  an artefact of interpolating between two points.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

#: Only these count as gold. Anything else is detector agreement, not accuracy.
HUMAN_GOLD_SOURCES = frozenset({"human_adjudicated", "human_consensus"})

#: Q7: AUPRC needs a continuous score, so it applies to D2 and D3 only.
CONTINUOUS_SCORE_DETECTORS = frozenset({"D2", "D3"})


class GoldStandardMissing(RuntimeError):
    """Detector performance was requested without human gold labels."""


@dataclass(frozen=True, slots=True)
class ConfusionMatrix:
    tp: int
    fp: int
    fn: int
    tn: int

    @property
    def n(self) -> int:
        return self.tp + self.fp + self.fn + self.tn

    @property
    def precision(self) -> float | None:
        d = self.tp + self.fp
        return self.tp / d if d else None      # nothing predicted positive

    @property
    def recall(self) -> float | None:
        d = self.tp + self.fn
        return self.tp / d if d else None      # no positives in the gold set

    @property
    def f1(self) -> float | None:
        p, r = self.precision, self.recall
        if p is None or r is None or (p + r) == 0:
            return None
        return 2 * p * r / (p + r)


def confusion_matrix(
    predicted: Sequence[bool], gold: Sequence[bool]
) -> ConfusionMatrix:
    if len(predicted) != len(gold):
        raise ValueError(f"{len(predicted)} predictions vs {len(gold)} gold labels")
    tp = sum(p and g for p, g in zip(predicted, gold, strict=True))
    fp = sum(p and not g for p, g in zip(predicted, gold, strict=True))
    fn = sum((not p) and g for p, g in zip(predicted, gold, strict=True))
    tn = sum((not p) and (not g) for p, g in zip(predicted, gold, strict=True))
    return ConfusionMatrix(tp, fp, fn, tn)


def average_precision(scores: Sequence[float], gold: Sequence[bool]) -> float | None:
    """Area under the precision-recall curve, by the step-wise AP estimator.

    AP is used rather than trapezoidal interpolation because interpolating a PR
    curve is optimistically biased at low positive counts, which is exactly the
    regime here.
    """
    if len(scores) != len(gold):
        raise ValueError(f"{len(scores)} scores vs {len(gold)} gold labels")
    n_pos = sum(gold)
    if n_pos == 0 or not scores:
        return None                 # undefined without positives
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    tp = 0
    total = 0.0
    for rank, idx in enumerate(order, start=1):
        if gold[idx]:
            tp += 1
            total += tp / rank      # precision at this recall step
    return total / n_pos


@dataclass(frozen=True, slots=True)
class DetectorScores:
    """Performance of one detector, on one stratum, against human gold."""

    detector: str
    stratum: str
    gold_source: str
    n_items: int
    n_gold_positive: int
    confusion: ConfusionMatrix
    auprc: float | None
    auprc_note: str = ""

    @property
    def precision(self) -> float | None:
        return self.confusion.precision

    @property
    def recall(self) -> float | None:
        return self.confusion.recall

    @property
    def f1(self) -> float | None:
        return self.confusion.f1


def require_human_gold(gold_source: str) -> None:
    """Refuse to compute performance against anything but adjudicated humans."""
    if gold_source not in HUMAN_GOLD_SOURCES:
        raise GoldStandardMissing(
            f"gold_source {gold_source!r} is not human annotation "
            f"(expected one of {sorted(HUMAN_GOLD_SOURCES)}). Precision, recall, "
            "F1 and AUPRC are defined against HUMAN gold only; scoring against "
            "another detector measures agreement, not accuracy, and must not be "
            "reported as detector performance."
        )


def score_detector(
    detector: str,
    predicted: Sequence[bool],
    gold: Sequence[bool],
    *,
    gold_source: str,
    stratum: str = "all",
    scores: Sequence[float] | None = None,
) -> DetectorScores:
    """P/R/F1 at the operating point, plus AUPRC where a score exists (Q7)."""
    require_human_gold(gold_source)
    cm = confusion_matrix(predicted, gold)

    auprc: float | None = None
    note = ""
    if detector not in CONTINUOUS_SCORE_DETECTORS:
        note = (
            f"{detector} is binary with a single operating point; Q7 records "
            "AUPRC as not applicable. An AUPRC here would interpolate between "
            "two points and mean nothing."
        )
    elif scores is None:
        note = f"{detector} supports AUPRC but no continuous scores were supplied"
    else:
        auprc = average_precision(scores, gold)
        if auprc is None:
            note = "no positive gold labels in this stratum; AUPRC undefined"

    return DetectorScores(
        detector=detector, stratum=stratum, gold_source=gold_source,
        n_items=len(predicted), n_gold_positive=sum(gold),
        confusion=cm, auprc=auprc, auprc_note=note,
    )
