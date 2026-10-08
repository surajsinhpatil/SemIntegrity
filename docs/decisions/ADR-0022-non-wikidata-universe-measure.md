# ADR-0022 — A taxonomic-authority measure in a comparison universe

**Kind:** METHODOLOGY

**Status:** APPROVED BY RESEARCHER 2026-10-08
**Date:** 2026-10-08

**Amends nothing.** ADR-0018 and ADR-0019 are unchanged. This ADR adds one
permitted *provenance* for an axis-5 `measure_value`.

## Context

`F-BIO-15` — "the largest extant species of a clade", four cells — was recorded
as blocked with "missing/irreconcilable per-member measures". That is correct,
and re-measuring it confirmed the diagnosis is a **data-quality fact about
Wikidata**, not an authoring failure:

```
P2067 (mass)            P2043 (length)
common ostrich   1.5 / 100 / 115        Balaenoptera musculus  27.1
Emu              32.7 / 38.3 / 581.2    all comparison members  (absent)
tiger            1.19 / 180 / 120
Asian elephant   95
jaguar           800
Crocodylus porosus, Nile crocodile, American alligator,
sperm whale, fin whale, Southern Cassowary   — no P2043/P2048/P2067 at all
```

The values are multi-valued, unit-inconsistent and in places plainly wrong — a
581 kg emu, a 95 kg Asian elephant, an 800 kg jaguar. No clade was found whose
extant members carry consistent, machine-checkable size measures in Wikidata.
Under ADR-0018's enumerated route the extremum is re-derived from the recorded
`measure_value`s, so authoring this cell from `P2067` would either fail that
check or pass it on a value known to be wrong.

A comparison universe nevertheless needs numeric per-member measures, and the
one remaining lever is where those measures come from.

## Decision

**For an axis-5 comparison universe, `UniverseMember.measure_value` may be taken
from an ADR-0019-approved provider instead of from Wikidata**, on these
conditions:

1. **Approved provider only.** The provider must appear in
   `approved_independent_providers` and the retrieval host in that provider's
   `provider_hosts` list. For `F-BIO-15` this is `taxonomic-authority` /
   `www.marinespecies.org` (WoRMS), already verified byte-stable in the
   feasibility study.
2. **Frozen, hashed, replayable.** The artefact is retrieved through
   `kb.fetchers.HttpDocumentFetcher`, stored in the corroboration store
   (`KBCache` kind `corroboration`) and recorded as a `CorroboratingSource` with
   its `snapshot` key and `content_hash`. ADR-0011 re-checkability is satisfied
   by that store, not by the Wikidata cache.
3. **Members stay Wikidata entities.** `UniverseMember.qid` remains a Wikidata
   QID and `argmax_qid` must still be among the constraint's own `entity_qids`.
   The *identity* of a member is Wikidata's; only the *measure* is the external
   provider's. Nothing in `ComparisonUniverse` changes.
4. **The measure declares its provenance and its qualifiers verbatim.**
   `ComparisonUniverse.measure` must name the provider, the measurement type and
   every qualifier that disambiguates it. A bare "body size" is not admissible
   where the provider records several.
5. **The taxon identity is checked against Wikidata.** Each member's `P225`
   taxon name and its `P171` parent taxon are verified by ordinary evidence
   checks, so the mapping from the external measure to the Wikidata entity is
   machine-checked rather than asserted.
6. **This is not corroboration.** A source admitted here supplies a *measure*.
   Whether it *corroborates* the constraint's gold proposition is a separate
   question decided by ADR-0019's witness classification, unchanged. A
   `CorroboratingSource` recorded for provenance under this ADR does not by
   itself satisfy §4.3, and must not be read as doing so.

## The F-BIO-15 instance

WoRMS serves `Body size` with full qualifiers, retrieved during drafting:

```
Carcharodon carcharias  (105838)  594 cm  Type=maximum Dimension=length Sex=female
                                  541 cm  Type=maximum Dimension=length Sex=male
Isurus oxyrinchus       (105839)  400 cm  Type=maximum Dimension=length Sex=male/unsexed
Lamna nasus             (105841)  350 cm  Type=maximum Dimension=length Sex=male/unsexed
Lamna ditropis          (271421)  305 cm  Type=maximum Dimension=length Sex=male/unsexed
```

The clade is **Lamnidae** (`Q136902`); the bearer is the great white shark
(`Q129026`). The ordering 594 > 400 > 350 > 305 is unambiguous, and the claim is
**robust to the sex qualifier**: the male maximum, 541 cm, still exceeds every
other member. That robustness is recorded in `ambiguity_notes` rather than
glossed, because the great white is the only member whose maxima are sexed.

## What this does NOT change

* **ADR-0018.** No field is added, removed or retyped. The extremum check still
  re-derives the ordering from the recorded `measure_value`s.
* **ADR-0019.** The provider list, the independence criterion, the witness
  classification and the P248 rule are untouched. This ADR consumes that policy;
  it does not extend it.
* **`gold_source` stays Wikidata.** The primary source is unchanged; only the
  universe's measure has a second provenance, and it is declared.
* **CANON, K=8, the pilot, the Revision-4 matrix, ADR-0017, detectors,
  statistics.** Unchanged.

## Consequences

* **Authoring.** `F-BIO-15`'s four cells become authorable. The route generalises
  to any axis-5 cell whose measure Wikidata records badly, which on present
  evidence is most biological morphometry.
* **A new dependency.** These four cells' universes cannot be re-checked from the
  Wikidata cache alone; they need the corroboration store too. That is stated in
  each record via `snapshot` + `content_hash`, and is the cost of the decision.
* **Risk accepted.** WoRMS is a third-party service. The artefact is frozen, so
  the *record* survives the service changing; but a future re-retrieval may
  disagree with the snapshot, and that disagreement would be a finding to
  adjudicate, not an error to suppress.
