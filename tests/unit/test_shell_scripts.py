"""Every shell script and Slurm job must parse.

A syntax error in an sbatch file is not caught until the scheduler has already
granted an allocation, so it costs GPU time to discover. `bash -n` parses
without executing, which makes that a unit test instead.
"""

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
