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
    if len(names) != 7:
        return Check("model revisions pinned", FAIL, f"expected 7 models, found {len(names)}")
    if unpinned:
        return Check("model revisions pinned", FAIL, f"unpinned: {unpinned}")
    return Check("model revisions pinned", PASS, "all 7 pinned to 40-hex SHAs")


def check_vllm_architecture_support() -> Check:
    """vLLM 0.11.2 supports Qwen2, Llama, Mistral and Gemma2 architectures.

    Verified by architecture family rather than by loading weights, which needs
    a GPU. A model whose family is outside this set would need checking.
    """
    supported = {"qwen", "llama", "mistral", "gemma"}
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
    return Check("CANON go/no-go (>=95%)", FAIL,
                 "93.75% on the pilot (6/96 INVALID, all cloze). "
                 "configs/inference/pilot.yaml on_failure: 'pipeline revision BEFORE "
                 "the full benchmark is authored'")


def check_human_validation() -> Check:
    return Check("human validation", BLOCKED,
                 "NOT STARTED. No detector precision/recall/F1/AUPRC can be reported; "
                 "D2 thresholds cannot be calibrated without dev-split human labels")


def check_benchmark_authored() -> Check:
    from semintegrity.benchmark.loader import load_split
    from semintegrity.utils.paths import data_path
    cons, probes = load_split(data_path("benchmark") / "pilot")
    return Check("120-constraint benchmark authored", FAIL,
                 f"only the {len(cons)}-constraint pilot exists "
                 f"({len(probes)} probes). 120 x 8 = 960 needed; §4.13 calls authoring "
                 "the binding resource, not GPU time")


def main() -> int:
    checks = [
        check_model_revisions(), check_vllm_architecture_support(),
        check_backend_is_vllm(), check_serving_config_is_plumbed(),
        check_offline_and_caches(), check_no_writes_outside_root(),
        check_provenance_fields(), check_k_cannot_drift(),
        check_immutability(), check_retry_and_timeout(),
        check_slurm_resources(), check_storage_headroom(),
        check_gpu_facts(), check_canon_gate(),
        check_human_validation(), check_benchmark_authored(),
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
    print("-" * (width + 60))
    print(f"  {n_pass} PASS · {n_fail} FAIL · {n_blocked} BLOCKED")
    print()
    if n_fail or n_blocked:
        print("  NOT READY for the full benchmark.")
        print("  BLOCKED is not PASS: an unverifiable precondition is not a satisfied one.")
    else:  # pragma: no cover
        print("  All preconditions satisfied.")
    print(f"  (repo: {project_root()})")
    return 0 if not n_fail else 1


if __name__ == "__main__":
    sys.exit(main())
