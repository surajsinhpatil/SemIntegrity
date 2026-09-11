"""Configuration loading, snapshot hashing and path resolution."""


import pytest

from semintegrity.utils.config import (
    ConfigSnapshot,
    deep_merge,
    load_config,
    load_yaml,
    model_config,
    project_config,
    unresolved_decisions,
)
from semintegrity.utils.paths import data_path, p, project_root, results_path


# --- paths -----------------------------------------------------------------
def test_project_root_contains_the_marker():
    assert (project_root() / "configs" / "project.yaml").is_file()


def test_data_and_results_keys_resolve():
    assert data_path("benchmark").name == "benchmark"
    assert results_path("figures").name == "figures"


def test_unknown_path_key_lists_the_known_ones():
    with pytest.raises(KeyError, match="benchmark"):
        data_path("no_such_key")
    with pytest.raises(KeyError):
        results_path("no_such_key")


def test_env_override_requires_a_real_root(monkeypatch, tmp_path):
    project_root.cache_clear()
    monkeypatch.setenv("SEMINT_ROOT", str(tmp_path))
    try:
        with pytest.raises(FileNotFoundError, match="SEMINT_ROOT"):
            project_root()
    finally:
        monkeypatch.delenv("SEMINT_ROOT", raising=False)
        project_root.cache_clear()


def test_env_override_accepts_a_real_root(monkeypatch):
    real = project_root()
    project_root.cache_clear()
    monkeypatch.setenv("SEMINT_ROOT", str(real))
    try:
        assert project_root() == real
    finally:
        monkeypatch.delenv("SEMINT_ROOT", raising=False)
        project_root.cache_clear()


# --- config ----------------------------------------------------------------
def test_deep_merge_does_not_mutate_its_inputs():
    base = {"a": {"x": 1, "y": 2}, "b": 1}
    over = {"a": {"y": 3, "z": 4}}
    merged = deep_merge(base, over)
    assert merged == {"a": {"x": 1, "y": 3, "z": 4}, "b": 1}
    assert base == {"a": {"x": 1, "y": 2}, "b": 1}


def test_later_files_win_and_sources_are_recorded():
    snap = model_config("gemma2-9b")
    assert snap.data["model_id"] == "google/gemma-2-9b-it"
    assert snap.data["dtype"] == "bfloat16"  # inherited from _defaults
    assert snap.data["generation"]["temperature"] == 0.0  # inherited
    assert len(snap.sources) == 2
    assert snap.sources[0].endswith("_defaults.yaml")


def test_per_model_file_overrides_a_default():
    """gemma2-9b sets tensor_parallel_size itself; llama33-70b overrides it to 2."""
    assert model_config("gemma2-9b").data["serving"]["tensor_parallel_size"] == 1
    assert model_config("llama33-70b").data["serving"]["tensor_parallel_size"] == 2


def test_resolve_model_config_checks_required_keys_for_every_model():
    from semintegrity.utils.config import REQUIRED_MODEL_KEYS, resolve_model_config

    for name in ("llama31-8b", "mistral7b-v03", "qwen25-7b", "gemma2-9b",
                 "qwen25-3b", "qwen25-14b", "llama33-70b"):
        snap = resolve_model_config(name)
        assert set(snap.data) >= REQUIRED_MODEL_KEYS
        assert snap.data["dtype"] == "bfloat16"
        assert snap.data["quantisation"] == "none"


def test_resolve_model_config_rejects_selective_quantisation(tmp_path, monkeypatch):
    import semintegrity.utils.config as cfgmod

    bad = cfgmod.ConfigSnapshot(
        name="x",
        data={**cfgmod.model_config("qwen25-3b").data, "quantisation": "int4"},
        sources=(),
        sha256="0" * 64,
    )
    monkeypatch.setattr(cfgmod, "model_config", lambda _n: bad)
    with pytest.raises(ValueError, match="bf16 with no quantisation"):
        cfgmod.resolve_model_config("qwen25-3b")


def test_snapshot_hash_is_content_addressed():
    a, b = project_config(), project_config()
    assert a.sha256 == b.sha256 and len(a.sha256) == 64
    assert a.sha256 != model_config("qwen25-3b").sha256


def test_snapshot_dump_never_overwrites(tmp_path):
    snap = project_config()
    out = tmp_path / "snap.json"
    snap.dump(out)
    with pytest.raises(FileExistsError, match="never overwritten"):
        snap.dump(out)


def test_missing_config_names_the_path():
    with pytest.raises(FileNotFoundError, match="config not found"):
        load_config("configs/does_not_exist.yaml")


def test_load_config_requires_at_least_one_path():
    with pytest.raises(ValueError, match="at least one path"):
        load_config()


def test_non_mapping_yaml_is_rejected(tmp_path):
    bad = tmp_path / "list.yaml"
    bad.write_text("- a\n- b\n")
    with pytest.raises(TypeError, match="must contain a YAML mapping"):
        load_yaml(bad)


def test_empty_yaml_is_an_empty_mapping(tmp_path):
    empty = tmp_path / "empty.yaml"
    empty.write_text("")
    assert load_yaml(empty) == {}


def test_unresolved_scanner_reports_nested_paths():
    found = unresolved_decisions({"a": {"b": {"status": "UNRESOLVED"}}, "c": "UNKNOWN"})
    assert sorted(found) == ["a.b.status = UNRESOLVED", "c = UNKNOWN"]


def test_every_shipped_config_parses_and_hashes():
    """Guards against a config that loads in isolation but not through the loader."""
    for path in sorted(p("configs").rglob("*.yaml")):
        rel = str(path.relative_to(project_root()))
        snap = load_config(rel)
        assert isinstance(snap, ConfigSnapshot)
        assert len(snap.sha256) == 64
