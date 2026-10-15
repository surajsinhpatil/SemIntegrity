#!/usr/bin/env python3
"""Run D3 — the pairwise LLM judge — over one model's primary responses.

    python scripts/analysis/run_d3_judge.py --raw results/raw/primary_trackA/qwen25-3b.jsonl

Why this exists: `semintegrity.detectors.d3.judge` is complete and tested but has
never been executed, because nothing drove it over a split. This is that driver.
It adds no detector logic — `D3Judge` decides everything about a judgement.

THE BATCHING PROBLEM, AND WHY THIS IS A TWO-PASS SCRIPT
-------------------------------------------------------
`D3Judge.judge_pair` calls `generator.generate(prompt)` for ONE prompt at a
time. There are C(8,2)=28 pairs per constraint and 120 constraints, so 3,360
judgements per model. Driving vLLM one prompt at a time would waste almost all
of the GPU and take hours.

Rather than reimplement the judge's prompt construction (and silently drift from
it), this script runs `D3Judge` **twice** over the same seeded RNG:

1. **record** — a generator that returns a placeholder and records every prompt
   in order. This fixes the A/B randomisation and the exact prompts.
2. **batch**  — all recorded prompts go to the backend in one batched call.
3. **replay** — a FRESH `D3Judge` with the same seed re-runs, and a generator
   hands back the real completions in order.

The replay pass asserts that each prompt it is asked for is byte-identical to
the one recorded at that position. If the judge were ever non-deterministic the
assertion fires rather than silently pairing a completion with the wrong prompt.

What this script does NOT do:

* **No ensembling.** `single_shot: true` in the config; one generation per pair.
* **No set-level verdict.** `set_level_verdict_forbidden: true`.
* **No scoring against human gold.** None exists; `analysis.detector_scores`
  refuses that separately.
* **Nothing is overwritten.** Judgements are archived per model under
  `results/detectors/d3/raw/`, and an existing archive is resumed, not rebuilt.
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

from semintegrity.benchmark.loader import load_split
from semintegrity.canonicalization.canonicaliser import CANONICALISER_VERSION, canonicalise
from semintegrity.detectors.d3.judge import (
    D3Judge,
    D3Judgement,
    coverage,
    parse_failure_rate,
)
from semintegrity.inference.backend import assert_no_stub_responses, is_stub
from semintegrity.inference.provenance import software_matrix
from semintegrity.schemas.response import RawResponse
from semintegrity.utils.config import load_config
from semintegrity.utils.hashing import sha256_file, sha256_text
from semintegrity.utils.io import read_jsonl
from semintegrity.utils.paths import data_path

PLACEHOLDER = "__RECORDING_PASS__"
STUB_TEMPLATE_HASH = "stub"

#: Field recording the chat-template rendering a row was generated under.
#: Rows written before the §4.6 templating fix do not carry it, and they
#: cannot be mixed with rows that do -- see `_check_archive_rendering`.
TEMPLATE_FIELD = "judge_chat_template_hash"


class _Recorder:
    """Pass 1: capture every prompt D3Judge builds, in call order."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return PLACEHOLDER


class _Replayer:
    """Pass 2: hand back real completions, checking the prompt still matches."""

    def __init__(self, name: str, prompts: list[str], completions: list[str]) -> None:
        self.name = name
        self._prompts = prompts
        self._completions = completions
        self._i = 0

    def generate(self, prompt: str) -> str:
        i = self._i
        if i >= len(self._prompts):
            raise RuntimeError(
                f"replay asked for prompt {i} but only {len(self._prompts)} were "
                "recorded; D3Judge is not reproducing its recording pass"
            )
        if prompt != self._prompts[i]:
            raise RuntimeError(
                f"replay prompt {i} differs from the recorded one. D3Judge's A/B "
                "randomisation is not reproducing under the same seed, so a "
                "completion would be paired with the wrong prompt."
            )
        self._i += 1
        return self._completions[i]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", required=True, help="one model's primary JSONL")
    ap.add_argument("--split", default="test")
    ap.add_argument("--judge", default="primary_judge",
                    choices=["primary_judge", "reproducibility_judge"])
    ap.add_argument("--out-dir", default="results/detectors/d3/raw")
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--limit-constraints", type=int, default=None,
                    help="smoke-test on the first N constraints; NOT for reporting")
    ap.add_argument("--stub", action="store_true",
                    help="deterministic stub judge; output is FAKE and stamped NOT_REAL")
    ap.add_argument("--allow-no-slurm", action="store_true")
    ap.add_argument("--summary-only", action="store_true",
                    help="rebuild the summary from the archive; NEVER generates, "
                         "so it is safe on a login node")
    ap.add_argument("--dry-run", action="store_true",
                    help="build every prompt, generate nothing, report the workload")
    args = ap.parse_args(argv)

    if not args.stub:
        assert_no_stub_responses(args.raw, context="the D3 judge run")

    judge_file = load_config("configs/models/_judge.yaml").data
    jcfg = judge_file[args.judge]
    decoding = dict((judge_file.get("protocol") or {}).get("decoding") or {})
    dcfg = load_config("configs/detectors/d3_llm_judge.yaml").data
    prompt_template = Path(dcfg["protocol"]["prompt_file"]).read_text(encoding="utf-8")

    revision = jcfg.get("revision")
    if not args.stub and not (isinstance(revision, str) and len(revision) == 40):
        sys.exit(
            f"{args.judge} ({jcfg['model_id']}) has revision {revision!r}. §4.5 "
            "requires a pinned 40-hex SHA before any judging run: 'which judge "
            "produced this result' must be answerable. Pin it on the login node."
        )

    # §4.8.5 integrity: the judge must sit outside every evaluated family.
    if dcfg["integrity"]["judge_external_to_all_evaluated_models"]:
        import pathlib as _p

        import yaml as _y

        evaluated = {
            _y.safe_load(f.read_text()).get("family")
            for f in _p.Path("configs/models").glob("*.yaml")
            if not f.stem.startswith("_")
        }
        if jcfg.get("family") in evaluated:
            sys.exit(
                f"REFUSING: judge family {jcfg['family']!r} is also an EVALUATED "
                f"family {sorted(evaluated)}. configs/models/_judge.yaml's lineage "
                "rule is 'Different organisation is NOT the test; shared lineage is.'"
            )

    cons_list, probe_list = load_split(data_path("benchmark") / args.split)
    constraints = {c.constraint_id: c for c in cons_list}
    probes = {p.probe_id: p for p in probe_list}

    raws = [RawResponse.model_validate(r) for r in read_jsonl(args.raw)]
    if not raws:
        sys.exit(f"no responses in {args.raw}")
    model_id = raws[0].provenance.model_id
    stubbed = args.stub or is_stub(model_id)

    by_constraint: dict[str, list] = defaultdict(list)
    for r in raws:
        by_constraint[r.constraint_id].append(
            canonicalise(r, constraints[r.constraint_id], probes[r.probe_id])
        )
    cids = sorted(by_constraint)
    if args.limit_constraints:
        cids = cids[: args.limit_constraints]

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    safe = model_id.replace("/", "__")
    archive = out_dir / f"{safe}.jsonl"

    # Resume: a judging run is expensive, and a walltime kill must not mean
    # redoing 3,360 generations.
    done: set[str] = set()
    archived_hashes: set[str] = set()
    if archive.is_file():
        archived = [json.loads(line) for line in archive.read_text().splitlines() if line.strip()]
        done = {r["pair_id"] for r in archived}
        archived_hashes = {str(r.get(TEMPLATE_FIELD)) for r in archived}
        print(f"resuming: {len(done)} judgement(s) already archived in {archive}")
        _check_archive_rendering(archive, archived, allow=args.summary_only)

    pending_cids = [
        c for c in cids if not _all_done(constraints[c], by_constraint[c], done)
    ]
    print(f"model      : {model_id}")
    print(f"judge      : {jcfg['model_id']} @ {revision}")
    print(f"constraints: {len(pending_cids)} pending of {len(cids)}")

    # --- pass 1: record every prompt ---------------------------------------
    recorder = _Recorder(name=str(jcfg["model_id"]))
    judge = D3Judge(generator=recorder, prompt_template=prompt_template)
    for cid in pending_cids:
        judge.judge_all_pairs(constraints[cid], by_constraint[cid])
    prompts = recorder.prompts
    print(f"prompts    : {len(prompts)}")

    if args.dry_run:
        print("\n--dry-run: prompts built, nothing generated.")
        if prompts:
            print("\n--- first prompt (BEFORE chat templating) ---")
            print("NOTE: the judge's chat template is applied at GENERATION time,")
            print("so --dry-run cannot detect a templating fault (Q32). Only a real")
            print("generation can: use LIMIT=2 for a smoke test.")
            print(prompts[0][:800])
        return 0
    template_hash: str | None = None
    if args.summary_only:
        # Hard guarantee: no model is ever loaded on this path. Rebuilding a
        # report must never be able to start a 14B on a login node.
        print(f"--summary-only: skipping {len(prompts)} prompt(s); "
              "rebuilding the summary from the archive")
        prompts, completions = [], []
    elif not prompts:
        print("all pairs already judged; regenerating the summary from the archive")
        completions = []
    else:
        completions, template_hash = _generate(prompts, jcfg, decoding, args)
        # Appending rows rendered one way to rows rendered another would make the
        # archive a mixture no later analysis could separate.
        stale = {h for h in archived_hashes if h != template_hash}
        if stale:
            sys.exit(
                f"REFUSING TO APPEND: {archive} holds judgement(s) rendered under "
                f"chat template(s) {sorted(stale)}, but this run rendered under "
                f"{template_hash!r}. Move the old archive aside and re-judge, or "
                "the file becomes a mixture of two renderings."
            )

    # --- pass 3: replay, with the prompts verified -------------------------
    replayer = _Replayer(str(jcfg["model_id"]), prompts, completions)
    judge2 = D3Judge(generator=replayer, prompt_template=prompt_template)
    written = 0
    replay_cids = pending_cids if completions else []
    with archive.open("a", encoding="utf-8") as fh:
        for cid in replay_cids:
            for j in judge2.judge_all_pairs(constraints[cid], by_constraint[cid]):
                row: dict[str, Any] = {
                    "constraint_id": cid, "model_id": model_id,
                    "judge_model_id": jcfg["model_id"], "judge_revision": revision,
                    "canonicaliser_version": CANONICALISER_VERSION,
                    "prompt_sha256": sha256_text(j.prompt),
                    TEMPLATE_FIELD: template_hash,
                    "NOT_REAL": True if stubbed else None,
                    **{k: getattr(j, k) for k in (
                        "pair_id", "probe_a", "probe_b", "presented_swapped",
                        "label", "confidence", "conflicting_span_a",
                        "conflicting_span_b", "reason", "raw_output", "parse_error")},
                }
                fh.write(json.dumps(row, sort_keys=True) + "\n")
                written += 1

    rows = [json.loads(line) for line in archive.read_text().splitlines() if line.strip()]
    labels: dict[str, int] = defaultdict(int)
    for r in rows:
        labels[str(r["label"])] += 1
    n_pairs = sum(len(by_constraint[c]) * (len(by_constraint[c]) - 1) // 2 for c in cids)
    judgements = [_judgement_from_row(r) for r in rows]
    summary = {
        "generated_at_utc": dt.datetime.now(dt.UTC).isoformat(),
        "model_id": model_id, "raw_file": args.raw, "raw_sha256": sha256_file(args.raw),
        "judge": {"role": args.judge, "model_id": jcfg["model_id"], "revision": revision},
        "NOT_REAL": True if stubbed else None,
        "n_judgements": len(rows), "n_pairs_possible": n_pairs,
        "judge_chat_template_hashes": sorted(
            {str(r.get(TEMPLATE_FIELD)) for r in rows}
        ),
        # An EMPTY completion is a harness/serving failure, not judge
        # indecision. Job 15127 produced 0-token outputs because the prompt was
        # not rendered through phi-4's chat template, and folding those into
        # `parse_failure_rate` made a prompting defect look like a bad judge.
        "n_empty_raw_output": sum(1 for r in rows if not (r.get("raw_output") or "").strip()),
        "coverage": coverage(judgements, n_pairs) if rows else None,
        "parse_failure_rate": parse_failure_rate(judgements) if rows else None,
        "label_counts": dict(labels),
        "single_shot": dcfg["protocol"]["single_shot"],
        "set_level_verdict_forbidden": dcfg["protocol"]["set_level_verdict_forbidden"],
        "human_gold": "NONE — no precision/recall/F1/AUPRC can be computed",
        "software": software_matrix(),
    }
    (out_dir / f"{safe}.summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(f"\nwrote {written} new judgement(s) -> {archive}")
    print(f"labels: {dict(labels)}")
    print(f"coverage {summary['coverage']}  parse_failure_rate {summary['parse_failure_rate']}")
    if stubbed:
        print("\n*** STUB JUDGE — every row stamped NOT_REAL. Never report these. ***")
    return 0



def _judgement_from_row(row: dict[str, Any]) -> D3Judgement:
    """Rebuild a real D3Judgement from an archived row.

    `coverage` and `parse_failure_rate` read `j.verdict`, which is a PROPERTY
    derived from `label` — so a dict, or a class fabricated from one with
    `type("J", (), row)()`, has no `verdict` and raises. That shortcut cost job
    15127: all 2,325 judgements were generated and archived, then the summary
    crashed on the very last step. The archive was intact; only the report died.

    `prompt` is not archived (its sha256 is, and the prompt is reproducible from
    the template plus the constraint), so a placeholder is supplied here. It is
    never read by the two helpers this feeds.
    """
    return D3Judgement(
        pair_id=row["pair_id"], probe_a=row["probe_a"], probe_b=row["probe_b"],
        presented_swapped=bool(row["presented_swapped"]),
        label=row.get("label"), confidence=row.get("confidence"),
        conflicting_span_a=row.get("conflicting_span_a"),
        conflicting_span_b=row.get("conflicting_span_b"),
        reason=row.get("reason", ""), raw_output=row.get("raw_output", ""),
        prompt="", judge=str(row.get("judge_model_id", "")),
        parse_error=row.get("parse_error"),
    )


def _check_archive_rendering(
    archive: Path, rows: list[dict[str, Any]], *, allow: bool
) -> None:
    """Refuse an archive written before the §4.6 chat-template fix.

    Rows generated by the pre-fix harness carry no `judge_chat_template_hash`,
    because the judge prompt was handed to vLLM untemplated. phi-4 then ran as a
    completion model: it continued the document rather than answering, which
    produced transcript scaffolding and 0-token outputs. Those judgements are
    evidence about the harness, not about the judge, and must not be resumed
    into or reported from.

    `allow` is set for --summary-only, which generates nothing: summarising a
    known-bad archive is how you MEASURE how bad it is, so it is permitted, and
    the summary stamps the rendering it found.
    """
    unrendered = sum(1 for r in rows if not r.get(TEMPLATE_FIELD))
    if not unrendered:
        return
    message = (
        f"{archive} holds {unrendered} of {len(rows)} judgement(s) with no "
        f"{TEMPLATE_FIELD}: they were generated BEFORE the judge prompt was "
        "rendered through phi-4's own chat template (§4.6), so phi-4 was run as "
        "a completion model. Empty `raw_output` and 'no JSON object found' in "
        "that archive are harness artefacts, not judge indecision."
    )
    if allow:
        print(f"\nWARNING: {message}\n(--summary-only: summarising it anyway)\n")
        return
    sys.exit(
        f"REFUSING TO RESUME: {message}\n\n"
        f"Move it aside and re-judge from scratch:\n"
        f"  mv {archive} {archive}.untemplated-prefix\n"
        f"Or summarise it as-is with --summary-only to quantify the damage."
    )


def _all_done(constraint, responses, done: set[str]) -> bool:
    """Is every JUDGEABLE pair of this constraint already archived?

    Judgeable is the predicate D3Judge itself uses: `judge_pair` returns None
    when either response renders no claim (ABSTAIN/INVALID/AMBIGUOUS), and a
    None is never archived. An earlier version counted ALL C(n,2) pairs, so any
    constraint holding one abstention could never be marked done and was
    re-judged on every run -- 85 of 120 constraints on the first resume.
    """
    from itertools import combinations

    from semintegrity.detectors.d2.templates import render_claim
    from semintegrity.utils.ids import pair_id

    ids = [
        pair_id(a.probe_id, b.probe_id)
        for a, b in combinations(responses, 2)
        if render_claim(constraint, a) is not None
        and render_claim(constraint, b) is not None
    ]
    return bool(ids) and all(i in done for i in ids)


def _generate(
    prompts: list[str], jcfg: dict, decoding: dict, args
) -> tuple[list[str], str]:
    """One batched call to the judge backend. Returns (completions, template hash).

    THE PROMPT IS RENDERED THROUGH THE JUDGE'S OWN CHAT TEMPLATE (§4.6)
    ------------------------------------------------------------------
    phi-4 is instruction-tuned. Handing it the bare `d3_prompt.txt` text makes
    it a *completion* model: it continues the document instead of answering, so
    it invents transcript scaffolding ("- [Response]: {...}") and sometimes
    emits EOS immediately, yielding `raw_output: ''` and a
    `parse_error: "no JSON object found in judge output"` that looks like judge
    indecision but is a harness defect. Job 15127 produced both symptoms.

    §4.6 already requires this: "Each model uses its own official chat template
    while the semantic instruction is held constant, and the fully rendered
    prompt string is logged for every response." The inference runner has always
    done it via `inference.chat_template`; this path did not.

    The FROZEN prompt text is not altered. `d3_prompt.txt` goes in whole, as a
    single user turn (`prompt_frozen_before: test_evaluation` is respected to the
    byte) and only the model's own turn markers are added around it. Splitting it
    into a system turn plus a user turn WOULD change the frozen delivery, so it
    is not done here.
    """
    import os

    from semintegrity.inference.backend import make_backend
    from semintegrity.inference.chat_template import chat_template_hash

    if args.stub:
        return (
            ['{"label": "UNCLEAR", "confidence": 0.5, "reason": "stub"}'] * len(prompts),
            STUB_TEMPLATE_HASH,
        )

    if not os.environ.get("SLURM_JOB_ID") and not args.allow_no_slurm:
        sys.exit(
            "REFUSING TO RUN: no SLURM_JOB_ID. The judge is a 14B model and must "
            "go through Slurm:\n  sbatch slurm/40_d3_judge.sbatch"
        )
    serving = dict(jcfg.get("serving") or {})
    backend = make_backend(
        "vllm", model_id=jcfg["model_id"], revision=jcfg["revision"],
        dtype=jcfg.get("dtype", "bfloat16"), **serving,
    )
    # Raises if the judge has no official template; a generic substitute would
    # make this run incomparable with every other (§4.6).
    template_hash = chat_template_hash(backend.tokenizer)
    rendered = [
        backend.tokenizer.apply_chat_template(
            [{"role": "user", "content": p}], tokenize=False, add_generation_prompt=True
        )
        for p in prompts
    ]
    print(f"chat template: {template_hash} (rendered as one user turn)")

    # Decoding comes from configs/models/_judge.yaml:protocol.decoding, not from
    # literals here. The seed in particular was previously dropped, which left a
    # judging run unreproducible even though the config pinned one.
    kw: dict[str, Any] = {
        "max_new_tokens": int(decoding.get("max_new_tokens", 256)),
        "temperature": float(decoding.get("temperature", 0.0)),
        "top_p": float(decoding.get("top_p", 1.0)),
    }
    if decoding.get("seed") is not None:
        kw["seed"] = int(decoding["seed"])

    out: list[str] = []
    for i in range(0, len(rendered), args.batch_size):
        chunk = rendered[i : i + args.batch_size]
        out.extend(g.text for g in backend.generate(chunk, **kw))
        print(f"  judged {min(i + args.batch_size, len(rendered))}/{len(rendered)}", flush=True)
    return out, template_hash


if __name__ == "__main__":
    raise SystemExit(main())
