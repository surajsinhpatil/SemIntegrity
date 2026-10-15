#!/usr/bin/env python3
"""S1/S2/S3/S4 ground-truth and probe-exclusion sensitivity (ADR-0023 D9, Q33).

    python scripts/analysis/run_sensitivity.py \
        --raw results/raw/primary_trackA/qwen25-3b.jsonl \
        --out-dir results/analysis/sensitivity

CPU only. No GPU, no Slurm, no inference.

With human validation removed, these analyses are the primary defence of the
confirmatory results: 81 of 132 constraints are DRAFT for want of a §4.3 second
source, and nothing else now speaks to whether that matters.

* **S1** within-class EVIDENCE_VERIFIED vs DRAFT difference in PSCR. The
  comparability of each class is computed, not assumed, and a confounded or
  non-overlapping class yields no estimate.
* **S2** per-class PSCR restricted to EVIDENCE_VERIFIED. Descriptive.
* **S3** the arm contrast on the verified subset — a DIFFERENT contrast from
  H1_primary, never reported under that name.
* **S4** paired PSCR with and without the probes PROBE-C flags (Q33). SECONDARY;
  K=8 remains the primary design.

This script does NOT recompute H1_primary and cannot: `evaluate_primary.py`
owns the confirmatory analysis, and duplicating it here would create a second
definition of the project's headline result.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from semintegrity.analysis.evaluate import constraint_rows
from semintegrity.analysis.sensitivity import (
    confound_report,
    s1_within_class,
    s2_verified_only_profile,
    s3_restricted_contrast,
    s4_probe_exclusion,
    s4_probe_exclusion_plan,
)
from semintegrity.benchmark.loader import load_split
from semintegrity.canonicalization.canonicaliser import CANONICALISER_VERSION
from semintegrity.detectors.d0.registry import default_registry
from semintegrity.inference.backend import assert_no_stub_responses
from semintegrity.probes.pathology import audit as probe_audit
from semintegrity.schemas.response import RawResponse
from semintegrity.utils.config import load_config
from semintegrity.utils.hashing import sha256_file
from semintegrity.utils.io import read_jsonl
from semintegrity.utils.paths import data_path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", required=True)
    ap.add_argument("--split", default="test")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--metric", default="pscr")
    args = ap.parse_args(argv)

    assert_no_stub_responses(args.raw, context="the sensitivity analyses")

    conf = load_config("configs/analysis/statistics.yaml").data["confirmatory"]
    n_boot, ci, seed = int(conf["n_boot"]), float(conf["ci"]), int(conf["seed"])

    cons_list, probe_list = load_split(data_path("benchmark") / args.split)
    constraints = {c.constraint_id: c for c in cons_list}
    probes = {p.probe_id: p for p in probe_list}
    by_constraint: dict[str, list] = {}
    for p in probe_list:
        by_constraint.setdefault(p.constraint_id, []).append(p)

    raws = [RawResponse.model_validate(r) for r in read_jsonl(args.raw)]
    if not raws:
        sys.exit(f"no responses in {args.raw}")
    model_id = raws[0].provenance.model_id

    registry = default_registry()
    rows, _ = constraint_rows(raws, constraints, probes, d0_registry=registry)
    for r in rows:
        r["verification_status"] = str(constraints[r["constraint_id"]].verification_status)

    # --- S4: the exclusion set comes from probe TEXT, never from responses ---
    findings, probe_summary = probe_audit(cons_list, by_constraint)
    excluded = {f.probe_id for f in findings}
    plan = s4_probe_exclusion_plan(by_constraint, sorted(excluded))
    kept_raws = [r for r in raws if r.probe_id not in excluded]
    rows_excluded, _ = constraint_rows(kept_raws, constraints, probes, d0_registry=registry)
    for r in rows_excluded:
        r["verification_status"] = str(constraints[r["constraint_id"]].verification_status)

    ids_full = [r["constraint_id"] for r in rows]
    ids_excl = [r["constraint_id"] for r in rows_excluded]
    s4: dict[str, Any]
    if ids_full == ids_excl:
        s4 = s4_probe_exclusion(
            rows, rows_excluded, metric=args.metric, n_boot=n_boot, ci=ci, seed=seed
        )
    else:
        s4 = {
            "name": "S4 probe-exclusion sensitivity (secondary)",
            "estimate": None,
            "refusal": (
                "excluding the flagged probes removed every response of at least "
                f"one constraint ({len(ids_full)} vs {len(ids_excl)} constraints), "
                "so the paired comparison is not defined"
            ),
        }
    s4["plan"] = plan

    cf = confound_report(cons_list)
    report = {
        "generated_at_utc": dt.datetime.now(dt.UTC).isoformat(),
        "model_id": model_id, "raw_file": args.raw,
        "raw_sha256": sha256_file(args.raw), "split": args.split,
        "metric": args.metric,
        "canonicaliser_version": CANONICALISER_VERSION,
        "unit_of_analysis": "constraint",
        "h1_primary_on_verified_subset": {
            "computed": False,
            "why": (
                "there are no EVIDENCE_VERIFIED C4 constraints, so arm B would be "
                "C3 alone and the chance balance that protects the contrast is "
                "destroyed. See ADR-0023 D9."
            ),
        },
        "confound_report": {
            k: {
                "verdict": v.verdict, "n_verified": v.n_verified, "n_draft": v.n_draft,
                "chance_gap": v.chance_gap,
                "answer_types_verified": v.answer_types_verified,
                "answer_types_draft": v.answer_types_draft,
                "domains_missing_from_verified": list(v.domains_missing_from_verified),
                "median_sitelinks_verified": v.median_sitelinks_verified,
                "median_sitelinks_draft": v.median_sitelinks_draft,
                "notes": list(v.notes),
            }
            for k, v in cf.items()
        },
        "S1_within_class": s1_within_class(
            rows, cons_list, metric=args.metric, n_boot=n_boot, ci=ci, seed=seed
        ),
        "S2_verified_only_profile": s2_verified_only_profile(
            rows, metric=args.metric, n_boot=n_boot, ci=ci, seed=seed
        ),
        "S3_restricted_contrast": s3_restricted_contrast(
            rows, cons_list, metric=args.metric, n_boot=n_boot, ci=ci, seed=seed
        ),
        "S4_probe_exclusion": s4,
        "probe_c_summary": probe_summary,
        "human_gold": "NONE — no detector accuracy is computed anywhere here",
    }

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{model_id.replace('/', '__')}.sensitivity.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n")

    print(f"model : {model_id}")
    print(f"metric: {args.metric}   unit: constraint\n")
    print("S1 within-class EVIDENCE_VERIFIED vs DRAFT:")
    for klass, e in sorted(report["S1_within_class"].items()):
        est = e["estimate"]
        shown = "no estimate" if est is None else (
            f"{est:+.4f} ({e['ci_low']:+.4f}, {e['ci_high']:+.4f})"
        )
        print(f"  {klass}  {e['comparability']:28s} {shown}")
        if est is None:
            print(f"       means: verified={e['mean_verified']} draft={e['mean_draft']}")
    s3 = report["S3_restricted_contrast"]
    print(f"\nS3 {s3['name']}")
    if s3.get("estimate") is not None:
        print(f"   {s3['estimate']:+.4f} ({s3['ci_low']:+.4f}, {s3['ci_high']:+.4f})"
              f"   chance gap {s3['chance_gap']:+.4f}  — NOT H1_primary")
    print(f"\nS4 secondary, excluding {plan['n_excluded']} PROBE-C probe(s) "
          f"across {plan['n_constraints_affected']} constraint(s):")
    if s4.get("estimate") is not None:
        print(f"   paired {s4['estimate']:+.4f} ({s4['ci_low']:+.4f}, {s4['ci_high']:+.4f})"
              f"   excludes zero: {s4['excludes_zero']}")
    else:
        print(f"   {s4.get('refusal')}")
    print(f"\nwrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
