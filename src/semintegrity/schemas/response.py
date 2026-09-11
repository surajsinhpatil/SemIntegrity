"""Model response records with mandatory provenance (proposal §4.6).

The proposal lists 22 provenance fields "logged per response". All 22 are
**required** here, so a response missing one is rejected at write time rather
than discovered to be missing during analysis, when the GPU hours that produced
it are long gone.

Two records:

``RawResponse``       exactly what the model produced, immutable (§5.6).
``CanonicalResponse`` the Stage 0 mapping of a RawResponse (§4.7), which links
                      back to its source by ``response_id`` and never replaces it.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..utils.ids import CONSTRAINT_RE, PROBE_RE
from .enums import ResponseLabel, Tier, Track

NonEmptyStr = Annotated[str, Field(min_length=1)]

#: The 22 fields §4.6 requires on every response. Asserted against the schema by
#: `tests/unit/test_schemas.py`, so the two can never drift apart.
REQUIRED_PROVENANCE_FIELDS: tuple[str, ...] = (
    "model_id",
    "hf_revision_hash",
    "tokenizer_hash",
    "transformers_version",
    "vllm_version",
    "torch_version",
    "cuda_version",
    "gpu_model",
    "dtype",
    "quantisation",
    "temperature",
    "top_p",
    "top_k",
    "repetition_penalty",
    "max_new_tokens",
    "stop_sequences",
    "chat_template_hash",
    "rendered_prompt",
    "seed",
    "batch_size",
    "sample_index",
    "timestamp",
)


class Provenance(BaseModel):
    """Everything needed to re-create the conditions of one generation.

    Nothing here has a default: a missing value must be supplied by the runner,
    not silently filled in. ``quantisation`` is required even though the primary
    plan is always ``none`` — recording it explicitly is what makes the "no
    selective quantisation" claim (§4.6) auditable after the fact.
    """

    model_config = ConfigDict(extra="forbid")

    # identity of the weights
    model_id: NonEmptyStr
    hf_revision_hash: NonEmptyStr = Field(description="real commit SHA; never fabricated")
    tokenizer_hash: NonEmptyStr
    chat_template_hash: NonEmptyStr

    # software stack
    transformers_version: NonEmptyStr
    vllm_version: NonEmptyStr
    torch_version: NonEmptyStr
    cuda_version: NonEmptyStr

    # hardware and precision
    gpu_model: NonEmptyStr
    dtype: NonEmptyStr
    quantisation: NonEmptyStr = Field(description="'none' for the primary plan (§4.6)")

    # decoding
    temperature: float = Field(ge=0.0)
    top_p: float = Field(gt=0.0, le=1.0)
    top_k: int
    repetition_penalty: float = Field(gt=0.0)
    max_new_tokens: int = Field(gt=0)
    stop_sequences: list[str]
    seed: int

    # the exact input and the batching context
    rendered_prompt: NonEmptyStr = Field(
        description="the fully rendered prompt string after the model's own chat template (§4.6)"
    )
    batch_size: int = Field(gt=0)
    sample_index: int = Field(ge=0, description="0 for greedy; 0..n-1 for the stochastic subset")
    timestamp: dt.datetime

    @model_validator(mode="after")
    def _decoding_coherent(self) -> Provenance:
        if self.temperature == 0.0 and self.sample_index != 0:
            raise ValueError(
                "temperature 0 admits only sample_index 0; a repeated greedy sample "
                "belongs to the determinism check, which records it as a separate run"
            )
        return self


class RawResponse(BaseModel):
    """One immutable model output.

    Never edited after creation. Stage 0 produces a *separate* CanonicalResponse
    that points back here (§4.7: responses are never manually cleaned).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    response_id: str = Field(pattern=r"^R-[0-9a-f]{12}$")
    run_id: NonEmptyStr
    experiment_id: NonEmptyStr
    config_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    constraint_id: str = Field(pattern=CONSTRAINT_RE.pattern)
    probe_id: str = Field(pattern=PROBE_RE.pattern)
    tier: Tier
    track: Track
    semantic_instruction_id: NonEmptyStr

    raw_text: str = Field(description="verbatim model output; may be empty (-> INVALID at Stage 0)")
    finish_reason: str = ""
    n_generated_tokens: int | None = Field(default=None, ge=0)
    latency_ms: float | None = Field(default=None, ge=0)
    timed_out: bool = False
    retry_index: int = Field(default=0, ge=0, le=1, description="§4.7 allows exactly one retry")

    provenance: Provenance

    @model_validator(mode="after")
    def _probe_belongs_to_constraint(self) -> RawResponse:
        if not self.probe_id.startswith(self.constraint_id + "-P"):
            raise ValueError(f"probe {self.probe_id} does not belong to {self.constraint_id}")
        return self

    def resume_key(self) -> tuple[str, str, str, int]:
        """The key that makes re-submitting a killed job safe (ADR-0005)."""
        return (self.experiment_id, self.provenance.model_id, self.probe_id, self.provenance.sample_index)


class CanonicalResponse(BaseModel):
    """Stage 0 output (§4.7). Derived, and always traceable to its source."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    response_id: str = Field(description="the RawResponse this was derived from")
    constraint_id: str = Field(pattern=CONSTRAINT_RE.pattern)
    probe_id: str = Field(pattern=PROBE_RE.pattern)

    label: ResponseLabel
    canonical_answer: str | None = Field(
        default=None, description="a member of the constraint's answer_space; set iff label is ANSWER"
    )
    matched_alias: str | None = Field(default=None, description="the surface form that matched")
    candidates_found: list[str] = Field(
        default_factory=list, description="all answer-space members detected; >1 implies AMBIGUOUS"
    )

    canonicaliser_version: NonEmptyStr
    canonicaliser_sha256: str = Field(pattern=r"^[0-9a-f]{64}$", description="freeze marker")
    canonicalised_at: dt.datetime
    notes: str = ""

    @model_validator(mode="after")
    def _label_answer_coherence(self) -> CanonicalResponse:
        if self.label is ResponseLabel.ANSWER and not self.canonical_answer:
            raise ValueError("label ANSWER requires a canonical_answer")
        if self.label is not ResponseLabel.ANSWER and self.canonical_answer:
            raise ValueError(
                f"label {self.label.value} must not carry a canonical_answer "
                f"(got {self.canonical_answer!r})"
            )
        if self.label is ResponseLabel.AMBIGUOUS and len(self.candidates_found) < 2:
            raise ValueError("AMBIGUOUS requires at least two mutually exclusive candidates")
        return self

    @property
    def is_evaluable(self) -> bool:
        """Whether this response can participate in an evaluable pair (Q6)."""
        return self.label is ResponseLabel.ANSWER


def pair_is_evaluable(a: CanonicalResponse, b: CanonicalResponse) -> bool:
    """A pair is evaluable iff BOTH responses canonicalise to an ANSWER.

    Q6 — proposed definition, pending confirmation at Phase 4 preregistration.
    It is defined in exactly one place so the preregistered rule and the code
    cannot diverge.
    """
    return a.is_evaluable and b.is_evaluable
