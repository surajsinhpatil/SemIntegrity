# SemIntegrity — common tasks. Everything here is safe on a login node.
PY ?= python3
.DEFAULT_GOAL := help

.PHONY: help install test lint fmt typecheck validate-configs probe-cluster clean check

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Editable install with dev extras
	$(PY) -m pip install -e ".[dev]"

test: ## Run unit tests (no GPU, no network)
	$(PY) -m pytest -q -m "not gpu and not network"

lint: ## Ruff lint
	ruff check src tests scripts

fmt: ## Ruff format
	ruff format src tests

typecheck: ## mypy
	mypy

validate-configs: ## Parse every config and report unresolved decisions
	@$(PY) scripts/validate_configs.py; status=$$?; \
	if [ $$status -eq 1 ]; then echo "config validation FAILED"; exit 1; fi; \
	if [ $$status -eq 2 ]; then echo "(decisions still pending — informational, not a failure)"; fi

check: validate-configs lint test ## Everything that must pass before any sbatch
	@echo "All pre-flight checks passed. Safe to submit Slurm jobs."

probe-cluster: ## Read-only cluster reconnaissance (run on the login node)
	bash scripts/cluster/probe_cluster.sh

clean: ## Remove caches (never touches results/ or data/)
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache .mypy_cache
