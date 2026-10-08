"""§4.3 corroboration: the mechanism for an independent second source.

§4.3 requires that "all historical and temporal facts are corroborated against a
second authoritative source". Wikidata is the primary source and cannot
corroborate itself.

This module provides the *mechanism*. Which external sources count as
independent and authoritative is a methodology decision held in
``configs/benchmark/corroboration_policy.yaml``; it was unconfigured on purpose
until **ADR-0019 approved eight providers on 2026-10-07**, each verified to
serve its artefact to an honest plain GET. Before that decision
:meth:`CorroborationPolicy.satisfies` returned False for every source however
well-formed, and the code path that does so is unchanged and still fires
whenever the policy is empty.

**Admissibility is not qualification.** A provider on the approved list is
merely allowed to be considered. Whether a source actually corroborates a given
Wikidata claim is a property of the ``(claim, source)`` pair and is decided by
:mod:`semintegrity.kb.witness`: only an ``independent-witness`` satisfies §4.3.
An arbitrary URL is not corroboration, and neither is a source the claim itself
cites.

Three parts:

:class:`CorroborationPolicy`
    reads the policy, answers "does this source count?", and reports whether a
    policy exists at all.
:class:`CorroborationStore`
    freezes retrieved artefacts in the same generic :class:`KBCache` Wikidata
    evidence uses (ADR-0011), under ``kind="corroboration"``, so a corroborating
    artefact is content-addressed and replayable on the same terms and a FROZEN
    run never reaches the network.
:class:`CorroboratingSourceFetcher`
    the interface a provider adapter must implement. The single implementation
    lives in :mod:`semintegrity.kb.fetchers`; ADR-0019 needed no
    provider-specific adapter and no credentials.
"""

from __future__ import annotations

import datetime as dt
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any
from urllib.parse import urlparse

from ..schemas.constraint import CorroboratingSource
from ..utils.config import load_config
from ..utils.hashing import sha256_text
from ..utils.logging import get_logger
from .cache import CacheMode, KBCache

log = get_logger(__name__)

#: The cache ``kind`` corroborating artefacts are stored under.
CACHE_KIND = "corroboration"

POLICY_PATH = "configs/benchmark/corroboration_policy.yaml"

#: Reported verbatim wherever a corroboration decision cannot be made because
#: the policy has not been set. Tested against, so it stays stable.
NOT_CONFIGURED_MESSAGE = (
    "corroboration mechanism implemented; approved independent source policy "
    "not yet configured"
)


class CorroborationError(ValueError):
    """Raised when a corroborating source cannot be accepted or stored."""


class PolicyNotConfigured(CorroborationError):
    """Raised when an operation needs a provider policy that does not exist."""


@lru_cache(maxsize=1)
def _policy_config() -> dict[str, Any]:
    return load_config(POLICY_PATH).data


@dataclass(frozen=True, slots=True)
class CorroborationArtifact:
    """What a fetcher returns: the retrieved bytes plus where they came from.

    ``final_url``, ``charset`` and ``http_status`` are optional and were added
    with ADR-0019: the probe study showed that a redirect chain
    (``doi.org`` -> ``api.crossref.org``), a non-UTF-8 declaration
    (``Windows-1250``) and a success status that carried a challenge body all
    change what was actually frozen. Recording them is what makes the stored
    artefact reproducible rather than merely present.
    """

    provider: str
    url: str
    retrieved: dt.date
    content: str
    media_type: str = "text/plain"
    final_url: str | None = None
    charset: str | None = None
    http_status: int | None = None

    @property
    def content_hash(self) -> str:
        return sha256_text(self.content)


class CorroborationPolicy:
    """Which sources count as an independent second source, per §4.3.

    The policy is data, not code. This class reads it and refuses to guess.
    """

    def __init__(self, cfg: dict[str, Any] | None = None) -> None:
        self.cfg = cfg or _policy_config()

    # -- what the policy says ------------------------------------------------
    @property
    def status(self) -> str:
        return str(self.cfg.get("status", "NOT_CONFIGURED"))

    @property
    def approved_providers(self) -> tuple[str, ...]:
        return tuple(
            str(p).strip().lower()
            for p in (self.cfg.get("approved_independent_providers") or ())
        )

    @property
    def excluded_providers(self) -> tuple[str, ...]:
        return tuple(
            str(e["id"]).strip().lower()
            for e in (self.cfg.get("excluded_as_second_source") or ())
        )

    @property
    def independence_criterion(self) -> str | None:
        value = self.cfg.get("independence_criterion")
        return None if value is None else str(value)

    @property
    def configured(self) -> bool:
        """True only when a provider list AND an independence criterion exist.

        Both are required. A provider list without a stated criterion would be a
        list of names nobody can audit.
        """
        return bool(self.approved_providers) and self.independence_criterion is not None

    def describe(self) -> str:
        if self.configured:
            return (
                f"corroboration policy CONFIGURED ({len(self.approved_providers)} "
                f"approved provider(s)): {', '.join(self.approved_providers)}"
            )
        return NOT_CONFIGURED_MESSAGE

    # -- the decision --------------------------------------------------------
    def rejection_reason(self, source: CorroboratingSource) -> str | None:
        """Why this source does not satisfy §4.3, or None if it does.

        Well-formedness is already enforced by
        :class:`~semintegrity.schemas.constraint.CorroboratingSource`. What is
        decided here is the part that is *policy*: whether the provider is an
        approved independent authority.
        """
        provider = source.provider.strip().lower()
        if provider in self.excluded_providers:
            return (
                f"provider {source.provider!r} is excluded as a second source: it is "
                "the primary source, and a reference mediated by the primary source is "
                "not automatically independent"
            )
        if not self.configured:
            return NOT_CONFIGURED_MESSAGE
        if provider not in self.approved_providers:
            return (
                f"provider {source.provider!r} is not in the approved independent "
                f"source list {list(self.approved_providers)}"
            )
        return None

    def satisfies(self, source: CorroboratingSource) -> bool:
        return self.rejection_reason(source) is None

    # -- duplicate detection -------------------------------------------------
    def duplicate_groups(
        self, sources: Sequence[CorroboratingSource]
    ) -> list[tuple[str, list[str]]]:
        """Sources that are mechanically the same, grouped by what identifies them.

        One source must not be counted twice under two URLs. Identity is
        established on the keys the policy names — provider, URL host, content
        hash. Subtler identity (a reprint, a syndicated copy, a mirror on another
        domain) is **not** mechanically detectable and is a human-review matter;
        it is never silently accepted as independent.
        """
        keys = tuple(
            str(k) for k in (self.cfg.get("duplicate_detection", {}).get("mechanical_keys") or ())
        )
        out: list[tuple[str, list[str]]] = []
        for key in keys:
            buckets: dict[str, list[str]] = {}
            for src in sources:
                value = {
                    "provider": src.provider.strip().lower(),
                    "url_host": urlparse(src.url).netloc.lower(),
                    "content_hash": src.content_hash,
                }.get(key)
                if value:
                    buckets.setdefault(value, []).append(src.url)
            for value, urls in sorted(buckets.items()):
                if len(urls) > 1:
                    out.append((f"{key}={value}", sorted(urls)))
        return out


class CorroborationStore:
    """Frozen storage for corroborating artefacts.

    Reuses :class:`~semintegrity.kb.cache.KBCache` — the same generic store
    Wikidata evidence uses — under ``kind="corroboration"``. So a corroborating
    artefact inherits ADR-0011's semantics exactly: content-addressed, replayable,
    and in FROZEN mode never fetched.
    """

    def __init__(self, cache: KBCache) -> None:
        self.cache = cache

    @staticmethod
    def request_for(provider: str, url: str, fact: str) -> dict[str, str]:
        """The cache request key. Includes the FACT, so one page corroborating
        two different propositions is stored once per proposition rather than
        silently reused for a claim it was never checked against."""
        return {"provider": provider.strip().lower(), "url": url, "fact": fact}

    def snapshot_key(self, provider: str, url: str, fact: str) -> str:
        return self.cache.request_hash(CACHE_KIND, self.request_for(provider, url, fact))

    def put(self, artifact: CorroborationArtifact, fact: str) -> str:
        """Freeze an artefact and return its snapshot key."""
        request = self.request_for(artifact.provider, artifact.url, fact)
        entry = self.cache.put(
            CACHE_KIND,
            request,
            {
                "content": artifact.content,
                "content_hash": artifact.content_hash,
                "media_type": artifact.media_type,
                "retrieved": artifact.retrieved.isoformat(),
                "fact_supported": fact,
                # ADR-0019 provenance: what was actually retrieved, and how it
                # was represented. Omitted rather than guessed when unknown.
                **({"final_url": artifact.final_url} if artifact.final_url else {}),
                **({"charset": artifact.charset} if artifact.charset else {}),
                **({"http_status": artifact.http_status} if artifact.http_status else {}),
            },
            source=artifact.provider,
        )
        return entry.request_hash

    def get(self, source: CorroboratingSource) -> dict[str, Any] | None:
        entry = self.cache.get(
            CACHE_KIND,
            self.request_for(source.provider, source.url, source.fact_supported),
        )
        return None if entry is None else dict(entry.payload)

    def verify(self, source: CorroboratingSource) -> str | None:
        """Why this source's frozen artefact does not check out, or None.

        Checks that the snapshot exists and that its content still hashes to the
        recorded ``content_hash`` — so "frozen" is a property that was verified
        rather than a field that was filled in.
        """
        payload = self.get(source)
        if payload is None:
            return (
                f"no frozen artefact for {source.provider}/{source.fact_supported!r} "
                f"at snapshot {source.snapshot}"
            )
        expected = self.snapshot_key(source.provider, source.url, source.fact_supported)
        if source.snapshot != expected:
            return (
                f"snapshot {source.snapshot} does not match the key for this "
                f"provider/url/fact ({expected})"
            )
        recorded = str(payload.get("content_hash", ""))
        if recorded != source.content_hash:
            return (
                f"content_hash {source.content_hash} does not match the frozen "
                f"artefact's {recorded}"
            )
        live = sha256_text(str(payload.get("content", "")))
        if live != source.content_hash:
            return f"frozen content hashes to {live}, not the recorded {source.content_hash}"
        return None


class CorroboratingSourceFetcher(ABC):
    """Interface a provider adapter must implement.

    There is exactly one implementation,
    :class:`~semintegrity.kb.fetchers.HttpDocumentFetcher`, because every
    provider ADR-0019 approved serves its artefact to an honest plain
    unauthenticated GET. Adding an adapter was always a small amount of code;
    deciding it was allowed to count was the part that took a feasibility study.

    An adapter retrieves the artefact and nothing else: it does not decide
    whether its provider is approved (:class:`CorroborationPolicy`), whether the
    source is independent of the claim (:mod:`semintegrity.kb.witness`), or
    whether the artefact supports the fact (a human judgement recorded in
    ``fact_supported``).
    """

    #: The provider id this adapter speaks for; matched against the policy.
    provider: str = ""

    @abstractmethod
    def fetch(self, url: str, fact: str) -> CorroborationArtifact:
        """Retrieve the artefact at ``url`` that is claimed to support ``fact``."""


def available_fetchers() -> dict[str, CorroboratingSourceFetcher]:
    """One generic fetcher per approved provider.

    ADR-0019 approved eight providers, every one of which serves its artefact to
    an honest plain GET, so there is exactly **one** implementation
    (:class:`~semintegrity.kb.fetchers.HttpDocumentFetcher`) and **no**
    provider-specific adapters. Before the policy is configured this is empty,
    as it was for the whole period when no provider was approved.
    """
    policy = CorroborationPolicy()
    if not policy.configured:
        return {}
    from .fetchers import HttpDocumentFetcher

    return {p: HttpDocumentFetcher(p) for p in policy.approved_providers}


def policy_status_line() -> str:
    """One line for the readiness audit and the validator."""
    return CorroborationPolicy().describe()


def default_store(mode: CacheMode = CacheMode.FROZEN) -> CorroborationStore:
    from ..utils.paths import data_path

    return CorroborationStore(KBCache(data_path("wikidata_cache"), mode))
