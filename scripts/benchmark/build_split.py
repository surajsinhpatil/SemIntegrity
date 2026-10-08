#!/usr/bin/env python3
"""Build the TEST or DEV split from its candidates.yaml.

    python scripts/benchmark/build_split.py --split test                    # offline, DRAFT only
    python scripts/benchmark/build_split.py --split test --fetch-evidence   # query Wikidata
    python scripts/benchmark/build_split.py --split test --fetch-evidence --promote

The same builder as the pilot — ``semintegrity.benchmark.pilot_builder.build``,
whose module name is historical — with ``split``/``tier`` set for a primary-tier
split. **No parallel authoring system:** this is a driver, not a second pipeline.
Probes come from the approved factor design (K=8, syntax rotation keyed to
``semintegrity.benchmark.ordering``), untouched.

``--promote`` raises a constraint to EVIDENCE_VERIFIED **only** when every
declared evidence check passed, and the builder independently demotes anything
that §4.3 requires a second source for and that has none. It can never produce
HUMAN_VALIDATED or FROZEN.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import yaml  # noqa: E402

from semintegrity.benchmark.design_validator import corroboration_reason  # noqa: E402
from semintegrity.benchmark.loader import save_constraints, save_probes  # noqa: E402
from semintegrity.benchmark.pilot_builder import build, unpopulated_sitelinks  # noqa: E402
from semintegrity.kb.cache import CacheMode  # noqa: E402
from semintegrity.schemas.enums import Split, Tier, VerificationStatus  # noqa: E402
from semintegrity.utils.logging import setup_logging  # noqa: E402

SPLITS = {"test": Split.TEST, "dev": Split.DEV}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--split", choices=sorted(SPLITS), required=True)
    ap.add_argument("--fetch-evidence", action="store_true", help="query Wikidata (needs network)")
    ap.add_argument("--promote", action="store_true",
                    help="promote to EVIDENCE_VERIFIED where every check passed")
    ap.add_argument("--force", action="store_true", help="rebuild over existing records")
    ap.add_argument("--dry-run", action="store_true", help="build and report; write nothing")
    args = ap.parse_args()
    setup_logging()

    if args.promote and not args.fetch_evidence:
        print("--promote requires --fetch-evidence: a status cannot be earned without checks",
              file=sys.stderr)
        return 2

    split = SPLITS[args.split]
    directory = ROOT / "data" / "benchmark" / args.split
    candidates_path = directory / "candidates.yaml"
    if not candidates_path.is_file():
        print(f"no candidates at {candidates_path}", file=sys.stderr)
        return 2

    candidates = yaml.safe_load(candidates_path.read_text(encoding="utf-8"))
    result = build(
        candidates,
        fetch_evidence=args.fetch_evidence,
        promote_on_evidence=args.promote,
        cache_mode=CacheMode.LIVE,
        split=split,
        tier=Tier.PRIMARY,
    )

    print(f"built {len(result.constraints)} constraints, {len(result.probes)} probes "
          f"for split={args.split}")
    print(f"verification status: {dict(Counter(c.verification_status.value for c in result.constraints))}")
    print(f"class              : {dict(sorted(Counter(c.constraint_class.value for c in result.constraints).items()))}")
    print(f"answer type        : {dict(sorted(Counter(str(c.answer_type) for c in result.constraints).items()))}")
    print(f"domain             : {dict(sorted(Counter(c.domain.value for c in result.constraints).items()))}")
    if args.fetch_evidence:
        print(f"evidence checks    : {result.n_evidence_passed}/{result.n_evidence_total} passed")

    needs = [c for c in result.constraints if corroboration_reason(c)]
    with_source = [c for c in needs if c.corroborating_sources]
    print(f"corroboration      : {len(needs)} constraint(s) require a second source; "
          f"{len(with_source)} carry one")
    promoted = [c for c in result.constraints
                if c.verification_status is VerificationStatus.EVIDENCE_VERIFIED]
    print(f"EVIDENCE_VERIFIED  : {len(promoted)}")

    if result.warnings:
        print(f"\n{len(result.warnings)} warning(s):")
        for w in result.warnings:
            print(f"  - {w}")

    missing = unpopulated_sitelinks(result.constraints)
    if missing:
        print(f"\nsitelinks unpopulated for {len(missing)} constraint(s) (run --fetch-evidence)")

    if args.dry_run:
        print("\n--dry-run: nothing written")
        return 0

    cpath, ppath = directory / "constraints.jsonl", directory / "probes.jsonl"
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
