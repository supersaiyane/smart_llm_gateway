import os

# -------------------------
# Model Definitions
# -------------------------
MODEL_WEIGHTS = {
    "phi3:mini": 0.7,
    "llama3.2": 0.3
}

MODEL_REPLICAS = {
    "phi3:mini": 2,
    "llama3.2": 1
}

# -------------------------
# Dynamic Server Generation
# -------------------------
BASE_PORT = 11434

OLLAMA_SERVERS = []
MODEL_SERVERS = {}

idx = 1

for model, replicas in MODEL_REPLICAS.items():
    MODEL_SERVERS[model] = []

    for _ in range(replicas):
        server_url = f"http://ollama{idx}:11434"

        OLLAMA_SERVERS.append(server_url)
        MODEL_SERVERS[model].append(server_url)

        idx += 1


# -------------------------
# Other Config
# -------------------------
REDIS_HOST = os.getenv("REDIS_HOST", "redis")

CIRCUIT_TIMEOUT = 30
FAILURE_THRESHOLD = 3