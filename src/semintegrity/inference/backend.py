"""Generation backends.

``VLLMBackend`` is the real one: a single inference stack for every model, since
§4.13 forbids mixing frameworks across models.

``StubBackend`` produces deterministic fake text so the whole pipeline —
rendering, provenance, resume, canonicalisation, detection — can be exercised
end to end without a GPU. It exists to test *plumbing*, never to stand in for a
model.

**The stub can never be mistaken for a model.** Its ``model_id`` is forced to a
``stub://`` prefix, and :func:`assert_no_stub_responses` rejects any result file
containing one. Analysis paths call that check before reporting anything.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from ..utils.logging import get_logger

log = get_logger(__name__)

STUB_PREFIX = "stub://"


class StubOutputError(RuntimeError):
    """Raised when stub output reaches a path that requires real model output."""


@dataclass(frozen=True, slots=True)
class Generation:
    """One raw generation, before any canonicalisation."""

    text: str
    finish_reason: str = "stop"
    n_generated_tokens: int | None = None
    latency_ms: float | None = None
    timed_out: bool = False


class Backend(Protocol):
    """What the runner needs from a generation backend."""

    model_id: str
    revision: str
    tokenizer: Any

    def generate(self, prompts: Sequence[str], **kwargs: Any) -> list[Generation]: ...


class StubBackend:
    """Deterministic fake generations for pipeline testing. NOT a model.

    Given a mapping from probe text to a canned answer it returns that answer;
    otherwise it returns a stable hash-derived token. Either way the output is a
    pure function of the prompt, so resume and determinism logic can be tested
    exactly.
    """

    def __init__(
        self,
        *,
        answers: dict[str, str] | None = None,
        default: str = "UNKNOWN",
        model_id: str = "stub-deterministic",
    ) -> None:
        self.model_id = model_id if model_id.startswith(STUB_PREFIX) else STUB_PREFIX + model_id
        self.revision = STUB_PREFIX + "no-revision"
        self.tokenizer = _StubTokenizer()
        self._answers = answers or {}
        self._default = default

    def generate(self, prompts: Sequence[str], **kwargs: Any) -> list[Generation]:
        out: list[Generation] = []
        for prompt in prompts:
            answer = next(
                (v for k, v in self._answers.items() if k in prompt),
                None,
            )
            if answer is None:
                digest = hashlib.sha256(prompt.encode()).hexdigest()[:6]
                answer = self._default if self._default else f"STUB-{digest}"
            out.append(Generation(text=answer, n_generated_tokens=len(answer.split())))
        return out


class _StubTokenizer:
    """Minimal tokenizer stand-in with a real, hashable chat template."""

    chat_template = (
        "{% for m in messages %}<|{{ m['role'] }}|>\n{{ m['content'] }}\n{% endfor %}"
        "{% if add_generation_prompt %}<|assistant|>\n{% endif %}"
    )
    name_or_path = STUB_PREFIX + "tokenizer"
    vocab_size = 0
    model_max_length = 2048

    def get_vocab(self) -> dict[str, int]:
        return {}

    def apply_chat_template(
        self,
        conversation: list[dict[str, str]],
        *,
        tokenize: bool = False,
        add_generation_prompt: bool = True,
    ) -> str:
        parts = [f"<|{m['role']}|>\n{m['content']}\n" for m in conversation]
        if add_generation_prompt:
            parts.append("<|assistant|>\n")
        return "".join(parts)


class VLLMBackend:
    """vLLM-backed generation. Constructed only inside a Slurm allocation."""

    def __init__(
        self,
        model_id: str,
        *,
        revision: str,
        dtype: str = "bfloat16",
        tensor_parallel_size: int = 1,
        gpu_memory_utilization: float = 0.90,
        max_model_len: int = 2048,
        seed: int = 0,
    ) -> None:
        if not revision or revision.startswith(STUB_PREFIX):
            raise ValueError(
                f"refusing to load {model_id} without a real pinned revision "
                "(§4.5 requires pinned open-weight revisions); run "
                "scripts/models/pin_revisions.py first"
            )
        try:
            from transformers import AutoTokenizer
            from vllm import LLM
        except ImportError as exc:  # pragma: no cover - GPU nodes only
            raise RuntimeError(
                "vllm and transformers are required for real inference; this "
                "backend must only be constructed inside a Slurm GPU allocation"
            ) from exc

        self.model_id = model_id
        self.revision = revision
        self.tokenizer = AutoTokenizer.from_pretrained(model_id, revision=revision)
        self._llm = LLM(
            model=model_id,
            revision=revision,
            dtype=dtype,
            tensor_parallel_size=tensor_parallel_size,
            gpu_memory_utilization=gpu_memory_utilization,
            max_model_len=max_model_len,
            seed=seed,
        )
        log.info(
            "vLLM backend ready",
            extra={"extra_fields": {"model_id": model_id, "revision": revision, "dtype": dtype}},
        )

    def generate(self, prompts: Sequence[str], **kwargs: Any) -> list[Generation]:  # pragma: no cover
        from vllm import SamplingParams

        params = SamplingParams(
            temperature=kwargs.get("temperature", 0.0),
            top_p=kwargs.get("top_p", 1.0),
            top_k=kwargs.get("top_k", -1),
            repetition_penalty=kwargs.get("repetition_penalty", 1.0),
            max_tokens=kwargs.get("max_new_tokens", 24),
            stop=list(kwargs.get("stop_sequences", [])),
            seed=kwargs.get("seed"),
        )
        outputs = self._llm.generate(list(prompts), params)
        results: list[Generation] = []
        for o in outputs:
            completion = o.outputs[0]
            results.append(
                Generation(
                    text=completion.text,
                    finish_reason=str(completion.finish_reason or "stop"),
                    n_generated_tokens=len(completion.token_ids),
                )
            )
        return results


# --- stub containment -------------------------------------------------------
def is_stub(model_id: str) -> bool:
    return model_id.startswith(STUB_PREFIX)


def assert_no_stub_responses(path: str, *, context: str = "analysis") -> int:
    """Raise if any response in a result file came from the stub backend.

    Called before anything is reported. Stub output is deterministic and
    plausible-looking, so the only safe posture is to refuse it explicitly.
    """
    from ..utils.io import read_jsonl

    offenders = 0
    for rec in read_jsonl(path):
        model_id = rec.get("provenance", {}).get("model_id", "")
        if is_stub(model_id):
            offenders += 1
    if offenders:
        raise StubOutputError(
            f"{path} contains {offenders} response(s) generated by the stub backend. "
            f"Stub output is fake and must never reach {context}. "
            "Re-run against a real model inside a Slurm allocation."
        )
    return offenders
