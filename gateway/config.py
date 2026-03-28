"""
Gateway configuration loader.

Reads config.yaml once at startup. Supports hot-reload via reload_config().
All other modules import get_config() — never read the file directly.
"""

import os
from pathlib import Path
from typing import List, Optional, Dict

import yaml
from pydantic import BaseModel, field_validator

# Path resolution: env var overrides, default to /app/config.yaml in container
# or <repo-root>/config.yaml when running locally.
_DEFAULT_PATH = Path(__file__).parent.parent / "config.yaml"
CONFIG_PATH = Path(os.getenv("CONFIG_PATH", str(_DEFAULT_PATH)))


# ------------------------------------------------------------------
# Schema
# ------------------------------------------------------------------

class ModelConfig(BaseModel):
    name: str
    replicas: int
    weight: float
    fallback: Optional[str] = None


class GatewayConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8081
    max_concurrent: int = 20
    request_timeout: int = 30
    queue_size: int = 100


class LoadBalancingConfig(BaseModel):
    algorithm: str = "adaptive"

    @field_validator("algorithm")
    @classmethod
    def valid_algorithm(cls, v: str) -> str:
        allowed = {"round_robin", "least_connections", "weighted_latency", "adaptive"}
        if v not in allowed:
            raise ValueError(f"load_balancing.algorithm must be one of {allowed}, got '{v}'")
        return v


class CircuitBreakerConfig(BaseModel):
    failure_threshold: int = 3
    timeout: int = 30


class SelfHealingConfig(BaseModel):
    reconcile_interval: int = 20
    auto_restart: bool = True
    adaptive_weights: bool = True
    weight_adjust_step: float = 0.05
    weight_min: float = 0.05
    max_parallel_pulls: int = 2
    pull_retries: int = 5


class MonitoringConfig(BaseModel):
    prometheus_enabled: bool = True
    health_check_interval: int = 10


class RedisConfig(BaseModel):
    host: str = "redis"
    port: int = 6379


class AppConfig(BaseModel):
    gateway: GatewayConfig = GatewayConfig()
    models: List[ModelConfig]
    load_balancing: LoadBalancingConfig = LoadBalancingConfig()
    circuit_breaker: CircuitBreakerConfig = CircuitBreakerConfig()
    self_healing: SelfHealingConfig = SelfHealingConfig()
    monitoring: MonitoringConfig = MonitoringConfig()
    redis: RedisConfig = RedisConfig()

    # ------------------------------------------------------------------
    # Derived helpers (computed once per config load)
    # ------------------------------------------------------------------

    @property
    def model_map(self) -> Dict[str, ModelConfig]:
        return {m.name: m for m in self.models}

    def all_servers(self) -> List[str]:
        """
        Returns ordered list of all ollama server URLs.
        Order matches how generator.py names containers:
          first model replicas → ollama1, ollama2, ...
          next model replicas  → ollama3, ollama4, ...
        """
        servers = []
        idx = 1
        for m in self.models:
            for _ in range(m.replicas):
                servers.append(f"http://ollama{idx}:11434")
                idx += 1
        return servers

    def servers_for_model(self, model_name: str) -> List[str]:
        """Returns server URLs assigned to a specific model."""
        servers = []
        idx = 1
        for m in self.models:
            for _ in range(m.replicas):
                url = f"http://ollama{idx}:11434"
                if m.name == model_name:
                    servers.append(url)
                idx += 1
        return servers


# ------------------------------------------------------------------
# Singleton loader
# ------------------------------------------------------------------

_config: Optional[AppConfig] = None


def load_config(path: Path = None) -> AppConfig:
    global _config
    target = path or CONFIG_PATH
    with open(target, "r") as f:
        raw = yaml.safe_load(f)
    _config = AppConfig(**raw)
    return _config


def get_config() -> AppConfig:
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reload_config() -> AppConfig:
    """Hot-reload config from disk without restarting the process."""
    return load_config()
