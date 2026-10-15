"""The agreement driver's refusal paths.

An agreement number computed from the wrong archive is worse than none: it looks
like a measurement of two detectors disagreeing when it is a measurement of the
harness. Job 15127's archive parsed under 1% of its judgements because the judge
prompt was never rendered through phi-4's chat template (Q32), and it sits on
disk next to the good one. These tests pin that the driver refuses it by
inspection rather than trusting the filename.
"""

from __future__ import annotations

import datetime as _dt
import importlib.util
import json
import sys

import pytest

from semintegrity.benchmark.loader import load_split
from semintegrity.schemas.enums import Verdict
from semintegrity.schemas.response import Provenance, RawResponse
from semintegrity.utils.ids import pair_id
from semintegrity.utils.paths import data_path, project_root

GOOD_HASH = "f" * 64


def _load_driver():
    path = project_root() / "scripts" / "analysis" / "detector_agreement.py"
    spec = importlib.util.spec_from_file_location("agreement_driver", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["agreement_driver"] = mod
    spec.loader.exec_module(mod)
    return mod


def _row(pair: str, label: str | None, *, tmpl=GOOD_HASH, not_real=None, err=None):
    return {
        "constraint_id": "K-C1-GEO-01", "pair_id": f"K-C1-GEO-01-{pair}",
        "probe_a": "K-C1-GEO-01-P01", "probe_b": "K-C1-GEO-01-P02",
        "presented_swapped": False, "label": label, "confidence": 0.9,
        "conflicting_span_a": None, "conflicting_span_b": None,
        "reason": "", "raw_output": "{}", "parse_error": err,
        "judge_model_id": "microsoft/phi-4", "judge_revision": "a" * 40,
        "judge_chat_template_hash": tmpl, "NOT_REAL": not_real,
    }


def _write(tmp_path, rows):
    p = tmp_path / "archive.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return p


def test_an_untemplated_archive_is_refused(tmp_path):
    """The Q32 archive: 99% parse failure, evidence about the harness."""
    mod = _load_driver()
    bad = _row("P01xP02", None, err="no JSON object found in judge output")
    del bad["judge_chat_template_hash"]
    with pytest.raises(SystemExit) as exc:
        mod.load_d3(_write(tmp_path, [bad]))
    assert "REFUSING" in str(exc.value)
    assert "Q32" in str(exc.value)


def test_a_mixed_rendering_archive_is_refused(tmp_path):
    mod = _load_driver()
    rows = [_row("P01xP02", "COMPATIBLE"),
            _row("P01xP03", "COMPATIBLE", tmpl="e" * 64)]
    with pytest.raises(SystemExit) as exc:
        mod.load_d3(_write(tmp_path, rows))
    assert "mixes 2 chat-template renderings" in str(exc.value)


def test_stub_judgements_are_refused(tmp_path):
    mod = _load_driver()
    rows = [_row("P01xP02", "UNCLEAR", not_real=True)]
    with pytest.raises(SystemExit) as exc:
        mod.load_d3(_write(tmp_path, rows))
    assert "NOT_REAL" in str(exc.value)


def test_an_empty_archive_is_refused(tmp_path):
    mod = _load_driver()
    with pytest.raises(SystemExit):
        mod.load_d3(_write(tmp_path, []))


def test_a_good_archive_maps_labels_to_verdicts(tmp_path):
    """UNCLEAR and unparseable both mean the judge reached no decision, and
    `D3Judgement.verdict` is the single definition of that."""
    mod = _load_driver()
    rows = [
        _row("P01xP02", "CONTRADICTION"),
        _row("P01xP03", "COMPATIBLE"),
        _row("P02xP03", "UNCLEAR"),
    ]
    by_constraint, prov = mod.load_d3(_write(tmp_path, rows))
    verdicts = by_constraint["K-C1-GEO-01"]
    assert verdicts["K-C1-GEO-01-P01xP02"] is Verdict.VIOLATION
    assert verdicts["K-C1-GEO-01-P01xP03"] is Verdict.SATISFIED
    assert verdicts["K-C1-GEO-01-P02xP03"] is Verdict.NOT_APPLICABLE
    assert prov["n_judgements"] == 3
    assert prov["judge_chat_template_hash"] == GOOD_HASH
    assert len(prov["archive_sha256"]) == 64


def test_the_driver_computes_no_accuracy_metric():
    """Neither detector is gold, so no accuracy machinery may be reachable.

    Checked by IMPORT rather than by grepping for the words: the report says in
    prose that precision/recall/F1/AUPRC are not computable, and a word-level
    grep would flag that refusal as the thing it forbids.
    """
    import ast

    path = project_root() / "scripts" / "analysis" / "detector_agreement.py"
    tree = ast.parse(path.read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    assert not any("detector_scores" in m for m in imported), (
        "the agreement driver must not reach the gold-scoring module"
    )
    for forbidden in ("average_precision", "confusion_matrix", "score_detector"):
        assert forbidden not in imported, f"{forbidden} needs human gold"

    called = {
        n.func.id for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    assert not {"precision", "recall", "f1", "auprc"} & called


def test_every_interval_resamples_constraints_not_pairs():
    """statistics.yaml forbids pair-level independence."""
    src = (project_root() / "scripts" / "analysis" / "detector_agreement.py").read_text()
    assert "cluster_bootstrap" in src
    assert '"unit": "constraint"' in src


# --- main() end to end ----------------------------------------------------
#
# The driver's main() is what actually runs on the cluster, and a crash there
# costs a round trip through a machine this environment may not touch. These
# exercise it against the REAL frozen test split with synthesised responses.

TEST_SPLIT = data_path("benchmark") / "test"

_needs_split = pytest.mark.skipif(
    not (TEST_SPLIT / "constraints.jsonl").is_file(),
    reason="frozen test split not built",
)


def _provenance() -> Provenance:
    return Provenance(
        model_id="Qwen/Qwen2.5-3B-Instruct", hf_revision_hash="a" * 40,
        tokenizer_hash="t", chat_template_hash="c", transformers_version="4.57.6",
        vllm_version="0.11.2", torch_version="2.9.0", cuda_version="12.8",
        gpu_model="A100", dtype="bfloat16", quantisation="none", temperature=0.0,
        top_p=1.0, top_k=-1, repetition_penalty=1.0, max_new_tokens=24,
        stop_sequences=[], seed=20250058, rendered_prompt="p", batch_size=1,
        sample_index=0, timestamp=_dt.datetime(2026, 10, 15, tzinfo=_dt.timezone.utc),
    )


def _synthesise(tmp_path, n_constraints=3):
    """A consistent model: every probe answered with its expected answer.

    D1 then returns SATISFIED on every evaluable pair, which makes the expected
    concordance determinate rather than something the test has to recompute.
    """
    _, probe_list = load_split(TEST_SPLIT)
    by_constraint: dict[str, list] = {}
    for probe in probe_list:
        by_constraint.setdefault(probe.constraint_id, []).append(probe)
    cids = sorted(by_constraint)[:n_constraints]

    raw_path = tmp_path / "raw.jsonl"
    with raw_path.open("w") as fh:
        for cid in cids:
            for probe in by_constraint[cid]:
                r = RawResponse(
                    response_id="R-" + "b" * 12, run_id="r", experiment_id="agree",
                    config_snapshot_sha256="0" * 64, constraint_id=cid,
                    probe_id=probe.probe_id, tier="primary", track="A",
                    semantic_instruction_id="trackA.v1",
                    raw_text=probe.expected_answer, timed_out=False, retry_index=0,
                    provenance=_provenance(),
                )
                fh.write(r.model_dump_json() + "\n")

    # A judge that calls every third pair a contradiction, the rest compatible.
    d3_path = tmp_path / "d3.jsonl"
    with d3_path.open("w") as fh:
        for cid in cids:
            ids = [p.probe_id for p in by_constraint[cid]]
            for i, (a, b) in enumerate(
                [(x, y) for n, x in enumerate(ids) for y in ids[n + 1:]]
            ):
                label = "CONTRADICTION" if i % 3 == 0 else "COMPATIBLE"
                fh.write(json.dumps(_row("X", label) | {
                    "constraint_id": cid, "pair_id": pair_id(a, b),
                    "probe_a": a, "probe_b": b, "label": label,
                }) + "\n")
    return raw_path, d3_path, cids


@_needs_split
def test_main_runs_end_to_end_and_writes_a_report(tmp_path, capsys):
    mod = _load_driver()
    raw_path, d3_path, cids = _synthesise(tmp_path)
    out = tmp_path / "out"

    rc = mod.main(["--raw", str(raw_path), "--d3", str(d3_path), "--out-dir", str(out)])
    assert rc == 0

    written = list(out.glob("*.agreement.json"))
    assert len(written) == 1
    report = json.loads(written[0].read_text())

    assert report["model_id"] == "Qwen/Qwen2.5-3B-Instruct"
    assert report["n_constraints"] == len(cids)
    assert report["n_pairs"] == len(cids) * 28, "C(8,2) pairs per constraint"
    assert report["human_gold"].startswith("NONE")
    assert set(report["detectors_absent"]) == {"D2", "D4"}
    assert [r["detectors"] for r in report["overall"]] == [
        "D0 vs D1", "D0 vs D3", "D1 vs D3"
    ]

    d1_d3 = next(r for r in report["overall"] if r["detectors"] == "D1 vs D3")
    assert d1_d3["n_jointly_decided"] > 0
    # D1 said SATISFIED everywhere, so agreement is exactly D3's COMPATIBLE share
    # and D1's violation rate on the joint set is 0.
    assert d1_d3["D1_violation_rate_on_joint_set"] == 0.0
    assert d1_d3["both_violation"] == 0
    assert d1_d3["D3_only_violation"] > 0
    assert d1_d3["raw_agreement"] == pytest.approx(
        d1_d3["both_satisfied"] / d1_d3["n_jointly_decided"]
    )
    assert d1_d3["agreement_clustered"]["unit"] == "constraint"

    # kappa must be WITHHELD here: D1 gave one label to everything.
    assert d1_d3["cohens_kappa"] is None
    assert "identically 0" in d1_d3["cohens_kappa_note"]

    printed = capsys.readouterr().out
    assert "D1 vs D3" in printed
    assert "kappa withheld" in printed


@_needs_split
def test_main_refuses_when_the_d3_archive_is_absent(tmp_path):
    mod = _load_driver()
    raw_path, _, _ = _synthesise(tmp_path, n_constraints=1)
    with pytest.raises(SystemExit) as exc:
        mod.main(["--raw", str(raw_path), "--d3", str(tmp_path / "nope.jsonl"),
                  "--out-dir", str(tmp_path / "out")])
    assert "no D3 archive" in str(exc.value)
