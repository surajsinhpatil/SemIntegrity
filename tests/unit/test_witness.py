"""ADR-0019 witness classification: independent of the CLAIM, not just the source.

§4.3 wants a *second* authoritative source. A source the Wikidata claim itself
cites is not one: agreement with it is guaranteed by construction and carries no
error-detection power. So admissibility (is this provider approved?) and
qualification (is it independent of this claim?) are separate questions, and
only ``independent-witness`` satisfies §4.3.

These tests pin the behaviour that matters: the classification is per
``(claim, source)`` pair, it is read from the claim's own frozen references
rather than from a note, and anything it cannot establish blocks promotion.
"""

from __future__ import annotations

import datetime as dt

import pytest

from semintegrity.benchmark.design_validator import BenchmarkDesignValidator
from semintegrity.kb.cache import CacheMode, KBCache
from semintegrity.kb.corroboration import (
    CorroborationArtifact,
    CorroborationPolicy,
    CorroborationStore,
)
from semintegrity.kb.witness import (
    WitnessClass,
    WitnessClassifier,
    claims_from_constraint,
)
from semintegrity.schemas.constraint import Constraint, CorroboratingSource, Evidence
from semintegrity.schemas.enums import ConstraintClass, Domain, VerificationStatus
from tests.fixtures.synthetic_benchmark import make_constraint

APPROVED = "un-treaties"
SOURCE_URL = "https://treaties.un.org/doc/Publication/MTDSG/x.en.xml"
FACT = "Ruritania acceded to the pact on 1940-11-20."
CONTENT = "Ruritania ... accession 20 Nov 1940 ..." * 40


# --- fixtures --------------------------------------------------------------
def _entity_payload(qid: str, prop: str, references: list[dict] | None) -> dict:
    """A wbgetentities payload shaped exactly as the frozen cache stores it."""
    statement: dict = {"mainsnak": {"property": prop}}
    if references is not None:
        statement["references"] = references
    return {"entities": {qid: {"claims": {prop: [statement]}}}}


def _stated_in(qid: str) -> dict:
    return {"snaks": {"P248": [{"datavalue": {"value": {"id": qid}}}]}}


def _reference_url(url: str) -> dict:
    return {"snaks": {"P854": [{"datavalue": {"value": url}}]}}


@pytest.fixture
def cache(tmp_path) -> KBCache:
    return KBCache(tmp_path / "kb", CacheMode.LIVE)


@pytest.fixture
def store(tmp_path) -> CorroborationStore:
    return CorroborationStore(KBCache(tmp_path / "corr", CacheMode.LIVE))


def _policy(**overrides) -> CorroborationPolicy:
    cfg = {
        "approved_independent_providers": [APPROVED, "crossref"],
        "independence_criterion": "directional non-derivation plus witness class",
        "excluded_as_second_source": [{"id": "wikidata"}],
        "duplicate_detection": {"mechanical_keys": ["provider", "url_host", "content_hash"]},
        "witness_classification": {
            "qualifying": ["independent-witness"],
            "undetermined_blocks_promotion": True,
            "wikidata_stated_in_qids": {},
            # Q26: provider identity is declared, never inferred.
            "provider_hosts": {
                APPROVED: ["treaties.un.org"],
                "crossref": ["api.crossref.org", "doi.org"],
                "nasa": ["nssdc.gsfc.nasa.gov", "ntrs.nasa.gov", "www.nasa.gov"],
            },
        },
    }
    cfg.update(overrides)
    return CorroborationPolicy(cfg)


def _source(store: CorroborationStore, *, provider: str = APPROVED, url: str = SOURCE_URL,
            note: str = "") -> CorroboratingSource:
    artifact = CorroborationArtifact(
        provider=provider, url=url, retrieved=dt.date(2026, 10, 7), content=CONTENT
    )
    snapshot = store.put(artifact, FACT)
    return CorroboratingSource(
        name="Depositary record", provider=provider, url=url,
        retrieved=dt.date(2026, 10, 7), snapshot=snapshot,
        content_hash=artifact.content_hash, fact_supported=FACT, note=note,
    )


def _constraint() -> Constraint:
    """A C4 history constraint, so §4.3 demands corroboration of it."""
    return make_constraint(
        ConstraintClass.C4, Domain.HISTORY, 16, family_index=16, schema_index=6
    )


def _with_evidence(constraint: Constraint, query: str, *, supports_gold: bool = True,
                   source: str = "wikidata") -> Constraint:
    ev = Evidence(
        source=source, query=query, url="https://www.wikidata.org/wiki/Q1",
        retrieved_at=dt.date(2026, 10, 7), observed_value="x",
        supports_gold=supports_gold, comparison="exact match",
    )
    return Constraint.model_validate({**constraint.to_record(),
                                      "evidence": [ev.model_dump(mode="json")]})


# --- the headline cases ----------------------------------------------------
def test_unreferenced_claim_plus_approved_provider_is_an_independent_witness(cache, store):
    """69% of sampled Wikidata statements carry no references at all.

    A claim that cites nobody cannot be citing us, so an admissible source is a
    genuine second witness for it.
    """
    cache.put("entity", {"qid": "Q33946", "lang": "en"},
              _entity_payload("Q33946", "P576", None), source="test")
    verdict = WitnessClassifier(cache, _policy()).classify(
        _source(store), [("Q33946", "P576")]
    )
    assert verdict.classification is WitnessClass.INDEPENDENT
    assert verdict.qualifies is True


def test_claim_citing_the_sources_own_host_is_a_same_witness(cache, store):
    """The mechanical signal: the claim's reference URL shares our host."""
    cache.put("entity", {"qid": "Q1", "lang": "en"},
              _entity_payload("Q1", "P582",
                              [_reference_url("https://treaties.un.org/doc/other.pdf")]),
              source="test")
    verdict = WitnessClassifier(cache, _policy()).classify(_source(store), [("Q1", "P582")])
    assert verdict.classification is WitnessClass.SAME
    assert verdict.qualifies is False
    assert "treaties.un.org" in verdict.reason


def test_claim_citing_a_mapped_stated_in_item_is_a_same_witness(cache, store):
    """P248 resolves through the policy's own map, never through a guess."""
    cache.put("entity", {"qid": "Q11573", "lang": "en"},
              _entity_payload("Q11573", "P31", [_stated_in("Q19606873")]), source="test")
    policy = _policy(witness_classification={
        "undetermined_blocks_promotion": True,
        "wikidata_stated_in_qids": {APPROVED: ["Q19606873"]},
        "provider_hosts": {APPROVED: ["treaties.un.org"]},
    })
    verdict = WitnessClassifier(cache, policy).classify(_source(store), [("Q11573", "P31")])
    assert verdict.classification is WitnessClass.SAME
    assert "Q19606873" in verdict.reason


def test_an_unmapped_stated_in_reference_is_undetermined_not_independent(cache, store):
    """The classifier errs toward refusing: an unknown citation might be us."""
    cache.put("entity", {"qid": "Q140", "lang": "en"},
              _entity_payload("Q140", "P171", [_stated_in("Q1538807")]), source="test")
    verdict = WitnessClassifier(cache, _policy()).classify(_source(store), [("Q140", "P171")])
    assert verdict.classification is WitnessClass.UNDETERMINED
    assert verdict.qualifies is False
    assert "Q1538807" in verdict.reason


def test_a_claim_outside_the_frozen_cache_is_undetermined(cache, store):
    """Absent evidence is not evidence of independence."""
    verdict = WitnessClassifier(cache, _policy()).classify(_source(store), [("Q999", "P1")])
    assert verdict.classification is WitnessClass.UNDETERMINED
    assert "not in the frozen knowledge-base cache" in verdict.reason


def test_no_identifiable_claim_is_undetermined(cache, store):
    verdict = WitnessClassifier(cache, _policy()).classify(_source(store), [])
    assert verdict.classification is WitnessClass.UNDETERMINED


# --- the classification is claim-SOURCE specific ---------------------------
def test_classification_is_specific_to_the_claim_source_pair(cache, store):
    """The same source is a different witness for two different claims.

    This is the property the researcher's correction turns on: witness status is
    not a property of a provider.
    """
    cache.put("entity", {"qid": "Q10", "lang": "en"},
              _entity_payload("Q10", "P582",
                              [_reference_url("https://treaties.un.org/x")]), source="test")
    cache.put("entity", {"qid": "Q11", "lang": "en"},
              _entity_payload("Q11", "P582", None), source="test")
    classifier = WitnessClassifier(cache, _policy())
    src = _source(store)
    assert classifier.classify(src, [("Q10", "P582")]).classification is WitnessClass.SAME
    assert classifier.classify(src, [("Q11", "P582")]).classification is WitnessClass.INDEPENDENT


def test_two_sources_differ_on_one_claim(cache, store):
    """And symmetrically: one claim, two sources, two classifications."""
    cache.put("entity", {"qid": "Q12", "lang": "en"},
              _entity_payload("Q12", "P577",
                              [_reference_url("https://api.crossref.org/works/10.1/x")]),
              source="test")
    classifier = WitnessClassifier(cache, _policy())
    cited = _source(store, provider="crossref", url="https://api.crossref.org/works/10.1/x")
    other = _source(store, provider=APPROVED, url=SOURCE_URL)
    assert classifier.classify(cited, [("Q12", "P577")]).classification is WitnessClass.SAME
    assert classifier.classify(other, [("Q12", "P577")]).classification is WitnessClass.INDEPENDENT


def test_a_redirect_target_recorded_in_the_note_also_counts_as_our_host(cache, store):
    """doi.org -> api.crossref.org: the final host is the one that was read."""
    cache.put("entity", {"qid": "Q13", "lang": "en"},
              _entity_payload("Q13", "P577",
                              [_reference_url("https://api.crossref.org/works/10.2/y")]),
              source="test")
    src = _source(store, provider="crossref", url="https://doi.org/10.2/y",
                  note="final_url=https://api.crossref.org/works/10.2/y")
    verdict = WitnessClassifier(cache, _policy()).classify(src, [("Q13", "P577")])
    assert verdict.classification is WitnessClass.SAME


# --- claims are read from the constraint's own evidence --------------------
def test_claims_come_from_supports_gold_wikidata_evidence_only():
    base = _constraint()
    c = _with_evidence(base, "Q155 P36")
    assert claims_from_constraint(c) == [("Q155", "P36")]
    assert claims_from_constraint(_with_evidence(base, "Q155 P36", supports_gold=False)) == []
    assert claims_from_constraint(_with_evidence(base, "Q155 P36", source="britannica")) == []
    assert claims_from_constraint(_with_evidence(base, "not a qid")) == []
    assert claims_from_constraint(_with_evidence(base, "Q155")) == [("Q155", None)]


# --- the validator gate ----------------------------------------------------
def _temporal_draft(store, **src_overrides) -> Constraint:
    """A C4 constraint (so corroboration is required) carrying one source."""
    c = _constraint()
    src = _source(store, **src_overrides)
    record = {
        **c.to_record(),
        "evidence": [
            Evidence(
                source="wikidata", query="Q33946 P576",
                url="https://www.wikidata.org/wiki/Q33946",
                retrieved_at=dt.date(2026, 10, 7), observed_value="1992-12-31",
                supports_gold=True, comparison="exact match",
            ).model_dump(mode="json")
        ],
        "corroborating_sources": [src.model_dump(mode="json")],
        "verification_status": VerificationStatus.EVIDENCE_VERIFIED.value,
    }
    return Constraint.model_validate(record)


def test_same_witness_cannot_satisfy_the_promotion_gate(cache, store):
    """The whole point of the correction: descriptive, never qualifying.

    Run against the REAL approved policy, so this fails if the shipped provider
    list and the shipped gate ever disagree.
    """
    cache.put("entity", {"qid": "Q33946", "lang": "en"},
              _entity_payload("Q33946", "P576",
                              [_reference_url("https://treaties.un.org/doc/x")]),
              source="test")
    c = _temporal_draft(store)
    validator = BenchmarkDesignValidator(
        witness_classifier=WitnessClassifier(cache, _policy())
    )
    report = validator.validate([c], split=c.split)
    rule = next(r for r in report.results if r.rule == "corroboration")
    assert not rule.passed
    assert rule.severity == "error", "a promoted constraint with no independent witness must fail"
    assert any("same-witness" in o for o in rule.offenders)


def test_independent_witness_satisfies_the_promotion_gate(cache, store):
    cache.put("entity", {"qid": "Q33946", "lang": "en"},
              _entity_payload("Q33946", "P576", None), source="test")
    c = _temporal_draft(store)
    validator = BenchmarkDesignValidator(
        witness_classifier=WitnessClassifier(cache, _policy())
    )
    rule = next(
        r for r in validator.validate([c], split=c.split).results if r.rule == "corroboration"
    )
    assert rule.passed, rule.offenders


# ===========================================================================
# Q26 — provider-level identity, approved 2026-10-07.
#
# The first rule matched a reference URL "on the same host". Live validation
# showed that is too narrow in the direction that wrongly permits promotion:
# five of the eight approved providers are multi-host categories, so a claim can
# cite the provider on one of its hosts while the corroborating artefact comes
# from another. These tests pin the corrected rule and the refusal to infer
# ownership from anything but an explicit mapping.
# ===========================================================================
NASA_REFERENCE_URL = "https://www.nasa.gov/mission_pages/station/structure/iss_assembly_2a.html"
NSSDCA_ARTIFACT = "https://nssdc.gsfc.nasa.gov/nmc/spacecraft/display.action?id=1998-069F"


def test_q26_same_provider_same_host_is_same_witness(cache, store):
    cache.put("entity", {"qid": "Q20", "lang": "en"},
              _entity_payload("Q20", "P361",
                              [_reference_url("https://nssdc.gsfc.nasa.gov/nmc/other")]),
              source="test")
    src = _source(store, provider="nasa", url=NSSDCA_ARTIFACT)
    v = WitnessClassifier(cache, _policy()).classify(src, [("Q20", "P361")])
    assert v.classification is WitnessClass.SAME
    assert v.qualifies is False


def test_q26_the_real_nasa_case_same_provider_different_host_is_same_witness(cache, store):
    """The case that forced Q26, reproduced exactly.

    Wikidata's Q533336 P361 -> Q2025902 (Unity is part of the US Orbital
    Segment) cites www.nasa.gov. The authoritative NASA artefact for that fact
    is the NSSDCA master-catalogue record on nssdc.gsfc.nasa.gov. Same approved
    provider, different host: the claim already cites this provider, so the
    source is NOT independent confirmation of it.
    """
    cache.put("entity", {"qid": "Q533336", "lang": "en"},
              _entity_payload("Q533336", "P361", [_reference_url(NASA_REFERENCE_URL)]),
              source="test")
    src = _source(store, provider="nasa", url=NSSDCA_ARTIFACT)
    v = WitnessClassifier(cache, _policy()).classify(src, [("Q533336", "P361")])
    assert v.classification is WitnessClass.SAME, (
        "a different host of the same approved provider must be a same-witness; this is "
        "the exact under-detection Q26 corrects"
    )
    assert v.qualifies is False
    assert "www.nasa.gov" in v.reason
    assert "same provider" in v.reason


def test_q26_a_different_approved_provider_can_still_be_independent(cache, store):
    """Rule 3: another approved provider is not disqualified by this rule."""
    cache.put("entity", {"qid": "Q21", "lang": "en"},
              _entity_payload("Q21", "P361", [_reference_url(NASA_REFERENCE_URL)]),
              source="test")
    src = _source(store, provider=APPROVED, url=SOURCE_URL)
    v = WitnessClassifier(cache, _policy()).classify(src, [("Q21", "P361")])
    assert v.classification is WitnessClass.INDEPENDENT
    assert v.qualifies is True


def test_q26_an_unmapped_cited_host_is_undetermined_not_independent(cache, store):
    """Rule 4: if ownership cannot be established, refuse rather than accept."""
    cache.put("entity", {"qid": "Q22", "lang": "en"},
              _entity_payload("Q22", "P361",
                              [_reference_url("https://example.invalid/page")]),
              source="test")
    src = _source(store, provider="nasa", url=NSSDCA_ARTIFACT)
    v = WitnessClassifier(cache, _policy()).classify(src, [("Q22", "P361")])
    assert v.classification is WitnessClass.UNDETERMINED
    assert v.qualifies is False
    assert "example.invalid" in v.reason


def test_q26_ownership_is_never_inferred_from_a_similar_domain(cache, store):
    """Rule 6: `nasa.gov` does not vouch for an unlisted lookalike host.

    `nasa.gov.example.net` and `fake-nasa.gov` share substrings with a declared
    host and must NOT be treated as the provider. They resolve to no provider,
    so the verdict is undetermined — never same-witness by accident, and never
    independent-witness by accident either.
    """
    for lookalike in ("https://nasa.gov.example.net/x", "https://fake-nasa.gov/y",
                      "https://sub.nssdc.gsfc.nasa.gov/z"):
        cache.put("entity", {"qid": "Q23", "lang": "en"},
                  _entity_payload("Q23", "P361", [_reference_url(lookalike)]),
                  source="test")
        cache._memo.clear()
        classifier = WitnessClassifier(cache, _policy())
        assert classifier.provider_of_host(
            lookalike.split("/")[2]) is None, f"{lookalike} must own no provider"
        v = classifier.classify(
            _source(store, provider="nasa", url=NSSDCA_ARTIFACT), [("Q23", "P361")]
        )
        assert v.classification is WitnessClass.UNDETERMINED, lookalike


def test_q26_a_source_from_an_undeclared_host_is_undetermined(cache, store):
    """Provider identity must hold for the SOURCE too, not only the citation."""
    cache.put("entity", {"qid": "Q24", "lang": "en"},
              _entity_payload("Q24", "P361", None), source="test")
    src = _source(store, provider="nasa", url="https://history.nasa.gov/unlisted")
    v = WitnessClassifier(cache, _policy()).classify(src, [("Q24", "P361")])
    assert v.classification is WitnessClass.UNDETERMINED
    assert "does not declare" in v.reason


def test_q26_a_provider_with_no_declared_hosts_is_undetermined(cache, store):
    """An unmapped provider cannot be reasoned about at all."""
    policy = _policy()
    policy.cfg["approved_independent_providers"] = [*policy.approved_providers, "govinfo"]
    cache.put("entity", {"qid": "Q25", "lang": "en"},
              _entity_payload("Q25", "P361", None), source="test")
    src = _source(store, provider="govinfo", url="https://www.govinfo.gov/content/x.pdf")
    v = WitnessClassifier(cache, policy).classify(src, [("Q25", "P361")])
    assert v.classification is WitnessClass.UNDETERMINED
    assert "no provider_hosts" in v.reason


def test_q26_same_witness_still_cannot_satisfy_the_promotion_gate(cache, store):
    """The whole point: provider-level detection must BLOCK, not merely label."""
    cache.put("entity", {"qid": "Q33946", "lang": "en"},
              _entity_payload("Q33946", "P576", [_reference_url(NASA_REFERENCE_URL)]),
              source="test")
    c = _temporal_draft(store, provider="nasa", url=NSSDCA_ARTIFACT)
    validator = BenchmarkDesignValidator(
        witness_classifier=WitnessClassifier(cache, _policy())
    )
    rule = next(
        r for r in validator.validate([c], split=c.split).results if r.rule == "corroboration"
    )
    assert not rule.passed
    assert rule.severity == "error"
    assert any("same-witness" in o for o in rule.offenders)


def test_q26_the_shipped_policy_maps_all_eight_approved_providers():
    """The mapping must cover the approved set, and only the approved set."""
    policy = CorroborationPolicy()
    mapped = set(policy.cfg["witness_classification"]["provider_hosts"])
    assert mapped == set(policy.approved_providers)
    for optional in ("ibge", "uk-parliament-api", "official-organisational-record"):
        assert optional not in mapped, "no optional provider was approved"
    # And the Q26 case is covered by the SHIPPED policy, not only by the fixture.
    classifier = WitnessClassifier(KBCache("/nonexistent", CacheMode.FROZEN), policy)
    assert classifier.provider_of_host("www.nasa.gov") == "nasa"
    assert classifier.provider_of_host("nssdc.gsfc.nasa.gov") == "nasa"
    assert classifier.provider_of_host("doi.org") == "crossref"
    assert classifier.provider_of_host("nasa.gov") is None, "no suffix matching"
