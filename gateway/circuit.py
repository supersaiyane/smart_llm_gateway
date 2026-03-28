"""
Per-server circuit breaker backed by Redis.

States:
  CLOSED     Normal operation. Requests flow through.
  OPEN       Too many failures. Requests are blocked.
  HALF_OPEN  Timeout elapsed. One probe request is allowed through.
             If it succeeds → CLOSED. If it fails → OPEN again.
"""

import time
import redis as redis_lib


class CircuitBreaker:

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(
        self,
        r: redis_lib.Redis,
        server: str,
        failure_threshold: int,
        timeout: int,
    ):
        self.r = r
        self.server = server
        self.key = f"server:{server}"
        self.failure_threshold = failure_threshold
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Return True if a request should be allowed to this server."""
        data = self.r.hgetall(self.key)
        circuit_open = int(data.get("circuit_open", 0))
        last_failure = float(data.get("last_failure", 0))

        if circuit_open == 0:
            return True  # CLOSED

        # OPEN — check whether the timeout has elapsed
        if time.time() - last_failure > self.timeout:
            return True  # Allow one HALF-OPEN probe

        return False  # Still OPEN

    def record_success(self):
        """Call this after a successful response. Closes the circuit."""
        pipe = self.r.pipeline()
        pipe.hset(self.key, "circuit_open", 0)
        pipe.hset(self.key, "failures", 0)
        pipe.execute()

    def record_failure(self):
        """Call this after a failed request. May open the circuit."""
        pipe = self.r.pipeline()
        pipe.hincrby(self.key, "failures", 1)
        pipe.hset(self.key, "last_failure", time.time())
        pipe.execute()

        failures = int(self.r.hget(self.key, "failures") or 0)
        if failures >= self.failure_threshold:
            self.r.hset(self.key, "circuit_open", 1)

    def state(self) -> str:
        data = self.r.hgetall(self.key)
        circuit_open = int(data.get("circuit_open", 0))
        last_failure = float(data.get("last_failure", 0))

        if circuit_open == 0:
            return self.CLOSED
        if time.time() - last_failure > self.timeout:
            return self.HALF_OPEN
        return self.OPEN
