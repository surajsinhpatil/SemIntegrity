#!/usr/bin/env python3
"""Resolve and pin real Hugging Face commit SHAs for the evaluated models.

§4.5 requires pinned open-weight revisions. A revision hash is **never** written
by hand: this script resolves the current commit SHA from the Hub and writes it
into the per-model config.

Needs network. Run on the login node or a laptop, never inside a GPU job.
Downloads **no weights** — it reads repository metadata only.

    python scripts/models/pin_revisions.py                 # report only
    python scripts/models/pin_revisions.py --write         # pin all
    python scripts/models/pin_revisions.py --model qwen25-3b --write

Gated repositories need HF_TOKEN in the environment, and the licence must
already be accepted with your own account. The token is read from the
environment and is never printed, logged or written to any file.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def model_files() -> list[Path]:
    return sorted(p for p in (ROOT / "configs" / "models").glob("*.yaml") if not p.stem.startswith("_"))


def resolve(model_id: str, token: str | None) -> tuple[str | None, str]:
    """Return (sha, status). Never invents a value."""
    try:
        from huggingface_hub import HfApi
        from huggingface_hub.utils import GatedRepoError, RepositoryNotFoundError
    except ImportError:
        return None, "huggingface_hub not installed"
    api = HfApi()
    try:
        info = api.model_info(model_id, token=token)
    except GatedRepoError:
        return None, "GATED — accept the licence on huggingface.co with your account, then set HF_TOKEN"
    except RepositoryNotFoundError:
        return None, "repository not found (or token lacks access)"
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"
    sha = getattr(info, "sha", None)
    if not sha or not SHA_RE.match(str(sha)):
        return None, f"Hub returned an unusable revision {sha!r}"
    return str(sha), "ok"


def write_revision(path: Path, sha: str) -> None:
    text = path.read_text(encoding="utf-8")
    stamp = dt.datetime.now(dt.timezone.utc).date().isoformat()
    text = re.sub(r"^revision:.*$", f"revision: {sha}", text, count=1, flags=re.MULTILINE)
    text = re.sub(r"^revision_pinned_at:.*$", f"revision_pinned_at: {stamp}", text,
                  count=1, flags=re.MULTILINE)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", help="short name; default is every evaluated model")
    ap.add_argument("--write", action="store_true", help="write the resolved SHA into the config")
    args = ap.parse_args()

    import yaml

    token = os.environ.get("HF_TOKEN") or None
    print(f"HF_TOKEN: {'present' if token else 'NOT SET (gated repos will fail)'}\n")

    paths = model_files()
    if args.model:
        paths = [p for p in paths if p.stem == args.model]
        if not paths:
            print(f"no config named {args.model!r}", file=sys.stderr)
            return 2

    failures = 0
    for path in paths:
        cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
        model_id, current = cfg["model_id"], cfg.get("revision")
        if current and SHA_RE.match(str(current)):
            print(f"  {path.stem:16s} already pinned  {current[:12]}  ({model_id})")
            continue
        sha, status = resolve(model_id, token)
        if sha is None:
            failures += 1
            gate = " [gated]" if cfg.get("gated_on_hf") else ""
            print(f"  {path.stem:16s} UNRESOLVED{gate}  {model_id}\n"
                  f"  {'':16s}   -> {status}")
            continue
        if args.write:
            write_revision(path, sha)
            print(f"  {path.stem:16s} PINNED  {sha[:12]}  ({model_id})")
        else:
            print(f"  {path.stem:16s} resolved {sha[:12]}  ({model_id})  [--write to pin]")

    print(f"\n{len(paths) - failures}/{len(paths)} resolved.")
    if failures:
        print("Unresolved models are almost always gated: accept each licence on "
              "huggingface.co, create a read token, export HF_TOKEN, and re-run.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
