"""CLI: Stage 0 + D1 over a pilot run, with the descriptive counts.

    python -m semintegrity.analysis.pilot_report --raw results/raw/pilot/qwen25-3b.jsonl --split pilot

Reports the reliability triad separately (§4.10) — accuracy, consistency and
abstention are never collapsed — and refuses stub output.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from ..benchmark.loader import load_split
from ..canonicalization.canonicaliser import canonicalise
from ..detectors.d1.exact_match import check_all_pairs, coverage
from ..inference.backend import assert_no_stub_responses
from ..schemas.enums import ResponseLabel, Verdict
from ..schemas.response import RawResponse
from ..utils.io import read_jsonl
from ..utils.paths import data_path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", required=True)
    ap.add_argument("--split", default="pilot")
    ap.add_argument("--out")
    ap.add_argument("--allow-stub", action="store_true",
                    help="permit stub output; the report is then marked NOT REAL")
    args = ap.parse_args(argv)

    if not args.allow_stub:
        assert_no_stub_responses(args.raw, context="the pilot report")

    constraints = {c.constraint_id: c for c in load_split(data_path("benchmark") / args.split)[0]}
    raws = [RawResponse.model_validate(r) for r in read_jsonl(args.raw)]
    if not raws:
        print(f"no responses in {args.raw}")
        return 2

    by_constraint = defaultdict(list)
    for r in raws:
        if r.constraint_id not in constraints:
            raise KeyError(f"response references unknown constraint {r.constraint_id}")
        by_constraint[r.constraint_id].append(canonicalise(r, constraints[r.constraint_id]))

    rows, labels = [], Counter()
    for cid, canon in sorted(by_constraint.items()):
        c = constraints[cid]
        labels.update(x.label for x in canon)
        results = check_all_pairs(canon)
        evaluable = [r for r in results if r.verdict is not Verdict.NOT_APPLICABLE]
        contradictions = sum(r.is_contradiction for r in results)
        answered = [x for x in canon if x.label is ResponseLabel.ANSWER]
        correct = sum(x.canonical_answer == c.gold_answer for x in answered)
        cluster = Counter(x.canonical_answer for x in answered)
        rows.append({
            "constraint_id": cid,
            "class": c.constraint_class.value,
            "domain": c.domain.value,
            "n_responses": len(canon),
            "n_answer": len(answered),
            "n_abstain": sum(x.label is ResponseLabel.ABSTAIN for x in canon),
            "n_pairs": len(results),
            "n_evaluable_pairs": len(evaluable),
            "n_contradictory_pairs": contradictions,
            # PSCR is UNDEFINED with no evaluable pairs — never imputed as 0 (Q6).
            "pscr": (contradictions / len(evaluable)) if evaluable else None,
            "pcs": (max(cluster.values()) / len(canon)) if cluster else None,
            "truth_accuracy": (correct / len(answered)) if answered else None,
            "abstention_rate": sum(x.label is ResponseLabel.ABSTAIN for x in canon) / len(canon),
            "d1_coverage": coverage(results),
        })

    defined = [r for r in rows if r["pscr"] is not None]
    report = {
        "raw_file": args.raw,
        "n_constraints": len(rows),
        "n_responses": len(raws),
        "stage0_labels": {k.value: v for k, v in labels.items()},
        "constraints_with_undefined_pscr": len(rows) - len(defined),
        "mean_pscr_over_defined": (sum(r["pscr"] for r in defined) / len(defined)) if defined else None,
        "mean_truth_accuracy": _mean(rows, "truth_accuracy"),
        "mean_abstention_rate": _mean(rows, "abstention_rate"),
        "mean_d1_coverage": _mean(rows, "d1_coverage"),
        "per_constraint": rows,
        "notes": [
            "PSCR is undefined where a constraint has no evaluable pairs and is reported as null, never 0 (Q6).",
            "Truth accuracy, PSCR and abstention are separate dimensions and are never collapsed (§4.10).",
            "Detector here is D1 only; D0/D2/D3/D4 are not part of the one-model pilot.",
        ],
    }

    print(f"responses          : {report['n_responses']}")
    print(f"Stage 0 labels     : {report['stage0_labels']}")
    print(f"constraints        : {report['n_constraints']} "
          f"({report['constraints_with_undefined_pscr']} with undefined PSCR)")
    print(f"mean PSCR (D1)     : {_fmt(report['mean_pscr_over_defined'])}")
    print(f"mean truth accuracy: {_fmt(report['mean_truth_accuracy'])}")
    print(f"mean abstention    : {_fmt(report['mean_abstention_rate'])}")
    print(f"mean D1 coverage   : {_fmt(report['mean_d1_coverage'])}")

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, indent=2))
        print(f"\nwritten: {args.out}")
    return 0


def _mean(rows, key):
    vals = [r[key] for r in rows if r[key] is not None]
    return sum(vals) / len(vals) if vals else None


def _fmt(x):
    return "undefined" if x is None else f"{x:.3f}"


if __name__ == "__main__":
    raise SystemExit(main())
