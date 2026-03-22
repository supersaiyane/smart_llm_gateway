import os
import sys
import json

sys.path.append(os.path.abspath("gateway"))

from config import MODEL_REPLICAS

services = []
volumes = []

idx = 1
port = 11434

ollama_nodes = []

# -------------------------
# Generate Ollama Services
# -------------------------
for model, replicas in MODEL_REPLICAS.items():
    for _ in range(replicas):

        name = f"ollama{idx}"
        volume_name = f"ollama_{name}_data"

        ollama_nodes.append(name)

        services.append(f"""
  {name}:
    image: ollama/ollama
    container_name: {name}
    ports:
      - "{port}:11434"
    volumes:
      - {volume_name}:/root/.ollama
    restart: unless-stopped
""")

        volumes.append(f"  {volume_name}:")

        idx += 1
        port += 1


# -------------------------
# Build dependency strings
# -------------------------
gateway_depends_lines = ""
controller_depends_lines = ""

for node in ollama_nodes:
    gateway_depends_lines += f"      - {node}\n"
    controller_depends_lines += f"      - {node}\n"

services_block = "".join(services)
volumes_block = "\n".join(volumes)

# -------------------------
# Inject Runtime Config
# -------------------------
model_config_json = json.dumps(MODEL_REPLICAS)
nodes_csv = ",".join(ollama_nodes)

# -------------------------
# Final Compose
# -------------------------
compose = f"""
version: "3.9"

services:

  # -------------------------
  # Core Services
  # -------------------------

  gateway:
    build: ./gateway
    container_name: smart-gateway
    ports:
      - "8081:8081"
    depends_on:
      - redis
{gateway_depends_lines}
    environment:
      REDIS_HOST: redis
    restart: unless-stopped    

  redis:
    image: redis:7
    container_name: smart-redis
    ports:
      - "6379:6379"
    restart: unless-stopped  

  nginx:
    image: nginx:latest
    container_name: smart-nginx
    ports:
      - "8080:80"
    volumes:
      - ./configs/nginx.conf:/etc/nginx/nginx.conf
    depends_on:
      - gateway       

  # -------------------------
  # Ollama Services
  # -------------------------
{services_block}

  # -------------------------
  # Controller (Self-Healing Brain)
  # -------------------------
  ollama-controller:
    image: ollama/ollama
    container_name: ollama-controller
    depends_on:
{controller_depends_lines}
    volumes:
      - ./init-scripts:/init-scripts
      - /var/run/docker.sock:/var/run/docker.sock
    entrypoint: >
      sh -c "
      apt-get update &&
      apt-get install -y jq curl docker.io bc redis-tools &&
      /bin/sh /init-scripts/ollama-controller.sh
      "
    environment:
      MODEL_REPLICAS: '{model_config_json}'
      OLLAMA_NODES: '{nodes_csv}'
      STRICT_MODE: 'false'
    restart: always    

volumes:
{volumes_block}
"""

# -------------------------
# Write file
# -------------------------
with open("docker-compose.generated.yml", "w") as f:
    f.write(compose)

print("✅ docker-compose.generated.yml generated (volume-enhanced, dynamic)")