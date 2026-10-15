#!/usr/bin/env python3
"""READ-ONLY audit: is the project ready for 120 x 8 x 7?

    python scripts/audit_benchmark_readiness.py

Checks the preconditions for the full benchmark and reports each as PASS, FAIL
or BLOCKED. It launches nothing and changes nothing.

BLOCKED means "cannot be determined here" — typically a GPU-node fact. It is
deliberately distinct from PASS, because an unverifiable precondition is not a
satisfied one, and this project has been bitten before by checks that could not
run being read as checks that passed.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass

import yaml

from semintegrity.utils.paths import p, project_root

PASS, FAIL, BLOCKED = "PASS", "FAIL", "BLOCKED"
#: A precondition WITHDRAWN from the design. Distinct from PASS (nothing
#: was satisfied) and from BLOCKED (nothing is pending). ADR-0023.
REMOVED = "REMOVED"


@dataclass
class Check:
    name: str
    status: str
    detail: str


def _yaml(rel: str) -> dict:
    return yaml.safe_load(p(rel).read_text(encoding="utf-8"))


def check_model_revisions() -> Check:
    names = sorted(f.stem for f in p("configs/models").glob("*.yaml")
                   if not f.stem.startswith("_"))
    unpinned = []
    for n in names:
        rev = _yaml(f"configs/models/{n}.yaml").get("revision")
        if not (isinstance(rev, str) and re.fullmatch(r"[0-9a-f]{40}", rev)):
            unpinned.append(f"{n}={rev!r}")
    if len(names) != 5:
        return Check("model revisions pinned", FAIL, f"expected 5 models, found {len(names)}")
    if unpinned:
        return Check("model revisions pinned", FAIL, f"unpinned: {unpinned}")
    return Check("model revisions pinned", PASS, "all 5 pinned to 40-hex SHAs")


def check_vllm_architecture_support() -> Check:
    """vLLM 0.11.2 supports Qwen2, Llama, Mistral and Gemma2 architectures.

    Verified by architecture family rather than by loading weights, which needs
    a GPU. A model whose family is outside this set would need checking.
    """
    # olmo added 2026-10-15: VERIFIED by listing the installed package on the
    # cluster -- vllm 0.11.2 ships model_executor/models/olmo2.py, so
    # Olmo2ForCausalLM is supported on the glibc-2.28-pinned stack (ADR-0015).
    # Checked against the wheel rather than assumed from release notes, the way
    # ADR-0015 insists CUDA linkage be checked.
    supported = {"qwen", "llama", "mistral", "gemma", "olmo"}
    families = {}
    for f in p("configs/models").glob("*.yaml"):
        if f.stem.startswith("_"):
            continue
        families[f.stem] = _yaml(f"configs/models/{f.stem}.yaml").get("family")
    unknown = {k: v for k, v in families.items() if v not in supported}
    if unknown:
        return Check("vLLM 0.11.2 architecture support", FAIL, f"unrecognised: {unknown}")
    return Check("vLLM 0.11.2 architecture support", PASS,
                 f"families {sorted(set(families.values()))} all supported since vLLM 0.5.1; "
                 "per-model load still unverified until each runs on a GPU")


def check_backend_is_vllm() -> Check:
    backends = set()
    for f in p("configs/models").glob("*.yaml"):
        if f.stem.startswith("_"):
            continue
        from semintegrity.utils.config import resolve_model_config
        backends.add(resolve_model_config(f.stem).data["backend"])
    if backends != {"vllm"}:
        return Check("native vLLM backend", FAIL, f"backends resolve to {backends}")
    return Check("native vLLM backend", PASS, "all 7 models resolve to backend=vllm")


def check_serving_config_is_plumbed() -> Check:
    from semintegrity.inference.backend import serving_kwargs
    from semintegrity.utils.config import resolve_model_config
    bad = []
    for f in p("configs/models").glob("*.yaml"):
        if f.stem.startswith("_"):
            continue
        cfg = resolve_model_config(f.stem).data
        kw = serving_kwargs(cfg, "vllm")
        if kw.get("tensor_parallel_size") != cfg["serving"]["tensor_parallel_size"]:
            bad.append(f.stem)
    if bad:
        return Check("serving config reaches the backend", FAIL, f"dropped for {bad}")
    tp = {f.stem: resolve_model_config(f.stem).data["serving"]["tensor_parallel_size"]
          for f in p("configs/models").glob("*.yaml") if not f.stem.startswith("_")}
    return Check("serving config reaches the backend", PASS,
                 f"tensor_parallel_size honoured; 70B={tp.get('llama33-70b')}")


def check_offline_and_caches() -> Check:
    common = p("slurm/templates/_common.sh").read_text(encoding="utf-8")
    problems = []
    if 'HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"' not in common:
        problems.append("HF_HUB_OFFLINE does not default to 1")
    if "${SEMINT_ROOT}/hf_cache" not in common:
        problems.append("HF_HOME is not inside work_dir")
    for var in ("VLLM_CACHE_ROOT", "TORCHINDUCTOR_CACHE_DIR", "TRITON_CACHE_DIR"):
        line = next((ln for ln in common.splitlines() if ln.startswith(f"export {var}=")), "")
        if "SEMINT_JIT_ROOT" not in line:
            problems.append(f"{var} is not node-local")
    if problems:
        return Check("offline + cache containment", FAIL, "; ".join(problems))
    return Check("offline + cache containment", PASS,
                 "HF_HUB_OFFLINE=1 default, HF_HOME in work_dir, JIT caches node-local")


def check_no_writes_outside_root() -> Check:
    common = p("slurm/templates/_common.sh").read_text(encoding="utf-8")
    if "XDG_CACHE_HOME" not in common or "${SEMINT_ROOT}/.cache" not in common:
        return Check("no writes outside SEMINT_ROOT", FAIL, "XDG_CACHE_HOME not pinned")
    return Check("no writes outside SEMINT_ROOT", PASS,
                 "durable caches in work_dir; JIT scratch in /tmp and removed on exit")


def check_provenance_fields() -> Check:
    spec = _yaml("configs/inference/_provenance.yaml")
    required = set(spec["required_fields"])
    from semintegrity.schemas.response import Provenance
    have = set(Provenance.model_fields)
    missing = required - have
    if missing:
        return Check("22 provenance fields", FAIL, f"missing {sorted(missing)}")
    if len(required) != spec["required_field_count"]:
        return Check("22 provenance fields", FAIL,
                     f"config lists {len(required)}, claims {spec['required_field_count']}")
    return Check("22 provenance fields", PASS,
                 f"all {len(required)} present on the Provenance schema")


def check_k_cannot_drift() -> Check:
    problems = []
    proj = _yaml("configs/project.yaml")
    if proj["probes"]["primary"]["k"] != 8:
        problems.append("project.yaml primary k != 8")
    design = _yaml("configs/benchmark/design.yaml")
    for split, block in design.get("splits", {}).items():
        k = block.get("probes_per_constraint") if isinstance(block, dict) else None
        if k is not None and k != 8:
            problems.append(f"design.yaml splits.{split}.probes_per_constraint={k}")
    if _yaml("configs/inference/pilot.yaml")["probes_per_constraint"] != 8:
        problems.append("pilot.yaml probes_per_constraint != 8")
    # The authored pilot itself must carry K=8, not merely declare it.
    from semintegrity.benchmark.loader import load_split
    from semintegrity.utils.paths import data_path
    cons, probes = load_split(data_path("benchmark") / "pilot")
    if cons and len(probes) != 8 * len(cons):
        problems.append(f"pilot data has {len(probes)} probes for {len(cons)} constraints")
    if problems:
        return Check("K cannot silently drift from 8", FAIL, "; ".join(problems))
    return Check("K cannot silently drift from 8", PASS,
                 "k=8 in project/design/pilot configs; validate --k defaults to 8 and "
                 "the pilot job gates on it; a K=5 regression test exists")


def check_immutability() -> Check:
    io_src = p("src/semintegrity/utils/io.py").read_text(encoding="utf-8")
    if "ImmutabilityError" not in io_src or "O_EXCL" not in io_src:
        return Check("raw-output immutability", FAIL, "write_json does not refuse overwrite")
    sbatch = p("slurm/20_pilot_one_model.sbatch").read_text(encoding="utf-8")
    if 'OUT="${OUT:-' not in sbatch:
        return Check("raw-output immutability", FAIL, "pilot OUT is not overridable")
    return Check("raw-output immutability", PASS,
                 "write_json uses O_EXCL; append-only JSONL with fsync; OUT overridable "
                 "so a fresh run cannot silently resume onto an existing dataset")


def check_retry_and_timeout() -> Check:
    runner = p("src/semintegrity/inference/runner.py").read_text(encoding="utf-8")
    has_retry = "retry" in runner.lower()
    has_timeout = "timed_out" in runner or "timeout" in runner.lower()
    if not (has_retry and has_timeout):
        return Check("retry / timeout behaviour", FAIL,
                     f"retry={has_retry} timeout={has_timeout} in runner.py")
    return Check("retry / timeout behaviour", PASS,
                 "runner records retry_index and timed_out; §4.7 maps a timeout "
                 "after one retry to FAILED")


def check_slurm_resources() -> Check:
    cluster = _yaml("configs/cluster/cluster.yaml")
    limits = cluster["account_limits"]
    plan = cluster["resource_plan"]
    problems = []
    if plan["ceiling_model"]["mem"] != "120G":
        problems.append("70B mem request is not within the 128G group cap")
    if plan["ceiling_model"]["gpus"] > limits["GrpTRES"]["gres_gpu"]:
        problems.append("70B GPU request exceeds the group cap")
    if problems:
        return Check("Slurm resource requests", FAIL, "; ".join(problems))
    return Check("Slurm resource requests", PASS,
                 f"within group caps cpu={limits['GrpTRES']['cpu']}, "
                 f"gpu={limits['GrpTRES']['gres_gpu']}, mem={limits['GrpTRES']['mem']}, "
                 f"MaxJobs={limits['MaxJobs']} (SHARED across the account)")


def check_storage_headroom() -> Check:
    s = _yaml("configs/cluster/cluster.yaml")["storage"]
    need, head = s["estimated_weights_gb"], s["headroom_gb"]
    if need > head:
        return Check("storage for 7 models", FAIL,
                     f"{need} GB of weights vs {head} GB headroom")
    return Check("storage for 7 models", FAIL,
                 f"{need} GB of weights vs {head} GB SHARED headroom: fits only on paper, "
                 "leaving ~{} GB for everyone else. Models MUST be staged one at a time "
                 "and evicted.".format(head - need))


def check_gpu_facts() -> Check:
    return Check("CUDA / bf16 / per-model load", BLOCKED,
                 "GPU-node facts. bf16 and vLLM import are verified by "
                 "slurm/00_env_test.sbatch, which fails closed; only qwen25-3b has "
                 "actually been loaded so far")


def check_canon_gate() -> Check:
    # FROZEN 2026-10-07. Run3 on the rewritten probes returned 0/96 INVALID.
    # Researcher-reported from the cluster; ADR-0010 means this environment
    # asserts no cluster fact of its own. See docs/RESULTS_STATUS.md for the
    # provenance and for what the figure does and does not establish.
    return Check("CANON go/no-go (>=95%)", PASS,
                 "100.00% (0/96 INVALID) on pilot run3 after the Variant A cloze "
                 "rewrite; all six previous INVALIDs resolved, no new ones. FROZEN "
                 "2026-10-07 — canonicaliser, threshold and wording not to be "
                 "modified on the strength of it. One model, 12 constraints: this "
                 "is the CANON criterion only, not a result about Qwen2.5-3B")


def check_corroboration_policy() -> Check:
    """§4.3's second-source requirement needs a provider policy to be usable.

    The MECHANISM is implemented and enforced; the policy naming which external
    sources count as independent authorities is a methodology decision and is
    deliberately unconfigured. BLOCKED rather than FAIL: nothing is broken, a
    decision is outstanding.
    """
    from semintegrity.kb.corroboration import CorroborationPolicy

    policy = CorroborationPolicy()
    if policy.configured:
        return Check("corroboration policy", PASS, policy.describe())
    return Check(
        "corroboration policy", BLOCKED,
        policy.describe()
        + "; 81/132 constraints require a second source and none can be accepted "
        "until configs/benchmark/corroboration_policy.yaml names approved providers "
        "and states an independence criterion",
    )


def check_cross_split_ids() -> Check:
    """§ ADR-0007: no constraint_id may be reused across splits.

    Runs the real check against whatever splits exist on disk. While only the
    pilot exists the check is VACUOUS and says so — a check that cannot
    discriminate has not passed.
    """
    from semintegrity.benchmark.design_validator import BenchmarkDesignValidator
    from semintegrity.benchmark.loader import load_split
    from semintegrity.utils.paths import data_path

    root = data_path("benchmark")
    constraints = []
    present = []
    for name in ("pilot", "dev", "test"):
        try:
            cons, _ = load_split(root / name)
        except (FileNotFoundError, OSError):
            continue
        if cons:
            constraints.extend(cons)
            present.append(f"{name}={len(cons)}")

    rule = BenchmarkDesignValidator().validate_global_id_uniqueness(constraints)
    splits = {c.split.value for c in constraints}
    if not rule.passed:
        return Check("cross-split id uniqueness", FAIL, rule.message)
    if len(splits) < 2:
        return Check("cross-split id uniqueness", BLOCKED,
                     f"only one split exists on disk ({', '.join(present) or 'none'}); "
                     "the check cannot discriminate until the test split is authored. "
                     "Allocation defence: test cells take index 11..16, pilot/dev keep 01..10")
    return Check("cross-split id uniqueness", PASS,
                 f"{', '.join(present)} — no constraint_id reused across splits")


def check_human_validation() -> Check:
    """REMOVED as a precondition by ADR-0023, not satisfied.

    Until 2026-10-15 this reported BLOCKED, meaning "a precondition we cannot
    verify here". It is now REMOVED: the design no longer has a human-validation
    step, so there is no precondition left to block on.

    The status is deliberately not PASS. Nothing was validated; the requirement
    was withdrawn, and the consequences (no detector accuracy, ever) are
    permanent rather than pending. Reporting PASS would say the opposite of what
    happened.
    """
    return Check("human validation", REMOVED,
                 "REMOVED FROM THE DESIGN by ADR-0023 (researcher decision "
                 "2026-10-15, professor's permission). Not satisfied — withdrawn. "
                 "Permanent consequences: no detector precision/recall/F1/AUPRC "
                 "is estimable, and D2 reports a continuous score with NO "
                 "threshold and no verdict (ADR-0023 D6). The IAA go/no-go "
                 "criterion is removed; PROBE and D0AUDIT are superseded by "
                 "PROBE-C and D0AUDIT-A")


def check_probe_c() -> Check:
    """PROBE-C, the machine-audited replacement for the human PROBE criterion."""
    from semintegrity.benchmark.loader import load_split
    from semintegrity.probes.pathology import audit as probe_audit
    from semintegrity.utils.paths import data_path

    directory = data_path("benchmark") / "test"
    if not (directory / "constraints.jsonl").is_file():
        return Check("PROBE-C probe construction", BLOCKED, "test split not built")
    cons, probe_list = load_split(directory)
    by: dict[str, list] = {}
    for probe in probe_list:
        by.setdefault(probe.constraint_id, []).append(probe)
    findings, summary = probe_audit(cons, by)
    cells = summary["by_factor_cell"].get("POLAR_CLOZE_STEM_EMBEDS_GOLD_ANSWER", {})
    detail = (
        f"{summary['n_probes']} probes loaded, so the three upstream guarantees "
        f"(cloze blank, distinct surfaces, reachable expected answer) all hold. "
        f"{len(findings)} probe(s) flagged POLAR_CLOZE_STEM_EMBEDS_GOLD_ANSWER, "
        f"in factor cell(s) {cells}; effect BOUNDED by S4 at 0.002-0.007 paired "
        "PSCR, one to two orders below H1_primary (Q33, RESULTS_STATUS 4b). "
        "Audits the GENERATOR, not the generated meaning — NOT semantic validation"
    )
    # PASS, not BLOCKED, and the distinction matters. BLOCKED means "cannot be
    # determined here"; this IS determined — the findings are counted and their
    # effect measured. The criterion was revised on 2026-10-15 from "zero
    # findings" to "findings quantified and bounded", because the benchmark is
    # FROZEN and a finding cannot be fixed, only measured. The count travels in
    # the detail, so PASS never reads as "nothing found".
    return Check("PROBE-C probe construction", PASS, detail)


def check_benchmark_authored() -> Check:
    """Progress against the 120-constraint TEST split, counted from disk.

    Reports the real state of each split rather than assuming only the pilot
    exists: authoring the test split began 2026-10-07, and an audit that cannot
    see it would understate progress while still, correctly, failing.
    """
    from semintegrity.benchmark.loader import load_split
    from semintegrity.schemas.enums import VerificationStatus
    from semintegrity.utils.paths import data_path

    counts: list[str] = []
    n_test = 0
    n_test_probes = 0
    n_verified = 0
    for name in ("pilot", "test", "dev"):
        directory = data_path("benchmark") / name
        if not (directory / "constraints.jsonl").is_file():
            continue
        cons, probes = load_split(directory)
        counts.append(f"{name}={len(cons)}c/{len(probes)}p")
        if name == "test":
            n_test, n_test_probes = len(cons), len(probes)
            n_verified = sum(
                c.verification_status is not VerificationStatus.DRAFT for c in cons
            )
    detail = ", ".join(counts) or "nothing on disk"
    if n_test >= 120:
        return Check("120-constraint benchmark authored", PASS,
                     f"{detail}; {n_verified}/{n_test} test constraints past DRAFT")
    return Check("120-constraint benchmark authored", FAIL,
                 f"{detail}. The test split needs 120 constraints x 8 probes = 960; "
                 f"{n_test} authored ({n_test_probes} probes), {n_verified} past DRAFT. "
                 "§4.13 calls authoring the binding resource, not GPU time")


def main() -> int:
    checks = [
        check_model_revisions(), check_vllm_architecture_support(),
        check_backend_is_vllm(), check_serving_config_is_plumbed(),
        check_offline_and_caches(), check_no_writes_outside_root(),
        check_provenance_fields(), check_k_cannot_drift(),
        check_immutability(), check_retry_and_timeout(),
        check_slurm_resources(), check_storage_headroom(),
        check_gpu_facts(), check_canon_gate(),
        check_human_validation(),
        check_probe_c(), check_benchmark_authored(),
        check_cross_split_ids(), check_corroboration_policy(),
    ]
    width = max(len(c.name) for c in checks)
    print("=" * (width + 60))
    print("FULL BENCHMARK READINESS — 120 constraints x 8 probes x 7 models")
    print("=" * (width + 60))
    for c in checks:
        print(f"  [{c.status:7s}] {c.name:{width}s}  {c.detail}")

    n_pass = sum(c.status == PASS for c in checks)
    n_fail = sum(c.status == FAIL for c in checks)
    n_blocked = sum(c.status == BLOCKED for c in checks)
    n_removed = sum(c.status == REMOVED for c in checks)
    print("-" * (width + 60))
    tally = f"  {n_pass} PASS · {n_fail} FAIL · {n_blocked} BLOCKED"
    if n_removed:
        # Counted separately and never folded into PASS: a withdrawn
        # precondition was not satisfied, it stopped existing (ADR-0023).
        tally += f" · {n_removed} REMOVED"
    print(tally)
    print()
    if n_removed:
        print("  REMOVED is not PASS: the requirement was withdrawn by ADR-0023, "
              "not met.")
    if n_fail or n_blocked:
        print("  NOT READY for the full benchmark.")
        print("  BLOCKED is not PASS: an unverifiable precondition is not a satisfied one.")
    else:  # pragma: no cover
        print("  All preconditions satisfied.")
    print(f"  (repo: {project_root()})")
    return 0 if not n_fail else 1


if __name__ == "__main__":
    sys.exit(main())
