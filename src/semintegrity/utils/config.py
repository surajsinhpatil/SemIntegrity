"""Configuration loading with snapshot hashing.

Every experiment records the *exact* configuration it ran under. Loading a
config therefore returns both the merged dict and a SHA-256 over its canonical
form, and the snapshot is written next to the results so that a run can be
reproduced from the archive alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .hashing import canonical_json, sha256_obj
from .paths import p, project_root


@dataclass(frozen=True)
class ConfigSnapshot:
    """An immutable, content-addressed view of the configuration of a run."""

    name: str
    data: dict[str, Any]
    sources: tuple[str, ...]
    sha256: str

    def dump(self, path: str | Path) -> Path:
        """Write the snapshot beside a result set. Never overwrites."""
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists():
            raise FileExistsError(f"config snapshot already exists (never overwritten): {out}")
        payload = {
            "name": self.name,
            "sources": list(self.sources),
            "sha256": self.sha256,
            "config": self.data,
        }
        out.write_text(canonical_json(payload), encoding="utf-8")
        return out


def load_yaml(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as fh:
        loaded = yaml.safe_load(fh)
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise TypeError(f"{path} must contain a YAML mapping, got {type(loaded).__name__}")
    return loaded


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursive merge; ``override`` wins. Neither input is mutated."""
    out = dict(base)
    for key, value in override.items():
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(*relative_paths: str, name: str | None = None) -> ConfigSnapshot:
    """Merge one or more config files (later files win) into a snapshot.

    Paths are relative to the project root, e.g. ``"configs/project.yaml"``.
    """
    if not relative_paths:
        raise ValueError("load_config requires at least one path")
    merged: dict[str, Any] = {}
    resolved: list[str] = []
    for rel in relative_paths:
        full = p(rel)
        if not full.is_file():
            raise FileNotFoundError(f"config not found: {full}")
        merged = deep_merge(merged, load_yaml(full))
        resolved.append(str(full.relative_to(project_root())))
    return ConfigSnapshot(
        name=name or Path(relative_paths[-1]).stem,
        data=merged,
        sources=tuple(resolved),
        sha256=sha256_obj(merged),
    )


def project_config() -> ConfigSnapshot:
    """The frozen master config. Cached by the OS page cache; cheap to re-read."""
    return load_config("configs/project.yaml", name="project")


def model_config(short_name: str) -> ConfigSnapshot:
    """Per-model config merged over the shared defaults."""
    return load_config(
        "configs/models/_defaults.yaml", f"configs/models/{short_name}.yaml", name=short_name
    )


#: Sentinel values that mark a decision the researcher has not yet taken.
UNRESOLVED_SENTINELS = frozenset({"UNRESOLVED", "UNKNOWN", "UNPROBED", "NOT_RUN"})

#: Keys whose value is legitimately one of those strings as *data*, not as a
#: status marker. Kept deliberately tiny and explicit: ``abstain_token`` holds
#: the literal token a model emits to abstain (proposal §4.7), which happens to
#: be the word UNKNOWN.
LITERAL_VALUE_KEYS = frozenset({"abstain_token"})


def unresolved_decisions(cfg: dict[str, Any], _prefix: str = "") -> list[str]:
    """Locate every unresolved-decision marker in a config.

    Used by the phase gates: a phase cannot be declared complete while a
    decision it depends on is still unresolved.
    """
    found: list[str] = []
    for key, value in cfg.items():
        path = f"{_prefix}{key}"
        if isinstance(value, dict):
            found.extend(unresolved_decisions(value, f"{path}."))
        elif (
            isinstance(value, str)
            and value in UNRESOLVED_SENTINELS
            and key not in LITERAL_VALUE_KEYS
        ):
            found.append(f"{path} = {value}")
    return found


#: Keys every resolved model config must carry after merging with the defaults.
REQUIRED_MODEL_KEYS = frozenset(
    {
        "model_id",
        "short_name",
        "family",
        "dtype",
        "quantisation",
        "revision",
        "generation",
        "serving",
        "gated_on_hf",
        "supports_system_role",
    }
)


def resolve_model_config(short_name: str) -> ConfigSnapshot:
    """Model config merged over the shared defaults, with required keys checked.

    Fails loudly on a missing key: a model silently defaulting to fp16, or to an
    unpinned revision nobody noticed, would be a confound rather than a crash.
    """
    snap = model_config(short_name)
    missing = REQUIRED_MODEL_KEYS - set(snap.data)
    if missing:
        raise KeyError(
            f"model config {short_name!r} is missing required key(s) {sorted(missing)}; "
            "check configs/models/_defaults.yaml and the per-model file"
        )
    if snap.data["dtype"] != "bfloat16" or snap.data["quantisation"] != "none":
        raise ValueError(
            f"{short_name}: §4.6 requires bf16 with no quantisation for every evaluated "
            f"model (got dtype={snap.data['dtype']!r}, quantisation={snap.data['quantisation']!r}). "
            "The documented fallback applies quantisation only to the 70B ceiling model, "
            "and that path is configured explicitly, never by a per-model default."
        )
    return snap
