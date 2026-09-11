"""Immutability and resume behaviour of the result store."""

import json

import pytest

from semintegrity.utils.io import (
    ImmutabilityError,
    append_jsonl,
    completed_keys,
    read_jsonl,
    write_json_exclusive,
)


def test_write_json_exclusive_refuses_to_overwrite(tmp_path):
    target = tmp_path / "snapshot.json"
    write_json_exclusive(target, {"a": 1})
    with pytest.raises(ImmutabilityError):
        write_json_exclusive(target, {"a": 2})
    assert json.loads(target.read_text())["a"] == 1


def test_append_and_read_round_trip(tmp_path):
    target = tmp_path / "r.jsonl"
    assert append_jsonl(target, [{"i": 0}, {"i": 1}]) == 2
    assert append_jsonl(target, [{"i": 2}]) == 1
    assert [r["i"] for r in read_jsonl(target)] == [0, 1, 2]


def test_truncated_tail_is_tolerated_but_mid_file_corruption_is_not(tmp_path):
    target = tmp_path / "r.jsonl"
    append_jsonl(target, [{"i": 0}, {"i": 1}])
    with target.open("a") as fh:
        fh.write('{"i": 2, "partial"')  # killed mid-write, no newline
    assert [r["i"] for r in read_jsonl(target)] == [0, 1]

    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"i": 0}\nnot json\n{"i": 2}\n')
    with pytest.raises(json.JSONDecodeError):
        list(read_jsonl(bad))


def test_completed_keys_supports_resume(tmp_path):
    target = tmp_path / "r.jsonl"
    append_jsonl(
        target,
        [
            {"model_id": "m", "probe_id": "K-C1-GEO-01-P01", "sample_index": 0},
            {"model_id": "m", "probe_id": "K-C1-GEO-01-P02", "sample_index": 0},
        ],
    )
    done = completed_keys(target, ["model_id", "probe_id", "sample_index"])
    assert ("m", "K-C1-GEO-01-P01", 0) in done
    assert ("m", "K-C1-GEO-01-P03", 0) not in done


def test_missing_resume_key_is_an_error_not_a_skip(tmp_path):
    target = tmp_path / "r.jsonl"
    append_jsonl(target, [{"model_id": "m"}])
    with pytest.raises(KeyError):
        completed_keys(target, ["model_id", "probe_id"])
