"""CLI: Stage 0 + D1 over a pilot run, with the descriptive counts.

    python -m semintegrity.analysis.pilot_report --raw results/raw/pilot/qwen25-3b.jsonl --split pilot

Reports the reliability triad separately (§4.10) — accuracy, consistency and
abstention are never collapsed — and refuses stub output.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

from ..benchmark.loader import load_split
from ..canonicalization.canonicaliser import CANONICALISER_VERSION, canonicalise
from ..detectors.d0.registry import default_registry
from ..detectors.d1.exact_match import check_all_pairs, coverage
from ..inference.backend import assert_no_stub_responses
from ..kb.adapter import WikidataKB
from ..kb.cache import CacheMode, KBCache
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

    by_constraint = defaultdict(list)
    for r in raws:
        if r.constraint_id not in constraints:
            raise KeyError(f"response references unknown constraint {r.constraint_id}")
        if r.probe_id not in probes:
            raise KeyError(f"response references unknown probe {r.probe_id}")
        by_constraint[r.constraint_id].append(
            canonicalise(r, constraints[r.constraint_id], probes[r.probe_id])
        )

    rows, labels = [], Counter()
    for cid, canon in sorted(by_constraint.items()):
        c = constraints[cid]
        labels.update(x.label for x in canon)
        results = check_all_pairs(canon)
        evaluable = [r for r in results if r.verdict is not Verdict.NOT_APPLICABLE]
        contradictions = sum(r.is_contradiction for r in results)

        # --- D0 -------------------------------------------------------------
        # BOTH readings are computed and stored. Q22 (whether "D0" is the
        # pairwise or the set-level verdict) is awaiting the researcher, and
        # picking one here would decide it by implementation.
        d0_pair_total = d0_pair_covered = d0_pair_violations = 0
        d0_set_verdict = None
        d0_note = d0_status
        if d0_kb is not None and d0_registry.has(c.formal_predicate):
            pred = d0_registry.get(c.formal_predicate)
            usable = [x for x in canon if x.label is ResponseLabel.ANSWER]
            for x, y in combinations(usable, 2):
                r = pred.check_pair(c, x, y, d0_kb)
                d0_pair_total += 1
                d0_pair_covered += r.is_covered
                d0_pair_violations += r.verdict is Verdict.VIOLATION
            set_result = pred.check_set(c, canon, d0_kb)
            d0_set_verdict = set_result.verdict.value
            d0_note = set_result.reason or "ok"
        elif d0_kb is not None:
            d0_note = f"no predicate registered for {c.formal_predicate!r}"
        # A NEGATED response asserted "not g". It IS an answer — the model
        # committed to something — but it is factually wrong whenever g is the
        # gold answer, so it counts in the denominator of truth accuracy and
        # never in the numerator. Folding it into abstention instead would
        # flatter the model by hiding a wrong answer as a refusal.
        definite = [x for x in canon if x.label is ResponseLabel.ANSWER]
        negated = [x for x in canon if x.label is ResponseLabel.NEGATED]
        answered = definite + negated
        correct = sum(x.canonical_answer == c.gold_answer for x in definite)
        cluster = Counter(x.canonical_answer for x in definite)
        rows.append({
            "constraint_id": cid,
            "class": c.constraint_class.value,
            "domain": c.domain.value,
            "n_responses": len(canon),
            "n_answer": len(answered),
            "n_definite": len(definite),
            "n_negated": len(negated),
            "n_abstain": sum(x.label is ResponseLabel.ABSTAIN for x in canon),
            "n_pairs": len(results),
            "n_evaluable_pairs": len(evaluable),
            "n_contradictory_pairs": contradictions,
            # PSCR is UNDEFINED with no evaluable pairs — never imputed as 0 (Q6).
            "pscr": (contradictions / len(evaluable)) if evaluable else None,
            # PCS uses the DEFINITE cluster only: "not Canberra" names no cluster.
            "pcs": (max(cluster.values()) / len(canon)) if cluster else None,
            "truth_accuracy": (correct / len(answered)) if answered else None,
            "abstention_rate": sum(x.label is ResponseLabel.ABSTAIN for x in canon) / len(canon),
            "d1_coverage": coverage(results),
            # D0 coverage is a RESULT in its own right (§4.8.1,
            # configs/detectors/d0_symbolic.yaml), never a diagnostic to hide.
            # It is computed over ALL pairs of the constraint, so responses D0
            # cannot use -- including NEGATED, which supplies no definite value
            # to a symbolic predicate -- register as reduced coverage.
            "d0_pairs_considered": d0_pair_total,
            "d0_pairs_covered": d0_pair_covered,
            "d0_coverage": (d0_pair_covered / len(results)) if results else None,
            "d0_pair_violations": d0_pair_violations,
            "d0_pscr": (d0_pair_violations / d0_pair_covered) if d0_pair_covered else None,
            "d0_set_verdict": d0_set_verdict,
            "d0_note": d0_note,
        })

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
