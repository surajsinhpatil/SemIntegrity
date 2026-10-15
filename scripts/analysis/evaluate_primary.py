#!/usr/bin/env python3
"""Evaluate the PRIMARY run: Stage 0 + D0 + D1, metrics, and the §4.11 statistics.

    python scripts/analysis/evaluate_primary.py \
        --raw results/raw/primary_trackA/*.jsonl \
        --out-dir results/analysis/primary_trackA

One raw JSONL per model. The per-constraint rows come from
``semintegrity.analysis.evaluate.constraint_rows`` — the SAME function
``pilot_report`` calls, so there is one definition of PSCR in the project and not
two that happen to agree.

What this produces, and what it deliberately does not:

* **Per model:** Stage 0 labels with the CANON gate, per-constraint rows, the
  descriptive four-class profile, and the two pre-specified confirmatory
  contrasts, each with a cluster-bootstrap interval over constraints.
* **Across models:** paired contrasts, because every model sees the identical
  120 constraints, with BH-FDR over the model-pair family only.
* **It does not run D2, D3 or D4.** D2's checkpoint is unselected and its
  thresholds uncalibrated (both refuse in code); D3 is run by its own driver,
  ``run_d3_judge.py``, and its archive is NOT read here; D4 is blocked on
  Q5/ADR-0016. Their absence is REPORTED in the output rather than left to be
  inferred from a missing column.
* **It does not report detector precision/recall/F1/AUPRC.** Those need human
  gold, which does not exist. ``analysis.detector_scores`` refuses them.
* **It does not promote anything.** A constraint still DRAFT because §4.3 wants
  a second source is counted and named, so a reader can see how much of the
  benchmark is provisional.
* **A bootstrap interval is not a test.** "Excludes zero" is reported as exactly
  that, never as a p-value.

Refuses stub output unless ``--allow-stub``, in which case every artefact is
stamped ``NOT_REAL`` so it cannot be mistaken for a result.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from semintegrity.analysis.bootstrap import paired_cluster_bootstrap
from semintegrity.analysis.evaluate import (
    canon_threshold,
    class_profile,
    confirmatory_contrasts,
    constraint_rows,
    stage0_summary,
)
from semintegrity.benchmark.loader import load_split
from semintegrity.canonicalization.canonicaliser import CANONICALISER_VERSION
from semintegrity.detectors.d0.registry import default_registry
from semintegrity.inference.backend import assert_no_stub_responses, is_stub
from semintegrity.inference.provenance import software_matrix
from semintegrity.kb.adapter import WikidataKB
from semintegrity.kb.cache import CacheMode, KBCache
from semintegrity.schemas.response import RawResponse
from semintegrity.utils.config import load_config
from semintegrity.utils.hashing import sha256_file, sha256_obj
from semintegrity.utils.io import read_jsonl
from semintegrity.utils.paths import data_path

#: Detectors that cannot run in this phase, and why. Reported, never silently
#: omitted: a missing column and a blocked detector look identical otherwise.
DETECTOR_STATUS: dict[str, str] = {
    "D0": "RUN — symbolic, against the frozen KB snapshot",
    "D1": "RUN — exact match over canonicalised answers",
    "D2": "RUN SEPARATELY — scripts/detectors/run_d2_nli.py; scored for all 5 models "
          "(jobs 15160/15162-15165). Reports a CONTINUOUS SCORE and NO verdict "
          "(ADR-0023 D6): its threshold is WITHDRAWN, so it contributes no "
          "contradiction count here or anywhere",
    "D3": "RUN SEPARATELY — scripts/analysis/run_d3_judge.py; executed for qwen25-3b "
          "(job 15140, parse_failure_rate 0.0). This evaluator does NOT read the D3 "
          "archive: its figures are D0/D1 only",
    "D4": "RUN SEPARATELY for qwen25-3b only — scripts/analysis/run_d4.py, job 15168. "
          "Q5 RESOLVED by ADR-0024 (T=1 frozen). EXPLORATORY and NOT a "
          "contradiction detector; it contributes to no metric in this evaluator",
}


def model_of(path: Path, rows: list[dict]) -> str:
    """The model a raw file belongs to, taken from provenance, not the filename."""
    ids = {r.get("provenance", {}).get("model_id", "") for r in rows}
    ids.discard("")
    if len(ids) == 1:
        return next(iter(ids))
    if not ids:
        return f"unknown:{path.stem}"
    raise ValueError(f"{path} mixes several model_ids: {sorted(ids)}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", nargs="+", required=True, help="one JSONL per model")
    ap.add_argument("--split", default="test")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--metric", default="pscr",
                    help="constraint-level metric the contrasts are computed on")
    ap.add_argument("--allow-stub", action="store_true",
                    help="permit stub output; every artefact is stamped NOT_REAL")
    args = ap.parse_args(argv)

    stats_cfg = load_config("configs/analysis/statistics.yaml").data
    conf = stats_cfg["confirmatory"]
    n_boot, ci = int(conf["n_boot"]), float(conf["ci"])
    seed = int(conf["seed"])
    canon_gate = canon_threshold()

    raw_paths = [Path(p) for p in args.raw]
    missing = [str(p) for p in raw_paths if not p.is_file()]
    if missing:
        sys.exit(f"no such raw file(s): {missing}")

    stubbed = False
    for p in raw_paths:
        if args.allow_stub:
            stubbed = stubbed or any(
                is_stub(r.get("provenance", {}).get("model_id", "")) for r in read_jsonl(str(p))
            )
        else:
            assert_no_stub_responses(str(p), context="the primary evaluation")

    # D0 up front, so an unavailable KB is a STATUS and not silent zero coverage.
    d0_registry = default_registry()
    d0_kb, d0_status = None, "ok"
    try:
        d0_kb = WikidataKB(KBCache(data_path("wikidata_cache"), mode=CacheMode.FROZEN))
    except Exception as exc:  # pragma: no cover - depends on snapshot state
        d0_status = f"kb_unavailable: {type(exc).__name__}: {exc}"

    cons_list, probe_list = load_split(data_path("benchmark") / args.split)
    constraints = {c.constraint_id: c for c in cons_list}
    probes = {p.probe_id: p for p in probe_list}
    n_draft = sum(1 for c in cons_list if str(c.verification_status) == "DRAFT")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    per_model: dict[str, dict[str, Any]] = {}
    rows_by_model: dict[str, list[dict]] = {}
    for path in sorted(raw_paths):
        records = list(read_jsonl(str(path)))
        if not records:
            print(f"SKIP {path}: no records")
            continue
        model = model_of(path, records)
        # Two files claiming the same model_id would silently collapse into one
        # entry and empty the comparison family. For the stub backend that is
        # expected (every stub file reports the same id), so it is disambiguated
        # by filename; for a real model it is ambiguous and refused.
        if model in per_model:
            if is_stub(model):
                model = f"{model}#{path.stem}"
            else:
                sys.exit(
                    f"two raw files report model_id {model!r}: "
                    f"{per_model[model]['raw_file']} and {path}. Refusing: the two "
                    "would collapse into one entry and silently drop a model from "
                    "every comparison."
                )
        raws = [RawResponse.model_validate(r) for r in records]
        rows, labels = constraint_rows(
            raws, constraints, probes,
            d0_kb=d0_kb, d0_registry=d0_registry, d0_status=d0_status,
        )
        s0 = stage0_summary(labels, threshold=canon_gate)
        rows_by_model[model] = rows
        per_model[model] = {
            "raw_file": str(path),
            "raw_sha256": sha256_file(path),
            "n_responses": len(raws),
            "n_constraints": len(rows),
            "stage0": {
                "labels": s0.labels, "n_invalid": s0.n_invalid,
                "canonicalisation_rate": s0.rate,
                "canon_gate_threshold": s0.threshold, "canon_gate_passed": s0.passed,
            },
            "class_profile": class_profile(
                rows, metric=args.metric, n_boot=n_boot, ci=ci, seed=seed),
            "confirmatory": confirmatory_contrasts(
                rows, metric=args.metric, n_boot=n_boot, ci=ci, seed=seed),
            "incomplete_run": len(raws) != len(probe_list),
        }
        print(f"{model:40s} {len(raws):5d} responses  {len(rows):4d} constraints  "
              f"canon={s0.rate:.4f} {'PASS' if s0.passed else 'FAIL'}")

    if not per_model:
        sys.exit("no usable raw files")

    # --- cross-model paired contrasts, BH-FDR over this family only ----------
    comparisons: list[dict[str, Any]] = []
    models = sorted(rows_by_model)
    for i, a in enumerate(models):
        for b in models[i + 1:]:
            ra = {r["constraint_id"]: r[args.metric] for r in rows_by_model[a]}
            rb = {r["constraint_id"]: r[args.metric] for r in rows_by_model[b]}
            shared = sorted(set(ra) & set(rb))
            res = paired_cluster_bootstrap(
                [ra[c] for c in shared], [rb[c] for c in shared],
                n_boot=n_boot, ci=ci, seed=seed,
            )
            comparisons.append({
                "model_a": a, "model_b": b, "metric": args.metric,
                "n_shared_constraints": len(shared),
                "estimate": res.estimate, "ci_low": res.ci_low, "ci_high": res.ci_high,
                "ci_level": res.ci_level, "method": "paired cluster bootstrap over constraints",
                "n_boot": res.n_boot, "n_defined": res.n_defined,
                "excludes_zero": (
                    None if res.ci_low is None or res.ci_high is None
                    else not (res.ci_low <= 0.0 <= res.ci_high)
                ),
            })
    # BH needs p-values; a bootstrap interval does not supply one. Rather than
    # invent a p-value from an interval, the family is reported with its size and
    # the correction is applied only where a p-value genuinely exists (none yet).
    bh_note = (
        "BH-FDR is configured for the descriptive model-comparison family "
        f"(m={len(comparisons)}). It is NOT applied here because a bootstrap "
        "interval yields no p-value, and deriving one from the interval would "
        "invent a test that was not run. Apply BH once the beta-binomial "
        "secondary model supplies p-values (statistics.yaml:secondary_model)."
    )

    payload = {
        "generated_at_utc": dt.datetime.now(dt.UTC).isoformat(),
        "split": args.split,
        "metric": args.metric,
        "NOT_REAL": stubbed or None,
        "stub_warning": (
            "STUB OUTPUT — these numbers are FAKE and must never be reported"
            if stubbed else None
        ),
        "benchmark": {
            "n_constraints": len(cons_list), "n_probes": len(probe_list),
            "n_draft": n_draft,
            "draft_note": (
                f"{n_draft} of {len(cons_list)} constraints are DRAFT because §4.3 "
                "requires an independent second source and none is attached. The "
                "benchmark is structurally complete; its ground truth is "
                "provisional to that extent."
            ),
        },
        "canonicaliser_version": CANONICALISER_VERSION,
        "detector_status": DETECTOR_STATUS,
        "d0_status": d0_status,
        "d0_predicates_registered": sorted(d0_registry.names()),
        "statistics": {
            "independent_unit": stats_cfg["independent_unit"],
            "resample": conf["resample"], "n_boot": n_boot,
            "ci": ci, "ci_method": conf["ci_method"], "seed": seed,
            "confirmatory_multiplicity": conf["multiplicity"],
            "bh_fdr": bh_note,
        },
        "human_validation": "NOT PERFORMED — no annotators, no gold, no IAA. "
                            "Detector precision/recall/F1/AUPRC are therefore "
                            "unavailable and are not estimated.",
        "per_model": per_model,
        "model_comparisons": comparisons,
        "software": software_matrix(),
    }
    payload["payload_sha256"] = sha256_obj(
        {k: v for k, v in payload.items() if k != "payload_sha256"}
    )

    stats_path = out_dir / "statistics.json"
    stats_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    # --- flat per-constraint table, one row per (model, constraint) ----------
    table_path = out_dir / "per_constraint.csv"
    field_order = sorted({k for rows in rows_by_model.values() for r in rows for k in r})
    with table_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["model", *field_order])
        writer.writeheader()
        for model, rows in sorted(rows_by_model.items()):
            for r in rows:
                writer.writerow({"model": model, **r})

    # --- per-model metric summary -------------------------------------------
    summary_path = out_dir / "metrics_by_model.csv"
    with summary_path.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["model", "metric", "class", "estimate", "ci_low", "ci_high",
                         "n_clusters", "n_defined"])
        for model, block in sorted(per_model.items()):
            for row in block["class_profile"]:
                writer.writerow([model, row["metric"], row["class"], row["estimate"],
                                 row["ci_low"], row["ci_high"], row["n_clusters"],
                                 row["n_defined"]])

    manifest = {
        "generated_at_utc": payload["generated_at_utc"],
        "NOT_REAL": payload["NOT_REAL"],
        "inputs": {str(p): sha256_file(p) for p in sorted(raw_paths)},
        "benchmark_inputs": {
            str(data_path("benchmark") / args.split / name):
                sha256_file(data_path("benchmark") / args.split / name)
            for name in ("constraints.jsonl", "probes.jsonl")
        },
        "outputs": {},
        "configs": {
            "configs/analysis/statistics.yaml":
                load_config("configs/analysis/statistics.yaml").sha256,
            "configs/inference/pilot.yaml":
                load_config("configs/inference/pilot.yaml").sha256,
        },
        "canonicaliser_version": CANONICALISER_VERSION,
        "software": software_matrix(),
    }
    for p in (stats_path, table_path, summary_path):
        manifest["outputs"][str(p)] = sha256_file(p)
    (out_dir / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )

    print()
    print(f"wrote {stats_path}")
    print(f"wrote {table_path}")
    print(f"wrote {summary_path}")
    print(f"wrote {out_dir / 'MANIFEST.json'}")
    if stubbed:
        print("\n*** STUB OUTPUT — artefacts stamped NOT_REAL. Never report these. ***")
    # Print every detector whose figures are NOT in this evaluator's output, so
    # a missing column is never left to be inferred. "NOT RUN" and "RUN
    # SEPARATELY" are different claims and both need saying.
    for det, status in DETECTOR_STATUS.items():
        if status.startswith(("NOT RUN", "RUN SEPARATELY")):
            print(f"  {det}: {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
