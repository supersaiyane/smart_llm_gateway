# =============================================================
#  Smart LLM Gateway — Standalone Image
#
#  Two-stage build:
#    builder  — installs Python dependencies
#    runtime  — lean image with only what's needed to run
#
#  Usage options:
#    1. Mount your own config.yaml   (-v ./config.yaml:/app/config.yaml)
#    2. Pass env vars                (-e GATEWAY_MODELS=... -e REDIS_HOST=...)
#
#  See README.md → "Docker Image" section for full flag reference.
# =============================================================

# ── Stage 1: dependency installer ────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build
COPY gateway/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: runtime ─────────────────────────────────────────
FROM python:3.11-slim

LABEL org.opencontainers.image.title="Smart LLM Gateway" \
      org.opencontainers.image.description="Intelligent LLM routing gateway with adaptive load balancing and self-healing" \
      org.opencontainers.image.source="https://github.com/supersaiyane/smart_llm_gateway"

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy gateway source
COPY gateway/ .

# Copy entrypoint
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 8081

# Liveness probe built into the image
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c \
        "import urllib.request, sys; \
         r = urllib.request.urlopen('http://localhost:8081/health', timeout=4); \
         sys.exit(0 if r.status == 200 else 1)"

ENTRYPOINT ["/docker-entrypoint.sh"]
