"""D3 — pairwise LLM judge (§4.8.5, configs/detectors/d3_llm_judge.yaml).

Implements what the configuration specifies:

* **unit: pair** — `set_level_verdict_forbidden: true`, because a set-level
  verdict discards which pair conflicted and invites position effects.
* **single_shot** — like-for-like with D1 and D2. No ensembling.
* **randomise_ab_order** — the judge sees A and B in an order decided by a
  seeded RNG, and the realised order is recorded so the flip is auditable
  rather than merely asserted.
* **structured output** — label, confidence, conflicting spans, reason.
* **archive every raw judgement** — the unparsed text is kept on the record,
  so a parsing change can be re-run against what the judge actually said.

The judge model is NOT chosen here; it is already decided in
`configs/models/_judge.yaml` (microsoft/phi-4, revision pinned, ADR-0008) with
the hard constraint that its lineage touch none of {llama, mistral, qwen,
gemma}. This module takes any callable text generator, so the protocol is
testable without 29 GB of weights.

**Malformed output is a RESULT, not an exception.** A judge that emits prose
instead of JSON has failed to answer, which is different from answering
UNCLEAR, and different again from answering CONTRADICTION. All three are
distinguishable on the record: `label=None` with `parse_error` set, versus
`label=UNCLEAR`, versus a real verdict. Collapsing an unparseable reply into
UNCLEAR would silently convert a broken run into usable-looking data.
"""

from __future__ import annotations

import json
import random
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from itertools import combinations
from typing import Protocol

from ...schemas.constraint import Constraint
from ...schemas.enums import DetectorId, Verdict
from ...schemas.response import CanonicalResponse
from ...utils.ids import pair_id
from ..d2.templates import render_claim

VALID_LABELS = ("CONTRADICTION", "COMPATIBLE", "UNCLEAR")

#: Matches the first {...} block, so a judge that prefixes "Here is my answer:"
#: is still parsed. Extraction is generous; VALIDATION is not.
_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


class TextGenerator(Protocol):
    """Anything that maps a prompt to a completion."""

    name: str

    def generate(self, prompt: str) -> str: ...


@dataclass(frozen=True, slots=True)
class D3Judgement:
    """One judgement, with everything needed to audit it after the fact."""

    pair_id: str
    probe_a: str
    probe_b: str
    #: True when the judge was shown the pair with A and B swapped. The verdict
    #: is reported in the CALLER's orientation regardless; this records what the
    #: judge actually saw, which is what a position-effect analysis needs.
    presented_swapped: bool
    label: str | None
    confidence: float | None
    conflicting_span_a: str | None
    conflicting_span_b: str | None
    reason: str
    raw_output: str
    prompt: str
    judge: str
    parse_error: str | None = None
    detector: str = DetectorId.D3.value

    @property
    def verdict(self) -> Verdict:
        if self.label == "CONTRADICTION":
            return Verdict.VIOLATION
        if self.label == "COMPATIBLE":
            return Verdict.SATISFIED
        # UNCLEAR, or unparseable: D3 reached no decision. Both are
        # NOT_APPLICABLE for coverage, and `parse_error` separates them.
        return Verdict.NOT_APPLICABLE

    @property
    def is_contradiction(self) -> bool:
        return self.verdict is Verdict.VIOLATION

    @property
    def parsed(self) -> bool:
        return self.parse_error is None


def parse_judgement(text: str) -> tuple[dict, str | None]:
    """Extract the structured verdict, or say why it could not be extracted.

    Returns (fields, error). `error` is None only when every required field is
    present AND valid. Never raises: a malformed judgement is data about the
    judge, and losing it to an exception would lose the evidence.
    """
    match = _JSON_BLOCK.search(text or "")
    if not match:
        return {}, "no JSON object found in judge output"
    try:
        obj = json.loads(match.group())
    except json.JSONDecodeError as exc:
        return {}, f"invalid JSON: {exc.msg}"
    if not isinstance(obj, dict):
        return {}, f"JSON is {type(obj).__name__}, expected an object"

    label = obj.get("label")
    if label is None:
        return obj, "missing 'label'"
    if not isinstance(label, str) or label.upper() not in VALID_LABELS:
        return obj, f"label {label!r} is not one of {VALID_LABELS}"

    confidence = obj.get("confidence")
    if confidence is None:
        return obj, "missing 'confidence'"
    if isinstance(confidence, bool) or not isinstance(confidence, int | float):
        return obj, f"confidence {confidence!r} is not a number"
    if not 0.0 <= float(confidence) <= 1.0:
        return obj, f"confidence {confidence} is outside [0, 1]"

    return obj, None


@dataclass
class D3Judge:
    """Pairwise LLM judge. `seed` makes the A/B randomisation reproducible."""

    generator: TextGenerator
    prompt_template: str
    seed: int = 20250058
    _rng: random.Random = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if "{claim_a}" not in self.prompt_template or "{claim_b}" not in self.prompt_template:
            raise ValueError("prompt template must contain {claim_a} and {claim_b}")
        self._rng = random.Random(self.seed)

    def judge_pair(
        self, constraint: Constraint, a: CanonicalResponse, b: CanonicalResponse
    ) -> D3Judgement | None:
        """Judge one pair, or None if either response makes no claim.

        Returning None rather than an UNCLEAR judgement keeps "the judge could
        not decide" distinct from "there was nothing to judge".
        """
        claim_a, claim_b = render_claim(constraint, a), render_claim(constraint, b)
        if claim_a is None or claim_b is None:
            return None

        swapped = self._rng.random() < 0.5
        shown_a, shown_b = (claim_b, claim_a) if swapped else (claim_a, claim_b)
        prompt = self.prompt_template.format(
            constraint_text=constraint.constraint_text, claim_a=shown_a, claim_b=shown_b
        )
        raw = self.generator.generate(prompt)
        obj, error = parse_judgement(raw)

        span_a = obj.get("conflicting_span_a")
        span_b = obj.get("conflicting_span_b")
        if swapped:
            # Report in the CALLER's orientation: the judge's "A" was our B.
            span_a, span_b = span_b, span_a

        label = obj.get("label")
        return D3Judgement(
            pair_id=pair_id(a.probe_id, b.probe_id),
            probe_a=a.probe_id, probe_b=b.probe_id,
            presented_swapped=swapped,
            label=(label.upper() if error is None and isinstance(label, str) else None),
            confidence=(float(obj["confidence"]) if error is None else None),
            conflicting_span_a=span_a if isinstance(span_a, str) else None,
            conflicting_span_b=span_b if isinstance(span_b, str) else None,
            reason=str(obj.get("reason", "")),
            raw_output=raw, prompt=prompt, judge=self.generator.name,
            parse_error=error,
        )

    def judge_all_pairs(
        self, constraint: Constraint, responses: Sequence[CanonicalResponse]
    ) -> list[D3Judgement]:
        out = []
        for a, b in combinations(responses, 2):
            j = self.judge_pair(constraint, a, b)
            if j is not None:
                out.append(j)
        return out


def coverage(judgements: Sequence[D3Judgement], n_pairs: int) -> float:
    """Fraction of ALL pairs on which D3 reached a decision.

    The denominator is every pair of the constraint, not just the ones judged,
    so pairs skipped for want of a claim register as reduced coverage rather
    than disappearing.
    """
    if n_pairs <= 0:
        return 0.0
    decided = sum(j.verdict is not Verdict.NOT_APPLICABLE for j in judgements)
    return decided / n_pairs


def parse_failure_rate(judgements: Sequence[D3Judgement]) -> float:
    """Share of judgements whose output could not be parsed — report it.

    A rising parse-failure rate means the judge is drifting off-format, which
    is a property of the run and must not be hidden inside UNCLEAR.
    """
    if not judgements:
        return 0.0
    return sum(not j.parsed for j in judgements) / len(judgements)
