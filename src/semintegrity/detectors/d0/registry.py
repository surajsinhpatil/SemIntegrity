"""D0 predicate registry and freeze manifest (proposal §4.8.2).

The freeze policy is the point of this module. §4.8.2 requires predicates to be
frozen before test evaluation, with a sharp asymmetry:

* on the **development** split, a D0-human disagreement is a formalisation bug
  and the predicate may be corrected;
* on the **test** split, a D0-human disagreement is D0's *measured error rate*
  and the predicate must not be modified.

That distinction is only meaningful if "the predicate did not change" is
checkable. :func:`write_freeze_manifest` records a hash per predicate;
:func:`verify_freeze` compares the live code against it and reports drift.
"""

from __future__ import annotations

import datetime as dt
import importlib
import pkgutil
from collections.abc import Iterator
from pathlib import Path

from ...utils.hashing import sha256_obj
from ...utils.logging import get_logger
from .base import D0Predicate

log = get_logger(__name__)

PREDICATE_PACKAGE = "semintegrity.detectors.d0.predicates"


class PredicateFrozenError(RuntimeError):
    """Raised when a predicate changed after the freeze."""


class PredicateRegistry:
    """Maps ``formal_predicate`` names to predicate instances."""

    def __init__(self) -> None:
        self._by_name: dict[str, D0Predicate] = {}

    def register(self, predicate: D0Predicate) -> D0Predicate:
        name = predicate.predicate_name
        if name in self._by_name:
            existing = type(self._by_name[name]).__name__
            raise ValueError(
                f"predicate {name!r} is already registered by {existing}; "
                "two predicates cannot claim one name"
            )
        self._by_name[name] = predicate
        return predicate

    def get(self, name: str) -> D0Predicate:
        try:
            return self._by_name[name]
        except KeyError as exc:
            raise KeyError(
                f"no D0 predicate registered as {name!r}; known: {sorted(self._by_name)}"
            ) from exc

    def has(self, name: str) -> bool:
        return name in self._by_name

    def names(self) -> list[str]:
        return sorted(self._by_name)

    def __len__(self) -> int:
        return len(self._by_name)

    def __iter__(self) -> Iterator[D0Predicate]:
        return iter(self._by_name[n] for n in sorted(self._by_name))

    # -- discovery ----------------------------------------------------------
    def autodiscover(self, package: str = PREDICATE_PACKAGE) -> int:
        """Import every module under ``predicates/`` and register what they declare.

        Import is idempotent (Python caches modules), so discovery reads the
        *declared* class list rather than relying on import side effects. That
        makes a fresh registry fully populated on every call, which is what lets
        the freeze policy be tested against an isolated registry.
        """
        _import_predicate_modules(package)
        before = len(self._by_name)
        for cls in DISCOVERED_PREDICATES:
            if cls.predicate_name not in self._by_name:
                self.register(cls())
        return len(self._by_name) - before

    # -- freeze -------------------------------------------------------------
    def fingerprint(self) -> dict[str, dict[str, str]]:
        return {p.predicate_name: p.describe() for p in self}

    def write_freeze_manifest(self, path: str | Path, *, note: str = "") -> Path:
        """Record every predicate's source hash. Never overwrites."""
        from ...utils.io import write_json_exclusive

        fp = self.fingerprint()
        manifest = {
            "frozen_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "note": note,
            "n_predicates": len(fp),
            "predicates": fp,
            "registry_sha256": sha256_obj(fp),
        }
        out = write_json_exclusive(path, manifest)
        log.info("froze D0 predicates", extra={"extra_fields": {"n": len(fp), "path": str(out)}})
        return out

    def verify_freeze(self, path: str | Path) -> list[str]:
        """Report drift against a freeze manifest (empty list = intact)."""
        import json

        src = Path(path)
        if not src.is_file():
            return [f"freeze manifest missing: {src}"]
        manifest = json.loads(src.read_text(encoding="utf-8"))
        recorded: dict[str, dict[str, str]] = manifest["predicates"]
        live = self.fingerprint()

        problems: list[str] = []
        for name, rec in sorted(recorded.items()):
            if name not in live:
                problems.append(f"removed after freeze: {name}")
            elif live[name]["source_sha256"] != rec["source_sha256"]:
                problems.append(
                    f"MODIFIED after freeze: {name} "
                    f"(v{rec['version']} -> v{live[name]['version']})"
                )
        for name in sorted(set(live) - set(recorded)):
            problems.append(f"added after freeze: {name}")
        return problems

    def assert_frozen(self, path: str | Path) -> None:
        """Raise unless every predicate matches the freeze manifest.

        Called by the test-split detector run. On the test split a changed
        predicate is not a fix — it is a silent change to a measured error rate.
        """
        problems = self.verify_freeze(path)
        if problems:
            raise PredicateFrozenError(
                "D0 predicates have drifted from the freeze manifest:\n  - "
                + "\n  - ".join(problems)
                + "\n\nOn the TEST split a predicate must not be modified (§4.8.2); a "
                "D0-human disagreement there is D0's measured error rate."
            )


#: Every predicate class declared with ``@register``, in declaration order.
#: Populated at import time; registries instantiate from it during discovery.
DISCOVERED_PREDICATES: list[type[D0Predicate]] = []


def register(cls: type[D0Predicate]) -> type[D0Predicate]:
    """Class decorator that declares a predicate for discovery.

    Declaring is not registering: the class is recorded here and instantiated
    into whichever registry calls :meth:`PredicateRegistry.autodiscover`. Binding
    directly to a global registry would make the freeze policy untestable and
    would silently no-op on a second import.
    """
    existing = {c.predicate_name: c for c in DISCOVERED_PREDICATES}
    prior = existing.get(cls.predicate_name)
    if prior is not None and prior is not cls:
        raise ValueError(
            f"predicate name {cls.predicate_name!r} is declared by both "
            f"{prior.__module__}.{prior.__name__} and {cls.__module__}.{cls.__name__}"
        )
    if prior is None:
        DISCOVERED_PREDICATES.append(cls)
    return cls


def _import_predicate_modules(package: str = PREDICATE_PACKAGE) -> int:
    """Import every non-underscore module under the predicate package."""
    try:
        pkg = importlib.import_module(package)
    except ModuleNotFoundError:  # pragma: no cover
        return 0
    n = 0
    for mod in pkgutil.iter_modules(pkg.__path__):
        if mod.name.startswith("_"):
            continue
        importlib.import_module(f"{package}.{mod.name}")
        n += 1
    return n


def default_registry(package: str = PREDICATE_PACKAGE) -> PredicateRegistry:
    """A fresh registry with every declared predicate loaded."""
    reg = PredicateRegistry()
    reg.autodiscover(package)
    return reg


#: Convenience process-wide registry. Prefer `default_registry()` in library
#: code so that callers are not coupled to shared mutable state.
REGISTRY = PredicateRegistry()
