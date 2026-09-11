"""Content hashing.

Every identifier, freeze marker and config snapshot in this project is derived
from a content hash, so that "the same input" is a checkable claim rather than
an assertion.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

_ENC = "utf-8"


def sha256_text(text: str) -> str:
    """SHA-256 of a string, hex-encoded."""
    return hashlib.sha256(text.encode(_ENC)).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path, chunk_size: int = 1 << 20) -> str:
    """SHA-256 of a file's contents, streamed."""
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        while chunk := fh.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def canonical_json(obj: Any) -> str:
    """Deterministic JSON: sorted keys, no insignificant whitespace.

    Used wherever a dict must hash to the same value across processes and
    Python versions.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256_obj(obj: Any) -> str:
    """SHA-256 of an object's canonical JSON encoding."""
    return sha256_text(canonical_json(obj))


def sha256_tree(paths: Iterable[str | Path]) -> str:
    """Order-independent hash over a set of files.

    Each file contributes ``<relative-ish name>:<file hash>``; the pairs are
    sorted before hashing, so the result depends on contents and names but not
    on iteration order.
    """
    parts = sorted(f"{Path(p).name}:{sha256_file(p)}" for p in paths)
    return sha256_text("\n".join(parts))


def short(digest: str, n: int = 12) -> str:
    """First ``n`` hex characters of a digest, for human-readable ids."""
    return digest[:n]
