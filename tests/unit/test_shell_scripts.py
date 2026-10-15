"""Every shell script and Slurm job must parse.

A syntax error in an sbatch file is not caught until the scheduler has already
granted an allocation, so it costs GPU time to discover. `bash -n` parses
without executing, which makes that a unit test instead.
"""

import re
import shutil
import subprocess

import pytest

from semintegrity.utils.paths import p, project_root

BASH = shutil.which("bash")


def _scripts():
    root = project_root()
    found = sorted(
        {
            path
            for pattern in ("slurm/**/*.sbatch", "slurm/**/*.sh", "scripts/**/*.sh")
            for path in root.glob(pattern)
            if path.is_file()
        }
    )
    return [f.relative_to(root) for f in found]


@pytest.mark.skipif(BASH is None, reason="bash not available")
@pytest.mark.parametrize("script", _scripts(), ids=str)
def test_shell_script_parses(script):
    result = subprocess.run(
        [BASH, "-n", str(script)], cwd=project_root(), capture_output=True, text=True
    )
    assert result.returncode == 0, f"{script} has a syntax error:\n{result.stderr}"


def test_some_scripts_were_actually_found():
    assert len(_scripts()) >= 8, "the glob found too few scripts to be checking anything"


@pytest.mark.skipif(BASH is None, reason="bash not available")
def test_sbatch_jobs_do_not_hard_code_a_partition():
    """Partition names are cluster-specific and must be passed at submission.

    A guessed `#SBATCH --partition=` produces a job that queues forever or is
    rejected, so the templates deliberately carry none.
    """
    offenders = []
    for job in p("slurm").glob("*.sbatch"):
        for line in job.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("#SBATCH") and "--partition" in stripped:
                offenders.append(f"{job.name}: {stripped}")
    assert not offenders, f"partition hard-coded in a job script: {offenders}"


@pytest.mark.parametrize("script", _scripts(), ids=str)
def test_no_head_on_a_pipe_under_pipefail(script):
    """`cmd | head -n` kills the writer with SIGPIPE, which pipefail makes fatal.

    Regression test for a real failure: on 2026-09-25 the first live run of
    `scripts/cluster/fix_torch_cuda.sh` exited **141** (128 + SIGPIPE) at the
    glibc check, because of

        GLIBC="$(ldd --version | head -1 | grep -oE '[0-9]+\\.[0-9]+$')"

    `head -1` closes the pipe after one line, `ldd` dies writing the second, and
    `set -o pipefail` promotes that to the script's exit status. Nothing was
    installed and the failure looked like a glibc problem rather than a quoting
    one. Read the output into a variable and slice it in the shell instead.

    Scoped to scripts where pipefail is actually in effect; elsewhere `| head` is
    fine. An sbatch file that sources `_common.sh` inherits pipefail from it, so
    checking only for a literal `pipefail` in the file would skip precisely the
    jobs where a 141 costs a GPU allocation.
    """
    text = p(script).read_text(encoding="utf-8")
    inherits = "_common.sh" in text
    if "pipefail" not in text and not inherits:
        pytest.skip(f"{script} does not set or inherit pipefail")

    offenders = [
        (n, line.strip())
        for n, line in enumerate(text.splitlines(), start=1)
        if re.search(r"\|\s*head\b", line) and not line.lstrip().startswith("#")
    ]
    assert not offenders, (
        f"{script} pipes into `head` while pipefail is set; the writer can die of "
        "SIGPIPE and abort the script (exit 141):\n"
        + "\n".join(f"  line {n}: {line}" for n, line in offenders)
    )


def test_durable_caches_stay_in_the_work_dir():
    """Shared lab account: durable artefacts may not be written outside work_dir.

    configs/cluster/cluster.yaml:shared_account_rules is explicit, and the tools
    default the other way -- job 11968 wrote a cache to $HOME before these were
    pinned.
    """
    common = p("slurm/templates/_common.sh").read_text(encoding="utf-8")
    for var in ("HF_HOME", "XDG_CACHE_HOME"):
        assert f"export {var}=" in common, f"_common.sh does not pin {var}"
        line = next(ln for ln in common.splitlines() if ln.startswith(f"export {var}="))
        assert "${SEMINT_ROOT}" in line, (
            f"{var} is not rooted at SEMINT_ROOT, so it can escape work_dir: {line}"
        )


def test_jit_caches_are_node_local_and_never_on_nfs():
    """JIT caches must NOT live on NFS, and this one is written in blood.

    Triton and Inductor cache compiled shared objects -- e.g.
    triton/<hash>/cuda_utils.cpython-311-x86_64-linux-gnu.so -- which are
    dlopen'd during CUDA initialisation. NFS gives no reliable locking and
    different mmap semantics, and the result is not a clean error.

    Pointing these at ${SEMINT_ROOT}/.cache cost FIVE failed GPU jobs on
    2026-09-26 (12081, 12089, 12090, 12092, 12093). The signature was exact: the
    runs that CREATED the cache succeeded and every run that READ it died with
    SIGSEGV inside EngineCore before parallel_state init, on four different
    nodes, with no Python-level traceback. Moving the caches aside fixed it on
    the first attempt.

    An earlier version of this very test asserted the OPPOSITE -- that all five
    variables be rooted at SEMINT_ROOT -- and so locked the bug in place. That is
    why this one names the mechanism rather than just the paths.
    """
    common = p("slurm/templates/_common.sh").read_text(encoding="utf-8")
    for var in ("VLLM_CACHE_ROOT", "TORCHINDUCTOR_CACHE_DIR", "TRITON_CACHE_DIR"):
        assert f"export {var}=" in common, f"_common.sh does not pin {var}"
        line = next(ln for ln in common.splitlines() if ln.startswith(f"export {var}="))
        assert "SEMINT_JIT_ROOT" in line, (
            f"{var} must live under SEMINT_JIT_ROOT (node-local), got: {line}"
        )
        assert "${SEMINT_ROOT}" not in line, (
            f"{var} is on NFS. This caused five SIGSEGV job failures: {line}"
        )
    jit = next(ln for ln in common.splitlines() if ln.startswith("SEMINT_JIT_ROOT="))
    assert "SLURM_TMPDIR" in jit and "/tmp" in jit, (
        f"SEMINT_JIT_ROOT must resolve to node-local scratch, got: {jit}"
    )
    assert "${SEMINT_ROOT}" not in jit, f"SEMINT_JIT_ROOT is on NFS: {jit}"
    assert "rm -rf" in common and "semint-jit-" in common, (
        "per-job JIT scratch is never cleaned up; /tmp will fill on shared nodes"
    )


# --- referenced script paths must EXIST (2026-10-14) ----------------------
# docs/CLUSTER_RUNBOOK.md told the researcher to run
# `bash scripts/env/cache_weights.sh --model <name>`. That path does not exist
# (scripts/env/ holds only .gitkeep) and the flag form was wrong too: the real
# script is scripts/models/cache_weights.sh with a POSITIONAL short name.
# Following the runbook staged nothing, and jobs 13032/13033 spent 8 h queued
# and two slots to discover it at preflight. A runbook command that cannot run
# is worse than no runbook, so the paths are now checked.
_SCRIPT_REF = re.compile(r"(?:bash|python3?)\s+((?:scripts|slurm)/[\w./-]+\.(?:sh|py|sbatch))")
_ROOT = project_root()


def _referenced_scripts(text: str) -> set[str]:
    return set(_SCRIPT_REF.findall(text))


def test_every_script_path_referenced_in_the_runbook_exists():
    runbook = _ROOT / "docs" / "CLUSTER_RUNBOOK.md"
    missing = sorted(
        ref for ref in _referenced_scripts(runbook.read_text())
        if not (_ROOT / ref).is_file()
    )
    assert not missing, (
        f"docs/CLUSTER_RUNBOOK.md tells the researcher to run script(s) that do "
        f"not exist: {missing}. A command in the runbook is executed on a cluster "
        f"where a wrong path costs a queue slot."
    )


def test_every_script_path_referenced_in_an_sbatch_file_exists():
    missing: dict[str, list[str]] = {}
    for sbatch in sorted((_ROOT / "slurm").glob("*.sbatch")):
        absent = sorted(
            ref for ref in _referenced_scripts(sbatch.read_text())
            if not (_ROOT / ref).is_file()
        )
        if absent:
            missing[sbatch.name] = absent
    assert not missing, f"sbatch scripts invoke non-existent paths: {missing}"


def test_the_staging_script_is_where_the_abort_message_says_it_is():
    """verify_cache.py's failure message names the recovery command."""
    named = (_ROOT / "scripts" / "models" / "verify_cache.py").read_text()
    assert "scripts/models/cache_weights.sh" in named
    assert (_ROOT / "scripts" / "models" / "cache_weights.sh").is_file()


def test_staging_verifies_itself_so_success_is_a_checked_claim():
    """A half-populated cache must fail on the login node, not in a GPU job."""
    staging = (_ROOT / "scripts" / "models" / "cache_weights.sh").read_text()
    assert "verify_cache.py" in staging, (
        "cache_weights.sh must end by running the offline verifier; otherwise it "
        "can report success having fetched only metadata — which is how "
        "qwen25-7b reached a compute node with 0 weight shards."
    )


def test_staging_checks_free_space_before_downloading():
    staging = (_ROOT / "scripts" / "models" / "cache_weights.sh").read_text()
    assert "weights_bf16_gb_estimate" in staging
    download_at = staging.index("snapshot_download(")
    space_at = staging.index("AVAIL_GB")
    assert space_at < download_at, "the space check must run BEFORE the download"


def test_space_preflight_consults_the_user_quota_not_just_df():
    """df sees the filesystem; the binding limit here is the per-user quota.

    Observed 2026-10-14: df reported 15T free on /nfs_home while `quota` showed
    955G of a 1000G hard limit. A df-only check waves through a download that
    cannot complete, which is how qwen25-7b/14b reached a compute node with 0
    weight shards.
    """
    staging = (_ROOT / "scripts" / "models" / "cache_weights.sh").read_text()
    assert "quota" in staging, "the preflight must consult the user quota"
    assert "QUOTA_GB" in staging and "DF_GB" in staging
    # and it must take the SMALLER of the two, never the rosier one
    assert "QUOTA_GB < AVAIL_GB" in staging


def test_primary_job_requests_at_least_64g_because_vllm_vsz_is_the_binding_size():
    """--mem stays at the proven 64G floor.

    The ORIGINAL rationale here was that --mem bounds virtual memory. That was
    disproven on 2026-10-15: job 15060 (mistral7b-v03) recorded MaxVMSize of
    98.3 GiB and COMPLETED under a 64G request, so --mem does not cap VSZ on
    this cluster. The 32G failure of job 14935 was GPU contention, not memory.

    The floor is kept anyway, on better grounds: 64G is the documented plan and
    three models have completed under it, while measured RSS is only 3-4 GiB, so
    there is no benefit to trimming it. The scheduling constraint on this
    cluster is the account's cpu=64 cap, not memory -- lowering --mem buys
    nothing and re-opens a variable that is currently settled.
    """
    text = (_ROOT / "slurm" / "30_primary_one_model.sbatch").read_text()
    m = re.search(r"^#SBATCH --mem=(\d+)G", text, re.MULTILINE)
    assert m, "the primary job must state an explicit --mem"
    assert int(m.group(1)) >= 64, (
        f"--mem={m.group(1)}G is below the 64G floor. vLLM needed >30 GiB of "
        "VIRTUAL memory for a 3B model; lowering this on MaxRSS reasoning caused "
        "job 14935 to die at cudaGetDeviceCount with 'out of memory'."
    )


def test_provenance_capture_cannot_abort_a_job():
    """Recording the GPU is diagnostics; failing to record it must not be fatal.

    csis.mn1 ships an nvidia-smi WRAPPER that prints "GPU ACCESS RESTRICTED" and
    exits non-zero even inside a Slurm job with a real allocation. The preamble
    ran `command -v nvidia-smi && nvidia-smi ...`, whose non-zero status under
    `set -e` killed job 14962 two seconds in, before any preflight.
    """
    common = (_ROOT / "slurm" / "templates" / "_common.sh").read_text()
    idx = common.index("nvidia-smi --query-gpu")
    window = common[idx:idx + 400]
    assert "||" in window, (
        "the nvidia-smi call in job_provenance must tolerate a non-zero exit; "
        "a restricted node otherwise kills the job during provenance capture"
    )


def test_staging_bounds_download_concurrency_for_a_shared_login_node():
    """Staging qwen25-14b aborted with a Rust allocator OOM on the login node.

    `memory allocation of 66713827 bytes failed ... Aborted (core dumped)` —
    the hf_xet backend fetching up to 8 multi-GB shards concurrently exhausted
    a machine shared with every other user. The 3B and 7B were small enough to
    survive the default; the 14B was not.
    """
    staging = (_ROOT / "scripts" / "models" / "cache_weights.sh").read_text()
    assert "HF_HUB_DISABLE_XET" in staging, "the Rust xet backend must be disabled"
    assert "max_workers=" in staging, "snapshot_download must bound its concurrency"
    assert "HF_MAX_WORKERS" in staging
