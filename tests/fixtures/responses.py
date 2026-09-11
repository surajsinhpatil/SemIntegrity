"""Helpers for building canonicalised responses in tests."""

from __future__ import annotations

import datetime as dt

from semintegrity.schemas.enums import ResponseLabel
from semintegrity.schemas.response import CanonicalResponse

_SHA = "0" * 64


def canon(
    probe_id: str,
    answer: str | None,
    *,
    label: ResponseLabel = ResponseLabel.ANSWER,
    candidates: list[str] | None = None,
) -> CanonicalResponse:
    constraint_id = probe_id.rsplit("-P", 1)[0]
    return CanonicalResponse(
        response_id="R-" + "a" * 12,
        constraint_id=constraint_id,
        probe_id=probe_id,
        label=label,
        canonical_answer=answer,
        candidates_found=candidates or ([answer] if answer else []),
        canonicaliser_version="test",
        canonicaliser_sha256=_SHA,
        canonicalised_at=dt.datetime(2026, 9, 11, tzinfo=dt.timezone.utc),
    )
