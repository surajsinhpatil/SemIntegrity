"""Teacher-forced candidate scorer for D4 (ADR-0024, §4.8.6).

`distributional.CandidateScorer` is a Protocol and nothing implemented it, so
D4 could not run. This is the implementation.

WHAT "TEACHER-FORCED, LENGTH-NORMALISED" MEANS HERE
---------------------------------------------------
For a prompt and a closed candidate set, each candidate is scored as the **mean
per-token log-probability of that candidate's tokens, conditioned on the
prompt** — not sampled, not generated. One forward pass over
``prompt + candidate`` gives logits at every position; the log-probability of
candidate token *t* is read at the position **before** it, and the mean is taken
over the candidate's tokens only, never the prompt's.

§4.8.6 requires the length normalisation because raw sequence probability is
length-biased: a one-token candidate would beat a four-token synonym on length
alone. Dividing by token count removes that, which is also why the result is
**not** a probability distribution and needs ADR-0024's softmax mapping.

PROMPTS ARE REUSED, NOT REBUILT
-------------------------------
Every primary response carries its fully rendered prompt in
``provenance.rendered_prompt`` (§4.6 logs it for exactly this kind of reuse).
D4 scores against those stored strings rather than re-rendering, so the
distribution is conditioned on the identical input the model actually saw.
Re-rendering would risk a template or tokenizer drift that silently changes the
conditioning.

WHAT THIS IS NOT
----------------
D4 is **exploratory** and is not a contradiction detector. This module returns
log-probabilities; it exposes no verdict, no threshold and no contradiction
count, and `D4Distributional` has no verdict interface to give it one.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

#: A pinned revision is a 40-character hexadecimal git SHA. Checking the length
#: alone would accept any 40-character string, so the character class is part of
#: the check: "z" * 40 is not a revision.
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


@dataclass
class TeacherForcedScorer:
    """Mean per-token log-probability of each candidate, given a prompt.

    `transformers` rather than vLLM: this needs per-position log-probabilities
    over a *forced* continuation, which is a plain forward pass. vLLM is built
    for generation and its prompt-logprob path would add a second serving stack
    to get the same numbers.
    """

    model_id: str
    revision: str
    dtype: str = "bfloat16"
    device: str = "auto"
    max_length: int = 2048
    _model: Any = field(default=None, init=False, repr=False)
    _tokenizer: Any = field(default=None, init=False, repr=False)
    _device: str = field(default="cpu", init=False, repr=False)

    @property
    def name(self) -> str:
        return f"teacher_forced({self.model_id}@{self.revision[:12]})"

    def __post_init__(self) -> None:
        if not (isinstance(self.revision, str) and _SHA_RE.match(self.revision)):
            raise ValueError(
                f"refusing to load {self.model_id} without a pinned 40-hex "
                f"revision (got {self.revision!r}); §4.5 requires it"
            )

    def load(self) -> None:
        """Load the evaluated model, placing shards directly on the device.

        The default path materialises every parameter in HOST memory before the
        model is moved, which killed D2's job 15158 with
        ``DefaultCPUAllocator: can't allocate memory`` on a node whose RAM was
        already consumed. D4 loads a full evaluated model — 3B to 14B, i.e. 6 to
        28 GB in bf16, 7 to 32 times D2's classifier — so the same path would
        fail far harder here. `device_map={"": device}` keeps host memory out of
        it. It needs `accelerate`; without it we fall back.
        """
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self._tokenizer = AutoTokenizer.from_pretrained(
            self.model_id, revision=self.revision
        )
        self._device = (
            ("cuda" if torch.cuda.is_available() else "cpu")
            if self.device == "auto" else self.device
        )
        torch_dtype = getattr(torch, self.dtype)
        model = None
        for dtype_kw in ("dtype", "torch_dtype"):
            try:
                model = AutoModelForCausalLM.from_pretrained(
                    self.model_id, revision=self.revision,
                    low_cpu_mem_usage=True,
                    device_map={"": self._device},
                    **{dtype_kw: torch_dtype},
                )
                break
            except TypeError:
                continue
            except (ImportError, ValueError) as exc:
                if "accelerate" not in str(exc).lower():
                    raise
                model = AutoModelForCausalLM.from_pretrained(
                    self.model_id, revision=self.revision,
                    **{dtype_kw: torch_dtype},
                )
                break
        if model is None:  # pragma: no cover - neither keyword accepted
            raise RuntimeError(
                "transformers accepted neither `dtype` nor `torch_dtype`"
            )
        # mypy reads from_pretrained as returning a str-accepting wrapper;
        # `.to(device)` on the concrete model is correct at runtime, and is a
        # no-op when device_map already placed the shards.
        self._model = model.to(self._device).eval()  # type: ignore[arg-type]

    def mean_token_logprobs(
        self, prompt: str, candidates: Sequence[str]
    ) -> list[float]:
        """One value per candidate. Satisfies `CandidateScorer`.

        Each candidate gets its own forward pass over ``prompt + candidate``.
        Batching across candidates would need padding, and a padded position's
        logits are not the unpadded ones for every architecture, so the loop is
        deliberate: D4 is exploratory and correctness costs more than speed here.
        """
        if self._model is None:
            raise RuntimeError("call load() before scoring")
        if not candidates:
            raise ValueError("cannot score an empty candidate set")
        import torch

        prompt_ids = self._tokenizer(prompt, return_tensors="pt").input_ids[0]
        out: list[float] = []
        for candidate in candidates:
            # add_special_tokens=False: the candidate continues the prompt and
            # must not acquire a BOS of its own, which would be scored as a
            # candidate token and corrupt the mean.
            cand_ids = self._tokenizer(
                candidate, return_tensors="pt", add_special_tokens=False
            ).input_ids[0]
            if len(cand_ids) == 0:
                raise ValueError(f"candidate {candidate!r} tokenises to nothing")
            ids = torch.cat([prompt_ids, cand_ids]).unsqueeze(0)
            if ids.shape[1] > self.max_length:
                raise ValueError(
                    f"prompt + candidate is {ids.shape[1]} tokens, over "
                    f"max_length {self.max_length}; truncating would change "
                    "what the distribution is conditioned on"
                )
            ids = ids.to(self._device)
            with torch.no_grad():
                logits = self._model(input_ids=ids).logits.float()
            # logits[0, i] predicts token i+1, so the log-probability of
            # candidate token j (at absolute position len(prompt_ids)+j) is read
            # at position len(prompt_ids)+j-1.
            logprobs = torch.log_softmax(logits[0], dim=-1)
            start = len(prompt_ids)
            total = 0.0
            for j, token_id in enumerate(cand_ids.tolist()):
                total += logprobs[start + j - 1, token_id].item()
            out.append(total / len(cand_ids))
        return out
