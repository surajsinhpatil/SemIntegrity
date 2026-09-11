#!/usr/bin/env python3
"""Validate every configuration file and report unresolved decisions.

Run this before any `sbatch`. It is read-only and safe on a login node.

Exit codes
----------
0  all configs parse and no BLOCKING decision is unresolved for the phase
1  a config failed to parse or an invariant failed
2  configs are valid but unresolved decisions remain (informational)
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import yaml  # noqa: E402

from semintegrity.utils.config import unresolved_decisions  # noqa: E402
from semintegrity.utils.hashing import sha256_file  # noqa: E402

GREEN, YELLOW, RED, RESET = "\033[32m", "\033[33m", "\033[31m", "\033[0m"


def main() -> int:
    config_files = sorted((ROOT / "configs").rglob("*.yaml"))
    if not config_files:
        print(f"{RED}no config files found under configs/{RESET}")
        return 1

    failures: list[str] = []
    unresolved: list[tuple[str, str]] = []

    print(f"Parsing {len(config_files)} config files\n")
    for path in config_files:
        rel = path.relative_to(ROOT)
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            failures.append(f"{rel}: {exc}")
            print(f"  {RED}FAIL{RESET}  {rel}")
            continue
        pending = unresolved_decisions(data) if isinstance(data, dict) else []
        unresolved.extend((str(rel), item) for item in pending)
        mark = f"{YELLOW}WARN{RESET}" if pending else f"{GREEN} OK {RESET}"
        print(f"  {mark}  {rel}  ({sha256_file(path)[:12]})")

    if failures:
        print(f"\n{RED}{len(failures)} config file(s) failed to parse:{RESET}")
        for f in failures:
            print(f"  - {f}")
        return 1

    if unresolved:
        print(f"\n{YELLOW}{len(unresolved)} unresolved decision(s):{RESET}")
        current = None
        for rel, item in unresolved:
            if rel != current:
                print(f"\n  {rel}")
                current = rel
            print(f"    - {item}")
        print(
            "\nThese are tracked in docs/OPEN_QUESTIONS.md. A phase that depends on"
            "\none of them must not be reported as complete."
        )
        return 2

    print(f"\n{GREEN}All configs valid; no unresolved decisions.{RESET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
