#!/usr/bin/env python3
"""READ-ONLY diagnostic: why did Stage 0 label each response the way it did?

    python scripts/analysis/inspect_stage0.py --raw results/raw/pilot/qwen25-3b.jsonl

The pilot's CANON go/no-go criterion (configs/inference/pilot.yaml) requires
Stage 0 to canonicalise >= 95% of valid responses. The first cluster pilot came
in at 66.7% (32/96 INVALID), which fails it. That failure has two very different
explanations and they must not be conflated:

  * the MODEL emitted something outside the constraint's closed answer space
    -- a finding about the benchmark, the probes or the model; or
  * the CANONICALISER failed to recognise an answer that is plainly present
    -- an engineering bug.

Telling them apart needs three things side by side: what the probe ASKED, what
the model SAID, and the answer space it was matched AGAINST. A raw answer of
'yes' is meaningless until you know whether the probe was a yes/no question.

The factor cross-tab at the end is the fastest read: if INVALID concentrates in
one polarity or syntax cell, the cause is structural rather than random.

Changes nothing. Recomputes Stage 0 rather than trusting a stored label.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict

from semintegrity.benchmark.loader import load_split
from semintegrity.canonicalization.canonicaliser import canonicalise
from semintegrity.schemas.response import RawResponse
from semintegrity.utils.io import read_jsonl
from semintegrity.utils.paths import data_path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", required=True)
    ap.add_argument("--split", default="pilot")
    ap.add_argument("--label", default="INVALID",
                    help="Stage 0 label to inspect; ALL for everything")
    ap.add_argument("--max-per-constraint", type=int, default=8)
    args = ap.parse_args(argv)

    cons_list, probe_list = load_split(data_path("benchmark") / args.split)
    constraints = {c.constraint_id: c for c in cons_list}
    probes = {p.probe_id: p for p in probe_list}
    raws = [RawResponse.model_validate(r) for r in read_jsonl(args.raw)]
    print(f"{len(raws)} responses from {args.raw}\n")

    unknown = sorted({r.constraint_id for r in raws} - set(constraints))
    if unknown:
        print(f"ERROR: {len(unknown)} constraint id(s) are not in the '{args.split}' "
              f"split: {unknown[:5]}")
        print("The smoke file uses synthetic K-*-99 ids; point --raw at a pilot run.")
        return 2

    labels: Counter[str] = Counter()
    grouped: dict[str, list] = defaultdict(list)
    by_factor: dict[str, Counter[str]] = defaultdict(Counter)

    for r in raws:
        c = constraints[r.constraint_id]
        res = canonicalise(r, c)
        labels[res.label.value] += 1
        grouped[r.constraint_id].append((r, res))
        p = probes.get(r.probe_id)
        if p is not None:
            for factor in ("polarity", "syntax", "directionality", "register"):
                key = f"{factor}={getattr(p, factor).value}"
                by_factor[key][res.label.value] += 1
            by_factor[f"answer_type={c.answer_type.value}"][res.label.value] += 1

    total = sum(labels.values())
    print("=== Stage 0 label distribution ===")
    for lab, n in labels.most_common():
        print(f"  {lab:10s} {n:4d}  {n / total:6.1%}")
    canonicalised = labels.get("ANSWER", 0) + labels.get("ABSTAIN", 0)
    rate = canonicalised / total if total else 0.0
    print(f"\n  canonicalisation rate : {rate:.1%}  (CANON go/no-go requires >= 95%)")
    print(f"  VERDICT               : {'PASS' if rate >= 0.95 else 'FAIL'}")

    print("\n=== INVALID rate by probe factor (is the failure structural?) ===")
    print(f"  {'cell':32s} {'INVALID':>8s} {'total':>7s} {'rate':>7s}")
    for key in sorted(by_factor):
        counts = by_factor[key]
        n_inv, n_tot = counts.get("INVALID", 0), sum(counts.values())
        print(f"  {key:32s} {n_inv:8d} {n_tot:7d} {n_inv / n_tot:6.1%}")

    want = args.label.upper()
    print(f"\n=== responses labelled {want}: probe asked / model said / space ===")
    for cid in sorted(grouped):
        c = constraints[cid]
        hits = [(r, res) for r, res in grouped[cid]
                if want == "ALL" or res.label.value == want]
        if not hits:
            continue
        print(f"\n--- {cid}  [{c.answer_type.value}]  gold={c.gold_answer!r}")
        print(f"    answer_space : {c.answer_space}")
        for r, res in hits[: args.max_per_constraint]:
            p = probes.get(r.probe_id)
            asked = p.probe_text if p is not None else "<probe not found>"
            facets = (f"{p.polarity.value}/{p.syntax.value}/{p.directionality.value}"
                      if p is not None else "?")
            print(f"    {r.probe_id}  [{facets}]")
            print(f"        asked : {asked}")
            print(f"        said  : {r.raw_text!r}")
            print(f"        why   : {res.notes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
