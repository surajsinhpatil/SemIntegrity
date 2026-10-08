# ADR-0019 — Independent second-source policy for §4.3 corroboration

**Kind:** METHODOLOGY

**Status:** **APPROVED BY RESEARCHER 2026-10-07** · **IMPLEMENTED 2026-10-07**
· **AMENDED 2026-10-07 (Q26: provider-level witness identity)**
· **CLARIFIED 2026-10-08 (Q27: the two uses of `provider_hosts`; documentation only)**
· resolves the provider-policy half of Q25; the four-cell gap in §7 stays OPEN

> **Approved with the researcher's correction of 2026-10-07 built in:
> `same-witness` does not satisfy §4.3.** The eight-provider core set was
> approved; the three optional providers were **deliberately not** approved and
> may be added later only if a concrete authored constraint genuinely requires
> one. The exclusions, the P248 rule and the frozen-artefact suitability rule
> were approved as drafted. §13 records what was configured and built.

**Date:** drafted 2026-10-07 · revised 2026-10-07 · approved and implemented 2026-10-07

**Evidence base:** `docs/CORROBORATION_SOURCE_FEASIBILITY.md` (Revisions 2-3)
and 150 HTTP probes, including a blocked-host re-probe and a Wikidata reference
census. Tracked as **Q25** in `docs/OPEN_QUESTIONS.md`.

---

## 1. Problem

§4.3 requires that *"all historical and temporal facts are corroborated against
a second authoritative source"*, with Wikidata primary and explicitly not
absolute truth. The mechanism is implemented and enforced
(`semintegrity.kb.corroboration`, `CorroboratingSource`,
`design_validator._corroboration`, `validate_corroboration_freeze`) and the
policy is deliberately unconfigured, so every corroboration is currently
rejected and the system reports *"corroboration mechanism implemented; approved
independent source policy not yet configured"*.

**81 of the 132 planned constraints** (72 test, 9 dev; 30 distinct fact
families) cannot be promoted past DRAFT until this policy exists.

Five things must be decided: an independence criterion; the status of a source
Wikidata itself cites; an approved provider list; the status of Wikidata
P248/reference values; and what makes a retrieved artefact *suitable for frozen
evidence* as opposed to merely fetchable.

## 2. Decision 1 — independence criterion, and what satisfies §4.3

> **Admissibility (necessary, not sufficient).** A source is admissible as a
> candidate second source when its content is not derived from Wikidata: it is
> not Wikidata, not a mirror, not a Wikidata-derived or Wikidata-ingesting
> dataset, and does not cite Wikidata or Wikipedia as its authority for the
> fact. Derivation is assessed **per provider**, recorded in this ADR, against
> three questions: (i) does the provider ingest, redistribute or cite
> Wikidata/Wikipedia for this fact class — if so it is **excluded**; (ii) does
> the provider have its own statutory, editorial, measurement or scholarly
> process producing the fact — **necessary**; (iii) did the provider's record
> predate Wikidata (2012) or Wikidata's claim — strong positive evidence, and
> decisive for statutes, treaties and dated publications.
>
> **Qualification (what §4.3 requires).** Admissibility alone does not
> corroborate. Every corroborating source is additionally classified **against
> the specific Wikidata claim it is offered for**:
>
> - **`independent-witness`** — the Wikidata claim does **not** cite this
>   provider or source. **This, and only this, satisfies §4.3's requirement for
>   a second authoritative source, and only this may support promotion past the
>   corroboration gate.**
> - **`same-witness`** — the Wikidata claim **does** cite this provider or
>   source: a P248 "stated in" value the policy maps to the provider, **or a
>   reference URL on any host the policy declares for that provider** (Q26,
>   below). The source may be authoritative and may establish the fact in its own
>   right, but it is **not independent confirmation of Wikidata's claim**. It
>   **does not satisfy §4.3**, and **must not by itself allow promotion**. It may
>   be recorded as descriptive provenance and reported as such.
>
> A constraint requiring corroboration is satisfied only when it carries at
> least one source that is admissible, `independent-witness` for its claim,
> and suitable for frozen evidence (§6).

**Why the stricter rule is right.** If Wikidata cites Provider X for the fact,
then agreement between Wikidata and X is guaranteed by construction and carries
no error-detection power — which is the capability §4.3 buys, and which has
already paid for itself twice in this project (the Q119251/Q119158 QID error and
the 1960-04-21/-22 date error). A gate that accepted such agreement would report
PASS on a check that could not fail.

**Why this is affordable — measured, not assumed.** A reference census of 16
Wikidata statements across 9 entities chosen to represent the affected families
found:

| finding | consequence |
|---|---|
| **11 of 16 statements (69%) carry no references at all** — including Czechoslovakia's dissolution date, Brazil's capital statements (the already-authored `K-C4-GEO-11`), the Byzantine Empire's end date and uranium's atomic mass | where Wikidata cites nobody, **every** admissible provider is `independent-witness`. The stricter rule does not bind at all |
| taxonomy claims cite **ITIS** and **Mammal Species of the World (3rd ed.)**, not WoRMS or Catalogue of Life | the proposed `taxonomic-authority` provider is `independent-witness` for those claims |
| metre's `P31` cites the **SI Brochure (8th ed.)** and ISO 80000 | **one confirmed conflict**: BIPM is `same-witness` for that claim and would not satisfy §4.3. Instance-fixable (§7.1) |
| the blue whale's conservation status cites the **IUCN Red List** | moot — IUCN is excluded anyway (§4) |

**Witness status is a property of the (claim, source) pair, not of the
provider.** This supersedes Revision 1's provider-level estimate of "≈24
same-witness cells", which was the wrong granularity: tolerable when the
classification was reporting metadata, inadequate now that it gates promotion.

### 2.1 Q26 amendment — identity is decided at provider level

> Witness independence is determined at the approved **provider** level, using
> the explicit, auditable `witness_classification.provider_hosts` map.
>
> 1. If the Wikidata claim cites a source belonging to the **same approved
>    provider** as the proposed corroborating source, the classification is
>    **`same-witness`**.
> 2. That holds **even when the cited source and the corroborating artefact use
>    different authoritative hosts of that provider**.
> 3. A source from a **different** approved provider may still qualify as
>    `independent-witness`, subject to the non-derivation and reference rules.
> 4. If the provider/host relationship **cannot be established from the explicit
>    map** — for the cited host or for the source's own host — the classification
>    is **`undetermined`**.
> 5. `same-witness` and `undetermined` **never** satisfy §4.3.
> 6. Provider ownership is **never inferred** from domain similarity. Only an
>    explicit entry in `provider_hosts` establishes it: `nasa.gov` does not vouch
>    for an unlisted subdomain, and a lookalike host owns nothing.

**Why the first rule was wrong, found by running it against live data.** The
original wording matched a reference URL "on the same host". Wikidata's
`Q533336 P361 → Q2025902` (Unity is part of the US Orbital Segment) cites
`www.nasa.gov`; the authoritative NASA artefact for that same fact is the NSSDCA
master-catalogue record on `nssdc.gsfc.nasa.gov`. Both are the approved provider
`nasa`, so the claim already cites that provider — yet host equality returned
`independent-witness`, in the direction that wrongly permits promotion. **Five of
the eight approved providers are deliberately multi-host categories**
(`nasa`, `official-gazette`, `taxonomic-authority`, `standards-body`, and
`crossref` via the `doi.org` → `api.crossref.org` redirect), so the gap was
structural rather than an edge case.

Hosts are declared only where the feasibility study retrieved them, and listing
a host can only make the classifier **more** likely to refuse. The map is the
same auditable shape as `wikidata_stated_in_qids`: populated by a human, after
checking, or not at all.

### 2.2 Q27 clarification — the two uses of `provider_hosts` (documentation only)

**This changes no rule.** Q27 established that one list was doing two jobs whose
risk asymmetries point in opposite directions, and that the safe response was to
say so rather than to edit the list. `provider_hosts` has two related but
distinct uses:

1. **Identifying provider ownership** for witness and reference classification —
   does a cited reference belong to the same provider as the candidate source?
   Here, listing a host is **conservative**: it can only produce more
   `same-witness` verdicts and therefore more refusals. Under-listing is the
   dangerous direction, which is what Q26 corrected.
2. **Serving as the explicit boundary of approved provider-host identity** — the
   statement that these hosts, and only these, are the provider. Here, listing a
   host is **permissive**: it asserts that artefacts served there count as this
   approved authority. Over-listing is the dangerous direction.

A single edit to the map acts in both capacities at once. So an addition is
never merely "tightening the witness test": it also widens what the provider is
taken to be. **The admissibility rule (§2) and the independence rule (§2.1) are
unchanged by this clarification.**

Two consequences recorded with it, both from Q27's evidence:

- **A sibling government host is not the provider.** That the authoritative
  instrument sits on another state host establishes nothing about provider
  membership. Ownership is never inferred from government ownership, the same
  country, the same institution, URL similarity, redirects, domain suffixes or
  shared web infrastructure — only from an explicit entry.
- **Different institutions reproducing the same instrument are not
  automatically independent.** A legislature's reproduction service and a
  ministry's gazette carry the same text; agreement between them has no
  error-detection power. This is the "mirror on another domain" case that
  `duplicate_detection` already routes to human review, and splitting such hosts
  across two providers would silently convert that reprint into two
  "independent" witnesses.

**Determination is mechanical and already available.** A Wikidata claim's
references are in the entity JSON the frozen cache already stores. The test is:
does any reference's P248 target, or any reference URL's host, correspond to the
candidate provider? Recommended as a **validator rule** rather than an authoring
convention — see §9. Not implemented.

**Options considered and rejected.** *Strict mutual non-derivation* (exclude any
source Wikidata imported from, whether or not it cites it for this claim) is a
provider-level ban; it would exclude Crossref, the standards bodies and the
taxonomic authorities outright, and the census shows that would be excessive,
because for most claims Wikidata cites nothing. *Directional non-derivation
alone*, with witness status recorded but not gating, is what Revision 1 proposed
and what the researcher has now rejected — correctly, for the reason above.

## 3. Decision 2 — approved providers

Eight provider ids. Every one was empirically verified as retrievable by plain
unauthenticated GET and **byte-stable across repeated retrievals**. No provider
requiring a credential, a token, JavaScript execution or any interaction with a
bot-challenge is proposed.

| provider id | what it is | tier | verified artefact |
|---|---|---|---|
| `crossref` | DOI registration-agency publication records | T1 | JSON, stable (needs `Accept`) |
| `un-treaties` | UN / League of Nations treaty depositary records, `treaties.un.org` only | T1 | MTDSG XML, byte-identical over 35 min |
| `govinfo` | U.S. Government Publishing Office, `/content/` paths only | T1 | PDF, stable |
| `nasa` | NSSDCA master catalogue and NTRS documents | T1 | XHTML + PDF, stable |
| `standards-body` | BIPM (SI Brochure) and CIAAW | T1 | PDF + HTML, stable |
| `official-gazette` | accessible official legal publishers: `gesetze-im-internet.de`, `psp.cz`, `alex.onb.ac.at` | T1 | HTML, stable |
| `taxonomic-authority` | WoRMS, ChecklistBank / Catalogue of Life, ZooBank | T2 | JSON, stable |
| `national-archives` | official archival institutions; NARA verified | T2 | HTML, stable |

**Optional additions**, each verified, each closing 1-2 singleton cells: `ibge`
(Brazilian statistical/geographic API), `uk-parliament-api`
(`members-api.parliament.uk`), `official-organisational-record` (AEC,
Commonwealth Secretariat, NPS, `royal.uk`).

**A provider's presence on this list never establishes that it corroborates a
given claim.** Each use must additionally pass §2's witness test and §6's
suitability test.

## 4. Decision 3 — exclusions

**Permanent:** Wikidata and anything mediated by it. `excluded_as_second_source`
unchanged.

**Excluded on the independence test (§2 step i):**

| excluded | evidence |
|---|---|
| `gbif` | aggregated checklists of unverified provenance; step (i) unanswered |
| `openalex` | uses Wikidata for entity reconciliation; hash-unstable |
| `nomisma` | probed directly: its Byzantine Empire record declares `skos:exactMatch` to **`wikidata.org/entity/Q12544`**, DBpedia and Freebase, carries 186 multilingual prefLabels and a `prov:used` pointing at a Google Sheets source. A Wikimedia-ecosystem concordance, and it does not state a terminal date in any case |
| `pleiades`, `trismegistos`, `papyri.info` | same class of scholarly gazetteer with Wikidata concordances; not audited, and they date places, texts and coins rather than the end of an empire |

**Excluded because retrieval is blocked or unsuitable** — all re-probed on
2026-10-07 and **all unchanged**: `legislation.gov.uk`, `eur-lex`,
`digitallibrary.un.org`, `doaks.org` (AWS WAF challenge); `legifrance`,
`www.un.org`, `nobelprize.org`, `hansard`, Kew `POWO`/`IPNI`, `si.edu`, Oxford
(403); `planalto.gov.br`, `camara.leg.br`, `in.gov.br` (silent or 403); `iucn`
(200-with-interstitial plus an issued-token API); `britannica`, USPTO generated
PDFs, `cia.gov`, `unesdoc`, `eci.gov.in` (hash-unstable or JS shells); search
and index endpoints (NTRS search, TNA Discovery, S3 listings — queries, not
documents).

## 5. Decision 4 — P248 and reference targets

> **A Wikidata P248 "stated in" value or reference URL is a pointer, never
> evidence.** It may be used to locate a candidate document and nothing more.
>
> The document it names may be used only when: it is retrieved from the
> provider's own authoritative host (never from Wikidata or a Wikimedia host);
> the provider is approved in its own right; the response passes the
> challenge/shell check; the artefact is frozen and `verify()` confirms its
> `content_hash`.
>
> **And because the Wikidata claim cites it, such a document is by definition
> `same-witness` for that claim. Under §2 it therefore does not satisfy §4.3 and
> must not support promotion.** It may be recorded as descriptive provenance
> only.

So the P248 route, followed to its end, never produces a qualifying second
source **for the claim that cites it**. That is not a defect of the rule; it is
the rule working. The same document may well be `independent-witness` for a
*different* claim that does not cite it, and is then admissible on the ordinary
terms.

Three independent justifications, any one sufficient: a P248 value is a Wikidata
statement about a Wikidata statement, so reading it is reading the primary
source; `CorroboratingSource` already refuses `provider == wikidata` at schema
construction; and the probes show "Wikidata cites this URL" is not even evidence
that the URL resolves to the cited content today — seven hosts return `200` with
a challenge or an empty shell.

## 6. Decision 5 — frozen-artefact suitability

> A response is **FETCHABLE** if a plain GET returns it. It is **SUITABLE FOR
> FROZEN EVIDENCE** only if it is additionally a document rather than an index
> or a JS shell, is not a challenge body, was **byte-stable across two
> retrievals**, and has its encoding recorded. Binary artefacts are stored as
> the original bytes, base64-encoded, with the true media type; text artefacts
> as raw bytes with the declared charset recorded; the relied-upon wording is
> quoted in `note`. Where several granules of one document exist, the smallest
> authoritative one is used.

Forced by evidence: **12 of 41 artefacts double-fetched returned different
bytes**, and seven hosts returned `200` with a challenge or shell body. Without
this rule, interstitials and nonce-bearing pages would be frozen as §4.3
evidence.

## 7. Gaps and exceptions

| gap | cells | nature |
|---|---|---|
| metre/SI-unit witness conflict | 1 | Wikidata's claim cites the SI Brochure, so BIPM is `same-witness` there. **Fixable by instance selection**: author the cell on a quantity/unit pair whose Wikidata claim carries no reference — 69% of sampled statements carry none |
| "the end of a classical empire" | **4** | **no qualifying route found.** See §7.1 — this requires a researcher decision and is not resolved here |
| "coastal versus landlocked states" | 1 | probably fixable by instantiating on a status fixed by a treaty, routing through `un-treaties`. **UNVERIFIED** — one probe owed |

### 7.1 The four classical-empire cells — options, not a decision

Family `F-HIS-16` (history, axis 6, theme *"the end of a classical empire"*).
Witness status is **not** the problem: the Byzantine Empire's `P576` carries no
references, so any admissible provider would be `independent-witness`.
**Retrieval and proposition support are the problem.** Ranked by methodological
cleanliness; **the choice is the researcher's and is deliberately left open.**

**A. An accessible instance within the existing theme — PROBED, no route found.**
The institutional classical-studies authorities were tested. `nomisma.org`
serves a hash-stable Byzantine Empire record with RDF and JSON-LD by content
negotiation — technically ideal — but it **states no terminal date** and
declares `skos:exactMatch` to Wikidata, DBpedia and Freebase, so it fails both
the proposition test and §2 step (i). Pleiades, papyri.info and Trismegistos
date places, documents and coins, not empire ends. No classical empire has a
first-party instrument, because its end is a historiographical convention rather
than a recorded act.

**B. An open-access scholarly source — LIMITED FINAL CHECK RUN 2026-10-07, no
qualifying artefact found.** Methodologically apt: for a periodisation claim,
peer-reviewed scholarship *is* the appropriate authority, and §4.3 says
"authoritative", not "first-party". Independence is strong (the claim is
unreferenced in Wikidata). The retrieval channel exists: the DOAJ article API
answers `200` with JSON and reports 118 open-access articles matching
*byzantine AND 1453*, with full text on university-journal hosts, and Cambridge
Core, Brill, De Gruyter, OpenEdition, Persée, Zenodo and JSTOR all answer `200`
at root. **But none of the matched articles states the proposition** — the top
hits concern autocephaly, the 1422 siege and liturgical practice. So the
category is reachable and **no document establishing the terminal date has been
identified**. Adopting B would mean accepting that retrievability,
hash-stability *and propositional support* are established per document at
authoring time, which is a weaker guarantee than the other seven providers
carry.

**C. Another defensible source — LIMITED FINAL CHECK RUN 2026-10-07, no
qualifying artefact found.** A successor polity's state archive or national
academy. The Turkish state archives (`devletarsivleri.gov.tr`) answer `200`, so
the host is reachable — but an Ottoman archive does not assert when the
Byzantine Empire ended, and for 476 no such institution exists. Reachable,
and not a source for this proposition.

**D. Revisit the theme in the coverage matrix.** `F-HIS-16`'s *slot* is
(history, axis 6); *"the end of a classical empire"* is a **theme label** in the
matrix's family table. Relabelling it — for example to "the end of an imperial
polity" — would touch the matrix table, the manifest's regenerated `theme`
string, and **nothing else**: not the allocation, not class balance, not the
factor lattice, not ADR-0017, not ADR-0018, not CANON, not K. It would then be
instantiable on the **Ottoman Empire** (the 1922 abolition instrument and the
Treaty of Lausanne in the League of Nations Treaty Series, reachable through the
verified `un-treaties` provider) or **Austria-Hungary** (ALEX's
*Gesamtstaatliche Gesetzesblätter*, verified at collection level).
**D is the only option that reaches a first-party instrument**, and so is the
strongest on evidential quality while being the only one that changes an
approved document. That tension is real and is for the researcher to resolve.

**E. A tertiary exception.** Doubly weak and **not proposed**: Britannica is
tertiary *and* hash-unstable, so it fails §6's suitability rule as well as the
authority preference. No hash-stable tertiary source was found.

**OUTCOME 2026-10-07: none of A-E is approved, and the gap is retained.** A and
B and C were each checked and none yielded a qualifying authoritative frozen
artefact; D was **not** adopted, because relabelling an approved theme to make a
coverage number look complete is not a reason to change an approved document;
E is refused outright. So **these 4 cells remain an explicit corroboration gap,
recorded in `corroboration_policy.yaml` under `recorded_gaps`**, and the
benchmark will report **77 of 81 corroborated** with the shortfall stated rather
than papered over. §4.3 is not weakened, the independence rule is not weakened,
and no tertiary exception exists.

**Option D remains an UNRESOLVED METHODOLOGICAL CHOICE, not a rejected one.** If
the researcher later wants complete coverage, relabelling `F-HIS-16`'s theme is
the only route to a first-party instrument, and it would need an explicit
decision and a coverage-matrix revision. It has not been made and must not be
made silently.

## 8. Consequences

**The approved allocation is unchanged.** 120 test · 12 dev · 132 new · 81
corroboration-required. ADR-0017, ADR-0018, CANON, K = 8 and the factor lattice
are untouched. The repair surface is **instance selection during authoring**,
free because the manifest holds *"the planned allocation ONLY — no entities,
QIDs, gold answers or sources"*. The one exception is option D above, which
would change a theme label and nothing structural.

One already-authored cell is affected: `K-C4-GEO-11` (Brazil/Brasília) is DRAFT
and every Brazilian statute host is blocked. Its Wikidata `P36` statements carry
**no references**, so whatever provider is eventually used will be
`independent-witness` — the obstacle there is retrieval, not witness status.

Three consequences that constrain authoring rather than design:
- **C2 conjunctions** (16 cells) cannot cite two documents from one host:
  `duplicate_groups` treats a shared `url_host` as the same source and the
  validator makes a duplicate an error at any status. `doi.org` resolving to
  `api.crossref.org` means two Crossref-corroborated facts on one constraint
  will trip this.
- **ADR-0018 universes** (8 cells) need provenance for every member, not just
  the argmax.
- The 81 may be **authored to DRAFT now**; only promotion is blocked.

**New under the tightened rule:** every corroboration-required cell acquires a
**witness determination step** — read the Wikidata claim's references from the
frozen cache; if any P248 target or reference-URL host corresponds to the
candidate provider, the source is `same-witness`, does not satisfy §4.3, and
either another provider or another instance is needed.

## 9. Engineering implications

**One** generic `HttpDocumentFetcher(provider, accept=None)` implementing
`CorroboratingSourceFetcher`, plus challenge/shell detection, plus an encoding
rule. **Zero provider-specific adapters. Zero credentials.**

The tightened rule adds one item, and makes it worth doing properly: a
**witness classifier** that reads the claim's references from the frozen cache
and returns `independent-witness` / `same-witness` / `undetermined`, wired into
`_corroboration` so that a `same-witness` source cannot satisfy the gate. That
is a validator change, roughly 40 lines plus tests, and it is **the only part of
this ADR that cannot be done by convention** — because a convention cannot block
a promotion. **Not implemented; not to be implemented before approval.**

Probably required: a hash-stability check at authoring time; a structured `note`
convention or two optional fields (`final_url`, `charset`); an artefact size
guard. Explicitly not to be built: token or OAuth adapters, JS rendering, WAF
handling, PDF/HTML text extraction, provider-specific parsers.

## 10. Relationship to §4.3

Nothing here widens or narrows §4.3; it operationalises *"a second authoritative
source"* as: a named provider that passes a stated independence test, retrieved
from its own host, frozen with a verifying hash, tied to an exact proposition,
**and independent of the Wikidata claim it corroborates**. The last clause is
what the researcher's correction adds, and it is the clause that makes the
requirement bite. The corroboration trigger itself is unchanged and still
derives from `design.yaml` (`corroboration_required_for: [history,
temporal_facts]`, `second_source_required: true`), with the axis trigger
preserved so the 2026-10-07 answer-type amendment could not narrow it.

## 11. Proposed values for `configs/benchmark/corroboration_policy.yaml`

**NOT WRITTEN. Presented for review only.** The file's own comment forbids
populating it without an approved ADR, and that condition is not met.

```yaml
policy_version: 2
status: CONFIGURED            # only on approval of ADR-0019

approved_independent_providers:
  - crossref
  - un-treaties
  - govinfo
  - nasa
  - standards-body
  - official-gazette
  - taxonomic-authority
  - national-archives
  # optional, each verified, each closing 1-2 singleton cells:
  # - ibge
  # - uk-parliament-api
  # - official-organisational-record

independence_criterion: >-
  ADMISSIBILITY: a source is admissible when its content is not derived from
  Wikidata - not Wikidata, not a mirror, not a Wikidata-derived or
  Wikidata-ingesting dataset, and not citing Wikidata or Wikipedia as its
  authority for the fact. Assessed per provider in ADR-0019 against three
  questions: does it ingest, redistribute or cite Wikidata for this fact class
  (excluded); does it have its own statutory, editorial, measurement or
  scholarly process (necessary); does its record predate Wikidata or Wikidata's
  claim (decisive for statutes, treaties and dated publications).
  QUALIFICATION: admissibility does not corroborate. Each source is classified
  against the specific Wikidata claim it is offered for. `independent-witness`
  (the claim does not cite this provider or source) is the ONLY classification
  that satisfies §4.3 and the only one that may support promotion.
  `same-witness` (the claim cites this provider or source, by P248 value or by a
  reference URL on the same host) may be recorded as descriptive provenance but
  DOES NOT satisfy the independent-corroboration requirement and MUST NOT allow
  promotion past the corroboration gate.

witness_classification:
  qualifying: [independent-witness]
  recorded_but_not_qualifying: [same-witness]
  undetermined_blocks_promotion: true
  determined_from: >-
    the Wikidata claim's own references in the frozen KB cache: a reference whose
    P248 target or reference-URL host corresponds to the candidate provider makes
    that source same-witness for that claim.

# unchanged
excluded_as_second_source:
  - id: wikidata
    reason: >-
      The primary source (§4.3). A second statement, a reference URL, a P248
      "stated in" value or any other reference attached to the same Wikidata
      claim is mediated by the primary source and is NOT automatically
      independent.

excluded_on_independence_test:
  - {id: gbif,         reason: aggregated checklists of unverified provenance}
  - {id: openalex,     reason: uses Wikidata for entity reconciliation; hash-unstable}
  - {id: nomisma,      reason: "skos:exactMatch to wikidata.org/entity/*; Wikimedia-ecosystem concordance"}
  - {id: pleiades,     reason: same class of gazetteer with Wikidata concordances; unaudited}

frozen_artifact_suitability:
  fetchable_is_not_sufficient: true
  require_document_not_index: true
  reject_challenge_or_shell_bodies: true
  require_hash_stability: true        # byte-identical across two retrievals
  record_charset: true
  binary_encoding: base64
  prefer_smallest_authoritative_granule: true

p248_rule: >-
  A P248 value or Wikidata reference URL is a pointer, never evidence. The
  document it names may be retrieved and frozen on the ordinary terms, but
  because the claim cites it, it is same-witness FOR THAT CLAIM and therefore
  does not satisfy §4.3 and must not support promotion. It may be independent
  for a different claim that does not cite it.

# required_of_every_corroborating_source, duplicate_detection and storage
# are UNCHANGED from policy_version 1.
```

## 12. What approval would and would not authorise

**Would:** populate the policy file with §11's values; build the single generic
fetcher and the witness classifier; begin corroborating the retrieval-verified
cells, each subject to its own witness determination.

**Would not:** author or promote any constraint without its own evidence check
and witness determination; settle proposition-level support for any cell (still
unknown for all 81); close the gaps in §7; adopt any of options A-E for the
classical-empire cells; or change any part of the approved benchmark design.


---

## 13. Implementation record — 2026-10-07

Built in the same session as the approval, against this ADR and nothing beyond
it.

| | what | where |
|---|---|---|
| **configured** | `policy_version: 2`, `status: CONFIGURED`, the eight approved providers, the admissibility+qualification criterion, `witness_classification`, `excluded_on_independence_test`, `p248_rule`, `frozen_artifact_suitability`, `recorded_gaps` | `configs/benchmark/corroboration_policy.yaml` |
| **one generic fetcher** | `HttpDocumentFetcher(provider, accept=None)` — honest plain GET, project User-Agent, throttle, redirect following, challenge/shell refusal, double-fetch hash-stability check, base64 for binary, declared-charset decode for text, size guard. **Zero provider-specific adapters, zero credentials** | `src/semintegrity/kb/fetchers.py` |
| **witness classifier** | `WitnessClassifier` — reads the Wikidata claim's **own references** out of the frozen KB cache; returns `independent-witness` / `same-witness` / `undetermined`; errs toward refusing | `src/semintegrity/kb/witness.py` |
| **validator gate** | `_corroboration` now admits a source only if the policy approves it **and** the classifier calls it an independent witness; a `same-witness` is reported and does not count | `src/semintegrity/benchmark/design_validator.py` |
| **artefact provenance** | `CorroborationArtifact` gained optional `final_url`, `charset`, `http_status`, all recorded in the frozen payload | `src/semintegrity/kb/corroboration.py` |
| **registry** | `available_fetchers()` returns one `HttpDocumentFetcher` per approved provider, and `{}` whenever the policy is empty — the pre-approval behaviour is intact | `src/semintegrity/kb/corroboration.py` |
| **tests** | 49 new (21 witness incl. 9 for Q26, 23 fetcher, 5 axis-5 authoring path); 5 existing tests updated to assert the approved state instead of the unconfigured one | `tests/unit/test_witness.py`, `tests/unit/test_corroboration_fetcher.py`, `tests/unit/test_comparison_universe.py` |
| **Q26 amendment** | `provider_hosts` for all 8 approved providers; provider-level matching with exact-host lookup, no inference; the source's own host must also be declared | `configs/benchmark/corroboration_policy.yaml`, `src/semintegrity/kb/witness.py` |
| **authoring path** | `comparison_universe` and `corroborating_sources` read from the candidates document (ADR-0018 and this ADR both defined fields the builder could not carry) | `src/semintegrity/benchmark/pilot_builder.py` |

**One engineering realisation worth recording, because it is conservative by
construction rather than by convention.** P248 "stated in" values are Wikidata
items, so mapping one to a provider id is a human judgement. The policy's
`witness_classification.wikidata_stated_in_qids` map is **explicitly empty** and
the classifier treats an **unmapped** "stated in" reference as `undetermined`,
which blocks promotion. It therefore never accepts something the rule forbids;
it can only over-refuse, and a researcher resolves a specific item once by
listing it after checking it. Nothing was assumed on the project's behalf.

**Validation after implementation:** 1,026 tests pass (1 skipped), ruff clean,
`make check` PASS, readiness audit **13 PASS · 2 FAIL · 3 BLOCKED** (the
corroboration-policy check moved BLOCKED → PASS), implementation verifier 33
PASS · 0 FAIL, authoring plan 8/8, pilot byte-identical, mypy 20 errors (19
pre-existing plus one missing-`types-requests` stub of the same class already
present in `kb/wikidata.py`).

**No constraint was authored or promoted, the 132-cell allocation is unchanged,
and nothing was committed.**
