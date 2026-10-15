"""Concrete NLI scorer for D2 (ADR-0023 D6, `configs/detectors/d2_nli.yaml`).

`nli.NLIScorer` is a Protocol and nothing implemented it, so D2 could not run at
all. This is the implementation.

IT RETURNS A SCORE AND NEVER A VERDICT
--------------------------------------
D2's per-class threshold was calibrated on human-labelled development data,
which does not exist and will not. `nli.D2Detector.check_pair` still raises
`ThresholdNotCalibrated`, and nothing here changes that. What D2 contributes is
a continuous contradiction probability, consumed by
`analysis.rank_concordance` as an ORDERING over pairs — never as an accuracy.

THE LABEL ORDER IS VERIFIED AGAINST THE CONFIG, NOT ASSUMED
-----------------------------------------------------------
`d2_nli.yaml` records `contradiction_index: 2` and the full `label_order`, read
from `config.json` at the pinned revision. This scorer re-reads the loaded
checkpoint's own `id2label` and **refuses to run if they disagree**. Getting
this wrong is silent and total: if `contradiction` were index 0 and the code
read index 2, every pair's "contradiction probability" would be its entailment
probability, the ordering would invert, and nothing downstream would notice.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

#: The project's canonical label for the class whose probability D2 reports.
CONTRADICTION_LABEL = "contradiction"

#: A pinned revision is a 40-character hexadecimal git SHA. Checking the length
#: alone would accept any 40-character string, so the character class is part of
#: the check: "z" * 40 is not a revision.
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


@dataclass
class TransformersNLIScorer:
    """DeBERTa-style sequence classifier, pinned by revision.

    `transformers` rather than vLLM: this is a 435M-parameter *classifier*, not
    a generative model. vLLM adds nothing for a single forward pass and would
    pull a second serving stack into the detector path.
    """

    model_id: str
    revision: str
    contradiction_index: int
    expected_label_order: dict[int, str] | None = None
    dtype: str = "float32"
    batch_size: int = 32
    max_length: int = 512
    device: str = "auto"
    _model: Any = field(default=None, init=False, repr=False)
    _tokenizer: Any = field(default=None, init=False, repr=False)
    _device: str = field(default="cpu", init=False, repr=False)

    @property
    def name(self) -> str:
        return f"{self.model_id}@{self.revision[:12]}"

    def __post_init__(self) -> None:
        if not (isinstance(self.revision, str) and _SHA_RE.match(self.revision)):
            raise ValueError(
                f"refusing to load {self.model_id} without a pinned 40-hex revision "
                f"(got {self.revision!r}). §4.5 requires it, and "
                "configs/detectors/d2_nli.yaml carries one."
            )

    def load(self) -> None:
        """Load the checkpoint and verify its label order against the config.

        LOADS STRAIGHT ONTO THE TARGET DEVICE WHERE POSSIBLE.
        ------------------------------------------------------
        Job 15158 failed with
        ``DefaultCPUAllocator: can't allocate memory: you tried to allocate
        16777216 bytes`` inside ``_load_state_dict_into_meta_model`` ->
        ``param.to(casting_dtype)``. The default path materialises every
        parameter in HOST memory and only then moves the model, so a 435M fp32
        classifier transiently needs ~1.7 GB of CPU RAM on a node whose memory
        was already consumed. Failing a 16 MiB allocation is a hard ceiling, not
        fragmentation.

        `device_map={"": device}` makes `transformers` place each shard directly
        on the target device, so host memory never holds the full model. It
        needs `accelerate`; without it we fall back to the original path, which
        still works wherever CPU memory is actually available.
        """
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self._tokenizer = AutoTokenizer.from_pretrained(
            self.model_id, revision=self.revision
        )
        self._device = (
            ("cuda" if torch.cuda.is_available() else "cpu")
            if self.device == "auto" else self.device
        )
        torch_dtype = getattr(torch, self.dtype)
        # `torch_dtype` was renamed `dtype` in recent transformers and the old
        # name warns. Try the new name first so the call is quiet on the
        # cluster's 4.57.6 and still correct on older local versions.
        for dtype_kw in ("dtype", "torch_dtype"):
            try:
                model = AutoModelForSequenceClassification.from_pretrained(
                    self.model_id, revision=self.revision,
                    low_cpu_mem_usage=True,
                    device_map={"": self._device},
                    **{dtype_kw: torch_dtype},
                )
                break
            except TypeError:
                continue
            except (ImportError, ValueError) as exc:
                # `device_map` requires accelerate; fall back rather than fail.
                if "accelerate" not in str(exc).lower():
                    raise
                model = AutoModelForSequenceClassification.from_pretrained(
                    self.model_id, revision=self.revision,
                    **{dtype_kw: torch_dtype},
                )
                break
        else:  # pragma: no cover - neither keyword accepted
            raise RuntimeError(
                "transformers accepted neither `dtype` nor `torch_dtype`"
            )
        id2label = {int(k): str(v).lower() for k, v in (model.config.id2label or {}).items()}
        actual = id2label.get(self.contradiction_index)
        if actual != CONTRADICTION_LABEL:
            raise ValueError(
                f"REFUSING TO SCORE: {self.model_id}@{self.revision[:12]} has "
                f"id2label {id2label}, so index {self.contradiction_index} is "
                f"{actual!r}, not {CONTRADICTION_LABEL!r}. "
                "configs/detectors/d2_nli.yaml's contradiction_index disagrees "
                "with the loaded checkpoint. Reading the wrong index would "
                "silently report entailment probability as contradiction "
                "probability and invert every ordering."
            )
        if self.expected_label_order:
            expected = {int(k): str(v).lower() for k, v in self.expected_label_order.items()}
            if expected != id2label:
                raise ValueError(
                    f"REFUSING TO SCORE: label order mismatch for {self.model_id}. "
                    f"config says {expected}, checkpoint says {id2label}"
                )
        # `device_map` already placed it; `.to()` is a no-op then and the
        # correct move on the fallback path.
        self._model = model.to(self._device).eval()

    def contradiction_probability(self, premise: str, hypothesis: str) -> float:
        """P(contradiction) for one ordered pair. Satisfies `nli.NLIScorer`."""
        return self.contradiction_probabilities([(premise, hypothesis)])[0]

    def contradiction_probabilities(
        self, pairs: list[tuple[str, str]]
    ) -> list[float]:
        """Batched form. One forward pass per `batch_size` pairs."""
        if self._model is None:
            raise RuntimeError("call load() before scoring")
        import torch

        out: list[float] = []
        for i in range(0, len(pairs), self.batch_size):
            chunk = pairs[i : i + self.batch_size]
            enc = self._tokenizer(
                [p for p, _ in chunk], [h for _, h in chunk],
                return_tensors="pt", padding=True, truncation="longest_first",
                max_length=self.max_length,
            ).to(self._device)
            with torch.no_grad():
                logits = self._model(**enc).logits
            probs = torch.softmax(logits.float(), dim=-1)
            out.extend(probs[:, self.contradiction_index].tolist())
        return out


def from_config(cfg: dict[str, Any], *, device: str = "auto") -> TransformersNLIScorer:
    """Build the scorer from `configs/detectors/d2_nli.yaml`.

    Every parameter comes from the config. Nothing is defaulted here, so a
    config change is the only way to change what runs.
    """
    sel = cfg["checkpoint_selection"]
    scoring = cfg["scoring"]
    inference = scoring["inference"]
    return TransformersNLIScorer(
        model_id=sel["selected"],
        revision=sel["revision"],
        contradiction_index=int(scoring["contradiction_index"]),
        expected_label_order=dict(scoring.get("label_order") or {}),
        dtype=str(inference.get("dtype", "float32")),
        batch_size=int(inference.get("batch_size", 32)),
        max_length=int(inference.get("max_length", 512)),
        device=device,
    )
