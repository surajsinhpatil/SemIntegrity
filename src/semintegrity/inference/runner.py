"""Resumable inference runner (proposal §4.6, §4.13).

Writes incrementally to JSONL so a walltime kill costs at most the in-flight
batch, and skips work already present so re-submitting is always safe (ADR-0005).

Timeouts follow §4.7 exactly: one retry under an identical configuration, then
the response is recorded with ``timed_out`` set and Stage 0 labels it FAILED.
"""

from __future__ import annotations

import datetime as dt
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..schemas.enums import Tier, Track
from ..schemas.probe import Probe
from ..schemas.response import RawResponse
from ..utils.hashing import sha256_obj
from ..utils.ids import response_id, run_id
from ..utils.io import append_jsonl, completed_keys
from ..utils.logging import get_logger
from .backend import Backend, Generation
from .chat_template import render
from .provenance import build_provenance, software_matrix, tokenizer_hash

log = get_logger(__name__)

#: Dotted paths, because model identity lives inside the provenance block.
RESUME_KEY_FIELDS = [
    "experiment_id",
    "provenance.model_id",
    "probe_id",
    "provenance.sample_index",
]


@dataclass(slots=True)
class RunStats:
    requested: int = 0
    skipped_existing: int = 0
    generated: int = 0
    retried: int = 0
    timed_out: int = 0
    elapsed_s: float = 0.0

    def summary(self) -> str:
        return (
            f"{self.generated} generated, {self.skipped_existing} already present, "
            f"{self.retried} retried, {self.timed_out} timed out, "
            f"{self.elapsed_s:.1f}s"
        )


@dataclass(slots=True)
class InferenceRunner:
    """Runs one experiment for one model, resumably."""

    backend: Backend
    experiment_id: str
    tier: Tier
    track: Track
    semantic_instruction: str
    semantic_instruction_id: str
    generation: dict[str, Any]
    dtype: str = "bfloat16"
    quantisation: str = "none"
    supports_system_role: bool = True
    system_merge_strategy: str = "none"
    batch_size: int = 16
    timeout_s: float | None = None
    config_snapshot_sha256: str = "0" * 64
    _software: dict[str, str] = field(default_factory=software_matrix)

    def run(
        self,
        probes: Sequence[Probe],
        out_path: str | Path,
        *,
        sample_index: int = 0,
        seed: int | None = None,
        resume: bool = True,
    ) -> RunStats:
        """Generate for every probe, appending to ``out_path``."""
        out = Path(out_path)
        stats = RunStats(requested=len(probes))
        started = time.monotonic()

        done: set[tuple] = (
            completed_keys(out, RESUME_KEY_FIELDS) if resume and out.is_file() else set()
        )
        pending = [
            p for p in probes
            if (self.experiment_id, self.backend.model_id, p.probe_id, sample_index) not in done
        ]
        stats.skipped_existing = len(probes) - len(pending)
        if stats.skipped_existing:
            log.info(
                "resuming run",
                extra={"extra_fields": {"skipped": stats.skipped_existing, "pending": len(pending)}},
            )
        if not pending:
            stats.elapsed_s = time.monotonic() - started
            return stats

        rid = run_id(self.experiment_id, self.config_snapshot_sha256)
        tok_hash = tokenizer_hash(self.backend.tokenizer)

        for start in range(0, len(pending), self.batch_size):
            batch = pending[start : start + self.batch_size]
            rendered = [
                render(
                    self.backend.tokenizer,
                    self.semantic_instruction,
                    p.probe_text,
                    supports_system_role=self.supports_system_role,
                    system_merge_strategy=self.system_merge_strategy,
                    semantic_instruction_id=self.semantic_instruction_id,
                )
                for p in batch
            ]
            generations, retried, timed_out = self._generate_with_retry([r.text for r in rendered])
            stats.retried += retried
            stats.timed_out += timed_out

            records = []
            for probe, prompt, gen in zip(batch, rendered, generations, strict=True):
                records.append(
                    self._record(
                        rid, probe, prompt, gen, tok_hash, sample_index, seed, len(batch)
                    ).model_dump(mode="json")
                )
            stats.generated += append_jsonl(out, records)
            log.info(
                "batch written",
                extra={"extra_fields": {"done": stats.generated, "of": len(pending)}},
            )

        stats.elapsed_s = time.monotonic() - started
        return stats

    # ------------------------------------------------------------------
    def _generate_with_retry(self, prompts: list[str]) -> tuple[list[Generation], int, int]:
        """§4.7: one retry under an identical configuration, then FAILED."""
        try:
            return self.backend.generate(prompts, **self.generation), 0, 0
        except Exception as exc:
            log.warning(
                "generation failed; retrying once under an identical configuration",
                extra={"extra_fields": {"error": f"{type(exc).__name__}: {exc}"}},
            )
        try:
            return self.backend.generate(prompts, **self.generation), 1, 0
        except Exception as exc:
            log.error(
                "generation failed after one retry; recording as timed out",
                extra={"extra_fields": {"error": f"{type(exc).__name__}: {exc}"}},
            )
            failed = [Generation(text="", finish_reason="error", timed_out=True) for _ in prompts]
            return failed, 1, len(prompts)

    def _record(
        self, rid, probe, prompt, gen, tok_hash, sample_index, seed, batch_size
    ) -> RawResponse:
        return RawResponse(
            response_id=response_id(rid, self.backend.model_id, probe.probe_id, sample_index),
            run_id=rid,
            experiment_id=self.experiment_id,
            config_snapshot_sha256=self.config_snapshot_sha256,
            constraint_id=probe.constraint_id,
            probe_id=probe.probe_id,
            tier=self.tier,
            track=self.track,
            semantic_instruction_id=self.semantic_instruction_id,
            raw_text=gen.text,
            finish_reason=gen.finish_reason,
            n_generated_tokens=gen.n_generated_tokens,
            latency_ms=gen.latency_ms,
            timed_out=gen.timed_out,
            retry_index=1 if gen.timed_out else 0,
            provenance=build_provenance(
                model_id=self.backend.model_id,
                hf_revision_hash=self.backend.revision,
                tokenizer_hash_value=tok_hash,
                chat_template_hash_value=prompt.chat_template_hash,
                dtype=self.dtype,
                quantisation=self.quantisation,
                generation=self.generation,
                rendered_prompt=prompt.text,
                batch_size=batch_size,
                sample_index=sample_index,
                seed=seed,
                software=self._software,
                timestamp=dt.datetime.now(dt.timezone.utc),
            ),
        )


def config_hash(cfg: dict[str, Any]) -> str:
    return sha256_obj(cfg)
