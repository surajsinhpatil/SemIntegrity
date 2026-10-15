#!/usr/bin/env python3
"""PROBE-C: machine-audited probe construction (ADR-0023 D2, go/no-go gate).

    python scripts/analysis/probe_c_audit.py --split test

CPU only, read-only, no model. Replaces the preregistered `PROBE` criterion,
which required ">= 90% of candidate probes survive HUMAN semantic-equivalence
validation" — never exercised; all 1,056 probes carry `validation_status: draft`.

PROBE-C passes when the probe set loads at all (three upstream guarantees, each
a hard failure) and no probe trips the one pathology check this project adds.
**It audits the GENERATOR, not the generated meaning.** A systematically
mis-specified `logical_form` passes. The result may be described as
"constructed and machine-audited", never as "validated".

Flagged probes are REPORTED. Nothing is rewritten or discarded: the benchmark is
frozen, and Q33 records the open decision about what to do with the finding.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from semintegrity.benchmark.loader import load_split
from semintegrity.probes.pathology import PATHOLOGIES, audit
from semintegrity.utils.paths import data_path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", default="test")
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--examples", type=int, default=3)
    args = ap.parse_args(argv)

    # Loading IS part of the audit: the three upstream guarantees are hard
    # failures raised here, so a split that loads has already passed them.
    cons, probe_list = load_split(data_path("benchmark") / args.split)
    by_constraint: dict[str, list] = {}
    for p in probe_list:
        by_constraint.setdefault(p.constraint_id, []).append(p)

    findings, summary = audit(cons, by_constraint)

    print(f"split      : {args.split}")
    print(f"constraints: {summary['n_constraints']}")
    print(f"probes     : {summary['n_probes']}")
    print(f"flagged    : {summary['n_flagged']}  ({summary['flagged_rate']:.4f})")
    print(f"PROBE-C    : {'PASS' if summary['passes_probe_c'] else 'FLAGGED'}")
    print()
    print("upstream guarantees (enforced elsewhere, verified by loading):")
    for g in summary["upstream_guarantees"]:
        print(f"  - {g['guarantee']}")
        print(f"      {g['enforced_by']} @ {g['when']} — {g['severity']}")
    print()
    print("checks implemented by PROBE-C itself:")
    for name in PATHOLOGIES:
        n = summary["counts"][name]
        cells = summary["by_factor_cell"].get(name, {})
        print(f"  - {name}: {n}" + (f"   by factor cell {cells}" if cells else ""))

    if args.examples:
        by_path: dict[str, list] = {}
        for f in findings:
            by_path.setdefault(f.pathology, []).append(f)
        for name, items in sorted(by_path.items()):
            print(f"\n--- {name} (showing {min(args.examples, len(items))} of {len(items)}) ---")
            probes = {p.probe_id: p for p in probe_list}
            for f in items[: args.examples]:
                print(f"  {f.probe_id}  cell={f.factor_cell}")
                print(f"    text: {probes[f.probe_id].probe_text!r}")

    print(f"\nscope: {summary['scope']}")
    print(f"status of the one check: {summary['stem_embeds_gold_answer_status']}")
    print(f"remedy: {summary['remedy']}")

    if args.out_dir:
        out = Path(args.out_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"probe_c.{args.split}.json"
        path.write_text(json.dumps({
            "generated_at_utc": dt.datetime.now(dt.UTC).isoformat(),
            **summary,
            "findings": [
                {"probe_id": f.probe_id, "constraint_id": f.constraint_id,
                 "pathology": f.pathology, "factor_cell": f.factor_cell,
                 "detail": f.detail}
                for f in findings
            ],
        }, indent=2, sort_keys=True) + "\n")
        print(f"\nwrote {path}")
    # Flagged probes are a MEASUREMENT, not a build failure: the benchmark is
    # frozen and Q33 holds the open decision. Exit 0 either way.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
