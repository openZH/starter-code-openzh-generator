.DEFAULT_GOAL := help

.PHONY: help setup format format-check lint test check generate verify build

help: ## Show available commands
	@awk 'BEGIN {FS = ":.*## "} /^[a-z-]+:.*## / {printf "  %-14s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

setup: ## Install locked runtime and development dependencies
	uv sync --locked

format: ## Format Python source and tests
	uv run --no-sync ruff format src tests

format-check: ## Check formatting without changing files
	uv run --no-sync ruff format --check src tests

lint: ## Lint Python source and tests
	uv run --no-sync ruff check src tests

test: ## Run the full test suite (includes loopback HTTP tests)
	uv run --no-sync pytest

check: format-check lint test ## Run all CI quality checks

generate: ## Fetch catalogue metadata and regenerate local output
	uv run --no-sync updater

verify: ## Verify existing output without fetching metadata
	uv run --no-sync updater --verify-output

build: ## Build wheel and source distribution
	uv build --locked
