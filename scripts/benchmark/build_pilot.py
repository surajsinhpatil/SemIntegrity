#!/usr/bin/env python3
"""Build the pilot benchmark from candidates.yaml.

    python scripts/benchmark/build_pilot.py                    # offline, DRAFT only
    python scripts/benchmark/build_pilot.py --fetch-evidence   # query Wikidata, still DRAFT
    python scripts/benchmark/build_pilot.py --fetch-evidence --promote

Needs network only with --fetch-evidence. Downloads no models. Writes to
``data/benchmark/pilot/``.

``--promote`` raises a constraint to EVIDENCE_VERIFIED **only** if every one of
its declared checks passed. It can never produce HUMAN_VALIDATED: that requires
a named human and is recorded by ``validate_pilot.py``.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import yaml  # noqa: E402

from semintegrity.benchmark.loader import save_constraints, save_probes  # noqa: E402
from semintegrity.benchmark.pilot_builder import (  # noqa: E402
    answer_type_by_class,
    build,
    unpopulated_sitelinks,
)
from semintegrity.kb.cache import CacheMode  # noqa: E402
from semintegrity.utils.logging import setup_logging  # noqa: E402

PILOT = ROOT / "data" / "benchmark" / "pilot"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fetch-evidence", action="store_true", help="query Wikidata (needs network)")
    ap.add_argument("--promote", action="store_true",
                    help="promote to EVIDENCE_VERIFIED where every check passed")
    ap.add_argument("--force", action="store_true", help="overwrite existing pilot records")
    args = ap.parse_args()
    setup_logging()

    if args.promote and not args.fetch_evidence:
        print("--promote requires --fetch-evidence: a status cannot be earned without checks",
              file=sys.stderr)
        return 2

    candidates = yaml.safe_load((PILOT / "candidates.yaml").read_text(encoding="utf-8"))
    result = build(
        candidates,
        fetch_evidence=args.fetch_evidence,
        promote_on_evidence=args.promote,
        cache_mode=CacheMode.LIVE,
    )

    print(f"built {len(result.constraints)} constraints, {len(result.probes)} probes")
    statuses = Counter(c.verification_status.value for c in result.constraints)
    print(f"verification status: {dict(statuses)}")
    if args.fetch_evidence:
        print(f"evidence checks    : {result.n_evidence_passed}/{result.n_evidence_total} passed")

    if result.warnings:
        print(f"\n{len(result.warnings)} warning(s):")
        for w in result.warnings:
            print(f"  - {w}")

    confound = {k: sorted(v) for k, v in answer_type_by_class(result.constraints).items()}
    if all(len(v) == 1 for v in confound.values()):
        print("\nNOTE — class is perfectly correlated with answer type in this pilot:")
        for k, v in sorted(confound.items()):
            print(f"    {k}: {v[0]}")
        print("  For the 120-constraint benchmark, answer type must be varied WITHIN class,")
        print("  or any class effect will be confounded with answer format.")

    missing = unpopulated_sitelinks(result.constraints)
    if missing:
        print(f"\nsitelinks unpopulated for {len(missing)} constraint(s) "
              f"(run with --fetch-evidence)")

    cpath, ppath = PILOT / "constraints.jsonl", PILOT / "probes.jsonl"
    if args.force:
        cpath.unlink(missing_ok=True)
        ppath.unlink(missing_ok=True)
    elif cpath.exists():
        print(f"\n{cpath} exists; pass --force to rebuild", file=sys.stderr)
        return 3

    save_constraints(cpath, result.constraints)
    save_probes(ppath, result.probes)
    print(f"\nwrote {cpath.relative_to(ROOT)}\nwrote {ppath.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
