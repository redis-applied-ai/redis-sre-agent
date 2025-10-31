# Makefile for redis-sre-agent
# Requires: uv (https://github.com/astral-sh/uv), docker-compose, mkdocs (installed via uv dev deps)

# Default goal
.DEFAULT_GOAL := help

UV ?= uv
NPM ?= npm
UI_DIR ?= ui
UI_DIST ?= $(UI_DIR)/dist

REDIS_DOCS_REPO_URL ?= https://github.com/redis/docs.git
REDIS_DOCS_BRANCH ?= main

.PHONY: help venv sync docs-build docs-serve local-services test test-integration test-all ui-install ui-dev ui-build redis-docs-sync

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

# --- Local services ---

local-services: ## Start local services with docker-compose up -d
	docker-compose up -d

# --- Testing ---

test: sync ## Run tests excluding integration tests
	$(UV) run pytest -m "not integration"

test-integration: sync ## Run integration tests only
	$(UV) run pytest -m integration

test-all: sync ## Run the full test suite (unit + integration)
	$(UV) run pytest


# --- UI ---

ui-install: ## Install UI dependencies (npm ci in ./ui)
	cd $(UI_DIR) && $(NPM) ci

ui-dev: ui-install ## Run the UI dev server (Vite)
	cd $(UI_DIR) && $(NPM) run dev

ui-build: ui-install ## Build the UI for production into $(UI_DIST)
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
