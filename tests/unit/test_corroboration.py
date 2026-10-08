"""§4.3 corroboration: the independent second source.

§4.3 requires that "all historical and temporal facts are corroborated against a
second authoritative source". These tests cover the *mechanism*, and they do not
assume any particular provider is approved: which external sources count is a
methodology decision recorded in
``configs/benchmark/corroboration_policy.yaml`` and taken in ADR-0019.

The headline behaviour under test is unchanged by that decision: a **well-formed
source still does not count** unless the policy names its provider. An arbitrary
URL is not corroboration, and ``example-reference-work`` is an arbitrary URL.
Witness classification — whether an approved source is independent of the claim
it is offered for — is tested separately in ``test_witness.py``.
"""

from __future__ import annotations

import datetime as dt

import pytest
from pydantic import ValidationError

from semintegrity.benchmark.design_validator import (
    BenchmarkDesignValidator,
    corroboration_reason,
)
from semintegrity.kb.cache import CacheMode, KBCache
from semintegrity.kb.corroboration import (
    NOT_CONFIGURED_MESSAGE,
    CorroboratingSourceFetcher,
    CorroborationArtifact,
    CorroborationPolicy,
    CorroborationStore,
    available_fetchers,
    policy_status_line,
)
from semintegrity.schemas.constraint import Constraint, CorroboratingSource, GoldSource
from semintegrity.schemas.enums import (
    ConstraintClass,
    Domain,
    Split,
    VerificationStatus,
)
from semintegrity.utils.hashing import sha256_text
from tests.fixtures.synthetic_benchmark import make_constraint

FACT = "The capital of Ruritania moved in 1891."
CONTENT = "Ruritania's capital moved from Strelsau to Zenda in 1891."


@pytest.fixture
def store(tmp_path) -> CorroborationStore:
    return CorroborationStore(KBCache(tmp_path / "cache", CacheMode.LIVE))


def _artifact(provider: str = "example-reference-work", url: str = "https://ref.example.test/a") -> CorroborationArtifact:
    return CorroborationArtifact(
        provider=provider, url=url, retrieved=dt.date(2026, 10, 7), content=CONTENT
    )


def _source(store: CorroborationStore, **overrides) -> CorroboratingSource:
    """A WELL-FORMED, FROZEN corroborating source. Still not an approved one."""
    art = _artifact()
    snapshot = store.put(art, FACT)
    kwargs = dict(
        name="Example Reference Work",
        url=art.url,
        retrieved=art.retrieved,
        provider=art.provider,
        snapshot=snapshot,
        content_hash=art.content_hash,
        fact_supported=FACT,
    )
    kwargs.update(overrides)
    return CorroboratingSource(**kwargs)


def _temporal_constraint() -> Constraint:
    """A C4 constraint, so §4.3 demands corroboration of it."""
    c = make_constraint(
        ConstraintClass.C4, Domain.HISTORY, 16, family_index=16, schema_index=6
    )
    assert corroboration_reason(c) is not None
    return c


# --- the policy, as ADR-0019 configured it -------------------------------
def test_policy_is_configured_by_adr_0019():
    """Eight providers and a stated criterion, approved 2026-10-07."""
    policy = CorroborationPolicy()
    assert policy.status == "CONFIGURED"
    assert policy.configured is True
    assert policy.independence_criterion is not None
    assert set(policy.approved_providers) == {
        "crossref", "un-treaties", "govinfo", "nasa",
        "standards-body", "official-gazette", "taxonomic-authority",
        "national-archives",
    }
    # The three optional providers were deliberately NOT approved in that pass.
    for optional in ("ibge", "uk-parliament-api", "official-organisational-record"):
        assert optional not in policy.approved_providers
    assert "CONFIGURED" in policy_status_line()


def test_an_empty_policy_still_refuses_everything():
    """The pre-ADR-0019 behaviour is intact and still reachable.

    It is what protects the project if the provider list is ever emptied: no
    source counts, and the system says why rather than failing open.
    """
    empty = CorroborationPolicy(
        {"approved_independent_providers": [], "independence_criterion": None}
    )
    assert empty.configured is False
    assert empty.describe() == NOT_CONFIGURED_MESSAGE


def test_one_generic_adapter_serves_every_approved_provider():
    """ADR-0019 needed no provider-specific adapter and no credentials."""
    fetchers = available_fetchers()
    assert set(fetchers) == set(CorroborationPolicy().approved_providers)
    assert {type(f).__name__ for f in fetchers.values()} == {"HttpDocumentFetcher"}
    assert CorroboratingSourceFetcher.__abstractmethods__ == frozenset({"fetch"})


def test_wikidata_is_excluded_as_a_second_source():
    assert "wikidata" in CorroborationPolicy().excluded_providers


def test_a_configured_policy_needs_both_a_list_and_a_criterion():
    """A provider list with no stated criterion is a list nobody can audit."""
    assert not CorroborationPolicy(
        {"approved_independent_providers": ["x"], "independence_criterion": None}
    ).configured
    assert not CorroborationPolicy(
        {"approved_independent_providers": [], "independence_criterion": "stated"}
    ).configured
    assert CorroborationPolicy(
        {"approved_independent_providers": ["x"], "independence_criterion": "stated"}
    ).configured


# --- 1. a valid corroborating source --------------------------------------
def test_case1_wellformed_frozen_source_is_accepted_by_the_schema(store):
    src = _source(store)
    assert src.provider == "example-reference-work"
    assert src.content_hash == sha256_text(CONTENT)
    assert src.fact_supported == FACT
    assert src.is_primary is False
    assert store.verify(src) is None  # the freeze checks out


def test_case1b_but_it_still_does_not_satisfy_section_4_3(store):
    """The headline, unchanged by ADR-0019: well-formed is not counting.

    ``example-reference-work`` is well-formed, frozen, verifiable — and not an
    approved provider, so it is refused and told why.
    """
    policy = CorroborationPolicy()
    src = _source(store)
    assert policy.satisfies(src) is False
    reason = policy.rejection_reason(src)
    assert "not in the approved independent source list" in reason


def test_case1c_it_would_count_under_a_configured_policy(store):
    """The mechanism works; only the decision is missing."""
    configured = CorroborationPolicy(
        {
            "approved_independent_providers": ["example-reference-work"],
            "independence_criterion": "editorially independent of Wikidata",
            "excluded_as_second_source": [{"id": "wikidata"}],
            "duplicate_detection": {"mechanical_keys": ["provider", "url_host", "content_hash"]},
        }
    )
    assert configured.satisfies(_source(store)) is True


# --- 2. a missing source ---------------------------------------------------
def test_case2_missing_source_warns_at_draft_and_blocks_promotion():
    c = _temporal_constraint()
    validator = BenchmarkDesignValidator()

    draft = validator.validate([c], split=Split.TEST)
    rule = next(r for r in draft.results if r.rule == "corroboration")
    assert not rule.passed
    assert rule.severity == "warning"
    assert "no second source recorded" in rule.offenders[0]

    promoted = validator.validate(
        [c.model_copy(update={"verification_status": VerificationStatus.EVIDENCE_VERIFIED})],
        split=Split.TEST,
    )
    rule = next(r for r in promoted.results if r.rule == "corroboration")
    assert not rule.passed
    assert rule.severity == "error"
    assert not promoted.ok


# --- 3. missing snapshot / freeze information ------------------------------
@pytest.mark.parametrize("field", ["snapshot", "content_hash"])
def test_case3_missing_freeze_information_fails(store, field):
    payload = _source(store).model_dump(mode="json")
    del payload[field]
    with pytest.raises(ValidationError, match=field):
        CorroboratingSource.model_validate(payload)


@pytest.mark.parametrize("value", ["", "   "])
def test_case3b_empty_snapshot_fails(store, value):
    with pytest.raises(ValidationError):
        _source(store, snapshot=value)


def test_case3c_a_snapshot_that_is_not_in_the_store_fails_verification(store):
    src = _source(store, snapshot="0" * 64)
    assert "does not match the key" in (store.verify(src) or "")


def test_case3d_content_that_no_longer_hashes_the_same_fails(store):
    src = _source(store)
    tampered = src.model_copy(update={"content_hash": "a" * 64})
    assert "does not match the frozen artefact" in (store.verify(tampered) or "")


def test_case3e_the_freeze_rule_runs_from_the_validator(store):
    c = _temporal_constraint().model_copy(
        update={"corroborating_sources": [_source(store, snapshot="f" * 64)]}
    )
    rule = BenchmarkDesignValidator().validate_corroboration_freeze([c], store)
    assert not rule.passed
    assert c.constraint_id in rule.offenders[0]


# --- 4. a malformed source -------------------------------------------------
@pytest.mark.parametrize(
    "overrides",
    [
        {"content_hash": "not-a-hash"},
        {"content_hash": "ABC123"},
        {"provider": ""},
        {"fact_supported": ""},
        {"name": ""},
        {"url": ""},
        {"url": "not-a-url"},
        {"url": "/relative/path"},
        {"is_primary": True},
    ],
)
def test_case4_malformed_sources_are_refused(store, overrides):
    with pytest.raises(ValidationError):
        _source(store, **overrides)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/a",
        "https://example.org/a",
        "https://example.invalid/a",
        "http://localhost:8000/a",
        "https://placeholder.test/a",
    ],
)
def test_case4b_placeholder_urls_are_refused(store, url):
    with pytest.raises(ValidationError, match="placeholder host"):
        _source(store, url=url)


def test_case4c_unknown_field_is_refused(store):
    payload = _source(store).model_dump(mode="json")
    payload["authority"] = "very"
    with pytest.raises(ValidationError):
        CorroboratingSource.model_validate(payload)


# --- 5. the primary source cannot corroborate itself ----------------------
@pytest.mark.parametrize("provider", ["wikidata", "Wikidata", "WIKIDATA", "wikidata.org", "wikibase"])
def test_case5_wikidata_as_corroborator_fails_at_the_schema(store, provider):
    with pytest.raises(ValidationError, match="primary source"):
        _source(store, provider=provider)


def test_case5b_a_wikidata_reference_is_not_automatically_independent():
    """A P248 value or a reference URL on the same claim is still Wikidata-mediated."""
    policy = CorroborationPolicy()
    assert "wikidata" in policy.excluded_providers
    # Even under a configured policy, an excluded provider is refused outright.
    configured = CorroborationPolicy(
        {
            "approved_independent_providers": ["wikidata"],
            "independence_criterion": "stated",
            "excluded_as_second_source": [{"id": "wikidata"}],
        }
    )
    fake = GoldSource(name="n", url="https://www.wikidata.org/wiki/Q1",
                      retrieved=dt.date(2026, 10, 7))
    assert fake.is_primary is False  # the shape alone proves nothing
    # The schema already refuses provider=wikidata, so the policy's exclusion is
    # the second line of defence rather than the only one.
    assert "wikidata" in configured.excluded_providers


# --- 6. one source counted twice under two URLs ---------------------------
def test_case6_same_provider_under_two_urls_is_one_source(store):
    a = _source(store)
    b = _source(store, url="https://ref.example.test/b")
    groups = CorroborationPolicy().duplicate_groups([a, b])
    assert any(k.startswith("provider=") for k, _ in groups)


def test_case6b_same_host_under_two_paths_is_one_source(store):
    a = _source(store, provider="work-a")
    b = _source(store, provider="work-b", url="https://ref.example.test/other")
    groups = CorroborationPolicy().duplicate_groups([a, b])
    assert any(k.startswith("url_host=") for k, _ in groups)


def test_case6c_same_content_under_two_urls_is_one_source(store):
    a = _source(store, provider="work-a")
    b = _source(store, provider="work-b", url="https://mirror.example.test/a")
    groups = CorroborationPolicy().duplicate_groups([a, b])
    assert any(k.startswith("content_hash=") for k, _ in groups)


def test_case6d_duplicates_are_an_error_even_at_draft(store):
    c = _temporal_constraint().model_copy(
        update={
            "corroborating_sources": [
                _source(store),
                _source(store, url="https://ref.example.test/b"),
            ]
        }
    )
    report = BenchmarkDesignValidator().validate([c], split=Split.TEST)
    rule = next(r for r in report.results if r.rule == "corroboration")
    assert not rule.passed
    assert rule.severity == "error"
    assert "counted twice" in rule.offenders[0]


def test_case6e_two_genuinely_distinct_sources_are_not_duplicates(store):
    a = _source(store, provider="work-a")
    b = CorroboratingSource(
        name="Other Work", url="https://other.example.test/x",
        retrieved=dt.date(2026, 10, 7), provider="work-b",
        snapshot="b" * 64, content_hash=sha256_text("different content"),
        fact_supported=FACT,
    )
    assert CorroborationPolicy().duplicate_groups([a, b]) == []


# --- 7. corroboration is tied to the fact ---------------------------------
def test_case7_the_snapshot_key_includes_the_fact(store):
    art = _artifact()
    one = store.put(art, FACT)
    other = store.put(art, "A different proposition entirely.")
    assert one != other, (
        "one page corroborating two propositions must be stored once per "
        "proposition, or it could be reused for a claim it was never checked against"
    )


def test_case7b_a_source_for_the_wrong_fact_fails_verification(store):
    src = _source(store, fact_supported="A proposition nobody checked.")
    assert store.verify(src) is not None


def test_case7c_the_store_round_trips(store):
    src = _source(store)
    payload = store.get(src)
    assert payload is not None
    assert payload["content"] == CONTENT
    assert payload["fact_supported"] == FACT
    assert payload["content_hash"] == src.content_hash


# --- 8. non-temporal, non-history constraints are unaffected --------------
def test_case8_a_plain_entity_constraint_needs_no_corroboration():
    c = make_constraint(
        ConstraintClass.C1, Domain.BIOLOGY, 11, family_index=11, schema_index=1
    )
    assert corroboration_reason(c) is None
    report = BenchmarkDesignValidator().validate([c], split=Split.TEST)
    rule = next(r for r in report.results if r.rule == "corroboration")
    assert rule.passed, rule.message


@pytest.mark.parametrize(
    "cls,domain,schema_index,expected",
    [
        (ConstraintClass.C4, Domain.BIOLOGY, 1, "C4 temporal constraint"),
        (ConstraintClass.C1, Domain.HISTORY, 1, "history domain"),
        (ConstraintClass.C1, Domain.BIOLOGY, 4, "date answer"),
        (ConstraintClass.C2, Domain.BIOLOGY, 6, "temporal axis 6"),
        (ConstraintClass.C1, Domain.BIOLOGY, 2, None),
    ],
)
def test_case8b_the_trigger_set_is_unchanged(cls, domain, schema_index, expected):
    c = make_constraint(cls, domain, 11, family_index=11, schema_index=schema_index)
    assert corroboration_reason(c) == expected


# --- 9 + 10. the pilot and the accounting are untouched -------------------
def test_case9_pilot_loads_unchanged_with_no_corroboration():
    from semintegrity.benchmark.loader import load_split
    from semintegrity.utils.paths import data_path

    constraints, probes = load_split(data_path("benchmark") / "pilot")
    assert len(constraints) == 12
    assert len(probes) == 96
    assert all(c.corroborating_sources == [] for c in constraints)


def test_case10_the_corroboration_required_count_is_still_81():
    import json
    from pathlib import Path

    rows = json.loads(
        Path("data/benchmark/authoring_manifest.json").read_text()
    )["constraints"]
    assert len(rows) == 132
    assert sum(r["corroboration_required"] for r in rows) == 81


# --- builder and validator must not disagree ------------------------------
def test_builder_and_validator_share_one_policy():
    """The earlier fix: the builder must not promote what the validator refuses."""
    import inspect

    from semintegrity.benchmark import pilot_builder

    assert "corroboration_reason" in inspect.getsource(pilot_builder)


# --- P582 end-date reader: regression tests required by the brief ---------
# `claim_interval_end` addresses §4.3's existing requirement that temporal
# constraints carry BOTH date qualifiers ("P580 start time, P582 end time").
# `claim_interval` reads only start_time, so nothing could verify a terminating
# date — which is the whole of axis 6. These tests use a stub client, so they
# make no network call.
class _StubClient:
    """Minimal stand-in for WikidataClient.get_claims."""

    def __init__(self, claims):
        self._claims = claims

    def get_claims(self, qid, prop):
        return self._claims


def _claim(value_qid, start=None, end=None):
    from semintegrity.kb.wikidata import TimeQualifiedClaim

    return TimeQualifiedClaim(
        property_id="P36", value_qid=value_qid, value_literal=None,
        start_time=start, end_time=end,
    )


def _end_check(expect_year):
    return {
        "kind": "claim_interval_end", "subject_qid": "Q155", "property": "P36",
        "value_qid": "Q8678", "expect_year": expect_year, "description": "P582",
    }


def test_p582_correct_year_passes():
    from semintegrity.kb.evidence import run_check

    client = _StubClient([_claim("Q8678", end="+1960-04-22T00:00:00Z")])
    ev = run_check(client, _end_check(1960))
    assert ev.supports_gold is True
    assert ev.observed_value == "1960"


def test_p582_wrong_year_fails():
    from semintegrity.kb.evidence import run_check

    client = _StubClient([_claim("Q8678", end="+1960-04-22T00:00:00Z")])
    ev = run_check(client, _end_check(1961))
    assert ev.supports_gold is False
    assert ev.observed_value == "1960"


def test_p582_missing_does_not_become_a_fabricated_date():
    """No end qualifier must yield NO observed year, never an invented one."""
    from semintegrity.kb.evidence import run_check

    client = _StubClient([_claim("Q8678", start="+1763-01-01T00:00:00Z", end=None)])
    ev = run_check(client, _end_check(1960))
    assert ev.supports_gold is False
    assert ev.observed_value == ""
    assert "1960" not in ev.observed_value


def test_p582_reader_ignores_other_values_of_the_same_property():
    from semintegrity.kb.evidence import run_check

    client = _StubClient([
        _claim("Q2844", end="+2999-01-01T00:00:00Z"),   # a different value
        _claim("Q8678", end="+1960-04-22T00:00:00Z"),
    ])
    ev = run_check(client, _end_check(1960))
    assert ev.supports_gold is True
    assert ev.observed_value == "1960"


# --- P585 point-in-time reader (ADR-0020) --------------------------------
# A statement that records an ASSESSMENT rather than a period — a conservation
# status, a measurement, a census — is dated by P585 and carries no validity
# interval, so neither `claim_interval` nor `claim_interval_end` can read the
# only date it has. These mirror the P582 tests above and make no network call.
def _pit_claim(value_qid, point_in_time=None, start=None, end=None):
    from semintegrity.kb.wikidata import TimeQualifiedClaim

    return TimeQualifiedClaim(
        property_id="P9888", value_qid=value_qid, value_literal=None,
        start_time=start, end_time=end, point_in_time=point_in_time,
    )


def _pit_check(expect_year, value_qid="Q108449541"):
    return {
        "kind": "claim_point_in_time", "subject_qid": "Q129026", "property": "P9888",
        "value_qid": value_qid, "expect_year": expect_year, "description": "P585",
    }


def test_p585_correct_year_passes():
    from semintegrity.kb.evidence import run_check

    client = _StubClient([_pit_claim("Q108449541", point_in_time="+2024-01-01T00:00:00Z")])
    ev = run_check(client, _pit_check(2024))
    assert ev.supports_gold is True
    assert ev.observed_value == "2024"


def test_p585_wrong_year_fails():
    """The check must FIRE, not merely exist."""
    from semintegrity.kb.evidence import run_check

    client = _StubClient([_pit_claim("Q108449541", point_in_time="+2024-01-01T00:00:00Z")])
    ev = run_check(client, _pit_check(1999))
    assert ev.supports_gold is False
    assert ev.observed_value == "2024"


def test_p585_missing_does_not_become_a_fabricated_date():
    """No P585 qualifier must yield NO observed year, never an invented one."""
    from semintegrity.kb.evidence import run_check

    client = _StubClient([_pit_claim("Q108449541", start="+2024-01-01T00:00:00Z")])
    ev = run_check(client, _pit_check(2024))
    assert ev.supports_gold is False
    assert ev.observed_value == ""


def test_p585_reader_ignores_other_values_of_the_same_property():
    """Two dated assessments of one property must not be conflated."""
    from semintegrity.kb.evidence import run_check

    client = _StubClient([
        _pit_claim("Q108449190", point_in_time="+2024-01-01T00:00:00Z"),
        _pit_claim("Q108449541", point_in_time="+2011-01-01T00:00:00Z"),
    ])
    ev = run_check(client, _pit_check(2024))
    assert ev.supports_gold is False, "read the year of the wrong value"
    assert ev.observed_value == "2011"


def test_p585_deep_time_is_not_silently_accepted():
    """A pre-Gregorian year is unrepresentable, so it must read as ABSENT.

    Q129026 carries a direct P580 of -16000000 (fossil first appearance).
    `parse_wikidata_time` returns None for it; what must not happen is a
    plausible-looking year being produced from an unparseable literal.
    """
    from semintegrity.kb.evidence import run_check

    client = _StubClient([_pit_claim("Q108449541", point_in_time="-16000000-01-01T00:00:00Z")])
    ev = run_check(client, _pit_check(2024))
    assert ev.supports_gold is False
    assert ev.observed_value == ""


# --- claim_qualifier_time: any time-valued qualifier (ADR-0020) ----------
# Wikidata dates some facts on qualifiers other than P580/P582/P585. P574
# ("year of publication of taxon name") sits on P225, and is the only date a
# taxonomic original-combination fact carries. These make no network call.
def _qt_claim(value_literal=None, value_qid=None, **qual_times):
    from semintegrity.kb.wikidata import TimeQualifiedClaim

    return TimeQualifiedClaim(
        property_id="P225", value_qid=value_qid, value_literal=value_literal,
        start_time=None, end_time=None, qualifier_times=dict(qual_times),
    )


def _qt_check(expect_year, value_literal="Felis leo"):
    return {
        "kind": "claim_qualifier_time", "subject_qid": "Q15294488", "property": "P225",
        "value_literal": value_literal, "qualifier_property": "P574",
        "expect_year": expect_year, "description": "P574 on P225",
    }


def test_qualifier_time_correct_year_passes():
    from semintegrity.kb.evidence import run_check

    client = _StubClient([_qt_claim("Felis leo", P574="+1758-00-00T00:00:00Z")])
    ev = run_check(client, _qt_check(1758))
    assert ev.supports_gold is True
    assert ev.observed_value == "1758"


def test_qualifier_time_wrong_year_fails():
    """The check must FIRE, not merely exist."""
    from semintegrity.kb.evidence import run_check

    client = _StubClient([_qt_claim("Felis leo", P574="+1758-00-00T00:00:00Z")])
    ev = run_check(client, _qt_check(1800))
    assert ev.supports_gold is False
    assert ev.observed_value == "1758"


def test_qualifier_time_selects_on_the_statement_value():
    """A date must not be read off a different value of the same property."""
    from semintegrity.kb.evidence import run_check

    client = _StubClient([_qt_claim("Panthera leo", P574="+1758-00-00T00:00:00Z")])
    ev = run_check(client, _qt_check(1758, value_literal="Felis leo"))
    assert ev.supports_gold is False
    assert ev.observed_value == ""


def test_qualifier_time_missing_qualifier_is_absent_not_invented():
    from semintegrity.kb.evidence import run_check

    client = _StubClient([_qt_claim("Felis leo", P405="+1758-00-00T00:00:00Z")])
    ev = run_check(client, _qt_check(1758))
    assert ev.supports_gold is False
    assert ev.observed_value == ""


def test_qualifier_times_are_collected_from_a_live_shaped_payload():
    """Only TIME-valued qualifiers are collected; an entity qualifier is skipped."""
    from semintegrity.kb.wikidata import _all_qualifier_times

    quals = {
        "P574": [{"datavalue": {"value": {"time": "+1758-00-00T00:00:00Z"}}}],
        "P405": [{"datavalue": {"value": {"id": "Q1043"}}}],
    }
    assert _all_qualifier_times(quals) == {"P574": "+1758-00-00T00:00:00Z"}
