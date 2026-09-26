#!/usr/bin/env python3
"""READ-ONLY: compare two runs of the same probes, response by response.

    python scripts/analysis/compare_runs.py \\
        --a results/raw/pilot/qwen25-3b.jsonl \\
        --b results/raw/pilot/qwen25-3b-rerun2.jsonl

§4.6 requires that determinism be VERIFIED rather than assumed, and forbids
calling fixed-decoding output "deterministic" on the strength of the decoding
parameters alone. This measures it: exact raw-text agreement per probe, plus
agreement at the canonical-answer level, which is the weaker property the
analysis actually depends on.

It also diffs the Stage 0 labels, so "do the SAME responses fail
canonicalisation in both runs?" is answered from the data rather than by
comparing summary counts and hoping they line up.

Scope, stated because it is easy to overclaim: two runs agreeing is evidence
about these two runs. The preregistered check in
configs/inference/determinism_check.yaml is a wider design over 100 prompts,
two batch compositions and every model. This is a component of it, not a
substitute for it.
"""

from __future__ import annotations

import argparse
from collections import Counter

from semintegrity.benchmark.loader import load_split
from semintegrity.canonicalization.canonicaliser import canonicalise
from semintegrity.schemas.response import RawResponse
from semintegrity.utils.io import read_jsonl
from semintegrity.utils.paths import data_path


def _load(path: str) -> dict[str, RawResponse]:
    by_probe: dict[str, RawResponse] = {}
    for record in read_jsonl(path):
        r = RawResponse.model_validate(record)
        if r.probe_id in by_probe:
            raise ValueError(f"{path}: duplicate probe_id {r.probe_id}")
        by_probe[r.probe_id] = r
    return by_probe


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--a", required=True, help="first run (JSONL)")
    ap.add_argument("--b", required=True, help="second run (JSONL)")
    ap.add_argument("--split", default="pilot")
    ap.add_argument("--show", type=int, default=10, help="max differing probes to print")
    args = ap.parse_args(argv)

    a, b = _load(args.a), _load(args.b)
    only_a, only_b = sorted(set(a) - set(b)), sorted(set(b) - set(a))
    shared = sorted(set(a) & set(b))

    print(f"A: {len(a)} responses  {args.a}")
    print(f"B: {len(b)} responses  {args.b}")
    print(f"shared probes: {len(shared)}")
    if only_a or only_b:
        print(f"  only in A: {len(only_a)} {only_a[:5]}")
        print(f"  only in B: {len(only_b)} {only_b[:5]}")
    if not shared:
        print("nothing to compare")
        return 2

    cons_list, probe_list = load_split(data_path("benchmark") / args.split)
    constraints = {c.constraint_id: c for c in cons_list}
    probes = {p.probe_id: p for p in probe_list}

    exact = 0
    canon_same = 0
    label_same = 0
    differing: list[str] = []
    label_pairs: Counter[str] = Counter()

    for pid in shared:
        ra, rb = a[pid], b[pid]
        same_text = ra.raw_text == rb.raw_text
        exact += same_text

        c = constraints[ra.constraint_id]
        p = probes[pid]
        ca, cb = canonicalise(ra, c, p), canonicalise(rb, c, p)
        label_same += ca.label is cb.label
        canon_same += (ca.label is cb.label and ca.canonical_answer == cb.canonical_answer)
        label_pairs[f"{ca.label.value} -> {cb.label.value}"] += 1

        if not same_text and len(differing) < args.show:
            differing.append(
                f"  {pid}\n      A: {ra.raw_text!r}\n      B: {rb.raw_text!r}"
            )

    n = len(shared)
    print("\n=== agreement ===")
    print(f"  exact raw-text match      : {exact}/{n}  {exact / n:.2%}")
    print(f"  same Stage 0 label        : {label_same}/{n}  {label_same / n:.2%}")
    print(f"  same canonical answer     : {canon_same}/{n}  {canon_same / n:.2%}")

    print("\n=== Stage 0 label transitions (A -> B) ===")
    for pair, count in label_pairs.most_common():
        marker = "" if pair.split(" -> ")[0] == pair.split(" -> ")[1] else "   <-- CHANGED"
        print(f"  {pair:24s} {count:4d}{marker}")

    if differing:
        print(f"\n=== differing responses (first {len(differing)}) ===")
        print("\n".join(differing))

    print("\n=== INVALID in each run: are they the same probes? ===")
    inv_a = {pid for pid in shared
             if canonicalise(a[pid], constraints[a[pid].constraint_id],
                             probes[pid]).label.value == "INVALID"}
    inv_b = {pid for pid in shared
             if canonicalise(b[pid], constraints[b[pid].constraint_id],
                             probes[pid]).label.value == "INVALID"}
    print(f"  A: {len(inv_a)}   B: {len(inv_b)}   both: {len(inv_a & inv_b)}")
    if inv_a ^ inv_b:
        print(f"  only A: {sorted(inv_a - inv_b)}")
        print(f"  only B: {sorted(inv_b - inv_a)}")
    else:
        print("  IDENTICAL set of INVALID probes in both runs")
        for pid in sorted(inv_a):
            print(f"    {pid}  {a[pid].raw_text!r}")

    if exact == n:
        print("\nAll shared responses are byte-identical across the two runs.")
        print("Evidence about THESE runs only -- not a general determinism claim.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
