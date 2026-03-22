# -------------------------
# Variables
# -------------------------
COMPOSE_FILE=docker-compose.generated.yml

# -------------------------
# Generate Compose
# -------------------------
generate:
	@echo "🛠️ Generating docker-compose..."
	python3 init-scripts/Production-Ready-generator.py

# -------------------------
# Start System
# -------------------------
up: generate
	@echo "🚀 Starting system..."
	docker compose -f $(COMPOSE_FILE) up --build -d

# -------------------------
# Stop System
# -------------------------
down:
	@echo "🛑 Stopping system..."
	docker compose -f $(COMPOSE_FILE) down -v

# -------------------------
# Restart System
# -------------------------
restart: down up

# -------------------------
# Rebuild Clean
# -------------------------
rebuild: down generate up

# -------------------------
# Clean (Hard Reset)
# -------------------------
clean:
	@echo "🧹 Cleaning all containers, volumes..."
	docker compose -f $(COMPOSE_FILE) down -v --remove-orphans
	docker system prune -f

# -------------------------
# Show Generated Compose
# -------------------------
show: generate
	@echo "📄 Generated docker-compose:"
	@cat $(COMPOSE_FILE)

# -------------------------
# Status
# -------------------------
ps:
	docker compose -f $(COMPOSE_FILE) ps

# -------------------------
# Logs (All)
# -------------------------
logs:
	docker compose -f $(COMPOSE_FILE) logs -f

# -------------------------
# Logs (Controller)
# -------------------------
logs-controller:
	docker compose -f $(COMPOSE_FILE) logs -f ollama-controller

# -------------------------
# Logs (Gateway)
# -------------------------
logs-gateway:
	docker compose -f $(COMPOSE_FILE) logs -f gateway

# -------------------------
# Shell into Controller
# -------------------------
shell-controller:
	docker exec -it ollama-controller sh

# -------------------------
# Check Config inside Controller
# -------------------------
check-config:
	docker exec -it ollama-controller sh -c 'echo $$MODEL_REPLICAS'

# -------------------------
# Check Models on Nodes
# -------------------------
models:
	@echo "🧠 Checking models across nodes..."
	docker exec -it ollama-controller sh /test-scripts/check_models.sh

# -------------------------
# Test Load Balancing
# -------------------------
test-lb:
	@echo "🚀 Testing load balancing..."
	python3 test-scripts/test_load_balancing.py

# -------------------------
# Health Check (Quick)
# -------------------------
health:
	@echo "🔍 Checking container health..."
	docker compose -f $(COMPOSE_FILE) ps

# -------------------------
# Full Validation (Models + LB)
# -------------------------
validate: models test-lb
	@echo "✅ Full validation completed"