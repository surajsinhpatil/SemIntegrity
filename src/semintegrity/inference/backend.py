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


def detect_device(preference: str = "auto") -> str:
    """Pick the compute device.

    ``auto`` prefers CUDA inside a Slurm allocation, then Apple MPS, then CPU.
    CUDA is only *probed* inside an allocation — on this cluster's login node the
    call blocks (see :mod:`semintegrity.inference.provenance`).
    """
    if preference != "auto":
        return preference
    try:
        import torch
    except ImportError:  # pragma: no cover
        return "cpu"

    from .provenance import cuda_probe_allowed

    if cuda_probe_allowed() and torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def assert_bf16_supported(device: str) -> None:
    """§4.6 requires bf16 for every evaluated model. Verify, do not assume.

    Checked by running a real bf16 matmul rather than trusting a capability
    flag, because a dtype that silently degrades to fp32 would make results
    incomparable across devices without anything appearing wrong.
    """
    import torch

    if device == "cpu":
        raise RuntimeError(
            "refusing to run on CPU: generation would be impractically slow and "
            "bf16 behaviour differs from both CUDA and MPS"
        )
    try:
        x = torch.randn(64, 64, dtype=torch.bfloat16, device=device)
        out = (x @ x).float().sum().item()
    except Exception as exc:
        raise RuntimeError(f"bf16 is not usable on {device}: {exc}") from exc
    if out != out:  # NaN
        raise RuntimeError(f"bf16 matmul on {device} produced NaN")


class TransformersBackend:
    """HuggingFace `transformers` generation. The default stack on this cluster.

    §4.13 requires "a single inference stack, since mixing frameworks across
    models would introduce an uncontrolled variable". It does not require vLLM,
    and on the BITS CSIS cluster vLLM is unusable: every published wheel from
    0.22 onward links CUDA 13 (`libcudart.so.13`), while the driver is 570.158.01
    = CUDA 12.8. Transformers runs on the cu128 torch build that does work.

    The workload suits it. Track A generations are capped at 24 new tokens
    (§4.4.3), every model up to 14B fits on one A100 80GB in bf16, and vLLM's
    advantage — continuous batching over long sequences — is not what this study
    stresses. D4's teacher-forced candidate scoring (§4.8.6) is also more direct
    here than through a serving engine.

    See docs/decisions/ADR-0012-inference-stack.md. Switching stacks is a
    decision with methodological surface, so it is recorded and awaits approval.
    """

    def __init__(
        self,
        model_id: str,
        *,
        revision: str,
        dtype: str = "bfloat16",
        device: str = "auto",
        device_map: str | None = None,
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
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:  # pragma: no cover - GPU nodes only
            raise RuntimeError("torch and transformers are required") from exc

        if dtype != "bfloat16":
            raise ValueError(f"§4.6 requires bf16 for every evaluated model, got {dtype!r}")

        self.model_id = model_id
        self.revision = revision
        self.max_model_len = max_model_len
        self.device = detect_device(device)
        assert_bf16_supported(self.device)
        torch.manual_seed(seed)
        log.info(
            "device selected", extra={"extra_fields": {"device": self.device, "dtype": dtype}}
        )

        self.tokenizer = AutoTokenizer.from_pretrained(model_id, revision=revision)
        # Decoder-only batch generation needs LEFT padding: with right padding the
        # pad tokens sit between the prompt and the continuation, so shorter
        # prompts in a batch generate from padding rather than from their text.
        self.tokenizer.padding_side = "left"
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        self._torch = torch
        # device_map="auto" shards across multiple CUDA devices. On MPS there is
        # exactly one device and the accelerate path is unnecessary, so the model
        # is moved explicitly instead.
        if self.device == "cuda":
            self.model = AutoModelForCausalLM.from_pretrained(
                model_id, revision=revision, dtype=torch.bfloat16,
                device_map=device_map or "auto",
            )
        else:
            self.model = AutoModelForCausalLM.from_pretrained(
                model_id, revision=revision, dtype=torch.bfloat16
            ).to(self.device)
        self.model.eval()
        log.info(
            "transformers backend ready",
            extra={"extra_fields": {"model_id": model_id, "revision": revision, "dtype": dtype}},
        )

    def generate(self, prompts: Sequence[str], **kwargs: Any) -> list[Generation]:  # pragma: no cover
        import time

        torch = self._torch
        temperature = float(kwargs.get("temperature", 0.0))
        max_new_tokens = int(kwargs.get("max_new_tokens", 24))
        stops = list(kwargs.get("stop_sequences", []))
        if (seed := kwargs.get("seed")) is not None:
            torch.manual_seed(int(seed))

        enc = self.tokenizer(
            list(prompts), return_tensors="pt", padding=True, truncation=True,
            max_length=self.max_model_len, add_special_tokens=False,
        ).to(self.model.device)  # follows device_map when CUDA shards the model

        gen_kwargs: dict[str, Any] = {
            "max_new_tokens": max_new_tokens,
            "pad_token_id": self.tokenizer.pad_token_id,
        }
        if temperature == 0.0:
            gen_kwargs["do_sample"] = False
        else:
            gen_kwargs.update(
                do_sample=True,
                temperature=temperature,
                top_p=float(kwargs.get("top_p", 1.0)),
            )
            if (top_k := int(kwargs.get("top_k", -1))) > 0:
                gen_kwargs["top_k"] = top_k
        if (rp := float(kwargs.get("repetition_penalty", 1.0))) != 1.0:
            gen_kwargs["repetition_penalty"] = rp

        started = time.monotonic()
        with torch.inference_mode():
            out = self.model.generate(**enc, **gen_kwargs)
        if self.device == "mps":
            # MPS queues work asynchronously; without this the timing would
            # measure submission rather than execution.
            torch.mps.synchronize()
        elapsed_ms = (time.monotonic() - started) * 1000 / max(len(prompts), 1)

        prompt_len = enc["input_ids"].shape[1]
        results: list[Generation] = []
        for row in out:
            new_ids = row[prompt_len:]
            text = self.tokenizer.decode(new_ids, skip_special_tokens=True)
            truncated = _apply_stops(text, stops)
            results.append(
                Generation(
                    text=truncated,
                    finish_reason="stop" if truncated != text else "length",
                    n_generated_tokens=int(new_ids.shape[0]),
                    latency_ms=elapsed_ms,
                )
            )
        return results


def _apply_stops(text: str, stops: Sequence[str]) -> str:
    """Truncate at the earliest stop sequence, as a serving engine would."""
    cut = len(text)
    for stop in stops:
        if stop and (idx := text.find(stop)) != -1:
            cut = min(cut, idx)
    return text[:cut]


def serving_kwargs(cfg_data: dict[str, Any], backend_name: str, device: str | None = None
                   ) -> dict[str, Any]:
    """Backend arguments from a resolved model config.

    Exists because the config and the code had silently disagreed: every model
    file carries `serving.tensor_parallel_size` and
    `serving.gpu_memory_utilization`, and neither entry point passed them, so
    VLLMBackend used its own defaults (tp=1, util=0.90). Harmless for the small
    models, fatal for llama33-70b -- ~141 GB declared tp=2 in config, would have
    run at tp=1 on one 80 GB A100 and OOM'd after queueing for two GPUs.

    Building the arguments in ONE place also stops smoke.py and run_pilot.py
    from drifting apart, which is how a smoke test can pass while the pilot it
    is meant to de-risk fails.
    """
    serving = cfg_data["serving"]
    kwargs: dict[str, Any] = {
        "model_id": cfg_data["model_id"],
        "revision": cfg_data["revision"],
        "dtype": cfg_data["dtype"],
        "max_model_len": serving["max_model_len"],
        "seed": cfg_data["generation"]["seed"],
    }
    if backend_name == "vllm":
        kwargs["tensor_parallel_size"] = serving["tensor_parallel_size"]
        kwargs["gpu_memory_utilization"] = serving["gpu_memory_utilization"]
    elif backend_name == "transformers" and device is not None:
        kwargs["device"] = device
    return kwargs


def make_backend(name: str, **kwargs: Any) -> Backend:
    """Construct the configured backend. One stack for every model (§4.13)."""
    backends = {"transformers": TransformersBackend, "vllm": VLLMBackend, "stub": StubBackend}
    if name not in backends:
        raise ValueError(f"unknown backend {name!r}; known: {sorted(backends)}")
    return backends[name](**kwargs)  # type: ignore[abstract]


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
