COMPOSE_FILE = docker-compose.yml

# ─────────────────────────────────────────────
#  Core lifecycle
# ─────────────────────────────────────────────

generate:
	@echo "Generating docker-compose from config.yaml ..."
	python3 init-scripts/generator.py

up: generate
	@echo "Starting Smart LLM Gateway ..."
	docker compose -f $(COMPOSE_FILE) up --build -d
	@echo ""
	@echo "  Gateway  → http://localhost:8080/generate"
	@echo "  Status   → http://localhost:8081/status"
	@echo "  Metrics  → http://localhost:8081/metrics"
	@echo "  Nodes    → http://localhost:8081/nodes"

down:
	docker compose -f $(COMPOSE_FILE) down

restart: down up

rebuild:
	docker compose -f $(COMPOSE_FILE) down -v
	python3 init-scripts/generator.py
	docker compose -f $(COMPOSE_FILE) up --build -d

clean:
	docker compose -f $(COMPOSE_FILE) down -v --remove-orphans
	docker system prune -f

# ─────────────────────────────────────────────
#  Observability
# ─────────────────────────────────────────────

status:
	@curl -s http://localhost:8081/status | python3 -m json.tool

nodes:
	@curl -s http://localhost:8081/nodes | python3 -m json.tool

health:
	@curl -s http://localhost:8081/health

reload:
	@curl -s -X POST http://localhost:8081/config/reload | python3 -m json.tool

# ─────────────────────────────────────────────
#  Logs
# ─────────────────────────────────────────────

logs:
	docker compose -f $(COMPOSE_FILE) logs -f

logs-gateway:
	docker compose -f $(COMPOSE_FILE) logs -f gateway

logs-controller:
	docker compose -f $(COMPOSE_FILE) logs -f controller

# ─────────────────────────────────────────────
#  Testing
#
#  Targets accept optional args via ARGS=:
#    make test        ARGS="--requests 50 --concurrency 10"
#    make test-lb     ARGS="--requests 40"
#    make test-health ARGS="--url http://localhost:8081"
#    make check-models ARGS="--nodes ollama1:11434,ollama2:11434"
# ─────────────────────────────────────────────

# Quick smoke test — validates every endpoint
test-health:
	python3 test-scripts/test_health.py $(ARGS)

# Concurrent load test — latency, throughput, server distribution
test:
	python3 test-scripts/test_gateway.py $(ARGS)

# Distribution validator — confirms lb is spreading traffic
test-lb:
	python3 test-scripts/test_load_balancing.py $(ARGS)

# Model inspector — shows what each Ollama node has loaded
check-models:
	python3 test-scripts/check_models.py $(ARGS)

# Run all tests in order: smoke → distribution → load
test-all: test-health test-lb test

# ─────────────────────────────────────────────
#  Misc
# ─────────────────────────────────────────────

ps:
	docker compose -f $(COMPOSE_FILE) ps

show: generate
	@cat $(COMPOSE_FILE)

.PHONY: generate up down restart rebuild clean status nodes health reload \
        logs logs-gateway logs-controller \
        test test-lb test-health check-models test-all \
        ps show
