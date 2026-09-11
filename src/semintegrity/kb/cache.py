"""Frozen, content-addressed knowledge-base cache (ADR-0011).

Two problems this solves.

**Compute nodes have no network.** Slurm jobs must resolve ground truth without
reaching Wikidata, so every fetch is recorded on the login node and replayed
from disk afterwards.

**Wikidata changes.** A constraint verified in September and re-verified in
December can silently differ. Every cached entry stores what was fetched, when,
and the hash of the request that produced it, so "the knowledge base the study
used" is an artefact rather than a memory.

Modes
-----
``LIVE``    fetch on miss, write to cache. Login node / laptop only.
``FROZEN``  never fetch; a miss is an error. The mode Slurm jobs and anyone
            reproducing the study runs in.
``REFRESH`` re-fetch even on hit, writing a NEW entry beside the old one. Never
            replaces history.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from ..utils.hashing import canonical_json, sha256_obj
from ..utils.logging import get_logger

log = get_logger(__name__)


class CacheMode(str, Enum):
    LIVE = "live"
    FROZEN = "frozen"
    REFRESH = "refresh"


class CacheMiss(KeyError):
    """Raised when a FROZEN cache is asked for something it does not hold."""


@dataclass(frozen=True, slots=True)
class CacheEntry:
    request_hash: str
    kind: str
    request: dict[str, Any]
    payload: Any
    fetched_at: dt.datetime
    source: str

    def to_json(self) -> dict[str, Any]:
        return {
            "request_hash": self.request_hash,
            "kind": self.kind,
            "request": self.request,
            "payload": self.payload,
            "fetched_at": self.fetched_at.isoformat(),
            "source": self.source,
        }

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> CacheEntry:
        return cls(
            request_hash=d["request_hash"],
            kind=d["kind"],
            request=d["request"],
            payload=d["payload"],
            fetched_at=dt.datetime.fromisoformat(d["fetched_at"]),
            source=d["source"],
        )


class KBCache:
    """A directory of content-addressed JSON entries.

    Layout::

        <root>/<kind>/<first two hex chars>/<request_hash>.json
        <root>/MANIFEST.json

    Sharding by the first two hex characters keeps directory sizes sane on NFS,
    which is where this will live on the cluster.
    """

    def __init__(self, root: str | Path, mode: CacheMode = CacheMode.FROZEN) -> None:
        self.root = Path(root)
        self.mode = mode
        self._memo: dict[str, CacheEntry] = {}

    # -- keys ---------------------------------------------------------------
    @staticmethod
    def request_hash(kind: str, request: dict[str, Any]) -> str:
        return sha256_obj({"kind": kind, "request": request})

    def _path(self, kind: str, request_hash: str) -> Path:
        return self.root / kind / request_hash[:2] / f"{request_hash}.json"

    # -- read/write ---------------------------------------------------------
    def get(self, kind: str, request: dict[str, Any]) -> CacheEntry | None:
        h = self.request_hash(kind, request)
        if h in self._memo:
            return self._memo[h]
        path = self._path(kind, h)
        if not path.is_file():
            return None
        entry = CacheEntry.from_json(json.loads(path.read_text(encoding="utf-8")))
        self._memo[h] = entry
        return entry

    def require(self, kind: str, request: dict[str, Any]) -> CacheEntry:
        """Fetch from cache or raise. Used by FROZEN consumers."""
        entry = self.get(kind, request)
        if entry is None:
            raise CacheMiss(
                f"frozen KB cache has no entry for {kind} {canonical_json(request)}; "
                f"expected at {self._path(kind, self.request_hash(kind, request))}. "
                "Run the snapshot script from a node with network access."
            )
        return entry

    def put(self, kind: str, request: dict[str, Any], payload: Any, source: str) -> CacheEntry:
        """Write an entry. Existing entries are archived, never overwritten."""
        if self.mode is CacheMode.FROZEN:
            raise RuntimeError("refusing to write to a FROZEN knowledge-base cache")
        h = self.request_hash(kind, request)
        entry = CacheEntry(
            request_hash=h,
            kind=kind,
            request=request,
            payload=payload,
            fetched_at=dt.datetime.now(dt.timezone.utc),
            source=source,
        )
        path = self._path(kind, h)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            stamp = entry.fetched_at.strftime("%Y%m%dT%H%M%SZ")
            archive = path.with_name(f"{h}.superseded-{stamp}.json")
            path.rename(archive)
            log.info("archived superseded KB entry", extra={"extra_fields": {"archived": str(archive)}})
        path.write_text(canonical_json(entry.to_json()), encoding="utf-8")
        self._memo[h] = entry
        return entry

    # -- snapshot integrity -------------------------------------------------
    def entries(self) -> list[Path]:
        return sorted(p for p in self.root.rglob("*.json") if p.name != "MANIFEST.json")

    def write_manifest(self) -> Path:
        """Record the exact cache contents so a snapshot can be verified later."""
        from ..utils.hashing import sha256_file

        files = self.entries()
        manifest = {
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "n_entries": len(files),
            "entries": {
                str(p.relative_to(self.root)): sha256_file(p) for p in files
            },
        }
        manifest["snapshot_sha256"] = sha256_obj(manifest["entries"])
        out = self.root / "MANIFEST.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(canonical_json(manifest), encoding="utf-8")
        return out

    def verify_manifest(self) -> list[str]:
        """Return a list of discrepancies against MANIFEST.json (empty = intact)."""
        from ..utils.hashing import sha256_file

        out = self.root / "MANIFEST.json"
        if not out.is_file():
            return ["MANIFEST.json is missing; the snapshot is unverifiable"]
        manifest = json.loads(out.read_text(encoding="utf-8"))
        recorded: dict[str, str] = manifest["entries"]
        problems: list[str] = []
        for rel, digest in recorded.items():
            path = self.root / rel
            if not path.is_file():
                problems.append(f"missing: {rel}")
            elif sha256_file(path) != digest:
                problems.append(f"modified: {rel}")
        on_disk = {str(p.relative_to(self.root)) for p in self.entries()}
        for extra in sorted(on_disk - set(recorded)):
            problems.append(f"untracked: {extra}")
        return problems

    def __len__(self) -> int:
        return len(self.entries())

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"KBCache(root={self.root}, mode={self.mode.value}, entries={len(self)})"
