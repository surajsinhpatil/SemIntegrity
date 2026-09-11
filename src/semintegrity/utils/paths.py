"""Project path resolution.

All paths derive from ``configs/paths.yaml`` relative to the project root. The
root is found by walking up from this file until ``configs/project.yaml`` is
seen, or is taken from ``$SEMINT_ROOT``. Nothing in the codebase builds a path
by string concatenation from a hard-coded prefix.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

_MARKER = Path("configs") / "project.yaml"


@lru_cache(maxsize=1)
def project_root() -> Path:
    env = os.environ.get("SEMINT_ROOT")
    if env:
        root = Path(env).expanduser().resolve()
        if not (root / _MARKER).is_file():
            raise FileNotFoundError(f"$SEMINT_ROOT={root} does not contain {_MARKER}")
        return root
    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        if (candidate / _MARKER).is_file():
            return candidate
    raise FileNotFoundError(
        f"could not locate the project root (no {_MARKER} above {here}); set $SEMINT_ROOT"
    )


@lru_cache(maxsize=1)
def _path_config() -> dict:
    with (project_root() / _MARKER).parent.joinpath("paths.yaml").open() as fh:
        return yaml.safe_load(fh)


def p(*parts: str) -> Path:
    """Absolute path under the project root."""
    return project_root().joinpath(*parts)


def data_path(key: str) -> Path:
    """Resolve a key from the ``data:`` block of ``configs/paths.yaml``."""
    cfg = _path_config()["data"]
    if key not in cfg:
        raise KeyError(f"unknown data path key {key!r}; known: {sorted(cfg)}")
    return p(cfg[key])


def results_path(key: str) -> Path:
    cfg = _path_config()["results"]
    if key not in cfg:
        raise KeyError(f"unknown results path key {key!r}; known: {sorted(cfg)}")
    return p(cfg[key])


def immutable_prefixes() -> list[Path]:
    """Paths under which files are create-exclusive or append-only."""
    cfg = _path_config().get("immutability", {})
    return [p(x) for x in cfg.get("append_only_or_create_exclusive", [])]
