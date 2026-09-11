"""Collect the 22 provenance fields §4.6 requires on every response.

Nothing here guesses. A version that cannot be determined is reported as
``"unavailable"`` **explicitly** rather than omitted or invented, so a gap in the
record is visible in the data instead of being discovered during analysis.
"""

from __future__ import annotations

import datetime as dt
import importlib
from typing import Any

from ..schemas.response import Provenance
from ..utils.hashing import sha256_text

UNAVAILABLE = "unavailable"


def _version(module_name: str) -> str:
    try:
        mod = importlib.import_module(module_name)
    except Exception:
        return UNAVAILABLE
    return str(getattr(mod, "__version__", UNAVAILABLE))


def cuda_version() -> str:
    try:
        import torch

        return str(torch.version.cuda or UNAVAILABLE)
    except Exception:
        return UNAVAILABLE


def gpu_model() -> str:
    try:
        import torch

        if not torch.cuda.is_available():
            return "cpu"
        names = {torch.cuda.get_device_properties(i).name for i in range(torch.cuda.device_count())}
        return ",".join(sorted(names))
    except Exception:
        return UNAVAILABLE


def software_matrix() -> dict[str, str]:
    """The version matrix logged with every response."""
    return {
        "transformers_version": _version("transformers"),
        "vllm_version": _version("vllm"),
        "torch_version": _version("torch"),
        "cuda_version": cuda_version(),
        "gpu_model": gpu_model(),
    }


def tokenizer_hash(tokenizer: Any) -> str:
    """Stable hash over a tokenizer's identity and vocabulary size.

    Full-vocabulary hashing would be exact but slow on every call; identity plus
    size catches the realistic failure — a different tokenizer revision silently
    substituted — and the model revision hash covers the rest.
    """
    parts = [
        type(tokenizer).__name__,
        str(getattr(tokenizer, "name_or_path", "")),
        str(getattr(tokenizer, "vocab_size", "")),
        str(len(getattr(tokenizer, "get_vocab", dict)() or {})),
        str(getattr(tokenizer, "model_max_length", "")),
    ]
    return sha256_text("|".join(parts))


def build_provenance(
    *,
    model_id: str,
    hf_revision_hash: str,
    tokenizer_hash_value: str,
    chat_template_hash_value: str,
    dtype: str,
    quantisation: str,
    generation: dict[str, Any],
    rendered_prompt: str,
    batch_size: int,
    sample_index: int,
    seed: int | None = None,
    software: dict[str, str] | None = None,
    timestamp: dt.datetime | None = None,
) -> Provenance:
    """Assemble a complete, schema-validated provenance record."""
    sw = software or software_matrix()
    return Provenance(
        model_id=model_id,
        hf_revision_hash=hf_revision_hash,
        tokenizer_hash=tokenizer_hash_value,
        chat_template_hash=chat_template_hash_value,
        transformers_version=sw["transformers_version"],
        vllm_version=sw["vllm_version"],
        torch_version=sw["torch_version"],
        cuda_version=sw["cuda_version"],
        gpu_model=sw["gpu_model"],
        dtype=dtype,
        quantisation=quantisation,
        temperature=float(generation["temperature"]),
        top_p=float(generation["top_p"]),
        top_k=int(generation["top_k"]),
        repetition_penalty=float(generation["repetition_penalty"]),
        max_new_tokens=int(generation["max_new_tokens"]),
        stop_sequences=list(generation["stop_sequences"]),
        seed=int(seed if seed is not None else generation["seed"]),
        rendered_prompt=rendered_prompt,
        batch_size=batch_size,
        sample_index=sample_index,
        timestamp=timestamp or dt.datetime.now(dt.timezone.utc),
    )
