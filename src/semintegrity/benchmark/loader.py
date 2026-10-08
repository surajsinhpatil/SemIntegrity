"""Load, save and freeze the benchmark.

The benchmark is JSONL: one constraint or probe per line, human-diffable, and
appendable during authoring. Freezing computes a content hash over the whole set
and writes it to a manifest, so "the frozen benchmark" is a checkable claim
(§4.1: *FROZEN BENCHMARK — no changes after this point*).
"""

from __future__ import annotations

import datetime as dt
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from pathlib import Path

from ..schemas.constraint import Constraint
from ..schemas.enums import Split
from ..schemas.probe import Probe, assert_distinct_surfaces, assert_mutually_equivalent
from ..utils.hashing import canonical_json, sha256_obj
from ..utils.io import append_jsonl, read_jsonl, write_json_exclusive
from ..utils.logging import get_logger

log = get_logger(__name__)

CONSTRAINTS_FILE = "constraints.jsonl"
PROBES_FILE = "probes.jsonl"
FREEZE_FILE = "FREEZE.json"


class BenchmarkFrozenError(RuntimeError):
    """Raised on an attempt to modify a frozen benchmark, or when it has drifted."""


# --- load / save -----------------------------------------------------------
def load_constraints(path: str | Path) -> list[Constraint]:
    """Load and validate constraints. A malformed record is an error, not a skip."""
    out: list[Constraint] = []
    for i, rec in enumerate(read_jsonl(path), start=1):
        try:
            out.append(Constraint.model_validate(rec))
        except Exception as exc:
            raise ValueError(f"{path}:{i} is not a valid constraint: {exc}") from exc
    return out


def load_probes(path: str | Path) -> list[Probe]:
    out: list[Probe] = []
    for i, rec in enumerate(read_jsonl(path), start=1):
        try:
            out.append(Probe.model_validate(rec))
        except Exception as exc:
            raise ValueError(f"{path}:{i} is not a valid probe: {exc}") from exc
    return out


def save_constraints(path: str | Path, constraints: Iterable[Constraint]) -> int:
    _refuse_if_frozen(Path(path).parent)
    return append_jsonl(path, [c.to_record() for c in constraints])


def save_probes(path: str | Path, probes: Iterable[Probe]) -> int:
    _refuse_if_frozen(Path(path).parent)
    return append_jsonl(path, [p.model_dump(mode="json") for p in probes])


def load_split(directory: str | Path) -> tuple[list[Constraint], list[Probe]]:
    """Load a split directory (``data/benchmark/test``, ``.../dev``, ...)."""
    d = Path(directory)
    return load_constraints(d / CONSTRAINTS_FILE), load_probes(d / PROBES_FILE)


# --- structural checks -----------------------------------------------------
def group_probes(probes: Sequence[Probe]) -> dict[str, list[Probe]]:
    grouped: dict[str, list[Probe]] = defaultdict(list)
    for p in probes:
        grouped[p.constraint_id].append(p)
    for v in grouped.values():
        v.sort(key=lambda p: p.index)
    return dict(grouped)


#: The (polarity, register, directionality) cells ADR-0003 requires every
#: constraint to carry EXACTLY ONCE. 2 x 2 x 2 = 8 = K, which is why this
#: crossing is complete within a constraint while syntax rotates across them.
REQUIRED_FACTOR_CELLS: frozenset[tuple[str, str, str]] = frozenset(
    (pol, reg, direction)
    for pol in ("affirmative", "negated")
    for reg in ("formal", "colloquial")
    for direction in ("direct", "reverse")
)


def check_factor_cell_completeness(probes: Sequence[Probe]) -> list[str]:
    """ADR-0003: each constraint carries all 8 factor cells exactly once.

    :func:`semintegrity.schemas.probe.assert_distinct_surfaces` is NOT a
    substitute. It checks that the 4-tuples (syntax, polarity, register,
    directionality) are pairwise distinct, and eight probes can satisfy that
    while still missing a required (polarity, register, directionality) cell —
    two probes differing only in syntax would pass distinctness and silently
    break the exact class-level balance §4.4.2 depends on. Completeness and
    distinctness are different properties and both are needed.
    """
    counts = Counter((p.polarity.value, p.register.value, p.directionality.value) for p in probes)
    problems: list[str] = []
    missing = sorted(REQUIRED_FACTOR_CELLS - set(counts))
    if missing:
        problems.append(
            f"missing {len(missing)} required factor cell(s): "
            + ", ".join("/".join(c) for c in missing)
        )
    repeated = sorted((cell, n) for cell, n in counts.items() if n > 1)
    for cell, n in repeated:
        problems.append(f"factor cell {'/'.join(cell)} appears {n} times, expected once")
    unexpected = sorted(set(counts) - REQUIRED_FACTOR_CELLS)
    for cell in unexpected:
        problems.append(f"factor cell {'/'.join(cell)} is not one of the 8 required cells")
    return problems


def check_distinct_probe_texts(probes: Sequence[Probe]) -> list[str]:
    """No two probes of one constraint may share surface text.

    A HARD failure, not a warning: identical surfaces inflate apparent agreement
    between probes that are supposed to be distinct paraphrases, which biases
    every consistency metric computed over the pair.
    """
    seen: dict[str, str] = {}
    problems: list[str] = []
    for p in probes:
        key = " ".join(p.probe_text.lower().split())
        if key in seen:
            problems.append(
                f"probes {seen[key]} and {p.probe_id} have identical text "
                "(identical surfaces inflate apparent agreement)"
            )
        else:
            seen[key] = p.probe_id
    return problems


def check_probe_sets(
    constraints: Sequence[Constraint], probes: Sequence[Probe], *, k: int
) -> list[str]:
    """Structural checks over probe sets. Returns problems; empty means clean."""
    problems: list[str] = []
    grouped = group_probes(probes)
    known = {c.constraint_id for c in constraints}

    for orphan in sorted(set(grouped) - known):
        problems.append(f"{orphan}: probes reference a constraint not in this split")

    for c in constraints:
        group = grouped.get(c.constraint_id, [])
        if len(group) != k:
            problems.append(f"{c.constraint_id}: {len(group)} probes, expected {k}")
            continue
        if [p.index for p in group] != list(range(1, k + 1)):
            problems.append(f"{c.constraint_id}: probe indices are not 1..{k}")
        try:
            assert_mutually_equivalent(group)
        except ValueError as exc:
            problems.append(f"{c.constraint_id}: {exc}")
        try:
            assert_distinct_surfaces(group)
        except ValueError as exc:
            problems.append(f"{c.constraint_id}: {exc}")
        # Completeness, on top of distinctness — see the docstring above.
        if k == len(REQUIRED_FACTOR_CELLS):
            problems.extend(f"{c.constraint_id}: {m}" for m in check_factor_cell_completeness(group))
        problems.extend(f"{c.constraint_id}: {m}" for m in check_distinct_probe_texts(group))
        for p in group:
            if p.expected_answer not in c.answer_space and p.answer_type.value != "boolean":
                problems.append(
                    f"{p.probe_id}: expected_answer {p.expected_answer!r} is outside the "
                    f"constraint's closed answer space"
                )
    return problems


# --- freeze ----------------------------------------------------------------
def content_hash(constraints: Sequence[Constraint], probes: Sequence[Probe]) -> str:
    """Order-independent hash over the benchmark's content."""
    return sha256_obj(
        {
            "constraints": sorted(canonical_json(c.to_record()) for c in constraints),
            "probes": sorted(canonical_json(p.model_dump(mode="json")) for p in probes),
        }
    )


def freeze(directory: str | Path, *, split: Split, k: int, note: str = "") -> Path:
    """Freeze a split: validate structurally, then write an immutable manifest."""
    d = Path(directory)
    constraints, probes = load_split(d)
    problems = check_probe_sets(constraints, probes, k=k)
    if problems:
        raise BenchmarkFrozenError(
            "refusing to freeze a benchmark with structural problems:\n  - "
            + "\n  - ".join(problems)
        )
    manifest = {
        "split": split.value,
        "frozen_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "note": note,
        "n_constraints": len(constraints),
        "n_probes": len(probes),
        "k": k,
        "content_sha256": content_hash(constraints, probes),
    }
    out = write_json_exclusive(d / FREEZE_FILE, manifest)
    log.info("froze benchmark split", extra={"extra_fields": manifest})
    return out


def is_frozen(directory: str | Path) -> bool:
    return (Path(directory) / FREEZE_FILE).is_file()


def verify_freeze(directory: str | Path) -> list[str]:
    """Report drift of a frozen split against its manifest."""
    import json

    d = Path(directory)
    manifest_path = d / FREEZE_FILE
    if not manifest_path.is_file():
        return [f"{d} is not frozen (no {FREEZE_FILE})"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    constraints, probes = load_split(d)

    problems: list[str] = []
    if len(constraints) != manifest["n_constraints"]:
        problems.append(
            f"constraint count changed: {manifest['n_constraints']} -> {len(constraints)}"
        )
    if len(probes) != manifest["n_probes"]:
        problems.append(f"probe count changed: {manifest['n_probes']} -> {len(probes)}")
    live = content_hash(constraints, probes)
    if live != manifest["content_sha256"]:
        problems.append(
            f"CONTENT CHANGED after freeze: {manifest['content_sha256'][:12]} -> {live[:12]}"
        )
    return problems


def assert_not_drifted(directory: str | Path) -> None:
    problems = verify_freeze(directory)
    if problems:
        raise BenchmarkFrozenError(
            f"{directory} has drifted from its freeze manifest:\n  - " + "\n  - ".join(problems)
        )


def _refuse_if_frozen(directory: Path) -> None:
    if is_frozen(directory):
        raise BenchmarkFrozenError(
            f"{directory} is frozen (§4.1: no changes after the freeze). "
            f"Remove {FREEZE_FILE} deliberately, with an ADR recording why, if the "
            "freeze genuinely must be broken."
        )
