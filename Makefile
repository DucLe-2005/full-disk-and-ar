SHELL := /bin/sh

DOCKER_COMPOSE = docker compose
DEV_COMPOSE := $(DOCKER_COMPOSE) -f docker-compose.yml -f docker-compose.dev.yml
TEST_COMPOSE := $(DOCKER_COMPOSE) -f docker-compose.test.yml
PROD_COMPOSE := $(DOCKER_COMPOSE) -f docker-compose.prod.yml

SERVICE ?=
START_TIME ?=
END_TIME ?=

.DEFAULT_GOAL := help

.PHONY: help up start stop down shutdown restart build rebuild pull ps logs \
	config scrape-events backfill backfill-range test test-build test-api \
	test-solar-events test-web prod-pull prod-up prod-start prod-stop prod-down \
	prod-restart prod-build prod-rebuild prod-logs

help: ## Show the available commands.
	@awk 'BEGIN {FS = ":.*## "; printf "Usage: make <target> [SERVICE=name]\n\n"} /^[a-zA-Z0-9_-]+:.*## / {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

up: ## Create and start the development stack in the background.
	$(DEV_COMPOSE) up -d

start: ## Start existing development containers without recreating them.
	$(DEV_COMPOSE) start $(SERVICE)

stop: ## Stop development containers without removing them.
	$(DEV_COMPOSE) stop $(SERVICE)

down: ## Stop and remove development containers and networks.
	$(DEV_COMPOSE) down --remove-orphans

shutdown: ## Completely shut down and delete volumes and orphan containers.
	$(DEV_COMPOSE) down -v --remove-orphans

restart: ## Restart all services, or one with SERVICE=worker.
	$(DEV_COMPOSE) restart $(SERVICE)

build: ## Build all images, or one with SERVICE=api.
	$(DEV_COMPOSE) build $(SERVICE)

rebuild: ## Rebuild without cache and recreate all services, or SERVICE=api.
	$(DEV_COMPOSE) build --no-cache $(SERVICE)
	$(DEV_COMPOSE) up -d --force-recreate $(SERVICE)

pull: ## Pull newer base/service images used by development.
	$(DEV_COMPOSE) pull $(SERVICE)

ps: ## Show development container status.
	$(DEV_COMPOSE) ps

logs: ## Follow logs for all services, or one with SERVICE=worker.
	$(DEV_COMPOSE) logs -f $(SERVICE)

config: ## Validate and render the merged development Compose configuration.
	$(DEV_COMPOSE) config

scrape-events: ## Populate the solar-events database from the scraper.
	$(DEV_COMPOSE) exec solar-events-api python scraper.py

backfill: ## Queue the default historical prediction backfill.
	$(DEV_COMPOSE) exec api python -m app.scripts.backfill_predictions

backfill-range: ## Queue a custom range; requires START_TIME and END_TIME.
	@test -n "$(START_TIME)" || (echo "START_TIME is required" >&2; exit 2)
	@test -n "$(END_TIME)" || (echo "END_TIME is required" >&2; exit 2)
	$(DEV_COMPOSE) exec api python -m app.scripts.backfill_predictions --start-time "$(START_TIME)" --end-time "$(END_TIME)"

test: test-build test-api test-solar-events test-web ## Build and run every isolated test suite.

test-build: ## Build all isolated test images.
	$(TEST_COMPOSE) build

test-api: ## Run the main API test suite.
	$(TEST_COMPOSE) run --build --rm api-test

test-solar-events: ## Run the solar-events service test suite.
	$(TEST_COMPOSE) run --build --rm solar-events-test

test-web: ## Run the web test suite.
	$(TEST_COMPOSE) run --build --rm web-test

prod-pull: ## Pull images declared by the production Compose file.
	$(PROD_COMPOSE) pull $(SERVICE)

prod-up: ## Create and start the production stack in the background.
	$(PROD_COMPOSE) up -d

prod-start: ## Start existing production containers.
	$(PROD_COMPOSE) start $(SERVICE)

prod-stop: ## Stop production containers without removing them.
	$(PROD_COMPOSE) stop $(SERVICE)

prod-down: ## Stop and remove production containers and networks.
	$(PROD_COMPOSE) down --remove-orphans

prod-restart: ## Restart all production services, or one with SERVICE=api.
	$(PROD_COMPOSE) restart $(SERVICE)

prod-build: ## Build production images when the production file has build rules.
	$(PROD_COMPOSE) build $(SERVICE)

prod-rebuild: ## Rebuild and force-recreate production services.
	$(PROD_COMPOSE) build --no-cache $(SERVICE)
	$(PROD_COMPOSE) up -d --force-recreate $(SERVICE)

prod-logs: ## Follow production logs, optionally with SERVICE=api.
	$(PROD_COMPOSE) logs -f $(SERVICE)

	