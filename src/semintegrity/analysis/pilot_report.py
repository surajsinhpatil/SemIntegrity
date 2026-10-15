"""CLI: Stage 0 + D1 over a pilot run, with the descriptive counts.

    python -m semintegrity.analysis.pilot_report --raw results/raw/pilot/qwen25-3b.jsonl --split pilot

Reports the reliability triad separately (§4.10) — accuracy, consistency and
abstention are never collapsed — and refuses stub output.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from ..benchmark.loader import load_split
from ..canonicalization.canonicaliser import CANONICALISER_VERSION
from ..detectors.d0.registry import default_registry
from ..inference.backend import assert_no_stub_responses
from ..kb.adapter import WikidataKB
from ..kb.cache import CacheMode, KBCache
from ..schemas.enums import ResponseLabel
from ..schemas.response import RawResponse
from ..utils.io import read_jsonl
from ..utils.paths import data_path
from .evaluate import constraint_rows


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

    # --- D0: symbolic predicate evaluation against the FROZEN KB snapshot ----
    # Built up front so an unavailable KB is reported as a STATUS rather than
    # silently producing zero coverage. "D0 covered nothing" and "D0 never ran"
    # are different claims and must not look alike in the output.
    d0_registry = default_registry()
    d0_kb = None
    d0_status = "ok"
    try:
        cache = KBCache(data_path("wikidata_cache"), mode=CacheMode.FROZEN)
        d0_kb = WikidataKB(cache)
    except Exception as exc:  # pragma: no cover - depends on snapshot state
        d0_status = f"kb_unavailable: {type(exc).__name__}: {exc}"

    cons_list, probe_list = load_split(data_path("benchmark") / args.split)
    constraints = {c.constraint_id: c for c in cons_list}
    probes = {p.probe_id: p for p in probe_list}
    raws = [RawResponse.model_validate(r) for r in read_jsonl(args.raw)]
    if not raws:
        print(f"no responses in {args.raw}")
        return 2

    rows, labels = constraint_rows(
        raws, constraints, probes,
        d0_kb=d0_kb, d0_registry=d0_registry, d0_status=d0_status,
    )

    # The CANON go/no-go criterion (configs/inference/pilot.yaml) is a
    # preregistered gate, so the report states it rather than leaving it to be
    # recomputed by hand. NEGATED and ABSTAIN both count as canonicalised: the
    # first is a resolved answer, the second a first-class outcome (§4.7).
    n_total = sum(labels.values())
    n_invalid = labels.get(ResponseLabel.INVALID, 0)
    canon_rate = (n_total - n_invalid) / n_total if n_total else 0.0

    defined = [r for r in rows if r["pscr"] is not None]
    report = {
        "raw_file": args.raw,
        "n_constraints": len(rows),
        "n_responses": len(raws),
        "stage0_labels": {k.value: v for k, v in labels.items()},
        "canonicalisation_rate": canon_rate,
        "canon_gate_threshold": 0.95,
        "canon_gate_passed": canon_rate >= 0.95,
        "canonicaliser_version": CANONICALISER_VERSION,
        "d0_status": d0_status,
        "d0_predicates_registered": sorted(d0_registry.names()),
        "mean_d0_coverage": _mean(rows, "d0_coverage"),
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
    gate = "PASS" if report["canon_gate_passed"] else "FAIL"
    print(f"canonicalisation   : {report['canonicalisation_rate']:.2%}  "
          f"(CANON gate >= 95%: {gate})   canonicaliser v{CANONICALISER_VERSION}")
    print(f"constraints        : {report['n_constraints']} "
          f"({report['constraints_with_undefined_pscr']} with undefined PSCR)")
    print(f"mean PSCR (D1)     : {_fmt(report['mean_pscr_over_defined'])}")
    print(f"mean truth accuracy: {_fmt(report['mean_truth_accuracy'])}")
    print(f"mean abstention    : {_fmt(report['mean_abstention_rate'])}")
    print(f"mean D1 coverage   : {_fmt(report['mean_d1_coverage'])}")
    print(f"mean D0 coverage   : {_fmt(report['mean_d0_coverage'])}   ({report['d0_status']})")
    d0_defined = [r for r in rows if r["d0_pscr"] is not None]
    if d0_defined:
        print(f"mean PSCR (D0)     : "
              f"{sum(r['d0_pscr'] for r in d0_defined) / len(d0_defined):.3f}"
              f"   over {len(d0_defined)}/{len(rows)} constraints")
    set_verdicts = Counter(r["d0_set_verdict"] for r in rows if r["d0_set_verdict"])
    if set_verdicts:
        print(f"D0 set-level       : {dict(set_verdicts)}   (Q22: both readings stored)")

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
