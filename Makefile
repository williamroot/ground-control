# ─── Ground Control — Znuny dev stack ───────────────────────────────
SHELL := /bin/bash
DC := docker compose

.DEFAULT_GOAL := help

.PHONY: help init build up down logs ps test shell psql redis-keys es-health reset

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n",$$1,$$2}'

init: ## Create .env / .env.prod from examples (no overwrite)
	@[ -f .env ]      || cp .env.example .env       && echo "✓ .env"
	@[ -f .env.prod ] || cp .env.prod.example .env.prod && echo "✓ .env.prod"

build: init ## Build the Znuny image
	$(DC) build

up: init ## Start the whole stack
	$(DC) up -d

down: ## Stop the stack (keep volumes)
	$(DC) down

logs: ## Tail logs (svc=NAME to filter)
	$(DC) logs -f $(svc)

ps: ## Show container status
	$(DC) ps

test: ## Run the end-to-end smoke test
	./scripts/smoke-test.sh

shell: ## Shell into znuny-web
	$(DC) exec znuny-web /bin/bash

psql: ## psql into the Znuny DB
	$(DC) exec postgres psql -U $${POSTGRES_USER:-znuny} -d $${POSTGRES_DB:-znuny}

redis-keys: ## Show Znuny cache keys in Redis
	$(DC) exec redis redis-cli KEYS '*'

es-health: ## OpenSearch cluster health
	$(DC) exec opensearch curl -fsS http://localhost:9200/_cluster/health?pretty

reset: ## DESTROY everything (volumes incl. DB) and restart
	$(DC) down -v
	$(DC) up -d --build
