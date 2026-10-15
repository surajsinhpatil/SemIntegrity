"""The general experiment driver (semintegrity.inference.run_experiment).

These tests exist because `run_pilot` hard-codes `experiment_id="pilot_<split>"`
and `tier=Tier.PILOT` and never passes a seed, so a primary-tier run could not
be produced through it. The driver's whole job is that identity, workload and
decoding come from CONFIGURATION, so each test pins one way it could silently
lie about what was run.

No test here generates text: the stub backend is used where a run is needed, and
its output is FAKE by construction.
"""

from __future__ import annotations

import json

import pytest

from semintegrity.inference.run_experiment import (
    TIER_SPLIT,
    ExperimentConfigError,
    main,
    merged_generation,
    resolve_experiment,
)
from semintegrity.schemas.enums import Split, Tier, Track


def test_primary_resolves_to_the_test_split_at_primary_tier():
    cfg, sha, tier, track, split = resolve_experiment("primary")
    assert cfg["experiment"] == "primary_trackA"
    assert tier is Tier.PRIMARY
    assert track is Track.A
    assert split is Split.TEST
    assert len(sha) == 64


def test_pilot_is_the_only_tier_reading_the_pilot_split():
    pilot_tiers = [t for t, s in TIER_SPLIT.items() if s is Split.PILOT]
    assert pilot_tiers == [Tier.PILOT]


def test_every_tier_declares_a_split():
    """A tier with no declared split must be an error, not an assumption."""
    assert set(TIER_SPLIT) == set(Tier)


def test_unknown_experiment_names_the_available_ones():
    with pytest.raises(ExperimentConfigError) as exc:
        resolve_experiment("no-such-experiment")
    assert "available" in str(exc.value)
    assert "primary" in str(exc.value)


def test_primary_declares_the_five_roster_models():
    """Roster reduced 7 -> 5 on 2026-10-15; see configs/models/retired/."""
    cfg, *_ = resolve_experiment("primary")
    assert len(cfg["models"]) == 5
    assert set(cfg["models"]) == {
        "qwen25-3b", "qwen25-7b", "qwen25-14b", "mistral7b-v03", "olmo2-7b",
    }
    for retired in ("llama33-70b", "gemma2-9b", "llama31-8b"):
        assert retired not in cfg["models"]


def test_primary_workload_matches_the_frozen_benchmark():
    """960 = 120 constraints x K=8. A config that drifts from the split is a bug."""
    cfg, *_ = resolve_experiment("primary")
    assert cfg["workload"]["probes"] == 960
    assert cfg["workload"]["total_generations"] == 960 * 5


# --- generation merge ----------------------------------------------------
def test_experiment_decoding_overrides_the_model_block():
    model_gen = {"temperature": 0.7, "top_p": 0.9, "max_new_tokens": 128, "seed": 1}
    cfg = {"decoding": {"temperature": 0.0, "top_p": 1.0, "seed": 20250058},
           "max_new_tokens": 24}
    got = merged_generation(model_gen, cfg)
    assert got["temperature"] == 0.0
    assert got["top_p"] == 1.0
    assert got["seed"] == 20250058
    assert got["max_new_tokens"] == 24


def test_generation_merge_keeps_model_keys_the_experiment_does_not_mention():
    model_gen = {"temperature": 0.0, "stop_sequences": ["\n\n"], "seed": 7}
    got = merged_generation(model_gen, {"decoding": {"temperature": 0.0}})
    assert got["stop_sequences"] == ["\n\n"]
    assert got["seed"] == 7


def test_real_primary_config_yields_the_recorded_seed_and_fixed_decoding():
    from semintegrity.utils.config import resolve_model_config

    cfg, *_ = resolve_experiment("primary")
    gen = merged_generation(resolve_model_config("qwen25-3b").data["generation"], cfg)
    assert gen["seed"] == 20250058
    assert gen["temperature"] == 0.0
    assert gen["max_new_tokens"] == 24


# --- refusals ------------------------------------------------------------
def test_a_model_outside_the_experiment_list_is_refused():
    with pytest.raises(SystemExit) as exc:
        main(["--experiment", "primary", "--model", "_judge", "--dry-run"])
    assert "not in" in str(exc.value)


def test_dry_run_generates_nothing_and_succeeds(capsys):
    assert main(["--experiment", "primary", "--model", "qwen25-3b", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "primary_trackA" in out
    assert "nothing generated" in out


def test_stub_run_writes_primary_tier_records_with_the_seed(tmp_path):
    out = tmp_path / "stub.jsonl"
    assert main(["--experiment", "primary", "--model", "qwen25-3b", "--stub",
                 "--out", str(out)]) == 0
    rows = [json.loads(line) for line in out.read_text().splitlines() if line.strip()]
    assert len(rows) == 960, "the primary workload is 960 probes"
    first = rows[0]
    assert first["experiment_id"] == "primary_trackA"
    assert first["tier"] == "primary"
    assert first["track"] == "A"
    # The seed is the point: run_pilot never passed one.
    assert first["provenance"]["seed"] == 20250058
    assert first["provenance"]["temperature"] == 0.0
    assert len(first["provenance"]) == 22, "all 22 provenance fields (section 4.6)"


def test_stub_run_resumes_rather_than_duplicating(tmp_path):
    out = tmp_path / "stub.jsonl"
    main(["--experiment", "primary", "--model", "qwen25-3b", "--stub", "--out", str(out)])
    main(["--experiment", "primary", "--model", "qwen25-3b", "--stub", "--out", str(out)])
    rows = [line for line in out.read_text().splitlines() if line.strip()]
    assert len(rows) == 960, "a second pass must resume, not append a second copy"


def test_workload_mismatch_is_refused(tmp_path, monkeypatch):
    """A config that disagrees with the split on disk must not run."""
    import semintegrity.inference.run_experiment as mod

    real = mod.resolve_experiment

    def drifted(name):
        cfg, sha, tier, track, split = real(name)
        cfg = dict(cfg)
        cfg["workload"] = dict(cfg["workload"], probes=999)
        return cfg, sha, tier, track, split

    monkeypatch.setattr(mod, "resolve_experiment", drifted)
    with pytest.raises(SystemExit) as exc:
        mod.main(["--experiment", "primary", "--model", "qwen25-3b", "--dry-run"])
    assert "999" in str(exc.value)
    assert "960" in str(exc.value)


def test_missing_seed_is_refused_for_a_fixed_decoding_tier(monkeypatch):
    import semintegrity.inference.run_experiment as mod

    monkeypatch.setattr(mod, "merged_generation", lambda *_a, **_k: {"temperature": 0.0})
    with pytest.raises(SystemExit) as exc:
        mod.main(["--experiment", "primary", "--model", "qwen25-3b", "--dry-run"])
    assert "seed" in str(exc.value).lower()


def test_config_without_required_identity_keys_is_refused():
    from semintegrity.inference.run_experiment import _require

    with pytest.raises(ExperimentConfigError) as exc:
        _require({"tier": "primary"}, "experiment", "fake.yaml")
    assert "never defaulted" in str(exc.value)
