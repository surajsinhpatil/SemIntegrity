"""Immutable, resumable JSONL I/O.

Two rules from the proposal drive this module:

* raw model outputs are immutable once generated (§5.6 release plan);
* a session disconnect must not lose a run (§4.13), so results are written
  incrementally and a job can resume where it stopped.

The implementation is append-only JSONL plus a sidecar of already-written keys.
Resume reads the sidecar, skips completed work, and appends. Nothing is ever
rewritten in place, so a crash truncates at most the final line, which is
detected and dropped on the next read.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from .hashing import canonical_json


class ImmutabilityError(RuntimeError):
    """Raised on an attempt to overwrite an immutable artefact."""


def write_json_exclusive(path: str | Path, obj: Any) -> Path:
    """Write JSON, failing loudly if the file already exists."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError as exc:
        raise ImmutabilityError(f"refusing to overwrite existing artefact: {out}") from exc
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(canonical_json(obj))
        fh.write("\n")
    return out


def append_jsonl(path: str | Path, records: Iterable[dict[str, Any]], *, fsync: bool = True) -> int:
    """Append records to a JSONL file, creating it if needed.

    ``fsync`` is on by default: cluster jobs are killed by walltime, and a
    result that is only in the page cache when the job dies is a lost result.
    """
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with out.open("a", encoding="utf-8") as fh:
        for rec in records:
            fh.write(canonical_json(rec))
            fh.write("\n")
            written += 1
        fh.flush()
        if fsync:
            os.fsync(fh.fileno())
    return written


def read_jsonl(path: str | Path, *, tolerate_truncated_tail: bool = True) -> Iterator[dict[str, Any]]:
    """Stream a JSONL file.

    A partial final line (a job killed mid-write) is dropped with
    ``tolerate_truncated_tail``; any *other* malformed line is an error, because
    silently skipping corrupt records would quietly change a result.
    """
    src = Path(path)
    if not src.is_file():
        return
    with src.open(encoding="utf-8") as fh:
        lines = fh.readlines()
    last = len(lines) - 1
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            yield json.loads(stripped)
        except json.JSONDecodeError:
            if i == last and tolerate_truncated_tail and not line.endswith("\n"):
                return
            raise


def completed_keys(path: str | Path, key_fields: list[str]) -> set[tuple]:
    """Keys already present in a result file, for resume.

    Returns a set of tuples in ``key_fields`` order. A record missing any key
    field is a schema violation and raises.
    """
    seen: set[tuple] = set()
    for rec in read_jsonl(path):
        try:
            seen.add(tuple(rec[f] for f in key_fields))
        except KeyError as exc:
            raise KeyError(f"record in {path} is missing resume key field {exc}") from exc
    return seen
