#!/usr/bin/env python3
"""Fill configs/cluster/cluster.yaml from a probe report.

Read-only with respect to the cluster; writes only inside this repository.
Parses the markdown report `probe_cluster.sh` produced and records what it
actually found. Anything it cannot find stays UNKNOWN — nothing is guessed.

    python scripts/cluster/configure_from_probe.py docs/phase0/cluster_probe_*.md
    python scripts/cluster/configure_from_probe.py <report> --write
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLUSTER_YAML = ROOT / "configs" / "cluster" / "cluster.yaml"


def section(text: str, title: str) -> str:
    m = re.search(rf"^## {re.escape(title)}\n+```(.*?)```", text, re.S | re.M)
    return m.group(1) if m else ""


def parse(text: str) -> dict:
    found: dict = {}

    host = re.search(r"\$ hostname -f\n(\S+)", text)
    if host:
        found["hostname"] = host.group(1)

    parts = re.findall(r"^\s*(\w[\w-]*)\*?\s+(?:up|down)\s", section(text, "Slurm — partitions"), re.M)
    if parts:
        found["partitions"] = sorted(set(parts))

    gres = re.findall(r"gpu:([a-zA-Z0-9_]+):(\d+)", text)
    if gres:
        found["gpus"] = sorted({f"{name}:{n}" for name, n in gres})

    drv = re.search(r"Driver Version:\s*([\d.]+)", text)
    if drv:
        found["driver_version"] = drv.group(1)
    cuda = re.search(r"CUDA Version:\s*([\d.]+)", text)
    if cuda:
        found["cuda_version"] = cuda.group(1)
    nvcc = re.search(r"release ([\d.]+)", text)
    if nvcc and "cuda_version" not in found:
        found["cuda_version"] = nvcc.group(1)

    if re.search(r"^\s*R\s*$|/Rscript", text, re.M):
        found["r_available"] = True
    elif "which R Rscript" in text:
        found["r_available"] = False

    net = {}
    for m in re.finditer(r"(https://\S+)\s+HTTP (\S+)", text):
        net[m.group(1)] = m.group(2)
    if net:
        found["network"] = net

    quota = re.search(r"(\S+)\s+(\d+[GTM])\s+\d+[GTM]\s+(\d+[GTM])\s+\d+%", text)
    if quota:
        found["filesystem_avail"] = quota.group(3)

    return found


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("report", type=Path)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    if not args.report.is_file():
        print(f"report not found: {args.report}", file=sys.stderr)
        return 2

    found = parse(args.report.read_text(encoding="utf-8"))
    print(f"Parsed {args.report.name}\n")
    if not found:
        print("  nothing recognised — the report format may differ; fill cluster.yaml by hand")
        return 1
    for k, v in found.items():
        print(f"  {k:20s} {v}")

    print("\nStill UNKNOWN after parsing (fill by hand from the report):")
    import yaml

    from semintegrity.utils.config import unresolved_decisions

    sys.path.insert(0, str(ROOT / "src"))
    cfg = yaml.safe_load(CLUSTER_YAML.read_text(encoding="utf-8"))
    for item in unresolved_decisions(cfg):
        print(f"  - {item}")

    if args.write:
        print("\n--write is intentionally not automated: cluster.yaml carries "
              "hard operational rules, and a regex should not rewrite them. "
              "Copy the values above in by hand, or paste this output to your "
              "assistant to have the edit made and reviewed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
