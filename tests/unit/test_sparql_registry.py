"""The registered SPARQL queries (configs/kb/sparql_queries.yaml).

The registry used to be a dict literal inside `kb/evidence.py`, so every C3
uniqueness count and every Axis-5 ranking would have added a one-off query to a
Python module. A query that decides whether a benchmark fact reaches
EVIDENCE_VERIFIED is part of the method, so it lives in configuration with the
rest of it. This moved WHERE queries live; the evidence methodology is unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from semintegrity.kb.evidence import (
    SUPPORTED_KINDS,
    QueryRegistryError,
    _sparql_registry,
    registered_queries,
    resolve_query,
)
from semintegrity.utils.paths import p as path_of

#: Queries the authoring plan depends on. Named explicitly so that deleting one
#: fails here rather than at authoring time.
REQUIRED = (
    "sovereign_states_with_capital",      # C3 functional uniqueness
    "inverse_property_subjects",          # C3, general form
    "entities_with_both_properties",      # C2 joint membership
    "class_members_ranked_by_measure",    # Axis-5 ranked_source
    "located_members_ranked_by_measure",  # Axis-5, geographically restricted
)


def test_registry_has_a_version_and_provenance():
    reg = _sparql_registry()
    assert reg["registry_version"] >= 1
    prov = reg["provenance"]
    assert "query.wikidata.org" in prov["endpoint"]
    assert "ADR-0011" in prov["cached_as"]


@pytest.mark.parametrize("name", REQUIRED)
def test_required_query_resolves(name):
    """A required registered query must resolve for its declared parameters."""
    entry = _sparql_registry()["queries"][name]
    sample = {"qid": "Q42", "property": "P31"}
    params = {k: sample[kind] for k, kind in (entry.get("parameters") or {}).items()}
    text = resolve_query(name, params)
    assert text.strip()
    assert "SELECT" in text
    assert "{" + "}" not in text


@pytest.mark.parametrize("name", REQUIRED)
def test_every_query_declares_version_description_and_count_label(name):
    entry = _sparql_registry()["queries"][name]
    assert entry["version"] >= 1
    assert entry["description"].strip()
    assert entry["count_label"].strip()


def test_every_parameter_has_a_known_type():
    reg = _sparql_registry()
    patterns = reg["parameter_patterns"]
    for name, entry in reg["queries"].items():
        for key, kind in (entry.get("parameters") or {}).items():
            assert kind in patterns, (name, key, kind)


def test_every_placeholder_is_a_declared_parameter():
    """No query may contain a placeholder it does not declare, or vice versa."""
    import re

    for name, entry in _sparql_registry()["queries"].items():
        declared = set(entry.get("parameters") or {})
        used = set(re.findall(r"\{(\w+)\}", str(entry["query"])))
        assert used == declared, (name, sorted(used), sorted(declared))


# --- substitution is deterministic and refuses anything else -------------
def test_substitution_is_deterministic():
    a = resolve_query("sovereign_states_with_capital", {"city": "Q2844"})
    b = resolve_query("sovereign_states_with_capital", {"city": "Q2844"})
    assert a == b
    assert "wd:Q2844" in a


def test_unknown_query_is_refused():
    with pytest.raises(QueryRegistryError, match="no SPARQL query registered"):
        resolve_query("not_a_query")


@pytest.mark.parametrize(
    "params",
    [
        {},                                      # missing
        {"city": "Q2844", "extra": "Q1"},        # unexpected
        {"city": "Q2844 } UNION { ?x ?y ?z"},    # injection attempt
        {"city": "P36"},                         # wrong type
        {"city": "canberra"},                    # not a QID
        {"city": ""},                            # empty
    ],
)
def test_malformed_parameters_are_refused(params):
    with pytest.raises(QueryRegistryError):
        resolve_query("sovereign_states_with_capital", params)


def test_no_live_query_is_hidden_in_authoring_code():
    """Query text may live in the registry and nowhere else.

    A SELECT embedded in a module is a per-constraint ad-hoc query by another
    name: unreviewable as data and invisible to the registry's version field.
    """
    import re

    offenders = []
    for pattern in ("src/semintegrity", "scripts"):
        for file in Path(path_of(pattern)).rglob("*.py"):
            text = file.read_text(encoding="utf-8")
            for line in text.splitlines():
                if re.search(r"\bSELECT\b.*\bWHERE\b", line) and "wdt:" in line:
                    offenders.append(f"{file}: {line.strip()[:70]}")
    assert offenders == [], offenders


# --- the frozen cache must still replay ----------------------------------
def test_legacy_query_reproduces_the_cached_request_byte_for_byte():
    """The cache is keyed on the query string (ADR-0011).

    Re-indenting the pilot's query would turn a FROZEN replay into a cache miss
    and a live re-query, which is exactly what FROZEN mode exists to prevent.
    """
    expected = resolve_query("capitals_of_canberra").strip()
    cached = [
        json.loads(f.read_text())["request"]["query"]
        for f in sorted(Path(path_of("data/raw/wikidata_cache/sparql")).rglob("*.json"))
    ]
    if not cached:
        pytest.skip("no cached SPARQL request to compare against")
    # Search by content: the cache accumulates entries, so "the first file" is
    # whichever query ran most recently, not the pilot's.
    assert expected in cached, (
        "the legacy query text no longer matches any cached request; a FROZEN "
        "replay of the pilot would miss the cache and re-query"
    )


def test_legacy_query_is_marked_superseded():
    entry = _sparql_registry()["queries"]["capitals_of_canberra"]
    assert entry["superseded_by"] == "sovereign_states_with_capital"
    assert not entry.get("parameters")


def test_parameterised_form_matches_the_legacy_query_modulo_whitespace():
    """The superseding query must ask the same question as the one it replaces."""
    legacy = " ".join(resolve_query("capitals_of_canberra").split())
    modern = " ".join(resolve_query("sovereign_states_with_capital", {"city": "Q3114"}).split())
    assert legacy == modern


def test_sparql_count_is_still_a_supported_kind():
    assert "sparql_count" in SUPPORTED_KINDS


def test_registry_listing_is_sorted_and_complete():
    names = registered_queries()
    assert names == sorted(names)
    assert set(REQUIRED) <= set(names)
