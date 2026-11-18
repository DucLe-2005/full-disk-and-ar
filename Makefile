SHELL := /bin/sh

DOCKER_COMPOSE = docker compose
DEV_COMPOSE := $(DOCKER_COMPOSE) -f docker-compose.yml -f docker-compose.dev.yml
TEST_COMPOSE := $(DOCKER_COMPOSE) -f docker-compose.test.yml
PROD_COMPOSE := $(DOCKER_COMPOSE) -f docker-compose.prod.yml

SERVICE ?=
START_TIME ?= 2026-01-01
END_TIME ?=
HOUR ?=
export START_TIME END_TIME

define sync_forecast_window
status=0; \
$(1) exec -T solar-events-api python scrape_window.py --start-time "$(2)" --end-time "$(3)" || status=1; \
$(1) run $(4) --rm -T predictor --start-time "$(2)" --end-time "$(3)" $(5) || status=1; \
exit $$status
endef

.DEFAULT_GOAL := help

.PHONY: help up start stop down shutdown restart build rebuild pull ps logs \
	config scrape-events predict-hour backfill backfill-range test test-build test-api \
	test-solar-events test-web prod-pull prod-up prod-start prod-stop prod-down \
	prod-restart prod-ps prod-logs prod-predict-hour prod-backfill

help: ## Show the available commands.
	@awk 'BEGIN {FS = ":.*## "; printf "Usage: make <target> [SERVICE=name]\n\n"} /^[a-zA-Z0-9_-]+:.*## / {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

up: ## Start the stack and sync events and forecasts for the last 24 UTC hours.
	$(DEV_COMPOSE) up -d --wait
	@window=$$($(DEV_COMPOSE) exec -T solar-events-api python -c 'from datetime import datetime, timedelta, timezone; end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0); print((end-timedelta(hours=24)).isoformat(), (end-timedelta(hours=1)).isoformat())') || exit $$?; \
	set -- $$window; \
	$(call sync_forecast_window,$(DEV_COMPOSE),$$1,$$2,,--allow-missing-magnetograms)

start: ## Start existing development containers without recreating them.
	$(DEV_COMPOSE) start $(SERVICE)

stop: ## Stop development containers without removing them.
	$(DEV_COMPOSE) stop $(SERVICE)

down: ## Stop and remove development containers and networks.
	$(DEV_COMPOSE) down --remove-orphans

shutdown: ## Completely shut down and delete volumes and orphan containers.
	$(DEV_COMPOSE) down -v --remove-orphans

restart: ## Restart all services, or one with SERVICE=api.
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

logs: ## Follow logs for all services, or one with SERVICE=api.
	$(DEV_COMPOSE) logs -f $(SERVICE)

config: ## Validate and render the merged development Compose configuration.
	$(DEV_COMPOSE) config

scrape-events: ## Populate the solar-events database from the scraper.
	$(DEV_COMPOSE) exec solar-events-api python scraper.py

predict-hour: ## Publish one UTC forecast. Set HOUR to replay an explicit slot.
	$(DEV_COMPOSE) run --rm -T predictor $(if $(HOUR),--hour "$(HOUR)",--current-hour) --attempts 3

backfill: ## Sync events and forecasts from START_TIME (default 2026-01-01) through END_TIME.
	@test -n "$$START_TIME" && test -n "$$END_TIME" || (echo "START_TIME and END_TIME are required" >&2; exit 2)
	$(DEV_COMPOSE) up -d --wait solar-events-api
	$(call sync_forecast_window,$(DEV_COMPOSE),$$START_TIME,$$END_TIME)

backfill-range: backfill

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
	$(PROD_COMPOSE) --profile forecast pull $(SERVICE)

prod-up: ## Start the production stack using previously pulled images.
	$(PROD_COMPOSE) up -d --wait --no-build --pull never

prod-start: ## Start existing production containers.
	$(PROD_COMPOSE) start $(SERVICE)

prod-stop: ## Stop production containers without removing them.
	$(PROD_COMPOSE) stop $(SERVICE)

prod-down: ## Stop and remove production containers and networks.
	$(PROD_COMPOSE) down --remove-orphans

prod-restart: ## Restart all production services, or one with SERVICE=api.
	$(PROD_COMPOSE) restart $(SERVICE)

prod-ps: ## Show production container status.
	$(PROD_COMPOSE) ps

prod-logs: ## Follow production logs, optionally with SERVICE=api.
	$(PROD_COMPOSE) logs -f $(SERVICE)

prod-predict-hour: ## Run the published predictor for the current UTC hour or HOUR.
	$(PROD_COMPOSE) run --no-deps --pull never --rm -T predictor $(if $(HOUR),--hour "$(HOUR)",--current-hour) --attempts 3

prod-backfill: ## Sync production events and forecasts from START_TIME through END_TIME.
	@test -n "$$START_TIME" && test -n "$$END_TIME" || (echo "START_TIME and END_TIME are required" >&2; exit 2)
	$(call sync_forecast_window,$(PROD_COMPOSE),$$START_TIME,$$END_TIME,--no-deps --pull never)
