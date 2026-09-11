"""Identifiers must be deterministic, parseable and range-checked."""

import pytest

from semintegrity.utils import ids


def test_constraint_id_shape():
    assert ids.constraint_id("C4", "geography", 3) == "K-C4-GEO-03"
    assert ids.constraint_id("C1", "public_office", 6) == "K-C1-POL-06"


def test_probe_and_constraint_round_trip():
    c = ids.constraint_id("C2", "biology", 1)
    p = ids.probe_id(c, 8)
    assert p == "K-C2-BIO-01-P08"
    assert ids.constraint_of(p) == c


def test_pair_id_is_unordered_and_canonical():
    a, b = "K-C4-GEO-03-P07", "K-C4-GEO-03-P02"
    assert ids.pair_id(a, b) == ids.pair_id(b, a) == "K-C4-GEO-03-P02xP07"


def test_pair_id_rejects_cross_constraint_and_self_pairs():
    with pytest.raises(ids.IdError):
        ids.pair_id("K-C4-GEO-03-P01", "K-C4-GEO-04-P01")
    with pytest.raises(ids.IdError):
        ids.pair_id("K-C4-GEO-03-P01", "K-C4-GEO-03-P01")


@pytest.mark.parametrize(
    "fn,args",
    [
        (ids.constraint_id, ("C5", "geography", 1)),
        (ids.constraint_id, ("C1", "not_a_domain", 1)),
        (ids.constraint_id, ("C1", "geography", 0)),
        (ids.schema_id, ("C9", 1)),
    ],
)
def test_malformed_inputs_raise(fn, args):
    with pytest.raises(ids.IdError):
        fn(*args)


def test_response_id_is_deterministic_and_timestamp_free():
    a = ids.response_id("run-1", "Qwen/Qwen2.5-7B-Instruct", "K-C1-GEO-01-P01", 0)
    b = ids.response_id("run-1", "Qwen/Qwen2.5-7B-Instruct", "K-C1-GEO-01-P01", 0)
    c = ids.response_id("run-1", "Qwen/Qwen2.5-7B-Instruct", "K-C1-GEO-01-P01", 1)
    assert a == b and a != c and a.startswith("R-")


def test_run_id_embeds_experiment_and_config_hash():
    rid = ids.run_id("primary_trackA", "deadbeefcafe0000")
    assert rid.startswith("primary_trackA-") and rid.endswith("-deadbe")
