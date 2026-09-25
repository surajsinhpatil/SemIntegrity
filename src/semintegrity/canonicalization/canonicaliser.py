"""Stage 0 — response canonicalisation (proposal §4.7).

    "Because constraints are hand-authored over a known knowledge base, the
    answer space for each constraint is closed and known in advance. Alias
    tables are therefore built at authoring time, making canonicalisation
    near-exact rather than a research problem in its own right."

Mapping, per §4.7's table:

===============================================  ==========================
Recognised canonical answer                      that answer (label ANSWER)
Polar answer asserting the complement            that answer (label NEGATED)
Refusal / "I don't know" / UNKNOWN               ABSTAIN
Malformed, unparseable or empty                  INVALID
Multiple mutually exclusive answers in one        AMBIGUOUS
Timeout (after one retry)                        FAILED
===============================================  ==========================

**Polarity mapping (Q21, adopted 2026-09-26).** §4.7 requires that "Is A the X
of B?" and "What is the X of B?" reach a common canonical space. A probe is
*polar* iff its ``expected_answer`` is YES/NO, and the model's YES/NO is a claim
about the proposition the probe asserts::

    affirms = (polarity == affirmative) == (response == YES)

For an entity/date constraint the asserted candidate is the constraint's gold
answer ``g``: ``affirms`` gives ANSWER(g), otherwise NEGATED(g). For a boolean
constraint it gives ANSWER("YES") or ANSWER("NO") according to whether the
proposition holds.

This is a **benchmark-validity correction, not a result**. Without it a
perfectly self-consistent model — one answering every probe with that probe's
own ``expected_answer`` — scored PSCR 0.643 rather than 0.000, because an
affirmative "YES" and a negated "NO" were recorded as different answers and
compared. ``tests/unit/test_perfect_model_invariant.py`` asserts that floor is
zero and will fail if it ever returns.

**The probe is a required argument.** Canonicalisation that cannot see what was
asked is exactly what produced the 0.643 artifact, so the signature makes it
impossible to omit rather than merely inadvisable.

Two rules are enforced structurally rather than by discipline:

* **Responses are never manually cleaned after results are inspected.** The
  canonicaliser's own source is hashed and the hash is written onto every
  canonical response, so a change after inspection is detectable.
* **Abstention is checked before answer matching.** "I don't know, but possibly
  Sydney" is an abstention that happens to contain an answer string; matching
  first would silently convert refusals into confident answers and deflate the
  abstention rate §4.7 calls a first-class outcome.
"""

from __future__ import annotations

import datetime as dt
import inspect
import re
import unicodedata
from dataclasses import dataclass

from ..schemas.constraint import Constraint
from ..schemas.enums import AnswerType, Polarity, ResponseLabel
from ..schemas.probe import Probe
from ..schemas.response import CanonicalResponse, RawResponse
from ..utils.hashing import sha256_text

CANONICALISER_VERSION = "1.1"  # 1.1 adds the Q21 polarity mapping

#: Leading tokens accepted as YES / NO on a polar probe. Deliberately short: a
#: hedged or discursive reply should fall through to answer-space matching or
#: INVALID rather than be forced into a boolean the model did not commit to.
_YES_TOKENS = frozenset({"yes", "y", "true", "correct", "right", "affirmative"})
_NO_TOKENS = frozenset({"no", "n", "false", "incorrect", "wrong", "negative"})

#: Phrases that mark a refusal. Tuned on the DEVELOPMENT split only, then frozen
#: before test evaluation (§5.6). Matched on a normalised, lower-cased string.
ABSTENTION_PATTERNS: tuple[str, ...] = (
    r"\bunknown\b",
    r"\bi (?:do not|don't) know\b",
    r"\bi'm not sure\b",
    r"\bi am not sure\b",
    r"\bnot sure\b",
    r"\bcannot determine\b",
    r"\bcan't determine\b",
    r"\bunable to (?:determine|answer|say)\b",
    r"\bno (?:information|answer)\b",
    r"\binsufficient information\b",
    r"\bas an ai\b",
    r"\bi cannot\b",
    r"\bunclear\b",
)

_ABSTAIN_RE = re.compile("|".join(ABSTENTION_PATTERNS), re.IGNORECASE)

_BOOLEAN_ALIASES: dict[str, tuple[str, ...]] = {
    "YES": ("yes", "true", "correct", "affirmative", "y", "indeed"),
    "NO": ("no", "false", "incorrect", "negative", "n"),
}

_DATE_RE = re.compile(r"\b(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?\b")


def normalise(text: str) -> str:
    """Casefold, strip accents and punctuation noise, collapse whitespace."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.replace("’", "'").replace("‘", "'")
    text = re.sub(r"[^\w\s'-]", " ", text)
    return re.sub(r"\s+", " ", text).strip().casefold()


def canonicaliser_hash() -> str:
    """Hash of this module's logic, written onto every canonical response."""
    return sha256_text(inspect.getsource(inspect.getmodule(normalise)))


@dataclass(frozen=True, slots=True)
class Stage0Result:
    label: ResponseLabel
    canonical_answer: str | None
    matched_alias: str | None
    candidates_found: tuple[str, ...]
    note: str = ""


def _alias_map(constraint: Constraint) -> dict[str, str]:
    """Normalised surface form -> canonical answer, from the closed answer space."""
    mapping: dict[str, str] = {}
    for answer in constraint.answer_space:
        mapping[normalise(answer)] = answer
        for alias in constraint.answer_aliases.get(answer, []):
            mapping[normalise(alias)] = answer
        if constraint.answer_type is AnswerType.BOOLEAN:
            for alias in _BOOLEAN_ALIASES.get(answer.upper(), ()):
                mapping[normalise(alias)] = answer
    return mapping


def _find_candidates(text: str, constraint: Constraint) -> list[tuple[str, str]]:
    """All answer-space members present, as (canonical, matched surface form)."""
    haystack = normalise(text)
    hits: list[tuple[str, str]] = []
    for surface, canonical in sorted(_alias_map(constraint).items(), key=lambda kv: -len(kv[0])):
        if not surface:
            continue
        matched = re.search(rf"(?<!\w){re.escape(surface)}(?!\w)", haystack)
        if matched and not any(canonical == c for c, _ in hits):
            hits.append((canonical, surface))
    return hits


def _canonicalise_date(text: str, constraint: Constraint) -> list[tuple[str, str]]:
    """Date answers match on year (and month/day when both carry them)."""
    hits: list[tuple[str, str]] = []
    found = _DATE_RE.findall(text)
    for answer in constraint.answer_space:
        a = _DATE_RE.search(answer)
        if not a:
            continue
        for f in found:
            if f[0] == a.group(1) and not any(answer == c for c, _ in hits):
                hits.append((answer, "-".join(x for x in f if x)))
    return hits


def canonicalise(raw: RawResponse, constraint: Constraint, probe: Probe) -> CanonicalResponse:
    """Map one raw response into the constraint's closed answer space."""
    result = classify(raw, constraint, probe)
    return CanonicalResponse(
        response_id=raw.response_id,
        constraint_id=raw.constraint_id,
        probe_id=raw.probe_id,
        label=result.label,
        canonical_answer=result.canonical_answer,
        matched_alias=result.matched_alias,
        candidates_found=list(result.candidates_found),
        canonicaliser_version=CANONICALISER_VERSION,
        canonicaliser_sha256=canonicaliser_hash(),
        canonicalised_at=dt.datetime.now(dt.timezone.utc),
        notes=result.note,
    )


def is_polar(probe: Probe) -> bool:
    """Whether the probe asks for YES/NO rather than a member of the answer space.

    Read off `expected_answer`, which the probe generator already records. On the
    pilot benchmark this is a clean partition and needs no text parsing.
    """
    return probe.expected_answer in ("YES", "NO")


def parse_yes_no(text: str) -> bool | None:
    """YES -> True, NO -> False, anything else -> None.

    Deliberately strict: only a LEADING yes/no token counts. "The answer is yes"
    returns None rather than True — inferring a polar answer from a word buried
    in a sentence would manufacture data that the model did not commit to.
    """
    tokens = normalise(text).split()
    if not tokens:
        return None
    if tokens[0] in _YES_TOKENS:
        return True
    if tokens[0] in _NO_TOKENS:
        return False
    return None


def classify(raw: RawResponse, constraint: Constraint, probe: Probe) -> Stage0Result:
    """The Stage 0 decision, separated from record construction for testing."""
    if raw.constraint_id != constraint.constraint_id:
        raise ValueError(
            f"response {raw.response_id} belongs to {raw.constraint_id}, "
            f"not {constraint.constraint_id}"
        )
    if probe.probe_id != raw.probe_id:
        raise ValueError(
            f"probe {probe.probe_id} does not match response probe {raw.probe_id}"
        )

    # 1. Timeout, after the one permitted retry (§4.7).
    if raw.timed_out:
        return Stage0Result(ResponseLabel.FAILED, None, None, (), "timed out after one retry")

    text = raw.raw_text.strip()

    # 2. Empty or unparseable.
    if not text:
        return Stage0Result(ResponseLabel.INVALID, None, None, (), "empty response")

    # 3. Abstention BEFORE answer matching — see the module docstring.
    if _ABSTAIN_RE.search(text):
        return Stage0Result(ResponseLabel.ABSTAIN, None, None, (), "refusal or UNKNOWN")

    # 4. Polarity mapping for polar probes (Q21, §4.7). BEFORE answer-space
    #    matching: on a polar probe the informative token is the yes/no, and the
    #    entity named in the probe text may also appear in the reply.
    if is_polar(probe):
        b = parse_yes_no(text)
        if b is None:
            # The probe asked a yes/no question and this is not a yes/no answer,
            # so it did not answer it. Falling through to answer-space matching
            # would be actively wrong on a boolean constraint, whose answer space
            # IS {YES, NO}: "The answer is yes" would match YES literally and
            # BYPASS the polarity inversion, reintroducing on negated probes the
            # exact artifact this mapping removes. Uniformly INVALID instead.
            return Stage0Result(
                ResponseLabel.INVALID, None, None, (),
                f"polar probe ({probe.polarity.value}) answered with no "
                "recognisable YES/NO",
            )
        else:
            affirms = (probe.polarity is Polarity.AFFIRMATIVE) == b
            if constraint.answer_type is AnswerType.BOOLEAN:
                value = "YES" if affirms else "NO"
                return Stage0Result(
                    ResponseLabel.ANSWER, value, text, (value,),
                    f"polar {probe.polarity.value} probe answered "
                    f"{'YES' if b else 'NO'} -> proposition {'holds' if affirms else 'fails'}",
                )
            g = constraint.gold_answer
            label = ResponseLabel.ANSWER if affirms else ResponseLabel.NEGATED
            return Stage0Result(
                label, g, text, (g,),
                f"polar {probe.polarity.value} probe answered "
                f"{'YES' if b else 'NO'} -> {'' if affirms else 'NOT '}{g}",
            )

    # 5. Answer-space matching.
    hits = (
        _canonicalise_date(text, constraint)
        if constraint.answer_type is AnswerType.DATE
        else _find_candidates(text, constraint)
    )

    if not hits:
        return Stage0Result(
            ResponseLabel.INVALID, None, None, (),
            "no member of the closed answer space was recognised",
        )
    if len(hits) > 1:
        return Stage0Result(
            ResponseLabel.AMBIGUOUS, None, None,
            tuple(c for c, _ in hits),
            f"{len(hits)} mutually exclusive answers in one response",
        )
    canonical, surface = hits[0]
    return Stage0Result(ResponseLabel.ANSWER, canonical, surface, (canonical,))
