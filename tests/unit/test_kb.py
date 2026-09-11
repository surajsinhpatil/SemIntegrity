"""Knowledge-base cache and client: offline replay, freeze integrity, no silent fetches."""

import datetime as dt

import pytest

from semintegrity.kb.adapter import StaticKB, WikidataKB
from semintegrity.kb.cache import CacheMiss, CacheMode, KBCache
from semintegrity.kb.wikidata import WikidataClient, WikidataError, parse_wikidata_time

AUSTRALIA = {
    "entities": {
        "Q408": {
            "labels": {"en": {"value": "Australia"}},
            "descriptions": {"en": {"value": "country in Oceania"}},
            "aliases": {"en": [{"value": "Commonwealth of Australia"}]},
            "sitelinks": {f"wiki{i}": {} for i in range(297)},
            "claims": {
                "P36": [
                    {
                        "mainsnak": {"datavalue": {"value": {"id": "Q3114"}}},
                        "qualifiers": {
                            "P580": [{"datavalue": {"value": {"time": "+1927-05-09T00:00:00Z"}}}]
                        },
                        "rank": "normal",
                    }
                ]
            },
        }
    }
}


@pytest.fixture
def seeded(tmp_path):
    cache = KBCache(tmp_path, CacheMode.LIVE)
    cache.put("entity", {"qid": "Q408", "lang": "en"}, AUSTRALIA, "seed")
    return tmp_path


# --- cache -----------------------------------------------------------------
def test_frozen_cache_refuses_writes(seeded):
    with pytest.raises(RuntimeError, match="FROZEN"):
        KBCache(seeded, CacheMode.FROZEN).put("entity", {"qid": "Q1"}, {}, "x")


def test_frozen_cache_miss_raises_rather_than_fetching(seeded):
    with pytest.raises(CacheMiss, match="snapshot"):
        KBCache(seeded, CacheMode.FROZEN).require("entity", {"qid": "Q999"})


def test_request_hash_is_order_independent():
    a = KBCache.request_hash("entity", {"qid": "Q1", "lang": "en"})
    b = KBCache.request_hash("entity", {"lang": "en", "qid": "Q1"})
    assert a == b
    assert a != KBCache.request_hash("entity", {"qid": "Q2", "lang": "en"})


def test_manifest_detects_tampering_and_untracked_files(seeded):
    cache = KBCache(seeded, CacheMode.LIVE)
    cache.write_manifest()
    assert cache.verify_manifest() == []

    entry = cache.entries()[0]
    entry.write_text(entry.read_text().replace("Australia", "Austria"))
    assert any("modified:" in p for p in cache.verify_manifest())


def test_untracked_entry_is_reported(seeded):
    cache = KBCache(seeded, CacheMode.LIVE)
    cache.write_manifest()
    cache.put("entity", {"qid": "Q99", "lang": "en"}, {"entities": {}}, "seed")
    assert any("untracked:" in p for p in cache.verify_manifest())


def test_missing_manifest_is_reported(tmp_path):
    assert "MANIFEST.json is missing" in KBCache(tmp_path, CacheMode.LIVE).verify_manifest()[0]


def test_refetch_archives_rather_than_overwrites(seeded):
    cache = KBCache(seeded, CacheMode.LIVE)
    before = len(cache.entries())
    cache.put("entity", {"qid": "Q408", "lang": "en"}, {"entities": {"Q408": {}}}, "refetch")
    assert len(cache.entries()) == before + 1
    assert any("superseded" in p.name for p in cache.entries())


# --- client ----------------------------------------------------------------
def test_client_resolves_entirely_offline(seeded):
    client = WikidataClient(KBCache(seeded, CacheMode.FROZEN))
    e = client.get_entity("Q408")
    assert e.label == "Australia"
    assert e.sitelinks == 297
    assert "Commonwealth of Australia" in e.aliases


def test_client_reads_temporal_qualifiers(seeded):
    client = WikidataClient(KBCache(seeded, CacheMode.FROZEN))
    claim = client.get_claims("Q408", "P36")[0]
    assert claim.value_qid == "Q3114"
    assert parse_wikidata_time(claim.start_time) == dt.date(1927, 5, 9)


def test_malformed_qid_is_rejected_before_any_lookup(seeded):
    client = WikidataClient(KBCache(seeded, CacheMode.FROZEN))
    with pytest.raises(ValueError, match="malformed QID"):
        client.get_entity("not-a-qid")


def test_missing_entity_surfaces_as_an_error(tmp_path):
    cache = KBCache(tmp_path, CacheMode.LIVE)
    cache.put("entity", {"qid": "Q1", "lang": "en"}, {"entities": {"Q1": {"missing": ""}}}, "seed")
    with pytest.raises(WikidataError, match="does not exist"):
        WikidataClient(KBCache(tmp_path, CacheMode.FROZEN)).get_entity("Q1")


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("+1901-01-01T00:00:00Z", dt.date(1901, 1, 1)),
        ("+1901-00-00T00:00:00Z", dt.date(1901, 1, 1)),  # unknown month/day clamp
        ("-0044-03-15T00:00:00Z", None),  # BCE out of scope
        (None, None),
        ("nonsense", None),
    ],
)
def test_wikidata_time_parsing(raw, expected):
    assert parse_wikidata_time(raw) == expected


# --- adapters --------------------------------------------------------------
def test_wikidata_kb_records_every_fact_it_used(seeded):
    kb = WikidataKB(KBCache(seeded, CacheMode.FROZEN))
    kb.entity_label("Q408")
    kb.sitelinks("Q408")
    assert kb.facts_used == ("label(Q408)", "sitelinks(Q408)")


def test_static_kb_raises_on_unknown_rather_than_returning_a_default():
    kb = StaticKB(labels={"Q1": "One"})
    assert kb.entity_label("Q1") == "One"
    with pytest.raises(KeyError):
        kb.entity_label("Q2")
    with pytest.raises(KeyError):
        kb.sitelinks("Q1")
    assert kb.claim_values("Q1", "P36") == []
