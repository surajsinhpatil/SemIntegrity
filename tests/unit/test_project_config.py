"""The frozen numbers in the proposal must be arithmetically self-consistent.

If any of these fail, either a config was edited without an ADR or the design
lattice no longer closes.
"""

import math

import pytest

from semintegrity.utils.config import load_config, project_config


@pytest.fixture(scope="module")
def cfg():
    return project_config().data


def test_benchmark_counts_close(cfg):
    b = cfg["benchmark"]
    assert b["constraints_per_class"] * 4 == b["total_constraints"] == 120
    assert b["constraints_per_domain_per_class"] * len(cfg["domains"]) == b["constraints_per_class"]
    assert b["families"] * 4 == b["total_constraints"]
    assert b["families_per_domain"] * len(cfg["domains"]) == b["families"]
    assert b["schemas_per_class"] * b["instances_per_schema"] == b["constraints_per_class"]


def test_primary_probe_counts_close(cfg):
    pr = cfg["probes"]["primary"]
    assert pr["k"] * cfg["benchmark"]["total_constraints"] == pr["total"] == 960
    assert math.comb(pr["k"], 2) == pr["pairs_per_constraint"] == 28


def test_saturation_counts_close(cfg):
    s = cfg["probes"]["saturation"]
    assert s["constraints_per_class"] * 4 == s["constraints"] == 24
    # The first 8 of the 50 are the primary probes, so only 42 are new.
    assert s["constraints"] * (s["k"] - cfg["probes"]["primary"]["k"]) == s["additional_probes"] == 1008
    assert s["evaluated_at_k"][-1] == s["k"]
    assert s["evaluated_at_k"] == sorted(s["evaluated_at_k"])


def test_classes_are_not_ordered(cfg):
    """Guards against anyone modelling class as an ordinal/continuous term."""
    assert cfg["constraint_classes"]["ordered"] is False


def test_modal_and_counterfactual_are_excluded(cfg):
    excluded = {e["id"] for e in cfg["constraint_classes"]["excluded"]}
    assert excluded == {"modal", "counterfactual"}


def test_primary_endpoint_is_pscr_and_triad_is_intact(cfg):
    assert cfg["metrics"]["primary_endpoint"] == "PSCR"
    assert cfg["metrics"]["key_secondary"] == "PCS"
    assert set(cfg["metrics"]["reliability_triad"]) == {
        "TruthAccuracy",
        "PSCR",
        "AbstentionRate",
    }


def test_independent_unit_is_the_constraint(cfg):
    st = cfg["statistics"]
    assert st["independent_unit"] == "constraint"
    assert st["confirmatory"]["arm_size"] * 2 == cfg["benchmark"]["total_constraints"]


def test_quantisation_is_not_selective(cfg):
    assert cfg["inference"]["dtype"] == "bfloat16"
    assert cfg["inference"]["quantisation"] == "none"


def test_d4_is_never_a_detector(cfg):
    assert "NOT a contradiction detector" in cfg["detectors"]["d4_disclaimer"]


def test_five_models_are_configured():
    from semintegrity.utils.paths import p

    names = sorted(f.stem for f in p("configs/models").glob("*.yaml") if not f.stem.startswith("_"))
    assert len(names) == 5
    families = set()
    for n in names:
        families.add(load_config(f"configs/models/{n}.yaml").data["family"])
    # Roster reduced 2026-10-15: llama and gemma retired, olmo added.
    # Three families now — qwen carries the within-family scale axis
    # (3B/7B/14B), mistral and olmo provide cross-family contrast.
    assert families == {"qwen", "mistral", "olmo"}


def test_no_model_revision_is_fabricated():
    """A revision must be null (unpinned) or a real 40-char hex SHA."""
    from semintegrity.utils.paths import p

    for f in p("configs/models").glob("*.yaml"):
        if f.stem.startswith("_"):
            continue
        rev = load_config(f"configs/models/{f.stem}.yaml").data["revision"]
        assert rev is None or (isinstance(rev, str) and len(rev) == 40 and all(
            c in "0123456789abcdef" for c in rev
        )), f"{f.stem}: suspicious revision {rev!r}"


def test_judge_is_external_to_evaluated_families():
    judge = load_config("configs/models/_judge.yaml").data
    chosen = judge["primary_judge"]["model_id"]
    if chosen is not None:  # still UNRESOLVED at this phase
        lowered = chosen.lower()
        for banned in ("llama", "mistral", "qwen", "gemma"):
            assert banned not in lowered, f"judge {chosen} is inside an evaluated family"


def test_unresolved_scanner_finds_markers_and_ignores_literal_values():
    from semintegrity.utils.config import unresolved_decisions

    found = unresolved_decisions(
        {
            "splits": {"status": "UNRESOLVED"},
            "cluster": {"hostname": "UNKNOWN", "nested": {"gpu": "UNPROBED"}},
            "answer_types": {"abstain_token": "UNKNOWN"},  # literal model token, not a marker
            "fine": {"status": "ACCEPTED"},
        }
    )
    assert set(found) == {
        "splits.status = UNRESOLVED",
        "cluster.hostname = UNKNOWN",
        "cluster.nested.gpu = UNPROBED",
    }


def test_no_hand_written_revision_hashes_in_docs():
    """Every 40-hex SHA in the docs must match a pinned config revision.

    A hash typed by hand is a fabricated provenance claim even when it looks
    right, so the docs may only quote hashes that the pinning script resolved.
    """
    import re

    import yaml

    from semintegrity.utils.paths import p, project_root

    pinned = set()
    for f in p("configs/models").glob("*.yaml"):
        cfg = yaml.safe_load(f.read_text(encoding="utf-8"))
        for value in (cfg.get("revision"), *(
            (cfg.get(k) or {}).get("revision") for k in ("primary_judge", "reproducibility_judge")
        )):
            if isinstance(value, str):
                pinned.add(value)

    # DETECTOR configs can pin a revision too, which became true on 2026-10-15
    # when D2's NLI checkpoint was pinned in configs/detectors/d2_nli.yaml
    # (ADR-0023 D6). Scanning only configs/models/ left a blind spot: a
    # genuinely resolved hash looked fabricated. This WIDENS where a hash may be
    # pinned, it does NOT relax the rule — a SHA in the docs must still match a
    # revision some config actually carries.
    for f in p("configs/detectors").glob("*.yaml"):
        cfg = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        for block in cfg.values():
            if isinstance(block, dict) and isinstance(block.get("revision"), str):
                pinned.add(block["revision"])

    offenders = []
    for doc in p("docs").rglob("*.md"):
        for m in re.finditer(r"\b[0-9a-f]{40}\b", doc.read_text(encoding="utf-8")):
            if m.group() not in pinned:
                offenders.append(f"{doc.relative_to(project_root())}: {m.group()}")
    assert not offenders, (
        "documentation contains SHA-like strings that match no pinned revision — "
        f"these are fabricated unless resolved from the Hub: {offenders}"
    )


def test_no_source_directory_is_hidden_by_gitignore():
    """Every configs/ and scripts/ file must be visible to git.

    Regression test for a real bug: an unanchored `models/` rule in .gitignore,
    meant to keep model weights out of the repository, also matched
    `configs/models/` and `scripts/models/`. All five model configs — including
    the pinned revisions — were silently untracked for several commits. A rule
    intended to exclude weights was excluding source instead.
    """
    import subprocess

    from semintegrity.utils.paths import project_root

    root = project_root()
    if not (root / ".git").exists():  # pragma: no cover - non-git checkouts
        import pytest

        pytest.skip("not a git checkout")

    def _is_source(path):
        # *.egg-info is generated by an editable install, not authored source.
        if any(part.endswith(".egg-info") for part in path.parts):
            return False
        if "__pycache__" in path.parts:
            return False
        return path.suffix in {".py", ".yaml", ".yml", ".sh", ".txt", ".in"}

    candidates = [
        str(p.relative_to(root))
        for d in ("configs", "scripts", "src", "tests")
        for p in (root / d).rglob("*")
        if p.is_file() and _is_source(p)
    ]
    assert candidates, "found no source files to check"

    result = subprocess.run(
        ["git", "check-ignore", "--stdin"],
        input="\n".join(candidates),
        capture_output=True,
        text=True,
        cwd=root,
    )
    hidden = [line for line in result.stdout.splitlines() if line.strip()]
    assert not hidden, (
        "these source files are excluded by .gitignore and would never be "
        f"committed: {hidden}"
    )


def test_inference_backend_matches_adr_0013():
    """One stack for all models, and it is the one the ACCEPTED ADR records.

    Regression test, twice over. First `backend: transformers` was written by an
    edit whose anchor silently failed to match. Then the correction overshot: the
    backend was set to transformers citing ADR-0012 six minutes after ADR-0012 had
    been REJECTED and superseded by ADR-0013, which directs vLLM 0.19.1.
    """
    from semintegrity.utils.config import resolve_model_config
    from semintegrity.utils.paths import p

    names = sorted(f.stem for f in p("configs/models").glob("*.yaml") if not f.stem.startswith("_"))
    assert len(names) == 5

    backends = {n: resolve_model_config(n).data["backend"] for n in names}
    assert len(set(backends.values())) == 1, (
        f"§4.13 requires ONE stack across all models; got {backends}"
    )
    assert set(backends.values()) == {"vllm"}, (
        f"ADR-0013 selects vLLM 0.19.1; config says {set(backends.values())}"
    )


def test_adr_0015_is_still_the_accepted_decision():
    """If the ADR stops being ACCEPTED, the test above must be revisited deliberately.

    The first version of this guard asked whether ADR-0012 contained "SUPERSEDED"
    in upper case. The ADR said "superseded" in lower case, so the guard never
    fired on the very event it existed to catch. Matching case-insensitively and
    asserting the positive state caught the ADR-0013 -> ADR-0015 supersession
    immediately, which is the behaviour being preserved here.
    """
    from semintegrity.utils.paths import p

    adr = p("docs/decisions/ADR-0015-vllm-0112-glibc228.md").read_text(encoding="utf-8")
    status = next(ln for ln in adr.splitlines() if ln.startswith("**Status:**"))
    assert "ACCEPTED" in status.upper(), f"ADR-0015 is no longer accepted: {status}"
    assert "vllm" in adr.lower()

    for superseded_adr in (
        "docs/decisions/ADR-0012-inference-stack.md",
        "docs/decisions/ADR-0013-vllm-cuda12-pin.md",
    ):
        text = p(superseded_adr).read_text(encoding="utf-8")
        old = next(ln for ln in text.splitlines() if ln.startswith("**Status:**"))
        assert any(w in old.upper() for w in ("REJECTED", "SUPERSEDED")), (
            f"{superseded_adr} is live again; the backend decision must be re-examined: {old}"
        )


def test_the_pinned_inference_stack_matches_adr_0015():
    """The version pins live in the install script; ADR-0015 is the source of truth.

    A pin that drifts from the ADR is the same class of bug as a config that
    contradicted it (see 350f89b): the document says one thing and the thing
    that actually runs says another.
    """
    from semintegrity.utils.paths import p

    script = p("scripts/cluster/fix_torch_cuda.sh").read_text(encoding="utf-8")
    for var, value in (
        ("VLLM_VERSION", "0.11.2"),
        ("TORCH_VERSION", "2.9.0"),
        ("TORCHVISION_VERSION", "0.24.0"),
        ("TORCHAUDIO_VERSION", "2.9.0"),
    ):
        assert f'{var}="{value}"' in script, (
            f"fix_torch_cuda.sh does not pin {var}={value} as ADR-0015 requires"
        )


def test_serving_config_actually_reaches_the_vllm_backend():
    """Every serving key in the model config must be passed, not defaulted.

    Regression test for a silent config/code disagreement: both entry points
    built backend arguments by hand and omitted `tensor_parallel_size` and
    `gpu_memory_utilization`, so VLLMBackend fell back to tp=1 / util=0.90.
    Harmless for the small models and FATAL for llama33-70b, which declares
    tp=2 in config: ~141 GB at tp=1 on one 80 GB A100 OOMs, and only after
    queueing for two GPUs. The config said one thing and the code did another.
    """
    import inspect

    from semintegrity.inference.backend import VLLMBackend, serving_kwargs
    from semintegrity.utils.config import resolve_model_config

    for name in ("qwen25-3b", "qwen25-14b"):
        cfg = resolve_model_config(name).data
        kwargs = serving_kwargs(cfg, "vllm")
        assert kwargs["tensor_parallel_size"] == cfg["serving"]["tensor_parallel_size"]
        assert kwargs["gpu_memory_utilization"] == cfg["serving"]["gpu_memory_utilization"]
        assert kwargs["max_model_len"] == cfg["serving"]["max_model_len"]
        assert kwargs["revision"] == cfg["revision"]
        # and every key must be one VLLMBackend actually accepts
        accepted = set(inspect.signature(VLLMBackend.__init__).parameters) - {"self"}
        assert set(kwargs) <= accepted, f"unknown kwargs: {set(kwargs) - accepted}"

    # A tp>1 config must survive the round trip. llama33-70b was that case
    # until it was retired on 2026-10-15 (141 GB of weights against ~52 GB of
    # quota), and no roster model declares tp>1 any more -- so the override path
    # is exercised against the retired config, which still declares tp=2. Losing
    # this assertion with the model would quietly drop coverage of the exact bug
    # this test was written for.
    import yaml

    from semintegrity.utils.paths import project_root

    retired = yaml.safe_load(
        (project_root() / "configs/models/retired/llama33-70b.yaml").read_text()
    )
    assert retired["serving"]["tensor_parallel_size"] == 2
    merged = {**resolve_model_config("qwen25-14b").data, "serving": retired["serving"]}
    assert serving_kwargs(merged, "vllm")["tensor_parallel_size"] == 2


def test_both_entry_points_build_backend_args_the_same_way():
    """smoke.py and run_pilot.py must not drift: a smoke test that passes while
    the pilot it de-risks fails is worse than no smoke test."""
    from semintegrity.utils.paths import p

    for module in ("src/semintegrity/inference/smoke.py",
                   "src/semintegrity/inference/run_pilot.py"):
        text = p(module).read_text(encoding="utf-8")
        assert "serving_kwargs(" in text, f"{module} does not use the shared helper"
        assert "max_model_len=cfg.data" not in text, (
            f"{module} still hand-builds backend arguments"
        )


def test_cluster_yaml_has_no_duplicate_keys():
    """A duplicated YAML key silently keeps the LAST value.

    On 2026-10-15 an edit added `time: "01:30:00"` to resource_plan.small_models
    while a stale `time: "04:00:00"` remained below it; yaml.safe_load returned
    the stale one, so the config said 4 h while the sbatch said 1 h 30. A
    resource plan that disagrees with the job script is worse than none.
    """
    import yaml

    from semintegrity.utils.paths import project_root

    class _StrictLoader(yaml.SafeLoader):
        pass

    def _no_dupes(loader, node, deep=False):
        mapping = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=deep)
            if key in mapping:
                raise AssertionError(f"duplicate key {key!r} in configs/cluster/cluster.yaml")
            mapping[key] = loader.construct_object(value_node, deep=deep)
        return mapping

    _StrictLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_dupes
    )
    text = (project_root() / "configs" / "cluster" / "cluster.yaml").read_text()
    yaml.load(text, Loader=_StrictLoader)


def test_readiness_audit_model_count_matches_the_actual_roster():
    """The count CHECK and its MESSAGE must agree.

    A 2026-10-15 edit changed the failure text from "expected 7" to
    "expected 5" but left the condition at `!= 7`, so the audit reported the
    self-contradictory "expected 5 models, found 5". A gate whose message
    disagrees with its own test is worse than no gate.
    """
    import re

    from semintegrity.utils.paths import project_root

    src = (project_root() / "scripts/audit_benchmark_readiness.py").read_text()
    condition = re.search(r"if len\(names\) != (\d+):", src)
    message = re.search(r"expected (\d+) models, found", src)
    assert condition and message
    assert condition.group(1) == message.group(1), (
        f"condition checks {condition.group(1)} but the message says "
        f"{message.group(1)}"
    )
    roster = sorted(
        f.stem for f in (project_root() / "configs/models").glob("*.yaml")
        if not f.stem.startswith("_")
    )
    assert int(condition.group(1)) == len(roster), (
        f"audit expects {condition.group(1)} models; roster has {len(roster)}: {roster}"
    )
