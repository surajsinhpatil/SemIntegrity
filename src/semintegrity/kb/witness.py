"""§4.3 witness classification: is a source independent *of the claim*?

ADR-0019 separates two things that the first draft of the corroboration policy
ran together:

**Admissibility** — is this provider allowed to be considered at all? That is
:class:`~semintegrity.kb.corroboration.CorroborationPolicy`, and it is a
property of the provider.

**Qualification** — does this source actually corroborate *this* Wikidata claim?
That is this module, and it is a property of the ``(claim, source)`` pair:

``independent-witness``
    The Wikidata claim does **not** cite this provider or source. This, and only
    this, satisfies §4.3 and may support promotion.
``same-witness``
    The claim **does** cite it, by a P248 "stated in" value or by a reference
    URL on the same host. The source may be authoritative and may establish the
    fact in its own right, but it is not independent confirmation of Wikidata's
    claim. Recorded as provenance; **never** sufficient for promotion.
``undetermined``
    The classification could not be established from the frozen evidence.
    Blocks promotion, because an unproven independence claim is not an
    independence claim.

Why mechanically and not by convention: a convention cannot block a promotion.
The determination reads the claim's **own references** out of the frozen KB
cache — the same entity payload ADR-0011 already stores — and never trusts a
hand-written ``note``.

**Identity is decided at PROVIDER level (Q26, approved 2026-10-07).** The first
rule matched a reference URL "on the same host", which live validation showed to
be too narrow: Wikidata's ``Q533336 P361 -> Q2025902`` cites ``www.nasa.gov``
while the authoritative NASA artefact for the same fact is on
``nssdc.gsfc.nasa.gov``. Both are the approved provider ``nasa``, so the claim
already cites that provider. Host equality returned ``independent-witness``, in
the direction that wrongly permits promotion, and five of the eight approved
providers are deliberately multi-host categories, so the gap was structural.
Ownership is now read from ``witness_classification.provider_hosts``.

**Ownership is never inferred.** Only an explicit entry in that map establishes
that a host belongs to a provider: domain similarity proves nothing, so
``nasa.gov`` does not vouch for an unlisted subdomain. A cited host the map does
not resolve yields ``undetermined``.

**The classifier errs toward refusing.** A claim that carries a P248 reference or
a reference host this policy cannot resolve yields ``undetermined``, not
``independent-witness``: the unknown is treated as a possible self-citation. A
researcher resolves such a case once, by adding the entry after checking it.
Nothing is assumed on the project's behalf.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from urllib.parse import urlparse

from ..schemas.constraint import Constraint, CorroboratingSource
from ..utils.logging import get_logger
from .cache import KBCache
from .corroboration import CorroborationPolicy

log = get_logger(__name__)

#: Wikidata's "stated in" reference property.
P_STATED_IN = "P248"

#: Reference properties whose value is a retrievable URL.
URL_REFERENCE_PROPERTIES = ("P854", "P4656", "P1065", "P953")

#: ``Evidence.query`` is free text by schema, but every record written by this
#: project starts with a QID and optionally names a property: ``"Q155 P36"``.
_CLAIM_QUERY_RE = re.compile(r"^(Q\d+)(?:\s+(P\d+))?")


class WitnessClass(str, Enum):
    """How a source stands in relation to the claim it is offered for."""

    INDEPENDENT = "independent-witness"
    SAME = "same-witness"
    UNDETERMINED = "undetermined"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


@dataclass(frozen=True, slots=True)
class WitnessVerdict:
    """The classification, plus why — so a reviewer can audit it."""

    classification: WitnessClass
    reason: str
    claims_checked: tuple[tuple[str, str | None], ...] = ()
    citations: tuple[str, ...] = field(default=())

    @property
    def qualifies(self) -> bool:
        """Whether this verdict satisfies §4.3. Only one class does."""
        return self.classification is WitnessClass.INDEPENDENT

    def __str__(self) -> str:
        return f"{self.classification.value}: {self.reason}"


def claims_from_constraint(constraint: Constraint) -> list[tuple[str, str | None]]:
    """The Wikidata claims a constraint's gold answer actually rests on.

    Read from the ``Evidence`` records that carry ``supports_gold`` and name
    Wikidata as their source. ``Evidence.query`` is the only place the claim's
    identity is recorded, so it is parsed rather than guessed; a record whose
    query does not start with a QID is skipped, which makes the result empty
    rather than wrong.
    """
    out: list[tuple[str, str | None]] = []
    for ev in constraint.evidence:
        if not ev.supports_gold or ev.source.strip().lower() != "wikidata":
            continue
        m = _CLAIM_QUERY_RE.match(ev.query.strip())
        if m is None:
            continue
        pair = (m.group(1), m.group(2))
        if pair not in out:
            out.append(pair)
    return out


def claim_references(
    cache: KBCache, qid: str, property_id: str | None, *, lang: str = "en"
) -> list[dict[str, Any]] | None:
    """Every reference on the named claim, from the frozen entity payload.

    Returns ``None`` when the entity is not in the cache — which is *not* the
    same as "no references" and must not be collapsed into it. With
    ``property_id`` as ``None`` the references of every statement on the entity
    are returned, which is the conservative reading of an evidence record that
    did not name a property.
    """
    entry = cache.get("entity", {"qid": qid, "lang": lang})
    if entry is None:
        return None
    payload = entry.payload
    if not isinstance(payload, dict):
        return None
    entity = (payload.get("entities") or {}).get(qid) or {}
    claims = entity.get("claims") or {}
    if not isinstance(claims, dict):
        return None
    wanted = [property_id] if property_id else list(claims)
    refs: list[dict[str, Any]] = []
    for prop in wanted:
        for statement in claims.get(prop) or ():
            for ref in statement.get("references") or ():
                refs.append(ref)
    return refs


def _reference_citations(refs: list[dict[str, Any]]) -> tuple[set[str], set[str]]:
    """Split a claim's references into (URL hosts cited, P248 QIDs cited)."""
    hosts: set[str] = set()
    stated_in: set[str] = set()
    for ref in refs:
        for prop, snaks in (ref.get("snaks") or {}).items():
            for snak in snaks or ():
                value = (snak.get("datavalue") or {}).get("value")
                if prop == P_STATED_IN and isinstance(value, dict):
                    qid = value.get("id")
                    if qid:
                        stated_in.add(str(qid))
                elif prop in URL_REFERENCE_PROPERTIES and isinstance(value, str):
                    host = urlparse(value).netloc.lower()
                    if host:
                        hosts.add(host)
    return hosts, stated_in


def _source_hosts(source: CorroboratingSource) -> set[str]:
    """Every host this source was actually retrieved from.

    The requested URL and, when the note records one, the final URL after
    redirects — ``doi.org`` resolving to ``api.crossref.org`` is exactly the case
    that makes both matter.
    """
    hosts = {urlparse(source.url).netloc.lower()}
    for match in re.finditer(r"final_url=(\S+)", source.note or ""):
        host = urlparse(match.group(1)).netloc.lower()
        if host:
            hosts.add(host)
    return {h for h in hosts if h}


class WitnessClassifier:
    """Classifies a ``(claim, source)`` pair against the approved policy."""

    def __init__(
        self,
        cache: KBCache,
        policy: CorroborationPolicy | None = None,
        *,
        lang: str = "en",
    ) -> None:
        self.cache = cache
        self.policy = policy or CorroborationPolicy()
        self.lang = lang

    # -- policy reads --------------------------------------------------------
    @property
    def _witness_cfg(self) -> dict[str, Any]:
        cfg = self.policy.cfg.get("witness_classification") or {}
        return cfg if isinstance(cfg, dict) else {}

    @property
    def undetermined_blocks(self) -> bool:
        """Whether an unproven classification blocks promotion. Default True."""
        return bool(self._witness_cfg.get("undetermined_blocks_promotion", True))

    def provider_hosts_for(self, provider: str) -> set[str]:
        """Hosts the policy explicitly declares for one provider."""
        mapping = self._witness_cfg.get("provider_hosts") or {}
        if not isinstance(mapping, dict):
            return set()
        return {
            str(h).strip().lower()
            for h in (mapping.get(provider.strip().lower()) or ())
            if str(h).strip()
        }

    def provider_of_host(self, host: str) -> str | None:
        """Which approved provider owns this host, or None if not declared.

        An EXACT host match against the policy's own map. No suffix matching, no
        registrable-domain matching, no similarity: Q26 requires that ownership
        be established explicitly or not at all.
        """
        mapping = self._witness_cfg.get("provider_hosts") or {}
        if not isinstance(mapping, dict):
            return None
        needle = host.strip().lower()
        for provider, hosts in mapping.items():
            for declared in hosts or ():
                if str(declared).strip().lower() == needle:
                    return str(provider).strip().lower()
        return None

    def _stated_in_map(self) -> dict[str, list[str]]:
        """The provider -> [P248 item] map, with its SHAPE checked.

        The map is keyed by PROVIDER and holds a list of QIDs. Writing it
        inverted (``Q19606873: standards-body``) used to yield silent nonsense:
        the provider string was iterated character by character, so
        ``_known_stated_in`` returned ``{'s','t','a','n','d',...}`` and every
        real citation looked unmapped. A mis-shaped policy must fail loudly —
        this map decides whether a source may corroborate a benchmark fact.
        """
        mapping = self._witness_cfg.get("wikidata_stated_in_qids") or {}
        if not isinstance(mapping, dict):
            raise ValueError(
                "witness_classification.wikidata_stated_in_qids must be a mapping "
                f"of provider -> [P248 item], got {type(mapping).__name__}"
            )
        out: dict[str, list[str]] = {}
        for provider, qids in mapping.items():
            if isinstance(qids, str) or not isinstance(qids, list | tuple | set):
                raise ValueError(
                    "witness_classification.wikidata_stated_in_qids is keyed by "
                    f"PROVIDER and holds a LIST of items, but {provider!r} maps to "
                    f"{qids!r}. Did you write it inverted (qid: provider)?"
                )
            bad = [q for q in qids if not re.fullmatch(r"Q\d+", str(q))]
            if bad:
                raise ValueError(
                    f"witness_classification.wikidata_stated_in_qids[{provider!r}] "
                    f"contains non-QID value(s) {bad}"
                )
            out[str(provider).strip().lower()] = [str(q) for q in qids]
        return out

    def stated_in_qids_for(self, provider: str) -> set[str]:
        """P248 items the policy has recorded as belonging to this provider."""
        return set(self._stated_in_map().get(provider.strip().lower(), ()))

    def _known_stated_in(self) -> set[str]:
        return {q for qids in self._stated_in_map().values() for q in qids}

    # -- the classification --------------------------------------------------
    def classify(
        self, source: CorroboratingSource, claims: list[tuple[str, str | None]]
    ) -> WitnessVerdict:
        """Classify one source against the claims it is offered for.

        Several claims are checked together because a source offered for a
        constraint is offered for that constraint's whole gold basis: if it is a
        ``same-witness`` for **any** of them it does not qualify. The strictest
        outcome over the claims wins.
        """
        if not claims:
            return WitnessVerdict(
                WitnessClass.UNDETERMINED,
                "no Wikidata claim could be identified from the constraint's "
                "supports_gold evidence, so independence from the claim cannot be "
                "established",
            )

        provider = source.provider.strip().lower()
        provider_qids = self.stated_in_qids_for(source.provider)
        resolvable = self._known_stated_in()
        hosts = _source_hosts(source)
        declared = self.provider_hosts_for(provider)
        unresolved: set[str] = set()
        unowned_hosts: set[str] = set()
        checked = tuple(claims)

        # Q26: the SOURCE's own host must be a declared host of its provider,
        # or provider identity cannot be established for the source either and
        # nothing downstream can be trusted.
        if declared and not (hosts & declared):
            return WitnessVerdict(
                WitnessClass.UNDETERMINED,
                f"the source was retrieved from {sorted(hosts)}, which the policy does "
                f"not declare as a host of provider {source.provider!r} "
                f"({sorted(declared)}); provider identity cannot be established, so "
                "independence cannot be either",
                checked,
            )
        if not declared:
            return WitnessVerdict(
                WitnessClass.UNDETERMINED,
                f"the policy declares no provider_hosts for {source.provider!r}, so "
                "whether a cited reference belongs to this provider cannot be decided",
                checked,
            )

        for qid, prop in claims:
            refs = claim_references(self.cache, qid, prop, lang=self.lang)
            if refs is None:
                return WitnessVerdict(
                    WitnessClass.UNDETERMINED,
                    f"{qid} is not in the frozen knowledge-base cache, so the claim's "
                    "own references cannot be read; snapshot it before promotion",
                    checked,
                )
            cited_hosts, cited_stated_in = _reference_citations(refs)

            shared = hosts & cited_hosts
            if shared:
                return WitnessVerdict(
                    WitnessClass.SAME,
                    f"the Wikidata claim {qid}"
                    f"{' ' + prop if prop else ''} cites this source's own host "
                    f"({', '.join(sorted(shared))}), so it is not independent "
                    "confirmation of that claim",
                    checked,
                    tuple(sorted(cited_hosts)),
                )
            # Q26: a DIFFERENT host of the SAME provider is still the same
            # witness. This is the case host equality missed.
            same_provider = sorted(
                h for h in cited_hosts if self.provider_of_host(h) == provider
            )
            if same_provider:
                return WitnessVerdict(
                    WitnessClass.SAME,
                    f"the Wikidata claim {qid}"
                    f"{' ' + prop if prop else ''} cites {', '.join(same_provider)}, "
                    f"which the policy declares a host of provider {source.provider!r} — "
                    "a different host of the same provider is the same witness, not an "
                    "independent one",
                    checked,
                    tuple(sorted(cited_hosts)),
                )
            unowned_hosts |= {
                h for h in cited_hosts if self.provider_of_host(h) is None
            }
            same_stated = cited_stated_in & provider_qids
            if same_stated:
                return WitnessVerdict(
                    WitnessClass.SAME,
                    f"the Wikidata claim {qid}"
                    f"{' ' + prop if prop else ''} cites "
                    f"{', '.join(sorted(same_stated))}, which the policy records as "
                    f"provider {source.provider!r}",
                    checked,
                    tuple(sorted(cited_stated_in)),
                )
            unresolved |= cited_stated_in - resolvable

        if unresolved:
            return WitnessVerdict(
                WitnessClass.UNDETERMINED,
                "the claim carries 'stated in' reference(s) "
                f"{', '.join(sorted(unresolved))} that the policy cannot map to a "
                "provider; an unmapped citation is treated as a possible "
                "self-citation. Resolve it once under "
                "witness_classification.wikidata_stated_in_qids",
                checked,
                tuple(sorted(unresolved)),
            )
        if unowned_hosts:
            return WitnessVerdict(
                WitnessClass.UNDETERMINED,
                "the claim cites host(s) "
                f"{', '.join(sorted(unowned_hosts))} that the policy's provider_hosts "
                "map does not resolve to any approved provider, so whether the citation "
                "is this provider cannot be decided. Ownership is never inferred from "
                "domain similarity; add the host under "
                "witness_classification.provider_hosts after checking it",
                checked,
                tuple(sorted(unowned_hosts)),
            )
        return WitnessVerdict(
            WitnessClass.INDEPENDENT,
            "no reference on the claim(s) names this source's host or provider, so "
            "it is an independent second witness",
            checked,
        )

    def classify_for_constraint(
        self, constraint: Constraint, source: CorroboratingSource
    ) -> WitnessVerdict:
        """Classify a source against the claims of the constraint it belongs to."""
        return self.classify(source, claims_from_constraint(constraint))
