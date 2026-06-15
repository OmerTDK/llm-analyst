.DEFAULT_GOAL := help

# Path to the credit-data-platform repo — only needed for build-fixture and
# check-semantic-drift. Default resolves to a sibling of the main llm-analyst
# repo directory (not the worktree). Override when laying out repos differently:
#   make build-fixture CDP=/path/to/credit-data-platform
_REPO_ROOT := $(shell git worktree list 2>/dev/null | head -1 | awk '{print $$1}')
_REPO_PARENT := $(shell dirname "$(_REPO_ROOT)")
CDP ?= $(_REPO_PARENT)/credit-data-platform

.PHONY: help install lint test ci check-sha check-semantic-drift build-fixture sync-platform docker-build docker-test

help: ## List available targets
	@grep -E '^[a-zA-Z][a-zA-Z0-9_-]*:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "%-22s %s\n", $$1, $$2}'

install: ## Install dependencies into .venv
	uv sync

lint: ## Ruff lint and format check
	uv run ruff check .
	uv run ruff format --check .

test: ## Run the test suite
	uv run pytest -v

check-sha: ## Verify the committed fixture SHA matches the file on disk
	sha256sum -c tests/fixtures/FIXTURE_SHA

check-semantic-drift: ## Fail if vendored YAML diverges from the pinned platform commit
	@PLATFORM_TAG=$$(cat platform/PLATFORM_TAG) && \
	echo "Checking vendored YAML against credit-data-platform @ $$PLATFORM_TAG" && \
	diff -r platform/models/semantic/ $(CDP)/models/semantic/ && \
	diff platform/models/metricflow/metricflow_time_spine.sql $(CDP)/models/metricflow/metricflow_time_spine.sql && \
	echo "OK — vendored YAML is in sync" || \
	(echo "ERROR: vendored semantic YAML diverges from $(CDP). Run: make sync-platform CDP=$(CDP)" && exit 1)

ci: lint check-sha test ## Run the CI suite (lint + fixture SHA + tests); check-semantic-drift requires CDP repo

# ── Fixture management ────────────────────────────────────────────────────────

build-fixture: ## Build semantic_fixture.duckdb from credit-data-platform (run once, commit result)
	# Step 1: generate a small synthetic loan book (3 cohorts × 500 loans, seed=42)
	cd $(CDP) && uv run python -m loanbook generate --seed 42 --cohorts 3 --loans-per-cohort 500
	# Step 2: build the backing fact/mart models and the time spine in credit-data-platform
	cd $(CDP) && DBT_PROFILES_DIR=. uv run dbt build --exclude tag:elementary \
		--select "+dim_date +dim_product +dim_loan +dim_borrower +dim_loan_current_state \
		+fct_loan_state_event +metricflow_time_spine +fct_loan_lifecycle +fct_loan_origination \
		+fct_payment +mart_risk_prepayment_speed +mart_risk_vintage_curve"
	# Step 3: copy the DuckDB file into the fixture location
	cp $(CDP)/data/local/credit_platform.duckdb tests/fixtures/semantic_fixture.duckdb
	# Step 4: build the platform backing views and metricflow_time_spine on top of the fixture
	DBT_PROFILES_DIR=platform uv run dbt build \
		--project-dir platform \
		--select "backing metricflow_time_spine"
	# Step 5: record the SHA so CI can verify the fixture is intact
	$(MAKE) _write-sha
	@echo "Fixture rebuilt. Commit tests/fixtures/semantic_fixture.duckdb and tests/fixtures/FIXTURE_SHA."

sync-platform: ## Sync vendored YAML and rebuild fixture from CDP at a specific commit (TAG required)
	@test -n "$(TAG)" || (echo 'Usage: make sync-platform TAG=<commit-sha> CDP=<path>' && exit 1)
	cp $(CDP)/models/semantic/_sem_*.yml platform/models/semantic/
	cp $(CDP)/models/metricflow/metricflow_time_spine.sql platform/models/metricflow/
	$(MAKE) build-fixture CDP=$(CDP)
	@echo "$(TAG)" > platform/PLATFORM_TAG

_write-sha: ## Internal: write FIXTURE_SHA (called by build-fixture)
	@HASH=$$(sha256sum tests/fixtures/semantic_fixture.duckdb | awk '{print $$1}') && \
	echo "$$HASH  tests/fixtures/semantic_fixture.duckdb" > tests/fixtures/FIXTURE_SHA && \
	echo "SHA written: $$HASH"

docker-build: ## Build the project image
	docker build -t llm-analyst .

docker-test: ## Run the test suite inside the image
	docker run --rm llm-analyst
