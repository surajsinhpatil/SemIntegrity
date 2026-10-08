# §4.3 second-source corroboration — source independence, provider feasibility, and the empirical probe record

**Status:** PROPOSED — AWAITING RESEARCHER DECISION

> **REVISION 3 — 2026-10-07.** The researcher has corrected the witness rule:
> **`same-witness` does not satisfy §4.3 and must not permit promotion.**
> §14 at the end of this document carries that correction, the blocked-host
> re-probe, a Wikidata reference census and the reworked classical-empire
> analysis. **§7.3's "convention only, both admissible" framing and §6.1's
> coverage accounting are SUPERSEDED by §14** — read §14 before acting on
> either.

**Revision 2 — 2026-10-07.** Revision 1 (same date, earlier) was written from
prior knowledge. **98 HTTP probes have since been run, and they contradicted
four of Revision 1's load-bearing claims.** This revision is rebuilt on the
probe evidence; Revision 1's superseded claims are listed in §12 and are **not**
preserved elsewhere in this document.

**Decides nothing.** `configs/benchmark/corroboration_policy.yaml` is
**UNCHANGED**: `status: NOT_CONFIGURED`, `approved_independent_providers: []`,
`independence_criterion: null`. `available_fetchers()` still returns `{}`. No
adapter exists, no constraint was authored or promoted, nothing is committed.
The system still reports, correctly, *"corroboration mechanism implemented;
approved independent source policy not yet configured"*.

Tracked as **Q25** in `docs/OPEN_QUESTIONS.md`. The decision this prepares is
drafted as **`docs/decisions/ADR-0019-corroboration-source-policy.md`**, marked
**DRAFT — NOT APPROVED**.

---

## 0. Executive summary

| question | answer |
|---|---|
| smallest defensible provider set | **8 providers**, all plain unauthenticated GET, all empirically hash-stable |
| cells it covers | **34 of 81** verified end-to-end for retrieval · **42** coverable but with the instance's document not yet identified · **5** residual gap |
| residual gap | "the end of a classical empire" (4 cells) and "coastal versus landlocked states" (1 cell) |
| does the 132-cell allocation survive | **Yes, unchanged.** Every repair is instance selection, which is still free |
| independence criterion | **Option C** — directional non-derivation **plus** witness classification |
| P248 rule | a pointer, never evidence; the named document may qualify only after independent retrieval from the provider's own host |
| production adapters needed | **one** generic HTTP document fetcher. **Zero** provider-specific adapters, **zero** credentials |
| engineering effort | one fetcher class, one suitability check, one PDF-encoding decision; ~1-2 focused sessions |
| what blew up in Revision 1 | the highest-value provider (`legislation.gov.uk`, 14 cells) is WAF-blocked; IUCN needs an issued token; Oxford is 403 before any paywall; `un-treaties` needs **no** adapter and is the best artefact in the set |

---

## 1. The decision, restated

`CorroborationPolicy.configured` is `True` only when a non-empty provider list
**and** a stated `independence_criterion` both exist. Three separable
sub-decisions:

| | sub-decision | treated in |
|---|---|---|
| **D-1** | the independence criterion | §7 (Phase 5) |
| **D-2** | the approved provider list | §5, §6 (Phases 3-4) |
| **D-3** | whether a Wikidata P248 / reference value may ever count | §8 (Phase 6) |

A fourth has emerged from the probes and did not exist in Revision 1:

| **D-4** | what makes a retrieved artefact **suitable for frozen evidence**, as distinct from merely fetchable | §9 (Phase 7) |

---

## 2. The empirical probe record

Probe-only instrumentation, kept out of `src/` and out of production:
`probe/probe_fetchability.py` plus raw records `batch1.json`,
`batch2.json`, `followup.json`, `stability.json`, `batch3_alternatives.json`,
`batch4_winners.json` in the session scratchpad. 98 requests, one request per
host per 1.2-1.3 s, User-Agent
`SemIntegrity-probe/0.1 (academic research source-feasibility probe; BITS Pilani M.E. dissertation) python-requests`.

What the probes test: **fetchability and reproducibility only.** Nothing here
establishes that a document supports a proposition. No bot challenge was solved
or circumvented; challenged hosts are recorded as blocked.

### 2.1 Three findings that change the design, not just the provider list

**(a) HTTP 200 is not evidence of retrieval.** The IUCN species page returns
`200` with a Cloudflare interstitial body (`_cf_chl_opt`, "Enable JavaScript and
cookies to continue", 5,714 bytes). Six further hosts return `200` with an
empty JS application shell: `eci.gov.in` (1,279 B), `govinfo.gov/app/details/…`
(2,616 B), `cia.gov` World Factbook (517 KB of bundle, no country text),
`unesdoc.unesco.org` (1,938 B), `documents.un.org`, `indiacode.nic.in` root
(2,009 B). A status-code-only probe would have scored all seven PASS. **Any
fetcher must detect challenge and shell bodies, or the corroboration store will
freeze interstitials as evidence.**

**(b) `content_hash` is not a re-retrieval identifier for a third of sources.**
Of 41 artefacts double-fetched, **12 returned different bytes on the second
GET** — some from a per-response nonce at identical byte length
(`iupac.org`, the USPTO generated PDF, `members.parliament.uk`), some from live
content (`britannica.com`, `ibge.gov.br` root, the TNA Discovery API, OpenAlex).
The freeze mechanism is unaffected — `CorroborationStore.verify` rehashes the
*stored* artefact — but "re-fetch and compare the hash" is **not** a universal
audit, and nothing in the schema currently distinguishes a hash-stable source
from a hash-unstable one.

**(c) Index endpoints are not artefacts.** The NTRS search API, the TNA
Discovery API and the USGS S3 bucket listing are all fetchable and all
unstable, because they are queries. They are legitimate **discovery** tools and
illegitimate **evidence**. The policy has to say so.

### 2.2 PASS — fetchable, hash-stable, real document returned

sha256 compared across two or more GETs. "Stable" = byte-identical.

| provider | artefact | status | media type | bytes | stable |
|---|---|---|---|---|---|
| `un-treaties` | MTDSG ch. XVIII **XML** | 200 | `text/html` (body is XML) | 119,352 | **YES — 3 GETs over ~35 min** |
| `un-treaties` | MTDSG ch. XVIII PDF | 200 | application/pdf | 204,137 | YES |
| `un-treaties` | certified true copy PDF | 200 | application/pdf | 20,830,926 | not re-tested |
| `un-treaties` | UNTS vol. 1 PDF | 200 | application/pdf | 4,561,196 | not re-tested |
| `crossref` | `api.crossref.org/works/10.1038/171737a0` | 200 | application/json | 4,481 | YES |
| `crossref` | `doi.org` + `Accept: …csl+json` | 200 after 302 | application/vnd.citationstyles.csl+json | 4,310 | YES |
| `crossref` | `api.crossref.org/works/10.1103/PhysRev.74.230` | 200 | application/json | 2,404 | — |
| `govinfo` | `/content/pkg/FR-2024-01-02/pdf/…pdf` | 200 | application/pdf | 13,257,131 | YES |
| `nasa` | NSSDCA `display.action?id=1969-059A` | 200 | text/xml | 16,551 | YES |
| `nasa` | NTRS document PDF `19710015566` | 200 | application/pdf | 12,485,794 | YES |
| `bipm` | SI Brochure 9th ed PDF | 200 | application/pdf | 3,503,078 | YES |
| `ciaaw` | `ciaaw.org/atomic-weights.htm` | 200 | text/html | 21,501 | YES |
| `taxonomic-authority` | WoRMS `AphiaRecordByAphiaID/126436` | 200 | application/json | 908 | YES |
| `taxonomic-authority` | ChecklistBank/COL name search | 200 | application/json | 4,583 | YES |
| `taxonomic-authority` | ZooBank root | 200 | text/html | 7,771 | YES (root only) |
| `national-archives` | NARA Declaration transcript | 200 | text/html | 48,690 | YES |
| `official-gazette` | `gesetze-im-internet.de` Grundgesetz | 200 | text/html | 305,445 | YES |
| `official-gazette` | `psp.cz` Act 542/1992 | 200 | text/html **charset=Windows-1250** | 28,925 | YES |
| `official-gazette` | `alex.onb.ac.at` root | 200 | text/html | 25,488 | YES (root only) |
| `canal-authority` | Suez Canal Authority history | 200 after redirect | text/html | 202,809 | YES |
| `canal-authority` | Panama Canal Authority history | 200 after redirect | text/html | 150,782 | YES |
| `ibge` | `servicodados.ibge.gov.br/api/v1/localidades/municipios/5300108` | 200 | application/json | 465 | YES |
| `uk-parliament-api` | `members-api.parliament.uk/api/Members/172` | 200 | application/json | 1,151 | YES |
| `commonwealth` | member countries | 200 | text/html | 115,193 | YES |
| `nps` | Denali park page | 200 | text/html | 80,660 | YES |
| `aec` | `aec.gov.au` root | 200 | text/html | 81,756 | YES |
| (roots only, no document probed) | `royal.uk`, `loc.gov`, `perseus.tufts.edu`, `scholar.archive.org`, `tbmm.gov.tr`, `unstats.un.org` | 200 | text/html | 23-78 KB | YES |

### 2.3 FETCHABLE BUT NOT SUITABLE — hash-unstable, shell, or index

| provider | artefact | why unsuitable |
|---|---|---|
| `britannica` | `/place/Brasilia` | 200, real content, but 144,658 → 144,604 B between GETs |
| `iupac.org` | periodic-table page | nonce: different hash at identical 79,411 B |
| `uspto` | generated print PDF US2524035 | nonce: different hash at identical 1,520,481 B |
| `uk-parliament` (web) | `members.parliament.uk` | nonce at identical 52,452 B — **use the API instead** |
| `un-treaties` | `ViewDetails.aspx` HTML | server-rendered and complete, but grew 474,633 → 479,295 B within the session — **use the XML instead** |
| `openalex` | `/works/doi:…` | different hash at identical 14,032 B; also a Wikidata-lineage concern (§7.4) |
| `ibge` | site root | live content |
| `nasa` | NTRS search API | index, unstable |
| `national-archives` | TNA Discovery API | index, unstable (14,407 → 14,135 B) |
| `usgs` | S3 staged-products listing | bucket listing, not a document, unstable |
| `cia` | World Factbook country page | 517 KB JS shell; "Bolivia"/"landlocked" absent from the body |
| `govinfo` | `/app/details/…` | JS shell — **the `/content/` path is the artefact** |
| `eci` | `eci.gov.in` | 1,279 B SPA shell |
| `unesdoc` | repository root | 1,938 B shell, unstable |
| `indiacode` | root | 2,009 B landing page; document retrieval unverified |
| `gbif` | species API | fetchable and stable, but **lineage unresolved** (§7.4) — excluded pending a check |

### 2.4 BLOCKED — and not to be worked around

| provider | evidence | consequence |
|---|---|---|
| `legislation.gov.uk` | `202 Accepted`, `Content-Length: 0`, **`x-amzn-waf-action: challenge`**, CloudFront. 6 requests: the Act, its `data.xml`, 4 retries at 5 s, a second Act, and **`/robots.txt`** — all 202/0 B | Revision 1's single highest-value provider, 14 cells. Gone |
| `eur-lex.europa.eu` | `202`, `x-amzn-waf-action: challenge` | EU law route closed |
| `digitallibrary.un.org` | `202`, `x-amzn-waf-action: challenge`, awselb | UN repository route closed |
| `www.un.org` (member states, growth in membership, OHRLLS LLDC) | `403`, CloudFront | `treaties.un.org` is open; `www.un.org` is not. "The UN" is two different retrieval propositions |
| `planalto.gov.br` | TCP connect 8.7 ms, then 0 bytes at 30 s, 60 s, 90 s | Brazilian federal law route closed |
| `legifrance.gouv.fr` | `403`, Cloudflare | French law route closed |
| `www2.camara.leg.br`, `in.gov.br` | `403`; connection closed without response | Brazilian alternates closed |
| `iucn` | site = **200 with Cloudflare interstitial**; API v4 = `403 {"error":"Forbidden"}`; API v3 = `404` (retired); api root = `403` | needs an **issued token**, not an adapter. 4 cells |
| `oxfordreference.com` / `doi.org/10.1093/acref/…` | `403` CloudFront, before any login | 16 history cells lose their Revision 1 fallback |
| `nobelprize.org` (page **and** API) | `403`, Cloudflare | institutional route for the Nobel-citation angle closed |
| `hansard.parliament.uk`, `loc.gov/collections/country-studies/…` | `403` (though `loc.gov` root is 200) | path-level blocks |
| Kew `POWO`, `IPNI` | `403`, Cloudflare | WoRMS/COL cover the same cells |
| `si.edu` object record | `403` | museum-specimen route unverified |
| EPO `OPS` | `403`, OAuth required | as predicted; USPTO `/content/` route exists but is hash-unstable |

**No challenge was solved and none will be.** Where a host refuses automated
retrieval, the entry above is the finding, not a problem to engineer around.

### 2.5 PDF payload cost — `CorroborationArtifact.content` is `str`

| artefact | raw | base64 into one KBCache JSON entry |
|---|---|---|
| UNTC chapter PDF | 0.20 MB | 0.27 MB |
| USPTO patent PDF | 1.52 MB | 2.03 MB |
| BIPM SI Brochure | 3.50 MB | 4.67 MB |
| UNTS volume PDF | 4.56 MB | 6.08 MB |
| NTRS Apollo 11 mission report | 12.49 MB | 16.65 MB |
| govinfo Federal Register daily issue | 13.26 MB | 17.68 MB |
| UNTC certified true copy | 20.83 MB | 27.77 MB |

Revision 1 recommended "base64 the original bytes" as a clean choice. With
these numbers it is a trade-off, and the operative discipline is **per-cell
artefact selection**: the 204 KB chapter PDF, not the 20.8 MB certified copy;
the 119 KB XML, not either PDF.

---

## 3. Scope — the 81 cells, unchanged

Read from `data/benchmark/authoring_manifest.json` (132 rows).
`corroboration_required` is set by `_corroboration_required`, mirroring
`design_validator.corroboration_reason`: **domain == history, OR answer_type ==
date, OR class == C4, OR axis in {4, 6}**. **81 rows — 72 test, 9 dev.**

| domain | C1 | C2 | C3 | C4 | total |
|---|---|---|---|---|---|
| history | 7 | 7 | 7 | 7 | **28** |
| science_technology | 3 | 3 | 3 | 7 | **16** |
| biology | 2 | 2 | 2 | 7 | **13** |
| geography | 2 | 2 | 2 | 6 | **12** |
| public_office | 2 | 2 | 2 | 6 | **12** |
| **total** | **16** | **16** | **16** | **33** | **81** |

Axes: 4 → 24 · 6 → 20 · 2 → 12 · 3 → 9 · 1 → 8 · 5 → 8. Answer types: boolean
46 · date 22 · entity 13. Eight of the 81 also require an ADR-0018
`ComparisonUniverse`. The 81 cells are **30 distinct fact families** (C1-C4 of
one family share entities and theme), so provider selection is a 30-way problem
and freezing is an 81-way one — `CorroborationStore.request_for` keys on
`(provider, url, fact)`.

Per-axis Wikidata evidence, from the manifest's own `evidence_policy`:

| axis | primary Wikidata evidence |
|---|---|
| 1 | the role property itself (P36-style single-valued claims); for C4, P580/P582 on the role-holding |
| 2 | membership claims for BOTH categories, **and a source for the DISJOINTNESS itself** |
| 3 | the containment claim at each level; for C3 the full chain x→y→z as separate records |
| 4 | P585/P580 date claims for both events |
| 5 | the measure for **every member** of the stated comparison set, plus the set definition |
| 6 | P580 **and** P582 on the interval; for C2 both intervals |

Axis 5 deserves a flag that Revision 1 missed: because ADR-0018 requires a
measure for every universe member, the **8 axis-5 corroboration cells carry a
multiplied corroboration burden** — the argmax and each member need provenance,
not just the winner.

---

## 4. Phase 3 — practical alternatives for the blocked categories

Only alternatives that are first-party, governmental, institutional, archival or
an authoritative domain registry were considered. Accessibility alone was not
treated as a qualification (§4.2 lists accessible candidates that were still
rejected).

### 4.1 Adopted alternatives

#### `govinfo` — U.S. Government Publishing Office (replaces `legislation.gov.uk`)
1. **Provider:** GPO's govinfo, the official publisher of U.S. federal
   documents (Statutes at Large, Federal Register, the Constitution, CFR).
2. **Independence:** statutory publisher of record; the documents are the
   enacted/published instruments and predate Wikidata by decades to centuries.
3. **Authority:** first-party and constitutive — the strongest class available.
4. **Fact types:** independence instruments (e.g. a proclamation granting
   independence), abolition/reorganisation of offices, incompatibility clauses,
   seat-of-government statutes, canal-administration records.
5. **URL stability:** the documented `/content/pkg/{packageId}/{fmt}/{granule}.{ext}`
   pattern. **VERIFIED** 200 + `application/pdf`.
6. **Freezable:** yes. **VERIFIED hash-stable** across two GETs (13,257,131 B).
7. **Generic GET sufficient:** **yes**.
8. **Adapter required:** no.
9. **Limitations:** the `/app/details/…` UI is a JS shell and must never be the
   artefact; daily Federal Register issues are 13 MB, so granule-level selection
   matters; US-jurisdiction only, so it constrains *instance* choice (§10).
10. **Realistic coverage:** up to **11-14 cells** across public_office and
    geography, by instance selection.

#### `official-gazette` — accessible official legal publishers (replaces Légifrance / Planalto / EUR-Lex)
1. **Providers probed:** `gesetze-im-internet.de` (German Federal Ministry of
   Justice), `psp.cz` (Chamber of Deputies, Sbírka zákonů), `alex.onb.ac.at`
   (Austrian National Library historical gazette archive).
2. **Independence:** official publishers of enacted law; instruments predate
   Wikidata.
3. **Authority:** first-party, constitutive.
4. **Fact types:** dissolution of a federal state (**Czechoslovakia, Act
   542/1992 — the canonical instance**), constitutional provisions, historical
   imperial gazettes (ALEX covers Habsburg-era instruments).
5. **URL stability:** `gesetze-im-internet.de` uses stable `BJNR…` document
   ids; `psp.cz` a stable `?cz=&r=` query; ALEX unverified below root.
6. **Freezable:** **VERIFIED hash-stable** — GG 305,445 B, Act 542/1992
   28,925 B, ALEX root 25,488 B.
7. **Generic GET sufficient:** yes.
8. **Adapter required:** no.
9. **Limitations:** `psp.cz` serves **`charset=Windows-1250`**, so the decode is
   part of the provenance (§9); non-English text puts the translation in
   `fact_supported` on the author; ALEX serves scanned gazettes, so a specific
   document is unverified.
10. **Realistic coverage:** **4-8 cells**, and it rescues the
    federal-dissolution family outright.

#### `ibge` — Instituto Brasileiro de Geografia e Estatística API (replaces the blocked statistics category)
1. **Provider:** IBGE's `servicodados.ibge.gov.br` open-data API.
2. **Independence:** Brazil's statutory statistical and geographic agency,
   producing its own primary administrative data.
3. **Authority:** first-party for Brazilian administrative geography.
4. **Fact types:** city-within-first-level-division (municipality → UF).
5. **URL stability:** stable numeric municipality codes (`5300108`).
6. **Freezable:** **VERIFIED hash-stable**, 465 B JSON — the smallest and
   cleanest artefact in the whole catalogue.
7. **Generic GET sufficient:** yes.
8. **Adapter required:** no.
9. **Limitations:** administrative geography only; it does **not** carry the
   capital-city *statute*, and the Brazilian statute host is blocked (§10.2).
10. **Realistic coverage:** **1 cell**, cleanly; the IBGE site *root* is
    hash-unstable and must not be used.

#### `uk-parliament-api` — `members-api.parliament.uk` (replaces the nonce-unstable web pages)
1. **Provider:** UK Parliament's members API.
2. **Independence:** Parliament's own record of its members.
3. **Authority:** first-party administrative.
4. **Fact types:** office tenure and service dates (longest-serving holder).
5. **URL stability:** stable numeric member ids.
6. **Freezable:** **VERIFIED hash-stable**, 1,151 B JSON — while
   `members.parliament.uk` HTML is nonce-unstable and `hansard.parliament.uk`
   is 403. Same institution, three different verdicts.
7. **Generic GET sufficient:** yes.
8. **Adapter required:** no.
9. **Limitations:** members of Parliament, not heads of state; comparison-universe
   members each need their own record.
10. **Realistic coverage:** **1-2 cells.**

#### `official-organisational-record` — AEC, Commonwealth Secretariat, NPS, royal.uk
1. **Providers:** Australian Electoral Commission; the Commonwealth
   Secretariat's member-countries record; US National Park Service; the Royal
   Household (`royal.uk`).
2. **Independence:** each publishes its own institutional record.
3. **Authority:** first-party organisational — the AEC *is* the authority on
   Australian divisions; NPS on Denali; the Royal Household on reigns.
4. **Fact types:** constituency within a federal unit; independence/membership
   dates; the continental high point; the longest reign.
5. **URL stability:** unverified below root for `royal.uk`; verified pages for
   NPS and the Commonwealth.
6. **Freezable:** **VERIFIED hash-stable** — Commonwealth 115,193 B, NPS
   80,660 B (contains "Denali"), AEC 81,756 B, `royal.uk` root 63,546 B.
7. **Generic GET sufficient:** yes.
8. **Adapter required:** no.
9. **Limitations:** corporate/institutional sites churn; these are *records*
   rather than instruments, so they sit a tier below a statute; `royal.uk`'s
   specific page is unverified (the path guessed in the probe 404'd).
10. **Realistic coverage:** **3-5 cells.**

#### `crossref` as the route for extinction and milestone dating (replaces IUCN for 4 cells)
The IUCN block is a credential problem, not an engineering one. The defensible
substitute is the **primary literature that establishes the extinction**, whose
publication record is already verified hash-stable through Crossref, combined
with instance selection toward an extinction with a documented last specimen.
Crossref gives the publication record, not the claim — so this route is
`COVERABLE, DOCUMENT UNVERIFIED` until the specific paper is identified.

### 4.2 Alternatives considered and rejected

| candidate | fetchability | why rejected anyway |
|---|---|---|
| `gbif` species API | 200, stable JSON | **lineage unresolved.** GBIF aggregates many checklists; whether any ingest Wikidata is unverified, and §7.3 Q1 must be answered before approval. Excluded pending that check |
| `openalex` | 200 | hash-unstable, **and** OpenAlex uses Wikidata for entity reconciliation — a directional-derivation risk pointing the wrong way |
| CIA World Factbook | 200 | 517 KB JS shell; the country text is not in the body |
| `unesdoc` | 200 | 1,938 B shell, unstable |
| USGS S3 staged products | 200 XML | a bucket **listing**, not a document; unstable; the data files are zips |
| `digitallibrary.un.org`, EUR-Lex | 202 WAF challenge | blocked; not to be worked around |
| `si.edu`, `nobelprize.org`, `hansard` | 403 | blocked |
| `scholar.archive.org`, `perseus`, `loc.gov`, `tbmm.gov.tr` | 200 roots, stable | **kept as leads, not adopted**: no document-level artefact was probed, so adopting them now would be exactly the unverified-assertion failure this phase exists to avoid |
| `britannica` | 200, real content | hash-unstable **and** tertiary. Admissible only as a recorded last resort (§6.3) |

---

## 5. Phase 4 — the minimal defensible provider set

Optimised for defensibility, independence, reproducibility, fetchability, low
engineering complexity and provider count — **not** for maximum coverage.

**Eight providers. All plain unauthenticated GET. All empirically hash-stable.
Zero credentials. Zero provider-specific adapters.**

| # | provider id | tier | artefact form | verified | cells it can serve |
|---|---|---|---|---|---|
| 1 | `crossref` | T1 | JSON (needs `Accept`) | stable | 12 + extinction/milestone routes |
| 2 | `un-treaties` | T1 | XML (preferred) / PDF | stable over 35 min | 8 alliances + independence cross-check |
| 3 | `govinfo` | T1 | PDF via `/content/` | stable | 11-14 by instance |
| 4 | `nasa` | T1 | XHTML + PDF | stable | 5 |
| 5 | `standards-body` (BIPM, CIAAW) | T1 | PDF + HTML | stable | 2-3 |
| 6 | `taxonomic-authority` (WoRMS, ChecklistBank, ZooBank) | T2 | JSON | stable | 5 |
| 7 | `official-gazette` (gesetze-im-internet, psp.cz, alex) | T1 | HTML | stable | 4-8 |
| 8 | `national-archives` (NARA verified) | T2 | HTML | stable | 4 + history by instance |

Two optional additions, each buying 1-2 cells and one more host to defend:
`ibge`, `uk-parliament-api`, and the `official-organisational-record` group
(AEC / Commonwealth / NPS / royal.uk). **Recommendation: approve the eight, and
add these three only if the researcher wants the singleton cells closed in the
same pass** — they are verified, so the only cost is provider count.

### 5.1 What the minimal set deliberately excludes

`iucn` (token), `oxford`/`scholarly-reference` (403), `legislation.gov.uk`
(WAF), `eur-lex` (WAF), `legifrance` (403), `planalto` (timeout), `eci` (shell),
`gbif` (lineage), `openalex` (unstable + lineage), `patent-office` (hash-unstable
generated PDF; Crossref covers the same cells), `britannica` (unstable,
tertiary), `national-statistics` as a general category (only the IBGE API
survived).

---

## 6. Phase 2 — the 81 cells mapped to the strongest currently feasible source

Legend — **fetch**: ✅ verified / ◻ provider verified, this document not probed /
⛔ blocked. **repro**: ✅ hash-stable / ◻ unverified / ✗ unstable.
**prop** (does the source state the proposition): ◻ **unknown for every row** —
no cell's exact proposition exists yet, because no cell is authored; this column
is deliberately all-unknown rather than guessed. **indep**: D = directional
non-derivation holds, likely `independent-witness`; S = likely `same-witness`
(§7). **host**: whether §9.5's same-host duplicate rule bites.

| # | family (cells) | candidate independent source | provider | fetch | repro | indep | same-host risk | verdict |
|---|---|---|---|---|---|---|---|---|
| 1 | history / wartime alliance membership (8) | treaty text + accession record | `un-treaties` | ◻ | ✅ | D | **yes** — C2 needs 2 docs, both on treaties.un.org | COVERABLE |
| 2 | history / capital of a historical polity (4) | imperial gazette instrument | `official-gazette` (ALEX) | ◻ | ◻ | D | low | COVERABLE |
| 3 | history / province within an empire (4) | gazette / archival catalogue | `official-gazette` / `national-archives` | ◻ | ◻ | D | low | COVERABLE |
| 4 | history / onset of the Atlantic revolutions (4) | NARA founding-document transcript | `national-archives` | ✅ | ✅ | D | low | **VERIFIED** |
| 5 | history / longest reign in a named monarchy (4) | Royal Household record | `official-organisational-record` | ◻ | ✅ (root) | D | low | COVERABLE |
| 6 | history / end of a classical empire (4) | — none found | — | ⛔ | — | — | — | **GAP** |
| 7 | sci / milestones in solid-state electronics (8) | publication record of the result | `crossref` | ✅ | ✅ | S | medium — C2 needs 2 DOIs, same host | **VERIFIED** |
| 8 | sci / end of a crewed spaceflight programme (4) | NASA programme document | `nasa` | ✅ | ✅ | D | medium | **VERIFIED** |
| 9 | sci / module within a crewed spacecraft (1) | NSSDCA master catalogue | `nasa` | ✅ | ✅ | D | n/a | **VERIFIED** |
| 10 | sci / SI base unit (1) | SI Brochure | `standards-body` | ✅ | ✅ | S | n/a | **VERIFIED** |
| 11 | sci / periodic-table group membership (1) | IUPAC table — **HTML is nonce-unstable**; the PDF was not probed | `standards-body` | ◻ | ✗ (HTML) | S | n/a | COVERABLE — 1 probe owed |
| 12 | sci / heaviest naturally occurring element (1) | CIAAW | `standards-body` | ✅ | ✅ | S | n/a | **VERIFIED** — wording risk stands |
| 13 | bio / landmark results in molecular genetics (4) | publication record | `crossref` | ✅ | ✅ | S | medium | **VERIFIED** |
| 14 | bio / extinction date of a named species (4) | primary paper / last-specimen record | `crossref` (IUCN ⛔) | ◻ | ✅ | S | medium | COVERABLE |
| 15 | bio / genus within a family (2) | WoRMS / COL record | `taxonomic-authority` | ✅ | ✅ | S | n/a | **VERIFIED** |
| 16 | bio / type species of a genus (1) | COL/ZooBank + original designation | `taxonomic-authority` | ◻ | ✅ | S | n/a | COVERABLE |
| 17 | bio / vertebrate class membership (1) | COL record | `taxonomic-authority` | ✅ | ✅ | S | n/a | **VERIFIED** |
| 18 | bio / largest extant species of a clade (1) | COL membership + measures from literature | `taxonomic-authority` + `crossref` | ◻ | ✅ | S | **yes** — universe members | COVERABLE |
| 19 | geo / opening of major interoceanic canals (4) | canal-administration record | `govinfo` (Panama) / `canal-authority` | ✅ fetch | ✅ | D | medium | COVERABLE — "1869" absent from the Suez page |
| 20 | geo / dissolution of a federal state (4) | Act 542/1992 | `official-gazette` (psp.cz) | ✅ | ✅ | D | **yes** — C2 needs both intervals | **VERIFIED** |
| 21 | geo / capital city of a country (1) | seat-of-government statute | `govinfo` (US) — Brazil host ⛔ | ◻ | ✅ | D | n/a | COVERABLE after instance choice (§10.2) |
| 22 | geo / city within a first-level admin division (1) | IBGE municipality record | `ibge` | ✅ | ✅ | D | n/a | **VERIFIED** |
| 23 | geo / coastal versus landlocked states (1) | — UN list ⛔, Factbook shell | — | ⛔ | — | — | — | **GAP** |
| 24 | geo / highest summit of a continent (1) | NPS Denali page | `official-organisational-record` | ✅ | ✅ | D | **yes** — universe members | **VERIFIED** (argmax only) |
| 25 | pol / decolonisation independence dates (4) | independence instrument + depositary record | `govinfo` + `un-treaties` | ◻ | ✅ | D | low — two providers available | COVERABLE |
| 26 | pol / abolition of a colonial office (4) | reorganisation instrument | `govinfo` (UK host ⛔) | ◻ | ✅ | D | medium | COVERABLE after instance choice |
| 27 | pol / holder of a single-seat head-of-state office (1) | official record | `govinfo` / `national-archives` | ◻ | ◻ | D | n/a | COVERABLE |
| 28 | pol / constitutionally incompatible offices (1) | constitutional text | `govinfo` | ◻ | ✅ | D | n/a | COVERABLE |
| 29 | pol / constituency within a federal unit (1) | AEC division record | `official-organisational-record` | ✅ (root) | ✅ | D | n/a | **VERIFIED** |
| 30 | pol / longest-serving holder of a named office (1) | members API record | `uk-parliament-api` | ✅ | ✅ | D | **yes** — universe members | **VERIFIED** (holder only) |

### 6.1 Recomputed coverage

| status | families | cells |
|---|---|---|
| **VERIFIED** — provider artefact fetched, hash-stable, real document returned | 4, 7, 8, 9, 10, 12, 13, 15, 17, 20, 22, 24, 29, 30 | **34** |
| **COVERABLE, DOCUMENT UNVERIFIED** — provider verified; this instance's document not yet identified or probed | 1, 2, 3, 5, 11, 14, 16, 18, 19, 21, 25, 26, 27, 28 | **42** |
| **GAP** — no verified provider route | 6, 23 | **5** |
| | | **81** |

Proposition-level support is **unknown for all 81** and stays that way until the
cells are authored. Revision 1's "43 at Tier 1, 38 at Tier 2, none unreachable"
is withdrawn: it counted provider categories, not retrievable artefacts.

---

## 7. Phase 5 — resolving the independence question

### 7.1 The problem, stated precisely
The principle excludes sources **derived from** Wikidata. It is silent on the
opposite direction: a provider that Wikidata **imported from**. Such a source is
authoritative and is not a Wikidata reproduction, but a corroboration against it
agrees with Wikidata *necessarily*, and so has no error-detection power — which
is the capability §4.3 exists to buy, and which has already paid for itself twice
in this project (the Q119251/Q119158 QID error and the 1960-04-21/-22 date
error, both caught by fetching rather than by assuming).

### 7.2 The three options, costed against the actual 81 cells

**Option A — strict mutual non-derivation.** Exclude a source if it copies
Wikidata *or* if Wikidata's claim was imported from it.
*Cost:* Wikidata carries external-identifier properties and bot imports for
Crossref DOIs, taxonomic databases and standards bodies. Under A, providers
1, 5 and 6 of the minimal set are excluded, which removes families 7, 10-18 —
**24 of the 81 cells** — and leaves the verified count at about 10. A is the
most rigorous reading and it is **not satisfiable at this scale**.

**Option B — directional non-derivation only.** Admit anything not derived from
Wikidata, record nothing further.
*Cost:* 24 cells would be corroborated by the very source Wikidata copied, and
the records would not say so. The gate would report PASS and the dissertation
would be unable to state what the corroboration actually demonstrated. B is
cheap and **not defensible**.

**Option C — directional non-derivation plus witness classification.** Admit on
B's test; require every source to declare which of two things it is.
*Cost:* one convention, no code. *Benefit:* the limitations section becomes
writable from the records instead of from memory.

### 7.3 Recommendation: **Option C**

Admissibility test (per provider, recorded once in the ADR):

1. Does the provider ingest, redistribute or cite Wikidata/Wikipedia as its
   authority for this fact class? → **excluded**.
2. Does the provider have its own statutory, editorial, measurement or
   scholarly process producing the fact? → **necessary**.
3. Did the provider's record predate Wikidata (2012) or Wikidata's claim? →
   strong positive evidence; decisive for statutes, treaties and publications,
   which is why §5's set is weighted toward them.

Classification (per source, recorded in `note`):

- **`independent-witness`** — Wikidata's claim does not cite this provider.
  Full §4.3 corroboration.
- **`same-witness`** — Wikidata's claim cites this provider (a P248 value or a
  reference URL on the same host). Admissible, because the provider establishes
  the proposition in its own right and the artefact was retrieved and frozen
  from the provider's own host — but it is **agreement, not independent
  confirmation**, and must be reported as such.

**Expected distribution under the minimal set:** `same-witness` ≈ **24 cells**
(the Crossref, standards-body and taxonomic families), `independent-witness` ≈
**52 cells** (the treaty, gazette, govinfo, NASA and archival families), 5 in the
gap. That the statute-and-treaty providers are also the independent ones is a
happy accident of §5's selection criteria, and it is worth keeping.

**Code impact:** none to proceed. `note` already exists on `GoldSource` and is
optional, so the marker is a convention. Enforcing it — refusing a source whose
`note` lacks a marker — would need one policy key and one validator branch.
Recommended: **convention now, enforcement only if the researcher wants the
distinction gated rather than reported.** `duplicate_groups` and
`rejection_reason` need no change either way.

### 7.4 Two providers excluded by this test, pending a check
`gbif` and `openalex` are both fetchable; both fail step 1 or cannot yet pass it
(GBIF's checklist lineage is unverified; OpenAlex uses Wikidata for entity
reconciliation). They are excluded from the proposal rather than admitted with a
caveat, because step 1 is the one test that must not be waived.

---

## 8. Phase 6 — Wikidata P248 / reference targets

### 8.1 Can a P248 value itself ever count?
**No, and the reasons are independent of each other.**

1. *Methodological.* A P248 value is a Wikidata statement about a Wikidata
   statement. Reading it is reading the primary source, which is what "second
   source" excludes by definition.
2. *Mechanical.* `CorroboratingSource._is_a_second_source` rejects
   `_PRIMARY_PROVIDERS` at schema construction, so such a record cannot be
   built; and the snapshot would be a Wikidata cache entry under the wrong
   `kind`.
3. *Empirical, new from the probes.* A reference URL is an assertion that a
   document at that address supports a claim. The probes show that assertion
   cannot be trusted without retrieval: seven hosts return `200` with a
   challenge or an empty shell, and twelve artefacts change bytes between two
   GETs. "Wikidata cites this URL" is therefore not even evidence that the URL
   resolves to the cited content today.

### 8.2 Can the referenced document count?
**Yes, conditionally** — on exactly the terms any other document faces, and with
no exception path:

1. retrieved from the **provider's own host**, never from Wikidata or a
   Wikimedia host;
2. the provider is on the approved list **in its own right**;
3. the response passes the challenge/shell check (§9.2) — a `200` is not enough;
4. the artefact is frozen in the corroboration store and `verify()` confirms the
   `content_hash`;
5. `note` records **`same-witness`**, because the derivation direction is known:
   Wikidata → cites → document.

### 8.3 The rule, and why it is worth stating positively
> **A P248 or reference value is a pointer, never evidence. The document it
> names may corroborate only after independent retrieval from the provider's own
> authoritative host, under the same freeze and verification rules as any other
> source, and is recorded as `same-witness`.**

The positive half matters as much as the prohibition. Reference values are the
cheapest available channel for *finding* candidate documents, and the
project's recorded candidate-error rate of about 1 in 4 is exactly what a good
discovery channel reduces. The rule keeps that benefit while refusing the
shortcut.

---

## 9. Phase 7 — FETCHABLE versus SUITABLE FOR FROZEN EVIDENCE

The probes force a distinction the current design does not make.

### 9.1 The proposed two-gate rule
A response is **FETCHABLE** if a plain GET returns it. It is **SUITABLE FOR
FROZEN EVIDENCE** only if, in addition: it is a *document* rather than an index
or a shell; it is not a challenge body; its bytes were **hash-stable across two
retrievals**; and its encoding is recorded.

### 9.2 Response classes and their verdicts

| class | observed in probes | fetchable | suitable | rule |
|---|---|---|---|---|
| **stable HTML** | NARA, psp.cz, gesetze-im-internet, Commonwealth, NPS, AEC, Suez, Panama | yes | **yes** | store raw bytes; record declared charset |
| **unstable HTML** | Britannica, iupac.org, members.parliament.uk, IBGE root | yes | **no** | refuse as evidence; seek an API or a document form from the same institution |
| **JSON API (record)** | Crossref, WoRMS, ChecklistBank, IBGE API, UK members API | yes | **yes** | best class in the set — small, stable, machine-readable |
| **search / index endpoint** | NTRS search, TNA Discovery, S3 listing | yes | **no** | discovery only; never the artefact |
| **XML** | UNTC MTDSG, NSSDCA | yes | **yes** | **do not trust the declared type** — UNTC XML is served as `text/html` |
| **PDF (static)** | BIPM, govinfo, NTRS doc, UNTC chapter | yes | **yes** | prefer the smallest authoritative granule |
| **PDF (generated)** | USPTO print PDF | yes | **no** | per-response nonce; different hash at identical length |
| **non-UTF-8** | psp.cz (`Windows-1250`) | yes | **yes, with the charset recorded** | the decode is part of the provenance; a different decode is a different hash |
| **challenge / interstitial** | IUCN (`200` + `_cf_chl_opt`), legislation.gov.uk (`202` + `x-amzn-waf-action`) | **no** | no | must be detected and refused; never worked around |
| **JS shell** | ECI, govinfo `/app/`, Factbook, unesdoc, documents.un.org, indiacode root | technically | no | content is not in the body |
| **redirects** | doi.org → api.crossref.org; Suez; Panama | yes | yes | **record the final URL** — see §9.5 |

### 9.3 Is `CorroborationArtifact` adequate?
**Adequate to proceed; five things it cannot currently express.** The model
carries `provider`, `url`, `retrieved`, `content: str`, `media_type` and a
derived `content_hash`; `CorroboratingSource` adds `provider`, `snapshot`,
`content_hash`, `fact_supported` to `GoldSource`'s `name`/`url`/`retrieved`/
`note`. Not expressible today:

1. the **final URL after redirects** (§9.5 — this one has a real consequence);
2. the **declared charset** (`Windows-1250`);
3. whether the artefact was **hash-stable** on re-fetch (the §9.1 suitability
   test);
4. the HTTP status and the challenge-check outcome;
5. `media_type` defaults to `text/plain`, which is correct for nothing observed,
   and the server's declared type is unreliable (UNTC XML as `text/html`).

**Recommendation: no code change is required to proceed** — all five fit in a
structured `note` line, which is also where §7.3's witness marker goes. The
small, defensible upgrade, if the researcher wants it: two optional fields
(`final_url`, `charset`) on `CorroborationArtifact`, and one policy key
(`require_hash_stability`). **Not implemented, not proposed for implementation
in this phase.**

### 9.4 PDF and encoding policy
Store the **original bytes, base64-encoded**, with the true `media_type` and the
relied-upon sentence quoted in `note`; for non-UTF-8 HTML store the raw bytes
and record the charset. Rationale: §4.3's artefact should be the document, and
`verify()` should be verifying the document, not an extraction whose extractor
version silently becomes part of the provenance. The operative discipline is
**granule selection** (§2.5): 204 KB, not 20.8 MB.

### 9.5 The same-host rule, and a trap it creates
`duplicate_groups` treats a shared `provider`, `url_host` **or** `content_hash`
as the same source, and `_corroboration` escalates a duplicate to an **error at
any status** — unlike absent corroboration, which is only a draft-stage warning.
Consequences:

- **C2 conjunctions** (16 of the 81) cannot cite two documents from one host.
  Affected rows in §6: families 1 (both treaty docs on treaties.un.org), 7 and
  13 (two DOIs), 20 (two Czech acts). Routes, in order of preference: one
  document stating both facts; two **different** providers; or one source per
  constraint, recorded as the exception it is.
- **ADR-0018 universes** (families 18, 24, 30) need provenance per member, and
  the members will usually share a host.
- **A redirect trap:** `doi.org` resolves to `api.crossref.org`. If `url`
  records the requested `doi.org/...`, two different DOIs share `url_host` and
  are flagged as the same source; if it records the final URL, they share it
  too. Either way, **two Crossref-corroborated facts on one constraint will trip
  the duplicate rule**. This is a direct consequence of §9.3's missing field and
  is the strongest practical argument for the `govinfo`/`un-treaties` pairing on
  C2 cells.

---

## 10. Phase 8 — does the approved allocation survive?

### 10.1 Yes, unchanged
**120 test · 12 dev · 132 new · 81 corroboration-required — all unchanged.** No
repair in this document touches allocation, class balance, the factor lattice,
ADR-0017, ADR-0018, CANON or K. The reason is structural: the manifest says of
itself *"the planned allocation ONLY — no entities, QIDs, gold answers or
sources"*, so **no entity in the 81 is fixed**, and the entire repair surface is
instance selection during authoring.

### 10.2 The instance choices the evidence implies
Each keeps the family, the schema, the axis and the answer type exactly as
approved:

| family | instance the evidence favours | provider |
|---|---|---|
| 20 dissolution of a federal state | **Czechoslovakia** (Act 542/1992) | `official-gazette` ✅ |
| 22 city within a first-level division | **a Brazilian município** | `ibge` ✅ |
| 24 highest summit of a continent | **North America / Denali** | NPS ✅ |
| 29 constituency within a federal unit | **Australia** (AEC), not India (ECI is a shell) | AEC ✅ |
| 30 longest-serving holder | **a UK parliamentary office** | `uk-parliament-api` ✅ |
| 19 canals | **Panama** via US administration records | `govinfo` |
| 25 independence dates | instruments on `govinfo` + depositary records | `govinfo`, `un-treaties` |
| 26 abolition of a colonial office | **a US territorial/insular office**, not a UK one | `govinfo` |
| 21 capital city of a country | a jurisdiction whose seat-of-government statute is retrievable | `govinfo` |
| 2, 3 historical polity / province | **Habsburg-era instruments** | `official-gazette` (ALEX) |
| 5 longest reign | **the British monarchy** | `royal.uk` |

**One already-authored cell is affected.** `K-C4-GEO-11` (Brazil / Brasília) is
DRAFT, and the Brazilian statute hosts (`planalto.gov.br`, `camara.leg.br`,
`in.gov.br`) are all blocked. The IBGE API is verified but carries the
municipality record, not the transfer statute. So either that cell keeps Brazil
and accepts a weaker corroborating artefact, or it is re-instantiated. It is one
DRAFT cell and the choice is the researcher's; §5.4 of Revision 1 also noted
that corroboration there would resolve an open `REQUIRES_HUMAN_REVIEW`
inference, which argues for finding a Brazilian route rather than abandoning it.

### 10.3 Where instance selection is **not** enough
- **Family 6 — "the end of a classical empire" (4 cells). Instance selection
  cannot fix this.** The theme requires a classical empire, and no classical
  empire has a first-party instrument or a verified institutional record of its
  end; the Oxford route is 403 and Britannica is hash-unstable and tertiary.
  Three options, all requiring a decision: (a) admit a tertiary source for these
  4 cells with a recorded reason; (b) admit an open-access scholarly publication
  retrieved from its publisher's host, accepting that fetchability is
  per-document; (c) change the theme, which **would** require the approved
  coverage matrix to be revisited. **This is the one place where the benchmark
  design and the source policy actually collide.**
- **Family 23 — "coastal versus landlocked states" (1 cell).** Probably
  instance-fixable: a landlocked status fixed by a boundary or peace treaty would
  route through `un-treaties`. UNVERIFIED, and worth one probe before it is
  counted as covered.

---

## 11. Phase 9 — engineering plan

### A. Definitely required
| # | item | notes |
|---|---|---|
| 1 | **one** `HttpDocumentFetcher(provider, accept=None)` implementing `CorroboratingSourceFetcher` | throttled GET, project UA, follow redirects, capture raw bytes, record status/final URL/declared charset. ~100 lines + tests |
| 2 | **challenge and shell detection** | Cloudflare `_cf_chl_opt` / "enable javascript and cookies", `x-amzn-waf-action`, `202`-with-empty-body, minimum-content heuristic. ~30 lines + tests. **New work Revision 1 did not foresee, and not optional** — without it an interstitial gets frozen as evidence |
| 3 | artefact encoding rule (base64 for binary, charset recorded for text) | ~20 lines |
| 4 | tests that an interstitial body is **refused**, and that an index endpoint is refused by convention | the gates already have the "test that it fires" convention |
| 5 | policy file population | the researcher's decision, not code |

### B. Probably required
| # | item | notes |
|---|---|---|
| 6 | hash-stability check at authoring time (double-fetch, compare, record) | the only honest way to populate §9.1's suitability test. ~20 lines |
| 7 | structured `note` convention, or two optional fields (`final_url`, `charset`) | §9.3 |
| 8 | artefact size guard | 20.8 MB raw → 27.8 MB base64 in one JSON entry |

### C. Avoidable complexity — do not build
IUCN token adapter · EPO OAuth adapter · browser/JS rendering · any WAF
handling · HTML-to-text extraction · PDF text extraction · provider-specific
parsers · a scholarly-paywall path. **Every one is avoided by provider or
instance selection**, which is the main practical argument for §5's set.

**Estimate:** A ≈ one focused session. B ≈ half a session. C ≈ zero.
**Provider-specific adapters: 0. Credentials: 0.**

---

## 12. Corrections to Revision 1

Listed because a superseded claim should be visible, not quietly deleted.

| Revision 1 claim | status | evidence |
|---|---|---|
| `national-legislation` is the highest-value provider, 14 cells, "generic GET sufficient: yes" | **FALSE** | `legislation.gov.uk` `202` + `x-amzn-waf-action: challenge` on 6 requests incl. `/robots.txt`; Légifrance `403`; Planalto timeout ×3 |
| `un-system`'s Treaty Collection is "the only genuinely unavoidable adapter" | **FALSE — reversed** | plain GET of a path-addressable XML, byte-identical across 3 GETs over 35 min; no adapter |
| `iucn` needs "a small adapter (token from the environment)" | **UNDERSTATED** | an **issued token** is a prerequisite; the website returns `200` with a Cloudflare interstitial; API v3 retired |
| `scholarly-reference` is admissible subject to a paywall caveat, up to 16 history cells | **FALSE** | `403` before any authentication, both via `doi.org` and directly |
| "43 cells at Tier 1, 38 at Tier 2, **0 unreachable**" | **WITHDRAWN** | counted provider categories, not retrievable artefacts. Recomputed: **34 verified · 42 coverable · 5 gap** |
| "26 cells unblock on two providers with zero adapters" | **HALF TRUE** | Crossref's 12 confirmed; `national-legislation`'s 14 blocked |
| `content_hash` implicitly treated as a re-retrieval identifier | **FALSE for 12 of 41 artefacts** | nonce or live content; see §2.1(b) |
| PDF encoding framed as a clean recommendation | **TRADE-OFF** | 0.27-27.77 MB base64; granule selection matters more than encoding |
| `patent-office` as the second corroborator for the 8 solid-state cells | **WEAKENED** | USPTO print PDF is nonce-unstable; EPO OPS `403` |
| `britannica` as "the" T3 fallback | **WEAKENED** | fetchable but hash-unstable, so unsuitable for frozen evidence as well as tertiary |

Unchanged from Revision 1 and reconfirmed: the 81-cell scope and its
distribution; the 30-fact-family structure; the same-host duplicate consequence
for C2; that the 81 can be authored to DRAFT before any policy exists; and that
instance selection is free because the manifest holds no entities.

---

## 13. What this document does not decide

- It does not configure the policy. `status: NOT_CONFIGURED`,
  `approved_independent_providers: []`, `independence_criterion: null` —
  unchanged.
- It does not approve ADR-0019. The draft at
  `docs/decisions/ADR-0019-corroboration-source-policy.md` is **DRAFT — NOT
  APPROVED**.
- It implements no fetcher, authors no constraint, promotes no constraint,
  changes no allocation, and touches neither ADR-0017, ADR-0018, CANON, K, the
  factor lattice, Q5 nor Q22.
- **Proposition-level support is unknown for all 81 cells** and is a separate
  question from everything established here.
- Probe claims are empirical as of 2026-10-07 from one network. Blocked hosts
  should be re-probed once from the cluster login node before the gap list is
  treated as final.

---

# 14. Revision 3 — the tightened witness rule, the re-probe, and the classical-empire gap

**2026-10-07, after researcher correction.** This section supersedes §7.3's
framing (where both witness classes were admissible and classification was a
reporting convention) and §6.1's coverage accounting. Everything else in
Revisions 1-2 stands. 52 further probes were run; **150 in total**.

## 14.1 The corrected rule

> **`independent-witness`** — the Wikidata claim does **not** cite this provider
> or source. **This, and only this, satisfies §4.3, and only this may support
> promotion past the corroboration gate.**
>
> **`same-witness`** — the Wikidata claim **does** cite this provider or source
> (a P248 value, or a reference URL on the same host). The source may be
> authoritative and may establish the fact in its own right, but it is **not
> independent confirmation of Wikidata's claim**. It **does not satisfy §4.3**
> and **must not by itself allow promotion**. It may be recorded as descriptive
> provenance.

Why this is right: if Wikidata cites Provider X, agreement between them is
guaranteed by construction and has no error-detection power — which is the
capability §4.3 buys and which has already paid for itself twice here (the
Q119251/Q119158 QID error, the 1960-04-21/-22 date error). A gate accepting that
agreement would report PASS on a check that could not fail.

**Two consequences Revision 2 got wrong.**

1. **Witness status is a property of the (claim, source) pair, not of the
   provider.** Revision 2's estimate of "≈24 same-witness cells, ≈52
   independent-witness" was provider-level. That granularity was tolerable while
   the classification was reporting metadata; it is **inadequate now that it
   gates promotion**, and it is **withdrawn**.
2. **Classification must be determined from evidence, per cell, at authoring
   time** — and it can be, cheaply: a Wikidata claim's references are already in
   the entity JSON the frozen cache stores.

## 14.2 Wikidata reference census — how much the tightened rule actually costs

Probe-only, public API, no writes to the project cache. 16 statements across 9
entities chosen to represent the affected families. **Indicative, not
conclusive** — the actual entities for the 81 cells are not yet chosen.

| family | entity | property | references found |
|---|---|---|---|
| 10 SI base unit | metre (Q11573) | P31 | **stated in: SI Brochure (8th ed.)**, ISO 80000-1 — *and three further P31 statements with none* |
| 14 extinction | blue whale (Q42196) | P141 | **stated in: IUCN Red List 2022.2** |
| 14 / 15 / 17 taxonomy | blue whale, lion (Q140) | P171, P105 | **stated in: ITIS; Mammal Species of the World (3rd ed.)** — *not WoRMS, not Catalogue of Life* |
| 12 heaviest natural element | uranium (Q1098) | P1086, P31 | **none** |
| 20 dissolution | Czechoslovakia (Q33946) | P576 | **none** |
| 21 capital city (the authored `K-C4-GEO-11`) | Brazil (Q155) | P36 ×2 | **none** |
| 6 end of a classical empire | Byzantine Empire (Q12544) | P576 | **none** |
| 7 solid-state milestones | transistor (Q5339) | P571 | *property absent* |
| 19 canal opening | Suez Canal (Q12370) | P1619 | *property absent* |

**11 of 16 statements (69%) carry no references at all.**

| implication | detail |
|---|---|
| where Wikidata cites nobody, the rule does not bind | **every** admissible provider is `independent-witness`. This covers the dissolution, capital-city, heaviest-element and classical-empire claims sampled |
| the taxonomic provider is **safer** than Revision 2 assumed | Wikidata cites ITIS and MSW3; the proposal uses WoRMS and ChecklistBank/COL, so those are `independent-witness` for the sampled claims |
| **one confirmed conflict** | metre `P31` cites the SI Brochure, so BIPM is `same-witness` there and would not satisfy §4.3. **Instance-fixable** — author the cell on a quantity/unit pair whose claim carries no reference, which 69% of sampled statements do |
| IUCN's citation is moot | IUCN is excluded on retrieval grounds anyway |

A second, quieter point: an **unreferenced** Wikidata claim is weaker as primary
evidence, so it is exactly where independent corroboration matters most. The
tightened rule is therefore not merely affordable — it is well targeted.

## 14.3 Recomputed coverage under the tightened rule

Coverage is now **two independent conditions per cell**, and a cell is satisfied
only when both hold:

| condition | status | can it be pre-computed? |
|---|---|---|
| **R — retrieval**: an artefact from an approved provider is fetchable and suitable for frozen evidence (§9) | **VERIFIED 34 · COVERABLE 42 · GAP 5** — unchanged by the correction | yes, and it was |
| **W — witness**: the source is `independent-witness` for *that* Wikidata claim | determinable **only per cell**, from the claim's references | **no** — but the census says it will rarely bind |

So the honest accounting is:

| | cells |
|---|---|
| retrieval-VERIFIED **and** no witness conflict identified | **33** |
| retrieval-VERIFIED **but** a confirmed witness conflict (metre/SI, instance-fixable) | **1** |
| retrieval-COVERABLE, witness to be determined at authoring | **42** |
| GAP — no qualifying route | **5** (4 classical-empire + 1 landlocked) |
| **total** | **81** |

**Revision 2's "≈52 independent-witness / ≈24 same-witness" split is withdrawn
and replaced by nothing**: the split is not knowable before the instances are
chosen, and claiming a number would be exactly the kind of guess this phase
exists to remove.

## 14.4 Blocked-host re-probe — nothing changed

Run from this environment on 2026-10-07, after the first round. **Every blocked
host returned an identical result**, so the blocks are **site policy, not a
transient**:

| host | first probe | re-probe |
|---|---|---|
| `legislation.gov.uk` | 202 + `x-amzn-waf-action: challenge` | **202, same** |
| `eur-lex.europa.eu` | 202 WAF | **202, same** |
| `digitallibrary.un.org` | 202 WAF | **202, same** |
| `www.un.org` | 403 CloudFront | **403, same** |
| `legifrance.gouv.fr` | 403 Cloudflare | **403, same** |
| `planalto.gov.br` | timeout | **timeout, same** |
| `iucn` site / API | 200 interstitial / 403 token | **same / same** |
| `oxfordreference.com` | 403 | **403, same** |
| `nobelprize.org` | 403 | **403, same** |
| Kew `POWO` | 403 | **403, same** |
| `hansard.parliament.uk` | 403 | **403, same** |
| newly probed: `doaks.org` | — | **202 WAF challenge** |

**Cluster login-node re-probe: not performed, and it cannot be performed from
here.** Per ADR-0010 the researcher runs all cluster commands; the exact command
is in §14.6. Its only purpose is to find out whether these results are
network-specific. **A different result there would not be permission to
circumvent anything** — it would only mean the same plain GET succeeds from that
network, and the gap list would be revised accordingly.

## 14.5 The four classical-empire cells, reworked

Family `F-HIS-16` — history, axis 6, theme *"the end of a classical empire"*.

**Witness status is not the obstacle.** The Byzantine Empire's `P576` carries no
references (§14.2), so any admissible provider would be `independent-witness`.
The obstacles are **retrieval** and **proposition support**.

**Option A — an accessible instance within the existing theme: PROBED, no route
found.** The institutional classical-studies authorities were tested directly.
`nomisma.org/id/byzantine_empire` returns `200`, is **byte-identical across two
GETs**, and serves **RDF/XML (11,425 B) and JSON-LD (17,364 B) by content
negotiation** — technically the cleanest artefact shape in this whole study. It
fails on two counts anyway:
- **it states no terminal date** — zero occurrences of "1453", no start/end
  fields; the record is labels and concept typing;
- it declares `skos:exactMatch` to **`wikidata.org/entity/Q12544`**, DBpedia and
  Freebase, carries 186 multilingual prefLabels, and its provenance
  (`prov:used`) points at a Google Sheets document. That is a
  Wikimedia-ecosystem concordance, and it **fails §7.3 step (i)**.

Pleiades (`200`, JSON available) and papyri.info (`200`) are the same class of
resource and date **places, documents and coins — not the end of an empire**.
Trismegistos could not be verified (TLS chain failure). **No classical empire has
a first-party instrument, because its end is a historiographical convention
rather than a recorded act.**

**Option B — an open-access scholarly source.** Methodologically apt: for a
periodisation claim, peer-reviewed scholarship *is* the appropriate authority,
and §4.3 requires "authoritative", not "first-party". Independence is strong.
Newly probed roots, all `200` on 2026-10-07: Cambridge Core, Brill, De Gruyter,
OpenEdition, Persée, Zenodo, JSTOR (Dumbarton Oaks is `202` WAF). So the category
is **not blocked the way Oxford is**. **Unverified at document level** — no
article page was probed, and publisher pages were repeatedly hash-unstable
elsewhere in this study. Adopting B means accepting that retrievability and
hash-stability are established **per document at authoring time**.

**Option C — another defensible source.** A successor polity's state archive or
national academy; for 1453 that means Ottoman archival material, for 476 nothing
exists. Unprobed, speculative.

**Option D — revisit the theme.** `F-HIS-16`'s *slot* is (history, axis 6);
*"the end of a classical empire"* is a **theme label** in the matrix's family
table (`docs/BENCHMARK_COVERAGE_MATRIX.md` §3 and the history table).
Relabelling it would touch that table and the manifest's regenerated `theme`
string and **nothing else** — not allocation, class balance, the factor lattice,
ADR-0017, ADR-0018, CANON or K. It would then be instantiable on the **Ottoman
Empire** (the 1922 abolition instrument; the Treaty of Lausanne in the League of
Nations Treaty Series, reachable through the verified `un-treaties` provider) or
**Austria-Hungary** (ALEX's *Gesamtstaatliche Gesetzesblätter*, verified at
collection level: `alex.onb.ac.at/node/14`). **D is the only option that reaches
a first-party instrument.**

**Option E — a tertiary exception. Not proposed.** Britannica is tertiary *and*
hash-unstable, so it fails §9's suitability rule as well as the authority
preference, and no hash-stable tertiary source was found.

**Ranking.** On methodological cleanliness: **D > B > C > A > E** — D because it
is the only route to an instrument, B because scholarship is the right authority
for a periodisation, A last among the live options because it was probed and
failed, E excluded. On *preserving approved documents*: **B > C > A > E > D**.
**These two orderings disagree, which is precisely why this is the researcher's
decision and is not taken here.**

**If none of A-E is approved**, the honest outcome is that these 4 cells stay
DRAFT and the benchmark reports **77 of 81 corroborated**, with the shortfall
stated. §4.3 is not weakened to close them.

## 14.6 The exact cluster command (researcher runs it; ADR-0010)

Copy-paste on the **login node**. No repo file, no Python, no dependencies
beyond `curl`; it writes one local text file and nothing else. It performs the
same plain GETs as this study and **does not attempt to pass any challenge**.

```bash
for u in https://www.legislation.gov.uk/ukpga/1947/30/contents \
         https://www.legislation.gov.uk/ukpga/1947/30/data.xml \
         https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:11957E/TXT \
         https://digitallibrary.un.org/ \
         https://www.un.org/en/about-us/growth-in-un-membership \
         https://www.legifrance.gouv.fr/ \
         https://www.planalto.gov.br/ccivil_03/leis/l3273.htm \
         https://www.iucnredlist.org/species/15951/115130419 \
         https://www.oxfordreference.com/display/10.1093/acref/9780199545568.001.0001 \
         https://hansard.parliament.uk/ ; do
  printf '%s\n' "=== $u"
  curl -sS -m 40 -A 'SemIntegrity-probe/0.1 (academic research source-feasibility probe; BITS Pilani M.E. dissertation) curl' \
       -o /dev/null -D - "$u" 2>&1 \
    | grep -i -E '^HTTP/|^server:|waf|^content-length:|^location:' | head -5
done | tee /tmp/semintegrity_blocked_host_reprobe.txt
```

**How to read the output.** `202` with `x-amzn-waf-action: challenge` or `403`
means still blocked — the gap list stands. A `200` with a non-zero
`content-length` means that host serves this network, and the provider becomes a
candidate **pending the same hash-stability and content checks every other
provider passed** (§9.1). Paste the file back; do not treat a `200` as
sufficient on its own, because seven hosts in this study returned `200` with a
challenge or an empty shell.

## 14.7 What Revision 3 changes in the proposal

| | before | after |
|---|---|---|
| witness rule | both classes admissible; classification a `note` convention | **only `independent-witness` satisfies §4.3**; `same-witness` is descriptive and blocks promotion |
| granularity | per provider (≈24 / ≈52 estimate) | **per (claim, source) pair**, determined from the frozen cache |
| P248 | document admissible, flagged `same-witness` | document retrievable, but **`same-witness` for the citing claim, so it never qualifies for that claim** |
| coverage | 34 / 42 / 5 | **33 / 1 conflict / 42 / 5** — retrieval unchanged, a second gate added |
| enforcement | convention, no code | **a validator rule is now required**, because a convention cannot block a promotion (≈40 lines + tests; not implemented) |
| provider set | 8 | **8, unchanged** — and the census makes `taxonomic-authority` safer than assumed |
| exclusions | gbif, openalex | **+ nomisma, + pleiades/trismegistos/papyri.info**, on §7.3 step (i) and proposition mismatch |

---

# 15. Revision 4 — approved and implemented, 2026-10-07

**ADR-0019 is APPROVED and IMPLEMENTED.** This document is now the evidence
base behind a decision rather than a proposal, and
`configs/benchmark/corroboration_policy.yaml` reads `status: CONFIGURED` with
the eight-provider core set. The three optional providers (`ibge`,
`uk-parliament-api`, `official-organisational-record`) were **deliberately not
approved** and may be added later only if a concrete authored constraint
requires one.

**Limited final check of options B and C (Part 2 of the closing instruction) —
no qualifying artefact found.** 8 further requests, no new campaign:

| option | probed | result |
|---|---|---|
| **B** open-access scholarship | DOAJ article API | `200` JSON, **118** OA articles match *byzantine AND 1453*, full text on university-journal hosts. **None of the matched articles states the proposition** — the top hits concern autocephaly, the 1422 siege and liturgical practice. Channel reachable; **no qualifying document identified** |
| **C** successor-polity archive | `devletarsivleri.gov.tr` | `200`, 58 KB — host reachable, but an Ottoman archive does not assert when the Byzantine Empire ended, and for 476 no such institution exists |

**Outcome: the four cells are retained as an explicit corroboration gap**,
recorded in the policy under `recorded_gaps`. The benchmark will report **77 of
81 corroborated**. §4.3 is not weakened, the independence rule is not weakened,
no tertiary exception exists, and **the theme was not relabelled** — option D
remains an unresolved methodological choice for the researcher, not something to
do silently to make a number look complete.

**What was built** (detail in ADR-0019 §13): one generic
`HttpDocumentFetcher`, one `WitnessClassifier` reading the Wikidata claim's own
frozen references, the validator gate that makes `same-witness` non-qualifying,
three optional provenance fields on `CorroborationArtifact`, and 35 new tests.
**Zero provider-specific adapters, zero credentials.**

**Post-implementation state:** 1,026 tests pass · ruff clean · `make check` PASS
· readiness audit 13 PASS · 2 FAIL · 3 BLOCKED · implementation verifier 33 PASS
· authoring plan 8/8 · pilot byte-identical. The allocation is unchanged and
nothing is committed.
