"""
Prometheus metrics definitions.

Import the individual metrics from here — never create new collectors elsewhere
or you'll get duplicate-registration errors on config reload.
"""

from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi.responses import Response

# ------------------------------------------------------------------
# Counters
# ------------------------------------------------------------------

requests_total = Counter(
    "gateway_requests_total",
    "Total inference requests received",
    ["model", "server", "status"],        # status: success | failure | fallback
)

fallbacks_total = Counter(
    "gateway_fallbacks_total",
    "Requests that triggered fallback routing",
    ["original_model", "fallback_model"],
)

circuit_opens_total = Counter(
    "gateway_circuit_opens_total",
    "Number of times a circuit breaker opened",
    ["server"],
)

# ------------------------------------------------------------------
# Histograms
# ------------------------------------------------------------------

request_latency_seconds = Histogram(
    "gateway_request_latency_seconds",
    "End-to-end request latency",
    ["model", "server"],
    buckets=[0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)

# ------------------------------------------------------------------
# Gauges
# ------------------------------------------------------------------

active_requests = Gauge(
    "gateway_active_requests",
    "Requests currently being processed",
)

queue_depth = Gauge(
    "gateway_queue_depth",
    "Requests waiting to acquire the concurrency semaphore",
)

model_weight = Gauge(
    "gateway_model_weight",
    "Current routing weight for each model (may differ from config after adaptive adjustment)",
    ["model"],
)

node_failures = Gauge(
    "gateway_node_failures",
    "Current failure count per Ollama node",
    ["server"],
)

node_latency = Gauge(
    "gateway_node_latency_seconds",
    "Most-recently observed latency per Ollama node",
    ["server"],
)


# ------------------------------------------------------------------
# Scrape endpoint
# ------------------------------------------------------------------

def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
