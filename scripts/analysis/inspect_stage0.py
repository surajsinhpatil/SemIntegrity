#!/usr/bin/env python3
"""READ-ONLY diagnostic: why did Stage 0 label each response the way it did?

    python scripts/analysis/inspect_stage0.py --raw results/raw/pilot/qwen25-3b.jsonl

The pilot's CANON go/no-go criterion (configs/inference/pilot.yaml) requires
Stage 0 to canonicalise >= 95% of valid responses. The first cluster pilot came
in at 66.7% (32/96 INVALID), which fails it. That failure has two very different
explanations and they must not be conflated:

  * the MODEL emitted something outside the constraint's closed answer space
    -- a finding about the benchmark, the prompt or the model; or
  * the CANONICALISER failed to recognise an answer that is plainly present
    -- an engineering bug.

Only the raw text, shown next to the answer space it was matched against, can
tell them apart. This script prints exactly that and changes nothing.
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
                    help="which Stage 0 label to inspect; ALL for everything")
    ap.add_argument("--max-per-constraint", type=int, default=8)
    args = ap.parse_args(argv)

    constraints = {c.constraint_id: c for c in load_split(data_path("benchmark") / args.split)[0]}
    raws = [RawResponse.model_validate(r) for r in read_jsonl(args.raw)]
    print(f"{len(raws)} responses from {args.raw}\n")

    labels: Counter[str] = Counter()
    grouped: dict[str, list[tuple[RawResponse, object]]] = defaultdict(list)
    unknown = sorted({r.constraint_id for r in raws} - set(constraints))
    if unknown:
        print(f"ERROR: {len(unknown)} constraint id(s) in this file are not in the "
              f"'{args.split}' split: {unknown[:5]}")
        print("The smoke file uses synthetic K-*-99 constraints; point --raw at a "
              "pilot run, or pass the matching --split.")
        return 2

    for r in raws:
        c = constraints[r.constraint_id]
        res = canonicalise(r, c)
        labels[res.label.value] += 1
        grouped[r.constraint_id].append((r, res))

    total = sum(labels.values())
    print("=== Stage 0 label distribution ===")
    for lab, n in labels.most_common():
        print(f"  {lab:10s} {n:4d}  {n / total:6.1%}")
    canonicalised = labels.get("ANSWER", 0) + labels.get("ABSTAIN", 0)
    rate = canonicalised / total if total else 0.0
    print(f"\n  canonicalisation rate : {rate:.1%}  (CANON go/no-go requires >= 95%)")
    print(f"  VERDICT               : {'PASS' if rate >= 0.95 else 'FAIL'}")

    want = args.label.upper()
    print(f"\n=== responses labelled {want} ===")
    for cid in sorted(grouped):
        c = constraints[cid]
        hits = [(r, res) for r, res in grouped[cid]
                if want == "ALL" or res.label.value == want]
        if not hits:
            continue
        space = getattr(c, "answer_space", None)
        aliases = getattr(c, "answer_aliases", None)
        print(f"\n--- {cid}  [{c.answer_type.value}]  gold={c.gold_answer!r}")
        print(f"    answer_space   : {space}")
        if aliases:
            print(f"    answer_aliases : {aliases}")
        for r, res in hits[: args.max_per_constraint]:
            print(f"    {r.probe_id:22s} {res.label.value:9s} raw={r.raw_text!r}")
            print(f"    {'':22s} {'':9s} why={res.note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
