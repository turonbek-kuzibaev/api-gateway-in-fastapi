from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class LoadBalancingAlgorithm(str, Enum):
    ROUND_ROBIN = "round-robin"
    LEAST_CONNECTIONS = "least-connections"
    IP_HASH = "ip-hash"
    WEIGHTED = "weighted"
    RANDOM = "random"


class HealthCheckType(str, Enum):
    HTTP = "http"
    TCP = "tcp"


class TargetConfig(BaseModel):
    host: str
    port: int = 80
    weight: int = 100
    priority: int = 0
    tags: list[str] = Field(default_factory=list)


class HealthCheckConfig(BaseModel):
    enabled: bool = True
    type: HealthCheckType = HealthCheckType.HTTP
    path: str = "/health"
    interval: int = 10
    timeout: int = 5
    healthy_threshold: int = 2
    unhealthy_threshold: int = 3
    expected_statuses: list[int] = Field(default_factory=lambda: [200])


class CircuitBreakerConfig(BaseModel):
    enabled: bool = True
    failure_threshold: int = 5
    success_threshold: int = 2
    timeout: int = 30
    half_open_requests: int = 3


class RetryConfig(BaseModel):
    enabled: bool = True
    max_retries: int = 3
    retry_on_status: list[int] = Field(default_factory=lambda: [502, 503, 504])
    backoff_factor: float = 0.5


class UpstreamConfig(BaseModel):
    name: str
    targets: list[TargetConfig]
    algorithm: LoadBalancingAlgorithm = LoadBalancingAlgorithm.ROUND_ROBIN
    health_check: HealthCheckConfig = Field(default_factory=HealthCheckConfig)
    circuit_breaker: CircuitBreakerConfig = Field(default_factory=CircuitBreakerConfig)
    retry: RetryConfig = Field(default_factory=RetryConfig)
    connect_timeout: int = 5000
    read_timeout: int = 30000
    write_timeout: int = 30000


class PluginConfig(BaseModel):
    name: str
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class RouteConfig(BaseModel):
    name: str
    paths: list[str]
    methods: list[str] = Field(default_factory=lambda: ["GET", "POST", "PUT", "DELETE", "PATCH"])
    hosts: list[str] = Field(default_factory=list)
    headers: dict[str, str] = Field(default_factory=dict)
    strip_path: bool = True
    preserve_host: bool = False
    plugins: list[PluginConfig] = Field(default_factory=list)


class ServiceConfig(BaseModel):
    name: str
    upstream: str
    routes: list[RouteConfig]
    plugins: list[PluginConfig] = Field(default_factory=list)
    protocol: str = "http"
    path: str = ""
    enabled: bool = True


class RateLimitConfig(BaseModel):
    requests_per_second: int | None = None
    requests_per_minute: int | None = 60
    requests_per_hour: int | None = None
    requests_per_day: int | None = None
    by: str = "ip"
    policy: str = "local"
    redis_host: str | None = None
    redis_port: int = 6379
    hide_client_headers: bool = False


class CORSConfig(BaseModel):
    origins: list[str] = Field(default_factory=lambda: ["*"])
    methods: list[str] = Field(default_factory=lambda: ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
    headers: list[str] = Field(default_factory=lambda: ["*"])
    exposed_headers: list[str] = Field(default_factory=list)
    credentials: bool = False
    max_age: int = 86400


class JWTConfig(BaseModel):
    secret: str = "your-secret-key"
    algorithm: str = "HS256"
    header_names: list[str] = Field(default_factory=lambda: ["Authorization"])
    claims_to_verify: list[str] = Field(default_factory=lambda: ["exp"])
    key_claim_name: str = "iss"
    anonymous: str | None = None


class APIKeyConfig(BaseModel):
    key_names: list[str] = Field(default_factory=lambda: ["X-API-Key", "apikey"])
    key_in_header: bool = True
    key_in_query: bool = True
    key_in_body: bool = False
    hide_credentials: bool = True


class ConsumerConfig(BaseModel):
    username: str
    custom_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    credentials: dict[str, Any] = Field(default_factory=dict)


class LoggingConfig(BaseModel):
    enabled: bool = True
    level: str = "INFO"
    format: str = "json"
    include_request_body: bool = False
    include_response_body: bool = False
    max_body_size: int = 10000


class GatewayConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    admin_port: int = 8001
    admin_enabled: bool = True
    prefix: str = ""
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    upstreams: list[UpstreamConfig] = Field(default_factory=list)
    services: list[ServiceConfig] = Field(default_factory=list)
    consumers: list[ConsumerConfig] = Field(default_factory=list)
    plugins: list[PluginConfig] = Field(default_factory=list)
