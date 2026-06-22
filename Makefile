# NowLens AI — developer task runner.
# Usage: `make <target>`. Run `make help` for the list.

.DEFAULT_GOAL := help
PYTHON ?= python
PKG := src/nowlens
TESTS := tests

.PHONY: help install install-dev format lint typecheck test test-cov check \
        serve bootstrap migrate clean docker-up docker-down docker-logs

help: ## Show this help
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## Install the package (runtime only)
	$(PYTHON) -m pip install -e .

install-dev: ## Install with dev + optional extras
	$(PYTHON) -m pip install -e ".[dev]"

format: ## Auto-format (black) and auto-fix lint (ruff)
	black $(PKG) $(TESTS)
	ruff check $(PKG) $(TESTS) --fix

lint: ## Lint (ruff) and check formatting (black)
	ruff check $(PKG) $(TESTS)
	black --check $(PKG) $(TESTS)

typecheck: ## Static type check (mypy)
	mypy src

test: ## Run the test suite (offline)
	pytest

test-cov: ## Run tests with coverage report
	pytest --cov=nowlens --cov-report=term-missing

check: lint typecheck test ## Full CI gate: lint + typecheck + test

serve: ## Run the API locally (auto-reload)
	nowlens serve --reload

bootstrap: ## Create the Qdrant collection
	nowlens bootstrap

migrate: ## Apply database migrations
	alembic upgrade head

docker-up: ## Build and start the full stack
	docker compose up -d --build

docker-down: ## Stop the stack
	docker compose down

docker-logs: ## Tail API logs
	docker compose logs -f api

clean: ## Remove caches and build artifacts
	rm -rf build dist *.egg-info .pytest_cache .ruff_cache .mypy_cache \
		htmlcov .coverage coverage.xml
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
