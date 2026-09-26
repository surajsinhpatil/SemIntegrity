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
