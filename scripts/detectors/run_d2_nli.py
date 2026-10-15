#!/usr/bin/env python3
"""Run D2 — NLI contradiction SCORING — over one model's primary responses.

    MODEL=qwen25-3b sbatch --partition=gpu-short --exclude=csis.mn1,csis.cn2 \
        --gres=gpu:1 slurm/50_d2_nli.sbatch

Scores only. **D2 produces no verdict**, because its per-class threshold was
calibrated on human-labelled development data that does not exist and will not
(ADR-0023 D6). `nli.D2Detector.check_pair` still raises
`ThresholdNotCalibrated`, this script never calls it, and nothing here applies
a threshold or counts a contradiction.

What it produces instead: a continuous contradiction probability per pair, and
**rank concordance** against the D1 and D3 partitions — does a soft semantic
signal ORDER pairs the way the symbolic rule PARTITIONS them? That is not
accuracy: neither reference is ground truth.

Why D2 is worth a GPU run at all: D0, D1 and D3 all reduce to comparing answer
slots (measured D0-vs-D1 pair agreement is 1.0000). D2 scores the full rendered
claims and is the only instrument in the stack whose mechanism is not
answer-identity, so it is the only one that can disagree for an interesting
reason. The divergences are the finding.

Nothing is overwritten; the archive is append-only and resumed.
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

from semintegrity.analysis.rank_concordance import ScoredPair, disagreement_examples, report
from semintegrity.benchmark.loader import load_split
from semintegrity.canonicalization.canonicaliser import CANONICALISER_VERSION, canonicalise
from semintegrity.detectors.d1.exact_match import check_all_pairs
from semintegrity.detectors.d2.nli import D2Detector
from semintegrity.detectors.d2.scorer import from_config
from semintegrity.detectors.d3.judge import D3Judgement
from semintegrity.inference.backend import assert_no_stub_responses
from semintegrity.inference.provenance import software_matrix
from semintegrity.schemas.enums import Verdict
from semintegrity.schemas.response import RawResponse
from semintegrity.utils.config import load_config
from semintegrity.utils.hashing import sha256_file
from semintegrity.utils.io import read_jsonl
from semintegrity.utils.paths import data_path

TEMPLATE_FIELD = "judge_chat_template_hash"


def _d3_verdicts(path: Path) -> dict[str, Verdict]:
    """D3's verdicts by pair id, refusing a pre-Q32 archive."""
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    missing = sum(1 for r in rows if not r.get(TEMPLATE_FIELD))
    if missing:
        sys.exit(
            f"REFUSING: {path} holds {missing} judgement(s) with no {TEMPLATE_FIELD} "
            "— they predate the §4.6 chat-template fix (Q32) and parsed under 1%"
        )
    out: dict[str, Verdict] = {}
    for r in rows:
        j = D3Judgement(
            pair_id=r["pair_id"], probe_a=r["probe_a"], probe_b=r["probe_b"],
            presented_swapped=bool(r["presented_swapped"]), label=r.get("label"),
            confidence=r.get("confidence"), conflicting_span_a=None,
            conflicting_span_b=None, reason="", raw_output="", prompt="",
            judge="", parse_error=r.get("parse_error"),
        )
        out[j.pair_id] = j.verdict
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", required=True)
    ap.add_argument("--split", default="test")
    ap.add_argument("--out-dir", default="results/detectors/d2/raw")
    ap.add_argument("--d3-dir", default="results/detectors/d3/raw")
    ap.add_argument("--device", default="auto")
    ap.add_argument("--limit-constraints", type=int, default=None,
                    help="smoke test; NOT for reporting")
    ap.add_argument("--dry-run", action="store_true",
                    help="build every pair, load nothing, report the workload")
    args = ap.parse_args(argv)

    assert_no_stub_responses(args.raw, context="the D2 scoring run")

    cfg = load_config("configs/detectors/d2_nli.yaml").data
    if cfg["estimand"]["produces_verdict"]:
        sys.exit("configs/detectors/d2_nli.yaml claims D2 produces a verdict; "
                 "ADR-0023 D6 says it does not. Refusing to run.")

    cons_list, probe_list = load_split(data_path("benchmark") / args.split)
    constraints = {c.constraint_id: c for c in cons_list}
    probes = {p.probe_id: p for p in probe_list}

    raws = [RawResponse.model_validate(r) for r in read_jsonl(args.raw)]
    if not raws:
        sys.exit(f"no responses in {args.raw}")
    model_id = raws[0].provenance.model_id

    by_constraint: dict[str, list] = defaultdict(list)
    for r in raws:
        by_constraint[r.constraint_id].append(
            canonicalise(r, constraints[r.constraint_id], probes[r.probe_id])
        )
    cids = sorted(by_constraint)
    if args.limit_constraints:
        cids = cids[: args.limit_constraints]

    n_pairs = sum(len(by_constraint[c]) * (len(by_constraint[c]) - 1) // 2 for c in cids)
    print(f"model      : {model_id}")
    print(f"checkpoint : {cfg['checkpoint_selection']['selected']}")
    print(f"revision   : {cfg['checkpoint_selection']['revision']}")
    print(f"constraints: {len(cids)}   pairs: {n_pairs}")
    print(f"contradiction_index: {cfg['scoring']['contradiction_index']} "
          f"({cfg['scoring']['label_order'][cfg['scoring']['contradiction_index']]})")
    if args.dry_run:
        print("\n--dry-run: pairs counted, no model loaded, nothing scored.")
        return 0

    scorer = from_config(cfg, device=args.device)
    scorer.load()                      # verifies the label order; refuses on mismatch
    print(f"loaded     : {scorer.name}\n")
    detector = D2Detector(scorer=scorer)   # NO thresholds: verdicts stay refused

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    safe = model_id.replace("/", "__")
    archive = out_dir / f"{safe}.jsonl"
    done: set[str] = set()
    if archive.is_file():
        done = {
            json.loads(line)["pair_id"]
            for line in archive.read_text().splitlines() if line.strip()
        }
        print(f"resuming: {len(done)} pair(s) already scored")

    written = 0
    with archive.open("a", encoding="utf-8") as fh:
        for n, cid in enumerate(cids, start=1):
            scores = detector.score_all_pairs(constraints[cid], by_constraint[cid])
            for s in scores:
                if s.pair_id in done:
                    continue
                fh.write(json.dumps({
                    "constraint_id": cid, "model_id": model_id,
                    "pair_id": s.pair_id, "probe_a": s.probe_a, "probe_b": s.probe_b,
                    "p_forward": s.p_forward, "p_backward": s.p_backward,
                    "contradiction_probability": s.contradiction_probability,
                    "evaluable": s.evaluable, "scorer": s.scorer,
                    "canonicaliser_version": CANONICALISER_VERSION,
                    "verdict": None,
                    "verdict_note": "D2 produces NO verdict (ADR-0023 D6)",
                }, sort_keys=True) + "\n")
                written += 1
            if n % 20 == 0 or n == len(cids):
                print(f"  scored {n}/{len(cids)} constraints", flush=True)

    rows = [json.loads(line) for line in archive.read_text().splitlines() if line.strip()]
    scored = {r["pair_id"]: r["contradiction_probability"] for r in rows}

    # --- references: D1 always, D3 when its archive exists -----------------
    refs: dict[str, list[ScoredPair]] = {}
    d1: dict[str, Verdict] = {}
    for cid in cids:
        for r in check_all_pairs(by_constraint[cid]):
            d1[r.pair_id] = r.verdict
    d3_path = Path(args.d3_dir) / f"{safe}.jsonl"
    d3 = _d3_verdicts(d3_path) if d3_path.is_file() else {}

    cons_of = {r["pair_id"]: r["constraint_id"] for r in rows}
    for name, partition in (("D1", d1), ("D3", d3)):
        if not partition:
            continue
        refs[name] = [
            ScoredPair(pair_id=pid, constraint_id=cons_of[pid], score=score,
                       reference_verdict=partition.get(pid))
            for pid, score in scored.items() if score is not None
        ]

    conc = report(refs) if refs else {"references": {}}
    summary: dict[str, Any] = {
        "generated_at_utc": dt.datetime.now(dt.UTC).isoformat(),
        "model_id": model_id, "raw_file": args.raw,
        "raw_sha256": sha256_file(args.raw),
        "checkpoint": cfg["checkpoint_selection"]["selected"],
        "revision": cfg["checkpoint_selection"]["revision"],
        "contradiction_index": cfg["scoring"]["contradiction_index"],
        "inference": cfg["scoring"]["inference"],
        "n_pairs_possible": n_pairs,
        "n_scored": sum(1 for r in rows if r["contradiction_probability"] is not None),
        "n_unscorable_no_claim": sum(1 for r in rows if not r["evaluable"]),
        "produces_verdict": False,
        "threshold": None,
        "threshold_status": "WITHDRAWN (ADR-0023 D6)",
        "human_gold": "NONE — no precision/recall/F1/AUPRC is computable",
        "rank_concordance": conc,
        "d3_archive": str(d3_path) if d3 else None,
        "software": software_matrix(),
    }
    (out_dir / f"{safe}.summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n"
    )
    if "D1" in refs:
        (out_dir / f"{safe}.divergences.json").write_text(
            json.dumps(disagreement_examples(refs["D1"], limit=25),
                       indent=2, sort_keys=True) + "\n"
        )

    print(f"\nwrote {written} new score(s) -> {archive}")
    for ref, block in sorted(conc.get("references", {}).items()):
        est = block["pooled_estimate"]
        cl = block["clustered"]
        print(f"rank concordance vs {ref}: "
              f"{'undefined' if est is None else f'{est:.4f}'}"
              f"   clustered {cl['estimate']} ({cl['ci_low']}, {cl['ci_high']})"
              f"  over {cl['n_defined']} constraints")
    print("\nD2 produced NO verdicts and NO contradiction counts, by design.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
