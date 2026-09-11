"""Synthetic test fixtures must never reach the benchmark directory.

A structurally valid but factually invented constraint that leaked into
`data/benchmark/` would be indistinguishable from real content at a glance and
would corrupt the study silently. This test is cheap insurance.
"""

from semintegrity.utils.paths import p
from tests.fixtures.synthetic_benchmark import SYNTHETIC_MARKER


def test_no_synthetic_content_under_data_benchmark():
    offenders = []
    root = p("data")
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".json", ".jsonl", ".yaml", ".csv", ".txt"}:
            continue
        try:
            if SYNTHETIC_MARKER in path.read_text(encoding="utf-8", errors="ignore"):
                offenders.append(str(path.relative_to(root)))
        except OSError:  # pragma: no cover
            continue
    assert not offenders, (
        f"synthetic test fixtures leaked into data/: {offenders}. "
        "These are factually invented and must never be treated as benchmark content."
    )


def test_no_synthetic_content_under_results():
    offenders = [
        str(path) for path in p("results").rglob("*")
        if path.is_file() and path.suffix in {".json", ".jsonl"}
        and SYNTHETIC_MARKER in path.read_text(encoding="utf-8", errors="ignore")
    ]
    assert not offenders, f"synthetic fixtures leaked into results/: {offenders}"
