#!/usr/bin/env python3
"""Rewrite the pilot's polar-cloze probe texts in place (CANON Variant A).

    python scripts/benchmark/rewrite_polar_cloze.py --check   # report, write nothing
    python scripts/benchmark/rewrite_polar_cloze.py --apply   # rewrite probes.jsonl

Why this is not ``build_pilot.py --force``: a full rebuild re-stamps
``generated_at`` on all 96 probes and re-derives every field, which would bury a
28-probe surface change in a 96-probe diff. This script rebuilds with the current
templates, then writes back **only** the probes whose ``probe_text`` actually
changed, giving those a fresh ``generated_at`` and leaving the other records
byte-identical.

It refuses to write if any field other than ``probe_text``/``generated_at``
differs, so the §4.4.1 guarantee -- that the rewrite changes surface text and not
the formal representation -- is enforced here rather than asserted.

Constraints are not touched. Raw model outputs are not touched and are not read:
they live under ``results/raw/`` on the cluster and are immutable (ADR-0005).
No inference of any kind is run.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import yaml  # noqa: E402

from semintegrity.benchmark.pilot_builder import build  # noqa: E402
from semintegrity.schemas.probe import (  # noqa: E402
    EQUIVALENCE_KEY_FIELDS,
    SURFACE_FACTOR_FIELDS,
)

PILOT = ROOT / "data" / "benchmark" / "pilot"
PROBES = PILOT / "probes.jsonl"

#: Fields a surface rewrite is permitted to change.
MUTABLE = {"probe_text", "generated_at"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="report the diff, write nothing")
    g.add_argument("--apply", action="store_true", help="write the rewritten probes")
    args = ap.parse_args()

    on_disk = [json.loads(line) for line in PROBES.read_text().splitlines() if line.strip()]
    by_id = {r["probe_id"]: r for r in on_disk}

    candidates = yaml.safe_load((PILOT / "candidates.yaml").read_text(encoding="utf-8"))
    rebuilt = {p.probe_id: p.model_dump(mode="json") for p in build(candidates).probes}

    if set(by_id) != set(rebuilt):
        print("probe id sets differ between disk and rebuild; refusing", file=sys.stderr)
        return 2

    changed: list[str] = []
    illegal: list[str] = []
    for pid, old in by_id.items():
        new = rebuilt[pid]
        for field in set(old) | set(new):
            if field in MUTABLE:
                continue
            if old.get(field) != new.get(field):
                illegal.append(f"{pid}.{field}: {old.get(field)!r} -> {new.get(field)!r}")
        if old["probe_text"] != new["probe_text"]:
            changed.append(pid)

    print(f"probes on disk        : {len(on_disk)}")
    print(f"probe_text rewritten  : {len(changed)}")
    print(f"formal/factor changes : {len(illegal)}")

    # The guarantee, checked rather than claimed.
    protected = ("constraint_id", "probe_id", *EQUIVALENCE_KEY_FIELDS, "answer_type")
    print(f"§4.4.1 formal representation {protected} unchanged: {'YES' if not illegal else 'NO'}")
    print(f"§4.4.2 surface factors {SURFACE_FACTOR_FIELDS} unchanged: "
          f"{'YES' if not illegal else 'NO'}")

    if illegal:
        print("\nREFUSING TO WRITE — a rewrite may only change probe_text:", file=sys.stderr)
        for line in illegal[:20]:
            print(f"  {line}", file=sys.stderr)
        return 3

    for pid in changed:
        print(f"\n  {pid}")
        print(f"    old: {by_id[pid]['probe_text']}")
        print(f"    new: {rebuilt[pid]['probe_text']}")

    if args.check:
        print(f"\n--check: nothing written. {len(changed)} probe(s) would be rewritten.")
        return 0

    if not changed:
        print("\nnothing to do; probes.jsonl already carries the current wording")
        return 0

    stamp = dt.datetime.now(dt.timezone.utc).isoformat()
    for pid in changed:
        by_id[pid]["probe_text"] = rebuilt[pid]["probe_text"]
        by_id[pid]["generated_at"] = stamp

    # Preserve file order; write atomically.
    tmp = PROBES.with_suffix(".jsonl.tmp")
    tmp.write_text(
        "".join(json.dumps(by_id[r["probe_id"]], ensure_ascii=False) + "\n" for r in on_disk),
        encoding="utf-8",
    )
    tmp.replace(PROBES)
    print(f"\nwrote {PROBES.relative_to(ROOT)} — {len(changed)} probe_text, "
          f"{len(on_disk) - len(changed)} untouched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
