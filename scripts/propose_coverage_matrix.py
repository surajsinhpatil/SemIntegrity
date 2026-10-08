#!/usr/bin/env python3
"""Emit the PROPOSED 120-constraint coverage matrix and dry-run it against the lattice.

This script authors **no constraints**. It declares an allocation — which schema
sits in which (family, class, domain) cell — and then proves that the allocation
closes under ``design_validator.py`` by instantiating 120 *structural
placeholders*: records that carry real ids, classes, domains, families and
schemas, and deliberately fake entities, gold answers and sources.

The placeholders exist so that "the lattice closes" is a check that RAN rather
than a claim in prose. They are never written to ``data/``. Their sitelinks are
all identical, which makes the familiarity-matching rule degenerate-but-honest
(it reports the degeneracy); real matching can only be tested once real entities
are chosen.

Usage::

    python scripts/propose_coverage_matrix.py              # markdown to stdout
    python scripts/propose_coverage_matrix.py --check      # lattice dry-run only

Status: PROPOSED. Nothing here is adopted. ADR-0002 (the lattice) and ADR-0003
(probe factors) are both still AWAITING RESEARCHER APPROVAL.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from semintegrity.benchmark.design_validator import (  # noqa: E402
    BenchmarkDesignValidator,
)
from semintegrity.schemas.constraint import Constraint  # noqa: E402
from semintegrity.schemas.enums import Split  # noqa: E402
from semintegrity.utils.ids import (  # noqa: E402
    DOMAIN_CODES,
    constraint_id,
    family_id,
    schema_id,
)

# ---------------------------------------------------------------------------
# Index allocation
#
# The pilot already occupies constraint index 01 in GEO/POL/SCI and family
# index 01 in those domains, and ADR-0007 sends those 12 records to DEV rather
# than into the 120. The id grammar carries no split marker, so a test set
# numbered 01..06 would mint K-C1-GEO-01 a SECOND time. design_validator
# validates one split at a time, so the collision would not be caught there.
#
# Renumbering the pilot is the worse option: its probe ids appear in the two
# byte-identical pilot result files, which ADR-0005 makes immutable. So the
# TEST set takes indices 11..16 and leaves 01..10 to pilot/dev.
# ---------------------------------------------------------------------------
TEST_INDEX_BASE = 10  # test cell indices are 11..16

DOMAINS: tuple[str, ...] = (
    "geography",
    "history",
    "biology",
    "public_office",
    "science_technology",
)
CLASSES: tuple[str, ...] = ("C1", "C2", "C3", "C4")


@dataclass(frozen=True)
class ClassRendering:
    """How one schema axis is rendered under one constraint class."""

    predicate: str
    logical_form: str
    requirement: str
    d0_status: str  # REGISTERED | PLACEHOLDER | TO_IMPLEMENT


@dataclass(frozen=True)
class Axis:
    """One schema axis: schema index ``n`` in every class, and family index ``n``
    in every domain.

    Because the §4.3 counts close exactly (30 families = 6 per domain x 5
    domains; 6 schemas per class x 5 instances), a fully crossed schema x domain
    design forces family to coincide with (domain, schema index). The axis is
    therefore the single organising unit: it names a family theme per domain and
    a schema per class.
    """

    index: int
    name: str
    idea: str
    answer_type: str
    renderings: dict[str, ClassRendering]
    themes: dict[str, str]  # domain -> family theme
    strain: tuple[str, ...] = ()  # (domain, class) cells expected to resist authoring


AXES: tuple[Axis, ...] = (
    Axis(
        index=1,
        name="Unique designated role-bearer",
        idea=(
            "A thing has exactly one designated bearer of a named functional role, "
            "and the role's answer space is closed."
        ),
        answer_type="entity",
        renderings={
            "C1": ClassRendering(
                "c1_mutual_exclusion",
                "role_of(E) = ?x",
                "one proposition; naming a second bearer contradicts the first",
                "REGISTERED",
            ),
            "C2": ClassRendering(
                "c2_role_conjunction",
                "role_of(E) = ?x AND property(?x)",
                "the bearer must satisfy the role AND a second predicate jointly",
                "PLACEHOLDER",
            ),
            "C3": ClassRendering(
                "c3_functional_uniqueness",
                "forall x: type(x) -> exists! y: role(x, y)",
                "universally quantified uniqueness, then bound to one instance",
                "PLACEHOLDER",
            ),
            "C4": ClassRendering(
                "c4_role_interval",
                "role_at(E, t) = ?x ; t within validity(?x)",
                "the role-holding is interval-bounded; the bearer differs by date",
                "TO_IMPLEMENT",
            ),
        },
        themes={
            "geography": "the capital city of a country",
            "history": "the capital of a historical polity",
            "biology": "the designated reference standard for a taxon",
            "public_office": "the holder of a single-seat head-of-state office",
            "science_technology": "the designated standard for a physical quantity",
        },
    ),
    Axis(
        index=2,
        name="Disjoint category membership",
        idea=(
            "Two categories are mutually exclusive by definition, so membership of "
            "one entails non-membership of the other."
        ),
        answer_type="boolean",
        renderings={
            "C1": ClassRendering(
                "c1_mutual_exclusion",
                "member(E, A) AND NOT member(E, B)",
                "one proposition over a closed two-category space",
                "REGISTERED",
            ),
            "C2": ClassRendering(
                "c2_conjunction",
                "member(E, A) AND trait(E, T)",
                "two propositions that must hold jointly of one entity",
                "PLACEHOLDER",
            ),
            "C3": ClassRendering(
                "c3_universal_disjointness",
                "forall x: member(x, A) -> NOT member(x, B)",
                "the disjointness is stated universally, then instantiated",
                "TO_IMPLEMENT",
            ),
            "C4": ClassRendering(
                "c4_category_revision",
                "member_at(E, A, t) ; valid(A-membership, [t0, t1])",
                "the category assignment itself holds only over an interval",
                "TO_IMPLEMENT",
            ),
        },
        themes={
            "geography": "coastal versus landlocked states",
            "history": "wartime alliance membership",
            "biology": "category membership of a vertebrate taxon",
            "public_office": "constitutionally incompatible offices",
            "science_technology": "periodic-table group membership",
        },
    ),
    Axis(
        index=3,
        name="Part-whole containment",
        idea=(
            "A containment hierarchy in which each part sits in exactly one whole "
            "at a given level, and containment composes."
        ),
        answer_type="entity",
        renderings={
            "C1": ClassRendering(
                "c1_mutual_exclusion",
                "contained_in(E, level) = ?x",
                "one containment proposition at one level",
                "REGISTERED",
            ),
            "C2": ClassRendering(
                "c2_two_level_containment",
                "contained_in(E, L1) = ?x AND contained_in(?x, L2) = ?y",
                "containment must hold jointly at two levels",
                "TO_IMPLEMENT",
            ),
            "C3": ClassRendering(
                "c3_containment_transitivity",
                "forall x,y,z: in(x,y) AND in(y,z) -> in(x,z)",
                "transitivity stated universally, then instantiated",
                "TO_IMPLEMENT",
            ),
            "C4": ClassRendering(
                "c4_containment_interval",
                "in_at(E, ?x, t) ; t within validity(in(E, ?x))",
                "containment that changed; the answer depends on the date",
                "TO_IMPLEMENT",
            ),
        },
        themes={
            "geography": "city within a first-level administrative division",
            "history": "province within an empire",
            "biology": "a taxon within a higher taxon",
            "public_office": "constituency within a federal unit",
            "science_technology": "module within a crewed spacecraft",
        },
        # biology/C4 resisted under Revision 4-5 (taxonomic P171 carries no date
        # qualifiers anywhere in Wikidata) and is AUTHORED under Revision 6: the
        # ORIGINAL COMBINATION (P1403) and its P574 publication-year qualifier
        # date the superseded placement, so the containing taxon differs by date.
        strain=(),
    ),
    Axis(
        index=4,
        name="Event precedence",
        idea=(
            "Two dated events stand in a fixed order, and the order is derivable "
            "from the dates without naming them."
        ),
        answer_type="date",
        renderings={
            "C1": ClassRendering(
                "s_c1_04",
                "occurred_in(E) = ?d",
                "one dated proposition over a closed candidate set",
                "EXCL + ANCHOR",
            ),
            "C2": ClassRendering(
                "s_c2_04",
                "occurred_in(A) = ?d AND occurred_in(B) = ?d",
                "two events that must share one boundary year",
                "EXCL + ANCHOR",
            ),
            "C3": ClassRendering(
                "s_c3_04",
                "forall x: work(x) -> date(x) > birth(author(x))",
                "a universal ordering law, then bound to one instance",
                "EXCL + ANCHOR",
            ),
            "C4": ClassRendering(
                "s_c4_04",
                "start(earlier(A, B)) = ?d",
                "the earlier of two intervals, answered as its boundary date",
                "EXCL + ANCHOR",
            ),
        },
        themes={
            "geography": "the opening of major interoceanic canals",
            "history": "the onset of the Atlantic revolutions",
            "biology": "landmark results in molecular genetics",
            "public_office": "decolonisation independence dates",
            "science_technology": "milestones in solid-state electronics",
        },
        strain=(
            "biology/C2",  # two landmark results sharing one publication year is scarce
        ),
    ),
    Axis(
        index=5,
        name="Extremal uniqueness",
        idea=(
            "A superlative over a closed comparison set has exactly one bearer, "
            "and the comparison set must be stated to make it well-defined."
        ),
        answer_type="boolean",
        renderings={
            "C1": ClassRendering(
                "s_c1_05",
                "argmax(measure, set) = E",
                "one superlative proposition over a stated set, as a closed yes/no",
                "EXCL",
            ),
            "C2": ClassRendering(
                "s_c2_05",
                "argmax(measure, set) = E AND member(E, S2)",
                "the extremal bearer must also satisfy a second membership",
                "EXCL",
            ),
            "C3": ClassRendering(
                "s_c3_05",
                "forall S: finite(S) -> exists! x: argmax(measure, S) = x",
                "uniqueness of the maximum stated universally, then instantiated",
                "EXCL",
            ),
            "C4": ClassRendering(
                "s_c4_05",
                "argmax(measure, set, window=[t0, t1]) = E",
                "the comparison set is restricted to a named interval",
                "EXCL",
            ),
        },
        themes={
            "geography": "the highest summit of a named region",
            "history": "the longest reign in a named monarchy",
            "biology": "the largest extant species of a clade",
            "public_office": "the longest-serving holder of a named office",
            "science_technology": "the heaviest naturally occurring element",
        },
        # Both resisted under Revision 4 and are now AUTHORED. sci/C4 is anchored
        # on uranium's 1789 discovery date rather than on a trivia window;
        # geo/C4 uses the Revision 5 re-theme ("named region"), which lets the
        # comparison set be scoped to a polity with a recorded end date
        # (Soviet Union, P576 = 1991-12-26) instead of to summit heights, which
        # are indeed not interval-scoped in Wikidata.
        strain=(),
    ),
    Axis(
        index=6,
        name="Interval boundary",
        idea=(
            "An entity or arrangement has a terminating boundary date, and nothing "
            "it did may be placed outside its interval."
        ),
        answer_type="date",
        renderings={
            "C1": ClassRendering(
                "c1_mutual_exclusion",
                "end_date(E) = ?d",
                "one date proposition over a closed candidate set",
                "REGISTERED",
            ),
            "C2": ClassRendering(
                "c2_boundary_conjunction",
                "end_date(A) = ?d AND start_date(B) = ?d",
                "two boundary propositions that must coincide",
                "TO_IMPLEMENT",
            ),
            "C3": ClassRendering(
                "c3_interval_wellformedness",
                "forall x: end(x) >= start(x)",
                "interval well-formedness stated universally",
                "TO_IMPLEMENT",
            ),
            "C4": ClassRendering(
                "c4_interval_precedence",
                "NOT overlaps(interval(A), interval(B))",
                "non-overlap of successive intervals",
                "REGISTERED",
            ),
        },
        themes={
            "geography": "the dissolution of a federal state",
            "history": "the end of a classical empire",
            "biology": "the extinction date of a named species",
            "public_office": "the abolition of a colonial office",
            "science_technology": "the end of a crewed spaceflight programme",
        },
        strain=(
            "biology/C2",  # an extinction date coinciding with another start date is rare
        ),
    ),
)


# ---------------------------------------------------------------------------
# Allocation
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Cell:
    constraint_id: str
    family_id: str
    schema_id: str
    domain: str
    cls: str
    axis: Axis

    @property
    def answer_type(self) -> str:
        """ADR-0017 as amended: a function of (axis, class)."""
        return answer_type_for(self.axis.index, self.cls)

    @property
    def rendering(self) -> ClassRendering:
        return self.axis.renderings[self.cls]

    @property
    def theme(self) -> str:
        return self.axis.themes[self.domain]


def allocate() -> list[Cell]:
    """The 120 cells.

    Family index == axis index within a domain, and schema index == axis index
    within a class. That identity is not a stylistic choice: with 6 families per
    domain, 6 schemas per class, one constraint per (schema, domain) cell and
    one constraint per class per family, the fully crossed design admits exactly
    this structure up to relabelling.
    """
    cells: list[Cell] = []
    for domain in DOMAINS:
        for axis in AXES:
            idx = TEST_INDEX_BASE + axis.index
            for cls in CLASSES:
                cells.append(
                    Cell(
                        constraint_id=constraint_id(cls, domain, idx),
                        family_id=family_id(domain, idx),
                        schema_id=schema_id(cls, axis.index),
                        domain=domain,
                        cls=cls,
                        axis=axis,
                    )
                )
    return cells


# ---------------------------------------------------------------------------
# Lattice dry-run
# ---------------------------------------------------------------------------
def _placeholder(cell: Cell) -> Constraint:
    """A structural placeholder. The ids and lattice fields are the proposal;
    everything else is visibly fake so it can never be mistaken for a record."""
    if cell.answer_type == "boolean":
        space, gold = ["YES", "NO"], "YES"
    else:
        space, gold = ["PLACEHOLDER_A", "PLACEHOLDER_B"], "PLACEHOLDER_A"
    return Constraint.model_validate(
        {
            "constraint_id": cell.constraint_id,
            "family_id": cell.family_id,
            "schema_id": cell.schema_id,
            "domain": cell.domain,
            "class": cell.cls,
            "formal_predicate": cell.rendering.predicate,
            "constraint_text": f"PLACEHOLDER — not authored ({cell.axis.name}, {cell.cls})",
            "entities": ["PLACEHOLDER"],
            "entity_qids": ["Q0"],
            "entity_sitelinks": [0],
            "gold_proposition": f"PLACEHOLDER {cell.constraint_id}",
            "gold_source": "NOT AUTHORED",
            "gold_source_url": "about:blank",
            "gold_source_date": dt.date(2026, 10, 6),
            "answer_type": cell.answer_type,
            "answer_space": space,
            "gold_answer": gold,
            # C4 is defined by interval reasoning, so the record requires a
            # validity interval. A placeholder interval is supplied to let the
            # LATTICE be checked; it asserts nothing about any real fact.
            "temporal_validity": (
                {"start": "1900-01-01", "end": None, "end_unknown": True, "precision": "year"}
                if cell.cls == "C4"
                else None
            ),
            "split": Split.TEST,
            "notes": "structural placeholder emitted by scripts/propose_coverage_matrix.py",
        }
    )


def dry_run(cells: list[Cell]) -> tuple[bool, str]:
    stubs = [_placeholder(c) for c in cells]
    validator = BenchmarkDesignValidator()
    report = validator.validate(stubs, split=Split.TEST, strict_schema_crossing=True)
    return report.ok, str(report)


PILOT_CONSTRAINTS = REPO / "data/benchmark/pilot/constraints.jsonl"


def id_collision_check(cells: list[Cell]) -> tuple[bool, str]:
    """Cross-split id collision, which `design_validator` cannot see.

    ``validate()`` filters to one split before checking ``unique_ids``, so a test
    constraint and a pilot constraint sharing an id both pass. The id grammar has
    no split field, so the only defence is the index allocation. This check runs
    the allocation against the ids that actually exist on disk, and against the
    counterfactual 01..06 allocation, so the claim is demonstrated rather than
    asserted.
    """
    import json

    if not PILOT_CONSTRAINTS.exists():  # pragma: no cover - defensive
        return True, f"SKIPPED: {PILOT_CONSTRAINTS} not found"

    existing = {
        json.loads(line)["constraint_id"] for line in PILOT_CONSTRAINTS.read_text().splitlines() if line.strip()
    }
    proposed = {c.constraint_id for c in cells}
    clash = sorted(existing & proposed)

    counterfactual = {
        constraint_id(c.cls, c.domain, c.axis.index) for c in cells
    }
    cf_clash = sorted(existing & counterfactual)

    lines = [
        f"existing ids on disk (pilot -> dev per ADR-0007): {len(existing)}",
        f"proposed test ids (index {TEST_INDEX_BASE + 1}..{TEST_INDEX_BASE + 6}): {len(proposed)}",
        f"collisions with the proposed allocation: {len(clash)}"
        + (f" -> {clash}" if clash else "  <- none"),
        f"collisions had test been numbered 01..06: {len(cf_clash)}"
        + (f" -> {', '.join(cf_clash)}" if cf_clash else ""),
    ]
    return not clash, "\n".join(lines)


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------
# --- D0 scope -------------------------------------------------------------
# Revision 2 onward. Revision 1 named 24 schema-specific predicates, 12 of which did not
# exist. Only TWO D0 behaviours are implemented, and only two are decidable from a
# Track A response at all:
#
#   EXCL    closed-space mutual exclusion. Schema-GENERAL (its own docstring says
#           so), carries no facts, uses no KB. Over a closed, mutually exclusive
#           answer space -- which §4.7 requires of every constraint -- pairwise
#           contradiction IS "the canonical answers differ". Covers all 24.
#   ANCHOR  temporal anchor precedence. The only predicate that decides something
#           EXCL cannot: a SINGLE response preceding temporal_validity.start, even
#           when both responses agree. Needs a parseable DATE answer, so it applies
#           only where the axis answer type is `date`.
#
# C2 and C3 structure is NOT decidable from a Track A response: the probe asks the
# conjunction or the instantiated claim as a whole and the model returns one token,
# so a model that checked one conjunct is indistinguishable from one that checked
# both, and nothing in the response carries the quantifier or its variable binding.
# That is a design fact, not a missing implementation.
STRUCTURALLY_DECIDABLE: tuple[str, ...] = ("C1", "C4")


def d0_behaviour(axis: Axis, cls: str | None = None) -> str:
    """ANCHOR requires a parseable DATE answer, so it follows (axis, class).

    Under the amended rule C2 and C3 are boolean on every axis, so a temporal
    anchor could never apply to them: their canonical answers are YES/NO and
    never parse as dates. Claiming it would be a formal statement the predicate
    cannot honour.
    """
    if cls is None:  # axis-level summary: ANCHOR where ANY class is date-typed
        is_date = any(answer_type_for(axis.index, c) == "date" for c in CLASSES)
    else:
        is_date = answer_type_for(axis.index, cls) == "date"
    return "EXCL + ANCHOR" if is_date else "EXCL"


def d0_note(cls: str) -> str:
    return "" if cls in STRUCTURALLY_DECIDABLE else "N/A-struct"


#: Chance agreement between two independent draws from a closed space of size m is
#: 1/m, so the chance "contradiction" rate is 1 - 1/m.
CARDINALITY: dict[str, int] = {"entity": 3, "boolean": 2, "date": 3}


def _answer_type_rule() -> dict:
    """ADR-0017's answer-type rule, read from configs/benchmark/design.yaml.

    Kept in the config rather than duplicated here so there is exactly one
    executable statement of the rule. Amended 2026-10-07 (Option B): answer type
    is a function of (axis, class), not of the axis alone.
    """
    from semintegrity.utils.config import load_config

    return load_config("configs/benchmark/design.yaml").data["lattice"]["answer_type"]


def answer_type_for(axis_index: int, cls: str) -> str:
    """The answer type of the (axis, class) cell.

    C2 and C3 are `boolean` on every axis. A conjunction and a universal have no
    single binary subject-relation-object, and the approved probe generator routes
    a direct+affirmative probe of an entity/date-answered constraint through
    ``_realise_open``, which requires exactly that. C1 and C4 retain the
    axis-fixed allocation.
    """
    rule = _answer_type_rule()
    per_class = rule["rule"][cls]
    if per_class == "per_axis":
        return str(rule["per_axis"][axis_index])
    return str(per_class)


def date_axes() -> tuple[int, ...]:
    return tuple(_answer_type_rule()["date_axes"])


def chance_pscr(m: int) -> float:
    return 1.0 - 1.0 / m


def markdown(cells: list[Cell], ok: bool, report: str, id_ok: bool, id_report: str) -> str:
    out: list[str] = []
    w = out.append

    w("# 120-constraint coverage matrix — Revision 6")
    w("")
    w("**Status: ADOPTED AS THE AUTHORING PLAN, 2026-10-06.** The allocation below")
    w("is approved (researcher decisions A1-A6). **No constraint is authored yet** —")
    w("this file carries no entities, QIDs, gold answers or sources.")
    w("Generated by `scripts/propose_coverage_matrix.py`; regenerate rather than edit.")
    w("")
    w("**Revision 6 (2026-10-08)** re-themes the ONE cell Revision 5 left")
    w("unfilled, axis 3 / biology, on the same terms. Same 120 constraint ids,")
    w("families, schemas, domains, axes and answer types.")
    w("")
    w("| axis | domain | was | now |")
    w("|---|---|---|---|")
    w("| 3 | biology | genus within a family | a taxon within a higher taxon |")
    w("")
    w("This is a WIDENING that makes the matrix MORE faithful to what was")
    w("already authored, not less: the dev family F-BIO-03's C1 cell is")
    w("tiger -> Panthera, a SPECIES within a GENUS, which the Revision-4")
    w("wording never described. Every authored C1/C2/C3 cell in both biology")
    w("axis-3 families is a taxon nested in a higher taxon and remains a")
    w("truthful instance; none was re-authored.")
    w("")
    w("It admits the C4 cell because the SUPERSEDED placement is dated even")
    w("though P171 is not: Wikidata records the original combination (P1403)")
    w("as its own taxon item, whose P225 carries a P574 publication-year")
    w("qualifier and whose P171 names the ORIGINAL genus. The lion (Q140) was")
    w("published as Felis leo (Q15294488) in Felis (Q228283) in 1758 and now")
    w("sits in Panthera (Q127960), so the containing taxon genuinely differs")
    w("by date. The TRANSFER date is not recorded and is not invented.")
    w("")
    w("**Revision 5 (2026-10-08)** re-themes FOUR (axis, domain) cells whose")
    w("themes could not host a C4 cell, under the Q29 decision. Same 120")
    w("constraint ids, families, schemas, domains, axes and answer types — only")
    w("the theme strings change, and only where the theme made the temporal")
    w("variant unauthorable:")
    w("")
    w("| axis | domain | was | now |")
    w("|---|---|---|---|")
    w("| 1 | biology | the type species of a genus | the designated reference standard for a taxon |")
    w("| 1 | science_technology | the SI base unit of a physical quantity | the designated standard for a physical quantity |")
    w("| 2 | biology | vertebrate class membership | category membership of a vertebrate taxon |")
    w("| 5 | geography | the highest summit of a continent | the highest summit of a named region |")
    w("")
    w("Each is a WIDENING, chosen so the already-authored and")
    w("EVIDENCE_VERIFIED C1/C2/C3 cells of those families remain truthful")
    w("instances of the new theme. A type species IS the nomenclatural")
    w("reference standard for a genus name; taxonomic class membership IS")
    w("category membership; a continent IS a named region; an SI base unit IS")
    w("a designated standard. Nothing authored was discarded.")
    w("")
    w("**axis 3 / biology is NOT re-themed and its C4 cell stays unfilled.**")
    w("No dated part-whole containment exists for a biological entity in")
    w("Wikidata: taxonomic containment carries no date qualifiers anywhere")
    w("(checked across Felidae, viruses, diseases and taxa with competing")
    w("classifications), and neither CITES Appendix (P7603), IUCN status")
    w("(P141) nor individual organisms carry dated containment. It is marked")
    w("`strain` on axis 3 and recorded in Q29.")
    w("")
    w("**Revision 4 (2026-10-07)** applies the approved ADR-0017 amendment")
    w("(Option B): answer type is a function of **(axis, class)**, with C2 and C3")
    w("`boolean` on every axis. **The allocation of cells is byte-identical to")
    w("Revision 3** — the same 120 constraint ids, families, schemas and domains;")
    w("only the derived answer-type column changes, and with it D0's `ANCHOR`")
    w("reach, which now covers C1/C4 on the two date axes only.")
    w("")
    w("**Revision 3 (2026-10-06)** applied the approved decisions: **two date axes**")
    w("(A4), so axis 4 becomes `date` and axis 5 becomes `boolean`, giving 10/10/10")
    w("per class; and the per-schema D0 registration scope (A5), now implemented in")
    w("`src/semintegrity/detectors/d0/predicates/schema_registrations.py`.")
    w("Revision 2 replaced Revision 1's D0 column, which named 24 schema-specific")
    w("predicates of which 12 did not exist, and added answer-space cardinality and")
    w("chance-PSCR. See `docs/DESIGN_RESOLUTION_2026-10-06.md`.")
    w("")
    w("This file declares an *allocation*: which schema occupies which")
    w("(family, class, domain) cell, and what each schema asks for. It contains no")
    w("entities, no QIDs, no gold answers and no sources — those are the authoring")
    w("work this matrix is meant to direct.")
    w("")

    # --- axes --------------------------------------------------------------
    w("## 1. The six schema axes")
    w("")
    w("\u00a74.3 asks for 6-8 schemas per class, each instantiated 4-5 times, *and* 6")
    w("families per domain, *and* one constraint per class per family. Those counts")
    w("close only if family coincides with (domain, schema index). So one axis")
    w("defines, at once, a family theme in each of the 5 domains and a schema in")
    w("each of the 4 classes: 6 axes → 30 families → 24 schemas → 120 constraints.")
    w("")
    w("| # | axis | C1 | C2 | C3 | C4 | the invariant it tests |")
    w("|---|---|---|---|---|---|---|")
    for a in AXES:
        types = " | ".join(f"`{answer_type_for(a.index, c)}`" for c in CLASSES)
        w(f"| {a.index} | **{a.name}** | {types} | {a.idea} |")
    w("")
    w("**Answer type is a function of (axis, class)** — ADR-0017 as amended")
    w("2026-10-07. C2 and C3 are `boolean` on every axis: a conjunction and a")
    w("universal have no single binary subject-relation-object, and the approved")
    w("probe generator routes a direct+affirmative probe of an entity/date-answered")
    w("constraint through `_realise_open`, which requires exactly that. C1 and C4")
    w("retain the axis-fixed allocation. The allocation of CELLS is untouched.")
    w("")
    per_cls = {
        c: sum(chance_pscr(CARDINALITY[answer_type_for(a.index, c)]) for a in AXES) / len(AXES)
        for c in CLASSES
    }
    conf_a = (per_cls["C1"] + per_cls["C2"]) / 2
    conf_b = (per_cls["C3"] + per_cls["C4"]) / 2
    w("chance-PSCR is 1 - 1/*m*, where *m* is the closed answer space's size: the")
    w("contradiction rate two independent draws would produce before any model")
    w("behaviour is involved. Under the amended rule:")
    w("")
    w("| | C1 | C2 | C3 | C4 |")
    w("|---|---|---|---|---|")
    w("| chance-PSCR | " + " | ".join(f"{per_cls[c]:.3f}" for c in CLASSES) + " |")
    w("")
    w(f"**Confirmatory contrast C1+C2 vs C3+C4: {conf_a:.3f} vs {conf_b:.3f}, gap")
    w(f"{abs(conf_a - conf_b):.3f}** — exactly balanced, and §4.11 rests the claim")
    w("on that contrast. The four-class **descriptive** profile carries a")
    w(f"{max(per_cls.values()) - min(per_cls.values()):.3f} spread, against 0.000 under the original")
    w("axis-only rule and 0.167 under a fully class-tied one. Answer type enters")
    w("the secondary model as a **covariate**, never as an experimental factor.")
    w("This allocation is an **interpretation** of §4.3's \"comparable answer")
    w("type\", not a requirement of it; see ADR-0017 and")
    w("`docs/DESIGN_RESOLUTION_2026-10-06.md` §3.")
    w("")

    # --- schemas -----------------------------------------------------------
    w("## 2. The 24 schemas")
    w("")
    w("Each axis is rendered once per class. The structural requirement changes")
    w("down each block; the domain, answer type and entity familiarity do not —")
    w("which is the nuisance control §4.3 asks families to provide.")
    w("")
    w("| schema | axis | class | answer | structural requirement | logical form | D0 |")
    w("|---|---|---|---|---|---|---|")
    for a in AXES:
        for cls in CLASSES:
            r = a.renderings[cls]
            note = d0_note(cls)
            d0 = d0_behaviour(a, cls) + (f" · {note}" if note else "")
            w(
                f"| `{schema_id(cls, a.index)}` | {a.index} | {cls} | {r.requirement} "
                f"| `{r.logical_form}` | {d0} |"
            )
    w("")
    n_anchor = sum(
        1 for a in AXES for c in CLASSES if answer_type_for(a.index, c) == "date"
    )
    n_struct = sum(1 for cls in CLASSES if cls not in STRUCTURALLY_DECIDABLE) * len(AXES)
    w("**D0 scope.** Two behaviours are implemented and two are decidable at all:")
    w("")
    w("* **`EXCL`** — closed-space mutual exclusion. `c1_mutual_exclusion` documents")
    w("  itself as *schema-general*, carries no facts and uses no knowledge base.")
    w("  Over a closed, mutually exclusive answer space — which §4.7 requires of")
    w(f"  every constraint — contradiction *is* \"the answers differ\". Covers {len(AXES) * len(CLASSES)}/24.")
    w("* **`ANCHOR`** — temporal anchor precedence. The only predicate that decides")
    w("  something `EXCL` cannot: a *single* response preceding")
    w("  `temporal_validity.start`, even when both responses agree. Needs a")
    w(f"  parseable date answer, so it reaches {n_anchor}/24 schemas under this allocation.")
    w(f"* **`N/A-struct`** ({n_struct}/24, every C2 and C3 schema) — the class's structure is")
    w("  not decidable from a Track A response. The probe asks the conjunction or")
    w("  the instantiated claim as a whole and the model returns one token, so a")
    w("  model that checked one conjunct is indistinguishable from one that checked")
    w("  both, and nothing in the response carries the quantifier or its variable")
    w("  binding. A design fact, not a missing implementation.")
    w("")
    w("So the minimum predicate scope is **no new detection logic**: 24 thin")
    w("per-schema registrations over the two existing behaviours, each carrying its")
    w("own `schema_id`, `version` and `formal_statement` so §4.8.2's three-instance")
    w("audit is per-schema and the freeze manifest records what each does *not*")
    w("formalise. D0 coverage per class is a reported result in its own right")
    w("(§4.8.1), so stating the limit is the requirement, not a concession.")
    w("")

    # --- families ----------------------------------------------------------
    w("## 3. The 30 families")
    w("")
    w("| family | domain | axis | theme |")
    w("|---|---|---|---|")
    for domain in DOMAINS:
        for a in AXES:
            fid = family_id(domain, TEST_INDEX_BASE + a.index)
            w(f"| `{fid}` | {domain} | {a.index} | {a.themes[domain]} |")
    w("")

    # --- allocation --------------------------------------------------------
    w(f"## 4. The {len(cells)} cells")
    w("")
    w("One block per domain. Each row is a family: four constraints, one per")
    w("class, sharing the domain, the theme and the answer type.")
    w("")
    by_class: dict[str, dict[str, int]] = {}
    for c in cells:
        by_class.setdefault(c.cls, {}).setdefault(c.answer_type, 0)
        by_class[c.cls][c.answer_type] += 1
    w("Answer type per class, counted from the allocation itself:")
    w("")
    w("| class | `entity` | `boolean` | `date` | chance-PSCR |")
    w("|---|---|---|---|---|")
    for cls in CLASSES:
        row = by_class[cls]
        mean = sum(
            chance_pscr(CARDINALITY[c.answer_type]) for c in cells if c.cls == cls
        ) / sum(1 for c in cells if c.cls == cls)
        w(
            f"| {cls} | {row.get('entity', 0)} | {row.get('boolean', 0)} "
            f"| {row.get('date', 0)} | {mean:.3f} |"
        )
    w("")
    w("C1 and C4 carry the axis-fixed mix; C2 and C3 are boolean throughout. The")
    w("mix is identical for C1 and C4, and identical for C2 and C3, which is what")
    w("keeps the confirmatory contrast C1+C2 vs C3+C4 balanced.")
    w("")
    for domain in DOMAINS:
        code = DOMAIN_CODES[domain]
        w(f"### {domain} (`{code}`)")
        w("")
        w("| family | theme | answer C1/C2/C3/C4 | C1 | C2 | C3 | C4 |")
        w("|---|---|---|---|---|---|---|")
        for a in AXES:
            idx = TEST_INDEX_BASE + a.index
            ids = " | ".join(f"`{constraint_id(cls, domain, idx)}`" for cls in CLASSES)
            w(
                f"| `{family_id(domain, idx)}` | {a.themes[domain]} "
                f"| `{a.answer_type}` | {ids} |"
            )
        w("")

    # --- strain ------------------------------------------------------------
    w("## 5. Cells expected to resist authoring (Q12 evidence)")
    w("")
    strained = [(a, s) for a in AXES for s in a.strain]
    if strained:
        w("A fully crossed 6x5 design is attempted first, as Q12 directs. These are")
        w("the cells where that attempt is predicted to fail, and they are recorded")
        w("*before* authoring so that a later relaxation is a measured retreat and")
        w("not a convenience:")
        w("")
        w("| axis | cell | why |")
        w("|---|---|---|")
        notes = {
            "science_technology/C4": "a window-restricted 'heaviest known element' reduces to trivia about discovery dates",
            "geography/C4": "summit elevation carries no P580/P582 interval in Wikidata, so the window is artificial",
            "biology/C2": "scarce — for axis 4, two landmark results sharing a publication year; for axis 6, an extinction date coinciding with another interval's start",
        }
        for a, s in strained:
            w(f"| {a.index} {a.name} | `{s}` | {notes.get(s, '—')} |")
    else:
        w("None predicted.")
    w("")
    w("Q12's fallback (a balanced incomplete schema x domain allocation) is")
    w("**not** invoked here: the allocation above is fully crossed. These three")
    w("cells are the places to look first if authoring proves otherwise.")
    w("")

    # --- dry run -----------------------------------------------------------
    w("## 6. Lattice dry-run")
    w("")
    w("The allocation was instantiated as 120 structural placeholders — real ids,")
    w("classes, domains, families, schemas; visibly fake entities and gold answers —")
    w("and run through `design_validator.py` with `strict_schema_crossing=True`.")
    w("The placeholders are never written to `data/`.")
    w("")
    w("```")
    w(report)
    w("```")
    w("")
    w(f"**Lattice closes: {'YES' if ok else 'NO'}.**")
    w("")
    w("`sitelink_matching` is **vacuous** here: every placeholder carries 0")
    w("sitelinks, so the rule reports perfect matching by degeneracy. Entity")
    w("familiarity can only be tested once real entities are chosen, and §4.3")
    w("calls that confound the most damaging alternative explanation for any class")
    w("effect. It must be re-run, for real, before the freeze.")
    w("")

    # --- id collision ------------------------------------------------------
    w("## 7. Cross-split id collision")
    w("")
    w("`design_validator.validate()` filters to one split before checking")
    w("`unique_ids`, and the id grammar has no split field. A test constraint and")
    w("a pilot/dev constraint sharing an id therefore pass both validations and")
    w("merge in any analysis that joins on `constraint_id`. The index allocation")
    w("is the only defence, so it is checked against what is actually on disk:")
    w("")
    w("```")
    w(id_report)
    w("```")
    w("")
    w(f"**No cross-split collision: {'YES' if id_ok else 'NO'}.**")
    w("")

    # --- what must be decided ---------------------------------------------
    w("## 8. Decision record")
    w("")
    w("All four methodology items below were settled on 2026-10-06. They are kept")
    w("here, with their evidence, because the allocation above is unreadable without")
    w("knowing which readings of §4.3 and §4.8 it rests on.")
    w("")
    w("### M1 — ADR-0002 and ADR-0003 (APPROVED 2026-10-06)")
    w("")
    w("This matrix is an instance of ADR-0002's lattice, and the 960 probes it")
    w("implies are an instance of ADR-0003's factor balancing. Both were approved")
    w("on 2026-10-06, which is what makes authoring against this allocation safe:")
    w("rejection after authoring would have re-keyed all 120 records.")
    w("")
    w("### M2 — answer type: an interpretation, not a requirement (DECIDED)")
    w("")
    w("§4.3 asks families to hold nuisance variation **approximately constant**")
    w("across classes, listing *\"comparable answer type\"* among them. Its words")
    w("are \"approximately\" and \"comparable\", not \"identical\" — and")
    w("`answer_type` is not one of §4.3's 17 per-constraint fields at all. It is a")
    w("*probe* field in §4.4.1, and §4.7 positively expects it to vary within a")
    w("constraint, since directionality \"mixes 'Is A the X of B?' (yes/no) with")
    w("'What is the X of B?' (an entity)\". §4.4.2 reserves \"balanced exactly")
    w("across classes\" for the four probe transformation factors, which do not")
    w("include answer type.")
    w("")
    w("The axis-fixed allocation above therefore **satisfies** §4.3 but is not")
    w("**required** by it. The 12 pilot constraints tie answer type to class")
    w("instead (C1 `entity`, C2/C3 `boolean`, C4 `date`), which is a perfect")
    w("functional dependence and harder to defend as \"approximately constant")
    w("across classes\" — but it is a deviation from a soft requirement, not a")
    w("violation of a hard one. §1 above gives the quantified difference. Two")
    w("consequences of the axis-fixed choice are real costs:")
    w("")
    w("* `ANCHOR` reaches only the `date` axes, so D0's structural coverage on C4")
    w("  is 10/30 under the approved two-date-axis allocation, against 30/30 had")
    w("  answer type stayed tied to class and 5/30 with a single date axis;")
    w("* the 12 pilot constraints stop being instances of these 24 schemas, so")
    w("  ADR-0007's \"dev constraints reuse the **same schemas**\" needs re-wording")
    w("  or 12 dev constraints that do match.")
    w("")
    w("**Decided 2026-10-06 (A3 + A4):** axis-fixed answer type with answer-space")
    w("cardinality retained as a covariate, and two `date` axes. Recorded in")
    w("`docs/decisions/ADR-0017-answer-type-allocation.md`. The three-way")
    w("comparison is in `docs/DESIGN_RESOLUTION_2026-10-06.md` §3.")
    w("")
    w("### M3 — the accounting (CONFIRMED 2026-10-06, A7)")
    w("")
    w("ADR-0007 makes the 120 the test set and sends the 12 pilot constraints into a")
    w("separate 24-constraint dev set, disjoint from the 120. The authoring job is")
    w("therefore **120 new test constraints** — not 108 — plus 12 more dev")
    w("constraints to bring dev to 24: **144 at freeze, 132 newly authored**, and")
    w("**1,056 new primary probes** (960 test + 96 new dev; the existing 96 pilot")
    w("probes stay as pilot/dev material). See `docs/BENCHMARK_ACCOUNTING.md`.")
    w("")
    w("### M4 — D0 predicate scope (DECIDED)")
    w("")
    w("The minimum scope is **no new detection logic** — see §2's D0 note. What")
    w("needs deciding is whether to accept that limit or change what the probes")
    w("ask. Genuine C2 and C3 predicates are not constructible from a Track A")
    w("response; making them constructible would mean probing conjuncts or")
    w("quantifier instances separately, or admitting knowledge-screen answers into")
    w("D0 — and §4.11 makes prerequisite conditioning \"a reporting view, never an")
    w("inclusion criterion\". Either route is a redesign, not an implementation")
    w("task. Accepting the limit costs nothing but honesty in the write-up, since")
    w("§4.8.1 already treats D0 coverage as a result.")
    w("")
    w("### E1 — index allocation (engineering, proposed as taken)")
    w("")
    w("Test constraints and families take index **11..16**; 01..10 stays with")
    w("pilot/dev. Section 7 shows the alternative collides on all 12 existing ids,")
    w("and renumbering the pilot instead would desynchronise the two byte-identical")
    w("pilot result files that ADR-0005 makes immutable.")
    w("")
    w("### Also needed, and not blocking this matrix")
    w("")
    w("* `_unique_ids` claims in its docstring to check that *family and schema ids")
    w("  are well-formed and unique*; it only checks `constraint_id` duplicates.")
    w("  Pattern 8 in `HANDOFF.md` — a guard that cannot fire.")
    w("* Entity selection must satisfy `sitelink_matching` for real (Kruskal-Wallis")
    w("  p > 0.10 across classes). Section 6's PASS is degenerate and proves")
    w("  nothing about familiarity.")
    w("")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="run the lattice dry-run only")
    ap.add_argument("-o", "--out", type=Path, help="write markdown here instead of stdout")
    args = ap.parse_args()

    cells = allocate()
    ok, report = dry_run(cells)
    id_ok, id_report = id_collision_check(cells)

    if args.check:
        print(report)
        print(f"\nlattice closes: {'YES' if ok else 'NO'}  ({len(cells)} cells)")
        print(f"\n{id_report}")
        print(f"\nno cross-split id collision: {'YES' if id_ok else 'NO'}")
        return 0 if (ok and id_ok) else 1

    ok = ok and id_ok
    md = markdown(cells, ok, report, id_ok, id_report)
    if args.out:
        args.out.write_text(md, encoding="utf-8")
        print(f"wrote {args.out} ({len(md.splitlines())} lines)")
    else:
        print(md)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
