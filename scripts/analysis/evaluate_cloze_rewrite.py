#!/usr/bin/env python3
"""Evaluate a fresh pilot run against the Variant A cloze rewrite.

    python scripts/analysis/evaluate_cloze_rewrite.py \
        --raw results/raw/pilot/qwen25-3b-run3.jsonl \
        [--baseline results/raw/pilot/qwen25-3b-run2.jsonl]

Answers, in one pass, exactly the questions the rewrite was approved to settle:

* the CANON invalid count and percentage, against the threshold **read from**
  ``configs/inference/pilot.yaml`` rather than written here;
* every INVALID probe id, with the probe's factor cell and the model's reply;
* whether the six previously-INVALID responses are still INVALID;
* whether the four subject-echo cases resolve;
* whether any NEW INVALID cases appear;
* entity/date fall-through observations — INVALIDs on a polar probe whose reply
  names a member of the constraint's answer space, which is the case the
  unadopted fall-through rule would recover;
* raw-output immutability;
* whether any probe id, factor field, expected answer or formal representation
  moved.

**Read-only.** It opens the raw JSONL for reading, writes nothing, and runs no
inference. ADR-0005 makes raw outputs immutable and §4.7 forbids manual
cleaning; this script is a reader.

It changes no threshold, no canonicaliser behaviour, no template and no expected
answer. Whatever the number is, it is the observed number.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import yaml  # noqa: E402

from semintegrity.benchmark.loader import load_split  # noqa: E402
from semintegrity.canonicalization.canonicaliser import (  # noqa: E402
    canonicalise,
    normalise,
)
from semintegrity.schemas.enums import AnswerType, ResponseLabel  # noqa: E402
from semintegrity.schemas.response import RawResponse  # noqa: E402
from semintegrity.utils.io import read_jsonl  # noqa: E402

# --- what the previous runs observed (jobs 11969 / 12095) -----------------
# Recorded in docs/PROBE_REWRITE_LOG.md RW-001 and docs/Q21_polarity_mapping_spec.md.
PREVIOUS_INVALID: dict[str, str] = {
    "K-C2-SCI-01-P01": "Au",
    "K-C2-SCI-01-P04": "Au",
    "K-C2-GEO-01-P03": "Canberra",
    "K-C2-GEO-01-P06": "CANBERRA",
    "K-C1-GEO-01-P06": "Melbourne",
    "K-C4-SCI-01-P04": "Albert Einstein",
}
#: The four whose reply echoed the assertion's SUBJECT — the cases the rewrite
#: was specifically designed to remove.
ECHO_CASES = ("K-C2-SCI-01-P01", "K-C2-SCI-01-P04", "K-C2-GEO-01-P03", "K-C2-GEO-01-P06")
#: Off-target for a reason unrelated to the cue; no reason to expect a change.
GENUINE_OFF_TARGET = "K-C4-SCI-01-P04"
#: An answer-space member given to a polar probe; the strict rule discards it.
FALL_THROUGH_CASE = "K-C1-GEO-01-P06"

# --- probe-record fingerprints, pinned at the approved state --------------
FORMAL_FIELDS = (
    "constraint_id", "probe_id", "logical_form", "subject", "predicate",
    "object", "time_scope", "quantifier", "polarity", "answer_type",
)
FACTOR_FIELDS = ("syntax", "polarity", "register", "directionality", "factor_cell_index")
PINNED = {
    "formal": "c377f3df44a37f3f93c087684838191d692dbce1dbbf513c0a0315a2e6f634d3",
    "factor": "3856d4b934a970f8115eba5cee6e9caf90dad812df1b6618bebdd49d1d3307b9",
    "expected_answer": "bd4ec4a86704deff7d8042d2877d034e383ac8b4cdc403babf9d36386c5ec2d3",
    "probe_text": "593196c8692f983d06977270a328609a91597b528cd227a5c516270b66e67d87",
    # Pre-rewrite probe_text, for reference: 7b549d7ee0a6c9964305328fe4529c24...
}


def canon_threshold_pct() -> float:
    """Read the ≥95% CANON criterion from the config. Never hardcoded here."""
    cfg = yaml.safe_load((ROOT / "configs/inference/pilot.yaml").read_text())
    for gate in cfg["go_no_go"]:
        if gate["id"] == "CANON":
            m = re.search(r">=\s*(\d+(?:\.\d+)?)\s*%", gate["criterion"])
            if not m:
                raise SystemExit(f"cannot parse a threshold from: {gate['criterion']!r}")
            return float(m.group(1))
    raise SystemExit("no CANON gate in configs/inference/pilot.yaml")


def _fp_rows(rows: list[dict], fields: tuple[str, ...]) -> str:
    items = sorted(tuple(str(r[f]) for f in fields) for r in rows)
    return hashlib.sha256(json.dumps(items, sort_keys=True).encode()).hexdigest()


def _fp_pairs(rows: list[dict], field: str) -> str:
    items = sorted((r["probe_id"], r[field]) for r in rows)
    return hashlib.sha256(json.dumps(items).encode()).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", required=True, help="the fresh run's JSONL")
    ap.add_argument("--baseline", help="an earlier run's JSONL, for a response-level diff")
    ap.add_argument("--split", default="pilot")
    args = ap.parse_args()

    raw_path = Path(args.raw)
    if not raw_path.is_file():
        raise SystemExit(f"no such file: {raw_path}")

    cons_list, probe_list = load_split(ROOT / "data" / "benchmark" / args.split)
    constraints = {c.constraint_id: c for c in cons_list}
    probes = {p.probe_id: p for p in probe_list}

    raws = [RawResponse.model_validate(r) for r in read_jsonl(raw_path)]

    print("=" * 96)
    print("FRESH PILOT RUN — Variant A cloze rewrite, empirical validation")
    print("=" * 96)
    print(f"raw file : {raw_path}")
    print(f"sha256   : {sha256_file(raw_path)}")
    print(f"size     : {raw_path.stat().st_size} bytes · mode {oct(raw_path.stat().st_mode)[-3:]}")
    print(f"records  : {len(raws)}")
    if raws:
        p = raws[0].provenance
        print(f"model    : {raws[0].provenance.model_id if hasattr(p, 'model_id') else 'see provenance'}")
        print(f"run_id   : {raws[0].run_id}")

    # --- 0. shape --------------------------------------------------------
    print("\n--- 0. shape -----------------------------------------------------------")
    expect = len(probe_list)
    print(f"  responses      : {len(raws)} (expected {expect})  "
          f"{'OK' if len(raws) == expect else 'MISMATCH'}")
    dupes = [k for k, n in Counter((r.probe_id, 0) for r in raws).items() if n > 1]
    print(f"  duplicate keys : {len(dupes)}  {'OK' if not dupes else dupes[:5]}")
    unknown = [r.probe_id for r in raws if r.probe_id not in probes]
    print(f"  unknown probes : {len(unknown)}  {'OK' if not unknown else unknown[:5]}")
    if len(raws) != expect or dupes or unknown:
        print("\n  SHAPE PROBLEM — the numbers below may not mean what they appear to.")

    # --- 1. Stage 0 ------------------------------------------------------
    canon = {}
    for r in raws:
        if r.probe_id not in probes:
            continue
        canon[r.probe_id] = canonicalise(r, constraints[r.constraint_id], probes[r.probe_id])

    labels = Counter(c.label for c in canon.values())
    invalid = sorted(pid for pid, c in canon.items() if c.label is ResponseLabel.INVALID)
    total = len(canon)
    rate = 100.0 * (total - len(invalid)) / total if total else 0.0
    threshold = canon_threshold_pct()

    print("\n--- 1. Stage 0 labels --------------------------------------------------")
    for label in ResponseLabel:
        if labels.get(label):
            print(f"  {label.value:10s} {labels[label]:3d}")

    print("\n--- 2. CANON gate -----------------------------------------------------")
    print(f"  INVALID            : {len(invalid)} / {total}")
    print(f"  canonicalisation   : {rate:.2f}%  ({total - len(invalid)}/{total})")
    print(f"  threshold (config) : >= {threshold:g}%   <- read from configs/inference/pilot.yaml")
    print(f"  VERDICT            : {'PASS' if rate >= threshold else 'FAIL'}")
    print("  This is the OBSERVED figure for this run. It is not adjusted, and the")
    print("  threshold is not negotiable from here.")

    # --- 3. the INVALIDs in full -----------------------------------------
    print("\n--- 3. every INVALID response ------------------------------------------")
    if not invalid:
        print("  none")
    for pid in invalid:
        pr, c = probes[pid], constraints[probes[pid].constraint_id]
        raw = next(r for r in raws if r.probe_id == pid)
        print(f"\n  {pid}")
        print(f"    cell      : {pr.syntax.value}/{pr.polarity.value}/"
              f"{pr.register.value}/{pr.directionality.value}")
        print(f"    constraint: {c.constraint_class.value} {c.answer_type.value} "
              f"space={c.answer_space}")
        print(f"    probe     : {pr.probe_text}")
        print(f"    expected  : {pr.expected_answer!r}")
        print(f"    replied   : {raw.raw_text.strip()!r}")
        print(f"    reason    : {canon[pid].notes}")

    # --- 4. against the previous six -------------------------------------
    print("\n--- 4. the six previously-INVALID responses ----------------------------")
    resolved, persisted = [], []
    for pid, old_reply in PREVIOUS_INVALID.items():
        if pid not in canon:
            print(f"  {pid:18s} ABSENT from this run")
            continue
        now = canon[pid].label
        raw = next((r for r in raws if r.probe_id == pid), None)
        reply = raw.raw_text.strip() if raw else "<missing>"
        tag = "still INVALID" if now is ResponseLabel.INVALID else f"RESOLVED -> {now.value}"
        (persisted if now is ResponseLabel.INVALID else resolved).append(pid)
        note = ""
        if pid in ECHO_CASES:
            note = "  [echo case]"
        elif pid == GENUINE_OFF_TARGET:
            note = "  [genuine off-target; no reason to expect a change]"
        elif pid == FALL_THROUGH_CASE:
            note = "  [answer-space member on a polar probe]"
        print(f"  {pid:18s} {tag:22s} was {old_reply!r} -> now {reply!r}{note}")

    echo_now = [p for p in ECHO_CASES if canon.get(p) and canon[p].label is ResponseLabel.INVALID]
    print(f"\n  echo cases resolved      : {len(ECHO_CASES) - len(echo_now)} / {len(ECHO_CASES)}"
          + (f"   still INVALID: {echo_now}" if echo_now else ""))
    print(f"  previous six resolved    : {len(resolved)} / 6")
    print(f"  previous six persisting  : {len(persisted)} / 6"
          + (f"   {persisted}" if persisted else ""))

    # --- 5. new INVALIDs --------------------------------------------------
    new_invalid = [pid for pid in invalid if pid not in PREVIOUS_INVALID]
    print("\n--- 5. NEW INVALID responses -------------------------------------------")
    if not new_invalid:
        print("  none — no response became INVALID that was not INVALID before")
    else:
        print(f"  {len(new_invalid)} probe(s) are INVALID that were not before:")
        for pid in new_invalid:
            raw = next(r for r in raws if r.probe_id == pid)
            pr = probes[pid]
            print(f"    {pid}  [{pr.syntax.value}/{pr.polarity.value}]  "
                  f"replied {raw.raw_text.strip()!r}")
        print("  A rewrite that fixes some probes and breaks others is a net result,")
        print("  not a success. Report both halves.")

    # --- 6. entity/date fall-through -------------------------------------
    print("\n--- 6. entity/date fall-through observations ---------------------------")
    print("  The unadopted rule would let a polar probe's reply match the answer")
    print("  space when that space is disjoint from {YES, NO}. Candidates here:")
    candidates = []
    for pid in invalid:
        pr, c = probes[pid], constraints[probes[pid].constraint_id]
        if pr.expected_answer not in ("YES", "NO"):
            continue
        if c.answer_type is AnswerType.BOOLEAN:
            continue  # space IS {YES,NO}; fall-through is meaningless and unsafe
        reply = normalise(next(r for r in raws if r.probe_id == pid).raw_text)
        hits = [m for m in c.answer_space if normalise(m) in reply]
        if hits:
            candidates.append((pid, c.answer_type.value, hits))
    if not candidates:
        print("    none")
    else:
        for pid, atype, hits in candidates:
            print(f"    {pid}  [{atype}]  reply names {hits}")
        print(f"    {len(candidates)} of {len(invalid)} INVALIDs would be recovered.")
        would_be = 100.0 * (total - len(invalid) + len(candidates)) / total
        print(f"    CONDITIONAL rate under that rule: {would_be:.2f}% "
              f"(the OBSERVED figure remains {rate:.2f}%)")
    print("    Q24 is closed; the fall-through question is NOT. This is evidence")
    print("    for that decision, not a decision.")

    # --- 7. probe-record integrity ---------------------------------------
    print("\n--- 7. probe records unchanged -----------------------------------------")
    rows = [
        json.loads(line)
        for line in (ROOT / "data/benchmark/pilot/probes.jsonl").read_text().splitlines()
        if line.strip()
    ]
    got = {
        "formal": _fp_rows(rows, FORMAL_FIELDS),
        "factor": _fp_rows(rows, FACTOR_FIELDS),
        "expected_answer": _fp_pairs(rows, "expected_answer"),
        "probe_text": _fp_pairs(rows, "probe_text"),
    }
    all_ok = True
    for key, want in PINNED.items():
        ok = got[key] == want
        all_ok &= ok
        print(f"  {key:16s} {'OK  ' if ok else 'MOVED'} {got[key][:16]}"
              + ("" if ok else f"  expected {want[:16]}"))
    print(f"  probe ids        {'OK   ' if {r['probe_id'] for r in rows} == set(probes) else 'MOVED'} "
          f"{len(rows)} probes")
    if not all_ok:
        print("  A MOVED fingerprint means the benchmark changed under the run.")

    # --- 8. raw immutability ---------------------------------------------
    print("\n--- 8. raw-output immutability ----------------------------------------")
    print(f"  this script wrote nothing to {raw_path.name} (opened read-only)")
    manifest = raw_path.parent / "MANIFEST.json"
    print(f"  MANIFEST.json    : {'present' if manifest.is_file() else 'absent'}")
    sidecar = Path(str(raw_path) + ".sha256")
    if sidecar.is_file():
        recorded = sidecar.read_text().split()[0]
        live = sha256_file(raw_path)
        print(f"  recorded sha256  : {recorded[:16]}  {'MATCHES' if recorded == live else 'DRIFT'}")
    else:
        print(f"  {sidecar.name}: absent — nothing to compare against")
    if args.baseline:
        base = Path(args.baseline)
        if base.is_file():
            print(f"  baseline         : {base.name}  sha256 {sha256_file(base)[:16]}")
            base_raws = {r.probe_id: r for r in
                         (RawResponse.model_validate(x) for x in read_jsonl(base))}
            same = sum(1 for r in raws if base_raws.get(r.probe_id)
                       and base_raws[r.probe_id].raw_text == r.raw_text)
            print(f"  identical replies: {same} / {len(raws)} vs the baseline")
            print("    A rewritten probe SHOULD differ; an untouched one should not.")
            touched = {p.probe_id for p in probe_list
                       if p.syntax.value == "cloze" and p.expected_answer in ("YES", "NO")}
            moved_untouched = [
                r.probe_id for r in raws
                if r.probe_id not in touched and base_raws.get(r.probe_id)
                and base_raws[r.probe_id].raw_text != r.raw_text
            ]
            print(f"  untouched probes that changed reply: {len(moved_untouched)}"
                  + (f"  {moved_untouched[:8]}" if moved_untouched else "  <- good"))
        else:
            print(f"  baseline         : {base} not found")

    print("\n" + "=" * 96)
    print(f"OBSERVED: {len(invalid)}/{total} INVALID = {rate:.2f}% canonicalisation, "
          f"gate >= {threshold:g}% -> {'PASS' if rate >= threshold else 'FAIL'}")
    print("=" * 96)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
