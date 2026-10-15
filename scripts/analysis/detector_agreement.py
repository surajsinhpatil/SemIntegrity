#!/usr/bin/env python3
"""Per-pair D0/D1/D3 concordance for one model (proposal §4.8.2).

    python scripts/analysis/detector_agreement.py \
        --raw results/raw/primary_trackA/qwen25-3b.jsonl \
        --out-dir results/analysis/agreement

"D0 vs D1 disagreement stays a reportable result (§4.8.2)." With a judge run on
disk that extends to D1 vs D3 and D0 vs D3. All detector logic lives in
`analysis.detector_agreement`; this script only loads, joins and reports.

WHY THE JOINT-COVERAGE RESTRICTION IS THE WHOLE POINT
-----------------------------------------------------
Each detector covers a different, model-dependent set of pairs. D3's coverage
over the frozen 120 ranges from 0.61 to 0.82 across the four CANON-passing
models, because coverage is the fraction of pairs where BOTH responses make a
claim -- a property of the model's abstention, not of the judge. Comparing one
detector's contradiction rate on its own coverage set with another's on a
different set conflates "they disagree" with "they were asked different
questions".

So every figure here is computed on the pairs both detectors DECIDED, and each
detector's rate is reported on that same set. Rates over a detector's own wider
coverage belong in the evaluation rows, not in an agreement report.

WHAT THIS DOES NOT DO
---------------------
* **No accuracy.** Neither detector is gold. No precision, recall, F1 or AUPRC
  -- `analysis.detector_scores` refuses those separately, for want of human
  labels.
* **No pair-level interval.** `statistics.yaml` sets
  `pair_level_independence_assumption: FORBIDDEN`, so pooled agreement and kappa
  are point estimates and every interval resamples CONSTRAINTS.
* **No D2, no D4.** D2's thresholds are uncalibrated and D4 is blocked on Q5;
  both refuse in code.
* **No promotion.** A disagreement is reported, never adjudicated. Deciding
  which detector is right where they differ needs human gold.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from semintegrity.analysis.bootstrap import cluster_bootstrap
from semintegrity.analysis.detector_agreement import (
    concordance,
    pair_table,
    per_constraint_agreement,
)
from semintegrity.benchmark.loader import load_split
from semintegrity.canonicalization.canonicaliser import CANONICALISER_VERSION, canonicalise
from semintegrity.detectors.d0.registry import default_registry
from semintegrity.detectors.d3.judge import D3Judgement
from semintegrity.inference.backend import assert_no_stub_responses
from semintegrity.inference.provenance import software_matrix
from semintegrity.kb.adapter import WikidataKB
from semintegrity.kb.cache import CacheMode, KBCache
from semintegrity.schemas.enums import Verdict
from semintegrity.schemas.response import RawResponse
from semintegrity.utils.config import load_config
from semintegrity.utils.hashing import sha256_file
from semintegrity.utils.io import read_jsonl
from semintegrity.utils.paths import data_path

#: The field recording which chat-template rendering a D3 row was judged under.
#: Rows without it predate the §4.6 fix (Q32) and are refused: they were
#: produced with phi-4 running as a completion model, at a 99% parse failure
#: rate, and they are evidence about the harness rather than about the judge.
TEMPLATE_FIELD = "judge_chat_template_hash"

#: Detector pairs to report, in a fixed order.
PAIRS: tuple[tuple[str, str], ...] = (("D0", "D1"), ("D0", "D3"), ("D1", "D3"))


def load_d3(path: Path) -> tuple[dict[str, dict[str, Verdict]], dict[str, Any]]:
    """D3 verdicts keyed by constraint, then pair, plus the archive's provenance.

    Refuses an untemplated or mixed-rendering archive rather than reporting from
    one. `D3Judgement.verdict` is a PROPERTY derived from `label`, so the row is
    rebuilt into the real dataclass instead of having its verdict re-derived
    here -- two definitions of "what UNCLEAR means for coverage" would drift.
    """
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if not rows:
        sys.exit(f"{path} holds no judgements")

    missing = sum(1 for r in rows if not r.get(TEMPLATE_FIELD))
    if missing:
        sys.exit(
            f"REFUSING: {path} holds {missing} of {len(rows)} judgement(s) with no "
            f"{TEMPLATE_FIELD}. They predate the §4.6 chat-template fix (Q32), so "
            "phi-4 was run as a completion model and parsed under 1% of them. No "
            "agreement figure may be computed from that archive."
        )
    hashes = sorted({str(r[TEMPLATE_FIELD]) for r in rows})
    if len(hashes) > 1:
        sys.exit(
            f"REFUSING: {path} mixes {len(hashes)} chat-template renderings "
            f"{hashes}. Judgements rendered differently are not comparable."
        )
    stubbed = [r for r in rows if r.get("NOT_REAL")]
    if stubbed:
        sys.exit(f"REFUSING: {path} holds {len(stubbed)} NOT_REAL (stub) judgement(s)")

    by_constraint: dict[str, dict[str, Verdict]] = defaultdict(dict)
    for r in rows:
        j = D3Judgement(
            pair_id=r["pair_id"], probe_a=r["probe_a"], probe_b=r["probe_b"],
            presented_swapped=bool(r["presented_swapped"]),
            label=r.get("label"), confidence=r.get("confidence"),
            conflicting_span_a=r.get("conflicting_span_a"),
            conflicting_span_b=r.get("conflicting_span_b"),
            reason=r.get("reason", ""), raw_output=r.get("raw_output", ""),
            prompt="", judge=str(r.get("judge_model_id", "")),
            parse_error=r.get("parse_error"),
        )
        by_constraint[r["constraint_id"]][j.pair_id] = j.verdict
    provenance = {
        "archive": str(path), "archive_sha256": sha256_file(str(path)),
        "n_judgements": len(rows),
        "judge_model_id": rows[0].get("judge_model_id"),
        "judge_revision": rows[0].get("judge_revision"),
        TEMPLATE_FIELD: hashes[0],
    }
    return dict(by_constraint), provenance


def _report(rows, a: str, b: str, *, n_boot: int, ci: float, seed: int) -> dict[str, Any]:
    """Pooled concordance plus the clustered interval on raw agreement."""
    c = concordance(rows, a, b)
    _, values = per_constraint_agreement(rows, a, b)
    boot = cluster_bootstrap(values, n_boot=n_boot, ci=ci, seed=seed)
    return {
        "detectors": f"{a} vs {b}",
        "n_pairs_in_scope": c.n_pairs,
        f"n_{a}_not_asked": c.n_a_not_asked,
        f"n_{b}_not_asked": c.n_b_not_asked,
        f"n_{a}_undecided": c.n_a_undecided,
        f"n_{b}_undecided": c.n_b_undecided,
        "n_jointly_decided": c.n_joint,
        "raw_agreement": c.raw_agreement,
        "n_agree": c.n_agree,
        "both_violation": c.both_violation,
        "both_satisfied": c.both_satisfied,
        f"{a}_only_violation": c.a_only_violation,
        f"{b}_only_violation": c.b_only_violation,
        f"{a}_violation_rate_on_joint_set": c.a_violation_rate,
        f"{b}_violation_rate_on_joint_set": c.b_violation_rate,
        "cohens_kappa": c.kappa,
        "cohens_kappa_note": c.kappa_note,
        "agreement_clustered": {
            "estimate": boot.estimate, "ci_low": boot.ci_low, "ci_high": boot.ci_high,
            "n_constraints": boot.n_clusters, "n_defined": boot.n_defined,
            "method": boot.method, "unit": "constraint",
            "note": "pair-level independence is FORBIDDEN (statistics.yaml); this "
                    "interval resamples constraints, carrying each one's pairs",
        },
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", required=True, help="one model's primary JSONL")
    ap.add_argument("--d3", default=None,
                    help="that model's D3 archive; derived from --d3-dir if omitted")
    ap.add_argument("--d3-dir", default="results/detectors/d3/raw")
    ap.add_argument("--split", default="test")
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args(argv)

    assert_no_stub_responses(args.raw, context="the detector agreement report")

    conf = load_config("configs/analysis/statistics.yaml").data["confirmatory"]
    n_boot, ci, seed = int(conf["n_boot"]), float(conf["ci"]), int(conf["seed"])

    cons_list, probe_list = load_split(data_path("benchmark") / args.split)
    constraints = {c.constraint_id: c for c in cons_list}
    probes = {p.probe_id: p for p in probe_list}

    raws = [RawResponse.model_validate(r) for r in read_jsonl(args.raw)]
    if not raws:
        sys.exit(f"no responses in {args.raw}")
    model_id = raws[0].provenance.model_id

    d3_path = Path(args.d3) if args.d3 else (
        Path(args.d3_dir) / f"{model_id.replace('/', '__')}.jsonl"
    )
    if not d3_path.is_file():
        sys.exit(
            f"no D3 archive at {d3_path}. Judge this model first:\n"
            f"  MODEL=<name> sbatch --partition=gpu-short "
            "--exclude=csis.mn1,csis.cn2 --gres=gpu:1 slurm/40_d3_judge.sbatch"
        )
    d3, d3_provenance = load_d3(d3_path)

    d0_registry = default_registry()
    d0_kb, d0_status = None, "ok"
    try:
        d0_kb = WikidataKB(KBCache(data_path("wikidata_cache"), mode=CacheMode.FROZEN))
    except Exception as exc:
        d0_status = f"kb_unavailable: {type(exc).__name__}: {exc}"

    by_constraint: dict[str, list] = defaultdict(list)
    for r in raws:
        by_constraint[r.constraint_id].append(
            canonicalise(r, constraints[r.constraint_id], probes[r.probe_id])
        )

    all_rows: list = []
    for cid in sorted(by_constraint):
        all_rows.extend(
            pair_table(
                constraints[cid], by_constraint[cid],
                d0_kb=d0_kb, d0_registry=d0_registry,
                d3_verdicts=d3.get(cid, {}),
            )
        )

    overall = [_report(all_rows, a, b, n_boot=n_boot, ci=ci, seed=seed) for a, b in PAIRS]
    by_class: dict[str, list[dict[str, Any]]] = {}
    for klass in sorted({r.constraint_class for r in all_rows}):
        subset = [r for r in all_rows if r.constraint_class == klass]
        by_class[klass] = [
            _report(subset, a, b, n_boot=n_boot, ci=ci, seed=seed) for a, b in PAIRS
        ]

    report = {
        "generated_at_utc": dt.datetime.now(dt.UTC).isoformat(),
        "model_id": model_id,
        "raw_file": args.raw, "raw_sha256": sha256_file(args.raw),
        "canonicaliser_version": CANONICALISER_VERSION,
        "split": args.split,
        "n_constraints": len(by_constraint),
        "n_pairs": len(all_rows),
        "d0_status": d0_status,
        "d0_pair_domain": "ANSWER/ANSWER only; a NEGATED response names no cluster",
        "d3": d3_provenance,
        "detectors_absent": {
            "D2": "uncalibrated thresholds; needs dev-split human labels",
            "D4": "blocked on Q5/ADR-0016; exploratory, NOT a contradiction detector",
        },
        "human_gold": "NONE — no precision/recall/F1/AUPRC is computable",
        "overall": overall,
        "by_class": by_class,
        "software": software_matrix(),
    }

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    safe = model_id.replace("/", "__")
    (out_dir / f"{safe}.agreement.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )

    print(f"model      : {model_id}")
    print(f"constraints: {len(by_constraint)}   pairs: {len(all_rows)}")
    print(f"d0         : {d0_status}")
    print(f"d3 archive : {d3_path} ({d3_provenance['n_judgements']} judgements)")
    print()
    for r in overall:
        agree = r["raw_agreement"]
        k, boot = r["cohens_kappa"], r["agreement_clustered"]
        print(f"{r['detectors']:10s} joint={r['n_jointly_decided']:5d}  "
              f"agreement={agree if agree is None else f'{agree:.4f}'}  "
              f"kappa={k if k is None else f'{k:+.4f}'}")
        if k is None:
            print(f"{'':10s}   kappa withheld: {r['cohens_kappa_note']}")
        if boot["estimate"] is not None and boot["ci_low"] is not None:
            print(f"{'':10s}   clustered over {boot['n_defined']} constraints: "
                  f"{boot['estimate']:.4f} ({boot['ci_low']:.4f}, {boot['ci_high']:.4f})")
    print(f"\nwrote {out_dir / f'{safe}.agreement.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
