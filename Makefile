COMPOSE := docker compose

.DEFAULT_GOAL := help
.PHONY: help config build up down restart ps logs logs-backend logs-worker seed \
	backend-shell db-shell redis-cli backend-test frontend-test test clean

help:
	@echo "Smart Learning System"
	@echo "  make config         Validate the resolved Compose configuration"
	@echo "  make build          Build backend and frontend images"
	@echo "  make up             Build and start all services"
	@echo "  make down           Stop services (preserves named volumes)"
	@echo "  make restart        Restart application services"
	@echo "  make ps             Show service status"
	@echo "  make logs           Follow all service logs"
	@echo "  make logs-backend   Follow API logs"
	@echo "  make logs-worker    Follow Celery worker logs"
	@echo "  make seed           Create/update local demo accounts"
	@echo "  make backend-test   Run backend tests in the local Python environment"
	@echo "  make frontend-test  Run frontend tests with local Node.js"
	@echo "  make test           Run backend and frontend tests"
	@echo "  make clean          STOP services and DELETE local Docker data"

config:
	$(COMPOSE) config --quiet

build:
	$(COMPOSE) build

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down --remove-orphans

restart:
	$(COMPOSE) restart backend worker frontend

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f --tail=200

logs-backend:
	$(COMPOSE) logs -f --tail=200 backend

logs-worker:
	$(COMPOSE) logs -f --tail=200 worker

seed:
	$(COMPOSE) exec backend python -m app.seed

backend-shell:
	$(COMPOSE) exec backend /bin/sh

db-shell:
	$(COMPOSE) exec postgres psql -U smart_learning -d smart_learning

redis-cli:
	$(COMPOSE) exec redis redis-cli -a "$${REDIS_PASSWORD}"

backend-test:
	cd backend && python -m pytest -q

frontend-test:
	cd frontend && npm run test

test: backend-test frontend-test

# Destructive by design: use only when a full local reset is intended.
clean:
	$(COMPOSE) down --volumes --remove-orphans
