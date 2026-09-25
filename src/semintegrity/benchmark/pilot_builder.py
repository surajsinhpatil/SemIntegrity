"""Build the pilot benchmark from ``data/benchmark/pilot/candidates.yaml``.

Turns hand-authored candidates into validated :class:`Constraint` and
:class:`Probe` records, optionally attaching machine-checked Wikidata evidence.

**Everything is written as DRAFT.** Promotion to EVIDENCE_VERIFIED happens only
when ``--promote`` is passed *and* every declared evidence check for that
constraint actually passed. Promotion to HUMAN_VALIDATED is never performed by
this module under any flag: that status requires a named human and is set by
``scripts/benchmark/validate_pilot.py --record-human-validation``.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from ..kb.cache import CacheMode, KBCache
from ..kb.evidence import run_check
from ..kb.wikidata import WikidataClient
from ..probes.factor_design import cells_for_constraint
from ..probes.surface import realise, realised_factors
from ..schemas.constraint import Constraint, Entity, Evidence, PrerequisiteFact, TemporalValidity
from ..schemas.enums import (
    ConstraintClass,
    Domain,
    Split,
    Tier,
    Track,
    ValidationStatus,
    VerificationStatus,
)
from ..schemas.probe import Probe
from ..utils.ids import probe_id
from ..utils.logging import get_logger
from ..utils.paths import data_path

log = get_logger(__name__)

K_PILOT = 8  # the design's guaranteed-balanced unit; §4.12's pilot RUN uses 5 of these


@dataclass(slots=True)
class BuildResult:
    constraints: list[Constraint] = field(default_factory=list)
    probes: list[Probe] = field(default_factory=list)
    evidence_by_constraint: dict[str, list[Evidence]] = field(default_factory=dict)
    factor_realisation: dict[str, dict[str, bool]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def n_evidence_passed(self) -> int:
        return sum(e.supports_gold for evs in self.evidence_by_constraint.values() for e in evs)

    @property
    def n_evidence_total(self) -> int:
        return sum(len(evs) for evs in self.evidence_by_constraint.values())


def build(
    candidates: dict[str, Any],
    *,
    fetch_evidence: bool = False,
    promote_on_evidence: bool = False,
    cache_mode: CacheMode = CacheMode.LIVE,
) -> BuildResult:
    """Build constraint and probe records from the candidates document."""
    result = BuildResult()
    client = None
    if fetch_evidence:
        client = WikidataClient(KBCache(data_path("wikidata_cache"), cache_mode))

    class_index: dict[str, int] = {}

    for family in candidates["families"]:
        domain = Domain(family["domain"])
        for spec in family["constraints"]:
            cls = ConstraintClass(spec["class"])
            idx = class_index.get(cls.value, 0)
            class_index[cls.value] = idx + 1

            evidence: list[Evidence] = []
            sitelinks: dict[str, int] = {}
            if client is not None:
                for check in spec.get("evidence_checks", []):
                    evidence.append(run_check(client, check))
                # Entity familiarity (§4.3): deterministic, from the KB, not
                # time-sensitive. Fetched here so the pilot can already report
                # the covariate the full benchmark matches classes on.
                for ent in spec["entities"]:
                    try:
                        sitelinks[ent["qid"]] = client.sitelink_count(ent["qid"])
                    except Exception as exc:
                        result.warnings.append(
                            f"{spec['constraint_id']}: sitelink lookup failed for "
                            f"{ent['qid']} ({type(exc).__name__})"
                        )
            result.evidence_by_constraint[spec["constraint_id"]] = evidence

            all_passed = bool(evidence) and all(e.supports_gold for e in evidence)
            # A recorded source discrepancy is not resolved by a check that
            # merely confirms the discrepancy exists. It needs a human decision,
            # so it blocks automatic promotion however many checks pass.
            discrepancies = [e for e in evidence if "DISCREPANCY" in (e.note or "")]
            if discrepancies:
                all_passed = False
                result.warnings.append(
                    f"{spec['constraint_id']}: {len(discrepancies)} recorded source "
                    "discrepancy/ies — blocked from EVIDENCE_VERIFIED pending human adjudication"
                )
            status = (
                VerificationStatus.EVIDENCE_VERIFIED
                if (promote_on_evidence and all_passed)
                else VerificationStatus.DRAFT
            )
            if promote_on_evidence and not all_passed:
                failed = [e.note for e in evidence if not e.supports_gold] or ["no checks declared"]
                result.warnings.append(
                    f"{spec['constraint_id']}: stays DRAFT — unmet check(s): {'; '.join(failed)}"
                )

            constraint = _make_constraint(
                spec, family, domain, cls, evidence, status, sitelinks, discrepancies
            )
            result.constraints.append(constraint)

            slots = spec["surface"]
            result.factor_realisation[constraint.constraint_id] = realised_factors(
                slots=slots, answer_type=constraint.answer_type, gold_answer=constraint.gold_answer
            )
            probes = _make_probes(constraint, slots, idx)
            _check_distinct_texts(constraint.constraint_id, probes, result.warnings)
            result.probes.extend(probes)

    return result


def _make_constraint(
    spec, family, domain, cls, evidence, status, sitelinks=None, discrepancies=None
) -> Constraint:
    sitelinks = sitelinks or {}
    entities = [
        Entity(
            label=e["label"],
            qid=e["qid"],
            sitelinks=sitelinks.get(e["qid"], 0),
            sitelinks_retrieved=dt.date.today().isoformat() if e["qid"] in sitelinks else None,
        )
        for e in spec["entities"]
    ]
    temporal = spec.get("temporal_validity")
    return Constraint.model_validate(
        {
            "constraint_id": spec["constraint_id"],
            "family_id": family["family_id"],
            "schema_id": spec["schema_id"],
            "domain": domain.value,
            "class": cls.value,
            "formal_predicate": spec["formal_predicate"],
            "constraint_text": " ".join(spec["constraint_text"].split()),
            "entities": [e.label for e in entities],
            "entity_qids": [e.qid for e in entities],
            "entity_sitelinks": [e.sitelinks for e in entities],
            "entity_records": [e.model_dump(mode="json") for e in entities],
            "gold_proposition": " ".join(spec["gold_proposition"].split()),
            "gold_source": "Wikidata",
            "gold_source_url": f"https://www.wikidata.org/wiki/{entities[0].qid}",
            "gold_source_date": dt.date.today().isoformat(),
            "temporal_validity": TemporalValidity.model_validate(temporal).model_dump(mode="json")
            if temporal
            else None,
            "ambiguity_notes": " ".join(spec.get("ambiguity_notes", "").split()),
            "prerequisite_atomic_facts": [
                PrerequisiteFact.model_validate(f).model_dump(mode="json")
                for f in spec.get("prerequisite_atomic_facts", [])
            ],
            "answer_type": spec["answer_type"],
            "answer_space": _answer_space(spec),
            "gold_answer": str(spec["gold_answer"]),
            "answer_aliases": spec.get("answer_aliases", {}),
            "split": Split.PILOT.value,
            "verification_status": status.value,
            "evidence": [e.model_dump(mode="json") for e in evidence],
            "review_notes": _review_notes(spec, discrepancies or []),
            "authored_by": "assistant draft — pending researcher review",
            "authored_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "notes": f"logical_form: {spec['logical_form']}",
        }
    )


def _answer_space(spec) -> list[str]:
    """Coerce the authored answer space, refusing YAML's boolean coercion.

    YAML 1.1 reads bare ``YES``/``NO`` as booleans, so an unquoted boolean answer
    space silently becomes ``['True', 'False']`` and every expected answer stops
    matching. That is a data-corrupting typo, not something to normalise away.
    """
    raw = spec["answer_space"]
    if any(isinstance(a, bool) for a in raw):
        raise ValueError(
            f"{spec['constraint_id']}: answer_space {raw} contains YAML booleans — "
            "quote them as [\"YES\", \"NO\"] in candidates.yaml"
        )
    return [str(a) for a in raw]


def _review_notes(spec, discrepancies=()) -> str:
    notes = [
        "Class assignment, wording and answer-space distractors all require human review.",
    ]
    for d in discrepancies:
        notes.append(f"ADJUDICATION REQUIRED — {' '.join((d.note or '').split())}")
    if spec["class"] in ("C2", "C3"):
        notes.append(
            "D0 predicate is a PLACEHOLDER that checks mutual exclusion only, not the "
            "conjunction/quantifier structure."
        )
    return " ".join(notes)


def _make_probes(constraint: Constraint, slots: dict, constraint_index: int) -> list[Probe]:
    probes: list[Probe] = []
    for i, cell in enumerate(cells_for_constraint(constraint_index, K_PILOT), start=1):
        r = realise(
            cell,
            slots=slots,
            answer_type=constraint.answer_type,
            gold_answer=constraint.gold_answer,
        )
        probes.append(
            Probe(
                constraint_id=constraint.constraint_id,
                probe_id=probe_id(constraint.constraint_id, i),
                logical_form=constraint.notes.removeprefix("logical_form: "),
                subject=constraint.entities[0],
                predicate=constraint.formal_predicate,
                object=constraint.gold_answer,
                time_scope=(
                    constraint.temporal_validity.start.isoformat()
                    if constraint.temporal_validity and constraint.temporal_validity.start
                    else ""
                ),
                quantifier="universal" if constraint.constraint_class is ConstraintClass.C3 else "none",
                polarity=cell.polarity.value,
                answer_type=r.answer_type.value,
                syntax=cell.syntax.value,
                register=cell.register.value,
                directionality=cell.directionality.value,
                factor_cell_index=cell.cell_index,
                probe_text=r.text,
                tier=Tier.PILOT.value,
                track=Track.A.value,
                expected_answer=r.expected_answer,
                validation_status=ValidationStatus.DRAFT.value,
                generated_at=dt.datetime.now(dt.timezone.utc).isoformat(),
                notes=f"form={r.form}; pilot_run_subset={'yes' if i <= 5 else 'no'}",
            )
        )
    return probes


def _check_distinct_texts(cid: str, probes: list[Probe], warnings: list[str]) -> None:
    seen: dict[str, str] = {}
    for p in probes:
        key = " ".join(p.probe_text.lower().split())
        if key in seen:
            warnings.append(
                f"{cid}: probes {seen[key]} and {p.probe_id} have identical text — "
                "identical surfaces inflate apparent agreement"
            )
        seen[key] = p.probe_id


def answer_type_by_class(constraints: list[Constraint]) -> dict[str, set[str]]:
    """Answer types used per class — surfaces a class/answer-type confound."""
    out: dict[str, set[str]] = {}
    for c in constraints:
        out.setdefault(c.constraint_class.value, set()).add(c.answer_type.value)
    return out


def unpopulated_sitelinks(constraints: list[Constraint]) -> list[str]:
    """Constraints whose entity familiarity metric has not been fetched (§4.3)."""
    return [c.constraint_id for c in constraints if all(s == 0 for s in c.entity_sitelinks)]
