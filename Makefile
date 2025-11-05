# Makefile for redis-sre-agent
# Requires: uv (https://github.com/astral-sh/uv), docker-compose, mkdocs (installed via uv dev deps)

# Default goal
.DEFAULT_GOAL := help

UV ?= uv
NPM ?= npm
UI_DIR ?= ui
UI_KIT_DIR ?= $(UI_DIR)/ui-kit
UI_DIST ?= $(UI_DIR)/dist

REDIS_DOCS_REPO_URL ?= https://github.com/redis/docs.git
REDIS_DOCS_BRANCH ?= main

.PHONY: help venv sync docs-build docs-serve local-services local-services-down local-services-logs test test-integration test-all ui-kit-install ui-kit-build ui-kit-dev ui-install ui-dev ui-build redis-docs-sync redis-docs-index

help: ## Show this help and available targets
	@awk 'BEGIN {FS = ":.*##"; printf "Usage: make <target>\n\nTargets:\n"} /^[a-zA-Z0-9][^:]*:.*##/ { printf "  %-20s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

venv: ## Create a virtual environment with uv (./.venv)
	$(UV) venv

sync: ## Sync project dependencies (including dev) into the uv virtualenv
	$(UV) sync --dev

# --- Documentation ---

docs-build: sync ## Build the MkDocs site into ./site
	$(UV) run mkdocs build

docs-serve: sync ## Run the MkDocs live-reload docs server (http://127.0.0.1:8000)
	$(UV) run mkdocs serve -a 127.0.0.1:8000


.PHONY: docs-gen docs-gen-check

docs-gen: sync ## Generate reference docs (CLI, REST) from code
	$(UV) run python scripts/generate_reference_docs.py

# Fails if generation produces diffs (useful in CI)
docs-gen-check: docs-gen ## Generate reference docs and fail if files changed
	@git diff --quiet -- docs/reference || (echo "Reference docs changed. Please run 'uv run python scripts/generate_reference_docs.py' and commit updates." && git --no-pager diff -- docs/reference && exit 1)

# --- Local services ---

local-services: ## Start local services with docker-compose up -d
	docker-compose up -d
	@echo ""
	@echo "Local services started:"
	@echo "  - SRE Agent API:       http://localhost:8000"
	@echo "  - SRE Agent UI:        http://localhost:3002"
	@echo "  - Grafana:             http://localhost:3001  (login: admin / admin)"
	@echo "  - Prometheus:          http://localhost:9090"
	@echo "  - Pushgateway:         http://localhost:9091"
	@echo "  - Tempo (traces):      http://localhost:3200"
	@echo "  - Loki (logs API):     http://localhost:3100"
	@echo "  - Redis (agent):       redis://localhost:7843"
	@echo "  - Redis (demo):        redis://localhost:7844"
	@echo "  - Redis (replica):     redis://localhost:7845"
	@echo "  - Redis Enterprise UI: https://localhost:8443  (self-signed cert)"
	@echo "  - Redis Enterprise API:https://localhost:9443"
	@echo ""
	@echo "Tips:"
	@echo "  docker-compose logs -f sre-agent"
	@echo "  docker-compose logs -f grafana prometheus redis redis-demo"
	@echo ""

# --- Testing ---

test: sync ## Run tests excluding integration tests
	$(UV) run pytest -m "not integration"

test-integration: sync ## Run integration tests only
	$(UV) run pytest -m integration

test-all: sync ## Run the full test suite (unit + integration)
	$(UV) run pytest


# --- UI ---

ui-kit-install: ## Install UI Kit dependencies (npm ci in ./ui/ui-kit)
	cd $(UI_KIT_DIR) && $(NPM) ci

ui-kit-build: ui-kit-install ## Build the UI Kit (produces dist/ for local package)
	cd $(UI_KIT_DIR) && $(NPM) run build

ui-kit-dev: ui-kit-install ## Watch-build the UI Kit (runs in watch mode)
	cd $(UI_KIT_DIR) && $(NPM) run dev

ui-install: ## Install UI dependencies (npm ci in ./ui)
	cd $(UI_DIR) && $(NPM) ci

ui-dev: ui-install ui-kit-build ## Run the UI dev server (Vite) and watch-build kit
	$(MAKE) -s ui-kit-dev &
	cd $(UI_DIR) && $(NPM) run dev

ui-build: ui-install ui-kit-build ## Build the UI for production into $(UI_DIST)
	cd $(UI_DIR) && $(NPM) run build

# --- Redis docs ---

redis-docs-sync: ## Clone or update redis/docs into ./redis-docs (no indexing)
	@if [ -d redis-docs/.git ]; then \
	  echo "Updating redis-docs (branch: $(REDIS_DOCS_BRANCH))..."; \
	  git -C redis-docs fetch origin; \
	  git -C redis-docs checkout $(REDIS_DOCS_BRANCH); \
	  git -C redis-docs pull --ff-only origin $(REDIS_DOCS_BRANCH); \
	elif [ -d redis-docs ]; then \
	  echo "Found ./redis-docs without .git; backing up and cloning fresh"; \
	  ts=$$(date +%s); \
	  mv redis-docs redis-docs.bak.$$ts; \
	  git clone --depth 1 --branch $(REDIS_DOCS_BRANCH) $(REDIS_DOCS_REPO_URL) redis-docs; \
	else \
	  echo "Cloning redis/docs into ./redis-docs ..."; \
	  git clone --depth 1 --branch $(REDIS_DOCS_BRANCH) $(REDIS_DOCS_REPO_URL) redis-docs; \
	fi

redis-docs-index: sync redis-docs-sync ## Scrape and index redis docs locally (full pipeline)
	$(UV) run redis-sre-agent pipeline full --scrapers redis_docs_local


# --- Local services management ---

local-services-down: ## Stop local services (docker-compose down)
	docker-compose down
	@echo "Local services stopped."

# Usage:
#   make local-services-logs            # follow default services
#   make local-services-logs SERVICES="sre-agent redis grafana"  # choose services
local-services-logs: ## Tail logs for key services (set SERVICES="..." to override)
	@services="$(SERVICES)"; \
	if [ -z "$$services" ]; then \
	  services="sre-agent sre-ui grafana prometheus redis redis-demo redis-demo-replica"; \
	fi; \
	echo "Following logs for: $$services"; \
	docker-compose logs -f --tail=100 $$services
