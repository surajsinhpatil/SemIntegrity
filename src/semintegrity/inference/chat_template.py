"""Chat-template rendering (proposal §4.6).

    "An identical system prompt does not produce an identical model input. Each
    model uses its own official chat template while the semantic instruction is
    held constant, and the fully rendered prompt string is logged for every
    response."

Two things follow, and both are handled here rather than in the runner:

* **Not every model accepts a system role.** Gemma-2's official template has no
  system turn, and Mistral-v0.3's raises on one. Dropping the instruction for
  those models would silently change the experiment for two of four families, so
  it is merged into the first user turn instead, and *which* strategy was used is
  recorded.
* **The template is part of the experiment.** Its hash is logged with every
  response, so a template change between runs is detectable rather than
  invisible.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from ..utils.hashing import sha256_text
from ..utils.logging import get_logger

log = get_logger(__name__)


class SystemMergeStrategy:
    """How a semantic instruction reaches a model with no system role."""

    NONE = "none"
    PREPEND_TO_FIRST_USER = "prepend_to_first_user"


class TokenizerLike(Protocol):
    """The slice of a HF tokenizer this module needs."""

    chat_template: str | None

    def apply_chat_template(
        self, conversation: list[dict[str, str]], *, tokenize: bool, add_generation_prompt: bool
    ) -> str: ...


@dataclass(frozen=True, slots=True)
class RenderedPrompt:
    """A prompt as the model will actually see it, plus how it got that way."""

    text: str
    chat_template_hash: str
    system_merge_strategy: str
    semantic_instruction_id: str
    used_system_role: bool

    def __len__(self) -> int:  # pragma: no cover - convenience
        return len(self.text)


def chat_template_hash(tokenizer: TokenizerLike) -> str:
    """Hash of the model's official chat template.

    A model with no template is an error, not a fallback: silently substituting a
    generic template would make the rendered prompt incomparable with every other
    model in the study.
    """
    template = getattr(tokenizer, "chat_template", None)
    if not template:
        raise ValueError(
            "tokenizer has no chat_template; SemIntegrity requires each model's "
            "own official template (§4.6) and will not substitute a generic one"
        )
    return sha256_text(template)


def build_conversation(
    instruction: str,
    user_text: str,
    *,
    supports_system_role: bool,
    system_merge_strategy: str,
) -> tuple[list[dict[str, str]], bool]:
    """Build the message list, merging the instruction where necessary."""
    instruction = instruction.strip()
    user_text = user_text.strip()

    if supports_system_role:
        return ([{"role": "system", "content": instruction},
                 {"role": "user", "content": user_text}], True)

    if system_merge_strategy == SystemMergeStrategy.PREPEND_TO_FIRST_USER:
        return ([{"role": "user", "content": f"{instruction}\n\n{user_text}"}], False)

    raise ValueError(
        f"model does not support a system role and system_merge_strategy is "
        f"{system_merge_strategy!r}; the semantic instruction would be dropped, "
        "which would silently change the experiment for this model"
    )


def render(
    tokenizer: TokenizerLike,
    instruction: str,
    user_text: str,
    *,
    supports_system_role: bool,
    system_merge_strategy: str,
    semantic_instruction_id: str,
) -> RenderedPrompt:
    """Render one probe into the exact string the model receives."""
    conversation, used_system = build_conversation(
        instruction,
        user_text,
        supports_system_role=supports_system_role,
        system_merge_strategy=system_merge_strategy,
    )
    text = tokenizer.apply_chat_template(
        conversation, tokenize=False, add_generation_prompt=True
    )
    return RenderedPrompt(
        text=text,
        chat_template_hash=chat_template_hash(tokenizer),
        system_merge_strategy=(
            SystemMergeStrategy.NONE if used_system else system_merge_strategy
        ),
        semantic_instruction_id=semantic_instruction_id,
        used_system_role=used_system,
    )


def audit_tokenizer(tokenizer: TokenizerLike, *, declared_supports_system: bool) -> dict[str, Any]:
    """Check a model's declared system-role support against reality.

    The per-model configs carry an *assumed* value taken from documentation.
    This probes the real template so the assumption is verified before the
    pilot rather than trusted.
    """
    probe = [{"role": "system", "content": "S"}, {"role": "user", "content": "U"}]
    try:
        rendered = tokenizer.apply_chat_template(
            probe, tokenize=False, add_generation_prompt=True
        )
        actual = "S" in rendered
        error = None
    except Exception as exc:
        actual, rendered, error = False, None, f"{type(exc).__name__}: {exc}"

    result = {
        "chat_template_hash": chat_template_hash(tokenizer),
        "declared_supports_system_role": declared_supports_system,
        "actual_supports_system_role": actual,
        "agrees": actual == declared_supports_system,
        "error_on_system_role": error,
        "rendered_sample": rendered,
    }
    if not result["agrees"]:
        log.warning(
            "declared system-role support disagrees with the real chat template",
            extra={"extra_fields": result},
        )
    return result
