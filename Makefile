# ─── Ground Control — Znuny dev stack ───────────────────────────────
SHELL := /bin/bash
# Interpola SEMPRE de .env (vars principais) + .env.prod (token do tunnel).
# docker compose mescla múltiplos --env-file (o último vence). Sem isso o
# ${CLOUDFLARE_TUNNEL_TOKEN} do cloudflared não é resolvido (fica MISSING).
DC := docker compose --env-file .env --env-file .env.prod

.DEFAULT_GOAL := help

.PHONY: help init build up down logs ps test shell psql redis-keys es-health reset

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n",$$1,$$2}'

# Arquivos reais (não .PHONY): criados dos exemplos só se ausentes, sem ruído.
.env:
	@cp -n .env.example .env && echo "✓ .env created from .env.example"
.env.prod:
	@cp -n .env.prod.example .env.prod && echo "✓ .env.prod created from .env.prod.example (paste real token)"

init: .env .env.prod ## Create .env / .env.prod from examples (no overwrite)
	@true

build: init ## Build the Znuny image
	$(DC) build

up: init ## Start the whole stack
	$(DC) up -d

down: init ## Stop the stack (keep volumes)
	$(DC) down

logs: init ## Tail logs (svc=NAME to filter)
	$(DC) logs -f $(svc)

ps: init ## Show container status
	$(DC) ps

test: init ## Run the end-to-end smoke test
	./scripts/smoke-test.sh

shell: init ## Shell into znuny-web
	$(DC) exec znuny-web /bin/bash

psql: init ## psql into the Znuny DB
	$(DC) exec postgres psql -U $${POSTGRES_USER:-znuny} -d $${POSTGRES_DB:-znuny}

redis-keys: init ## Show Znuny cache keys in Redis
	$(DC) exec redis redis-cli KEYS '*'

es-health: init ## OpenSearch cluster health
	$(DC) exec opensearch curl -fsS http://localhost:9200/_cluster/health?pretty

reset: init ## DESTROY everything (volumes incl. DB) and restart
	$(DC) down -v
	$(DC) up -d --build
