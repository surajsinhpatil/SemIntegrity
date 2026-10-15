#!/usr/bin/env python3
"""Decompose one run's Stage 0 INVALIDs into machine-decidable categories.

    python scripts/analysis/classify_invalid.py \
        --raw results/raw/primary_trackA/mistral7b-v03.jsonl --split test

Answers the question "Mistral fails CANON at 63.02% — of what?" by separating
responses that fell OUTSIDE the closed answer space (a finding about the model,
where INVALID is the correct label) from polar probes answered with an
answer-space member instead of YES/NO (the Q31 fall-through).

READ-ONLY. Recomputes Stage 0 rather than trusting stored labels, and CHANGES
NOTHING. Stage 0 and the >=95% CANON threshold are FROZEN (2026-10-07); this
script measures what the frozen rule forgoes so that it can be reported instead
of changed. It never relabels a response and never proposes a threshold.

Run it across every model: the comparison is the point. If the fall-through
categories are large for Mistral and near-zero for the other four, that is
evidence the gate is measuring the model.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from semintegrity.analysis.invalid_taxonomy import CATEGORIES, decompose
from semintegrity.benchmark.loader import load_split
from semintegrity.canonicalization.canonicaliser import CANONICALISER_VERSION
from semintegrity.schemas.response import RawResponse
from semintegrity.utils.hashing import sha256_file
from semintegrity.utils.io import read_jsonl
from semintegrity.utils.paths import data_path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", required=True)
    ap.add_argument("--split", default="test",
                    help="the split the run's constraint ids belong to")
    ap.add_argument("--out-dir", default=None,
                    help="write a JSON report here; printed to stdout regardless")
    ap.add_argument("--examples", type=int, default=0,
                    help="print up to N example replies per category")
    args = ap.parse_args(argv)

    cons_list, probe_list = load_split(data_path("benchmark") / args.split)
    constraints = {c.constraint_id: c for c in cons_list}
    probes = {p.probe_id: p for p in probe_list}

    raws = [RawResponse.model_validate(r) for r in read_jsonl(args.raw)]
    if not raws:
        sys.exit(f"no responses in {args.raw}")
    unknown = sorted({r.constraint_id for r in raws} - set(constraints))
    if unknown:
        sys.exit(
            f"{len(unknown)} constraint id(s) are not in the '{args.split}' split: "
            f"{unknown[:5]}\nA primary run needs --split test."
        )

    model_id = raws[0].provenance.model_id
    cases, summary = decompose(raws, constraints, probes)

    print(f"model        : {model_id}")
    print(f"responses    : {summary['n_responses']}")
    print(f"INVALID      : {summary['n_invalid']}  "
          f"({summary['invalid_rate']:.4f})")
    print(f"canonicalised: {1 - summary['invalid_rate']:.4f}"
          "   <- compare with the >=0.95 CANON gate")
    print()
    for cat in CATEGORIES:
        n = summary["counts"][cat]
        share = (n / summary["n_invalid"]) if summary["n_invalid"] else 0.0
        print(f"  {cat:40s} {n:5d}  {share:6.1%}")
    print()
    print(f"Q31 entity/date fall-through : {summary['n_q31_entity_date_fallthrough']:5d}  "
          f"{summary['q31_share_of_invalid'] or 0:.1%} of INVALID")
    print(f"boolean yes/no buried        : {summary['n_boolean_yesno_buried']:5d}  "
          "<- a DIFFERENT, deliberate guard; never pooled with Q31")
    print(f"outside closed space         : "
          f"{summary['n_correctly_invalid_model_error']:5d}  <- INVALID is CORRECT")
    print(f"negation marker present      : {summary['n_negation_marker_present']:5d}")
    ceiling = summary["ceiling_if_every_q31_case_were_recovered"]
    if ceiling is not None:
        verdict = "STILL FAILS" if ceiling < 0.95 else "would reach"
        print(f"\nceiling if EVERY Q31 case were recovered: {ceiling:.4f}  "
              f"<- {verdict} the >=0.95 gate")
        print("  (an UPPER BOUND, not a correction. Stage 0 stays FROZEN.)")
    if summary["n_unclassified"]:
        print(f"\n*** {summary['n_unclassified']} UNCLASSIFIED — the taxonomy is "
              "incomplete and must be extended, not ignored. ***")

    if args.examples:
        print()
        for cat in CATEGORIES:
            shown = [c for c in cases if c.category == cat][: args.examples]
            if not shown:
                continue
            print(f"--- {cat} ---")
            for c in shown:
                print(f"  {c.probe_id}  candidates={list(c.candidates)}  "
                      f"negation={c.has_negation}")
                print(f"    why: {c.note}")

    by_constraint = Counter(c.constraint_id for c in cases)
    report = {
        "generated_at_utc": dt.datetime.now(dt.UTC).isoformat(),
        "model_id": model_id, "raw_file": args.raw,
        "raw_sha256": sha256_file(args.raw),
        "split": args.split,
        "canonicaliser_version": CANONICALISER_VERSION,
        "canonicaliser_status": "FROZEN 2026-10-07 — not modified by this analysis",
        **summary,
        "most_affected_constraints": by_constraint.most_common(10),
        "cases": [
            {"probe_id": c.probe_id, "constraint_id": c.constraint_id,
             "category": c.category, "polar": c.polar,
             "candidates": list(c.candidates), "has_negation": c.has_negation,
             "note": c.note}
            for c in cases
        ],
    }
    if args.out_dir:
        out = Path(args.out_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"{model_id.replace('/', '__')}.invalid.json"
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(f"\nwrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
