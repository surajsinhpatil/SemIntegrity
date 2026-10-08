"""CLI: validate a benchmark split before spending GPU time.

    python -m semintegrity.benchmark.validate --split pilot --k 8

Read-only. Exits non-zero on any structural problem, so a Slurm job can gate on
it rather than discovering a malformed benchmark after the allocation starts.

Most rules apply to the split named by ``--split``. Three cannot: a constraint id
reused ACROSS splits, a dev constraint leaking a test entity set, and a
corroborating source whose frozen artefact no longer checks out. Those load every
split present on disk (and the corroboration store) and are always run, so none
is a check that exists without a caller.
"""

from __future__ import annotations

import argparse
import sys

from ..schemas.enums import Split
from ..utils.paths import data_path
from .design_validator import BenchmarkDesignValidator
from .loader import check_probe_sets, load_split


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--split", default="pilot", choices=[s.value for s in Split])
    ap.add_argument("--k", type=int, default=8, help="probes per constraint for this split")
    ap.add_argument("--strict-lattice", action="store_true",
                    help="also enforce the full 120-constraint design lattice (test split only)")
    ap.add_argument("--strict-d0", action="store_true",
                    help="treat an unregistered formal_predicate as an error, not a coverage gap")
    args = ap.parse_args(argv)

    split = Split(args.split)
    directory = data_path("benchmark") / split.value
    if not (directory / "constraints.jsonl").is_file():
        print(f"no benchmark at {directory}", file=sys.stderr)
        return 2

    constraints, probes = load_split(directory)
    print(f"{directory}: {len(constraints)} constraints, {len(probes)} probes\n")

    problems = check_probe_sets(constraints, probes, k=args.k)
    if problems:
        print(f"{len(problems)} structural problem(s):")
        for p in problems:
            print(f"  - {p}")
    else:
        print(
            f"[PASS] probe sets: {args.k} per constraint, mutually equivalent, "
            "all 8 factor cells present exactly once, no duplicate probe text"
        )

    from ..detectors.d0.registry import default_registry

    registry = default_registry()
    unregistered = sorted({c.formal_predicate for c in constraints} - set(registry.names()))
    if unregistered:
        # An unregistered predicate is ambiguous by nature: it is either a
        # deliberate D0 coverage gap (a legitimate RESULT per §4.8.1) or a typo
        # that will be silently reported AS a coverage gap. This command is used
        # as a Slurm preflight gate, so warning and exiting 0 lets the second
        # case burn an allocation and corrupt a reported coverage number.
        # --strict-d0 makes the caller state which reading applies; the default
        # stays a warning so that no existing caller's behaviour changes.
        stream = sys.stderr if args.strict_d0 else sys.stdout
        label = "ERROR" if args.strict_d0 else "WARN"
        print(f"\n[{label}] {len(unregistered)} predicate(s) not in the D0 registry: {unregistered}",
              file=stream)
        print("       D0 cannot verify these constraints; they count against D0 coverage.",
              file=stream)
        if args.strict_d0:
            problems.append(f"{len(unregistered)} unregistered D0 predicate(s): {unregistered}")
    else:
        print("[PASS] every formal_predicate resolves in the D0 registry")

    validator = BenchmarkDesignValidator()

    if args.strict_lattice:
        print()
        report = validator.validate(
            constraints, split=split, known_predicates=registry.names()
        )
        print(report)
        problems.extend(r.rule for r in report.errors)

    # --- cross-split rules ------------------------------------------------
    # These two are meaningless within a single split, so they load whatever
    # splits exist. A vacuous result is reported as vacuous: "nothing to compare"
    # is not the same claim as "no overlap", and must not read like one.
    print()
    everything, present = _load_all_splits()
    if not present:
        print("[WARN] cross-split rules: no split could be loaded")
    else:
        print(f"[INFO] cross-split rules over {', '.join(present)}")

        freeze_rule = validator.validate_corroboration_freeze(everything)
        print(f"  {freeze_rule}")
        if not freeze_rule.passed:
            problems.append(freeze_rule.rule)

        from ..kb.corroboration import CorroborationPolicy

        policy = CorroborationPolicy()
        print(f"  [{'INFO' if policy.configured else 'WARN'}] corroboration policy: "
              f"{policy.describe()}")

        id_rule = validator.validate_global_id_uniqueness(everything)
        print(f"  {id_rule}")
        if not id_rule.passed:
            problems.append(id_rule.rule)

        splits_present = {c.split for c in everything}
        has_test = Split.TEST in splits_present
        has_other = bool(splits_present - {Split.TEST})
        if has_test and has_other:
            dj = validator.validate_split_disjointness(everything)
            print(f"  {dj}")
            if not dj.passed:
                problems.append(dj.rule)
        else:
            missing = "test" if not has_test else "dev/pilot"
            print(
                f"  [VACUOUS] dev_test_disjoint: no {missing} split on disk, so there "
                "is nothing to compare. This is NOT a pass; it becomes meaningful "
                "once both splits exist."
            )

    return 1 if problems else 0


def _load_all_splits() -> tuple[list, list[str]]:
    """Every split present on disk, for the rules that span splits."""
    out: list = []
    present: list[str] = []
    for name in (s.value for s in Split):
        directory = data_path("benchmark") / name
        if not (directory / "constraints.jsonl").is_file():
            continue
        constraints, _ = load_split(directory)
        if constraints:
            out.extend(constraints)
            present.append(f"{name}={len(constraints)}")
    return out, present


if __name__ == "__main__":
    raise SystemExit(main())
