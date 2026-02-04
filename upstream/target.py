import time
from dataclasses import dataclass, field
from enum import Enum


class TargetState(Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DNS_ERROR = "dns_error"


@dataclass
class Target:
    host: str
    port: int
    weight: int = 100
    priority: int = 0
    tags: list[str] = field(default_factory=list)

    state: TargetState = TargetState.HEALTHY
    active_connections: int = 0
    total_requests: int = 0
    total_failures: int = 0
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    last_check_time: float = 0.0
    last_failure_time: float = 0.0

    @property
    def address(self) -> str:
        return f"{self.host}:{self.port}"

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def is_healthy(self) -> bool:
        return self.state == TargetState.HEALTHY

    @property
    def effective_weight(self) -> int:
        if not self.is_healthy:
            return 0
        return self.weight

    def record_success(self) -> None:
        self.total_requests += 1
        self.consecutive_successes += 1
        self.consecutive_failures = 0

    def record_failure(self) -> None:
        self.total_requests += 1
        self.total_failures += 1
        self.consecutive_failures += 1
        self.consecutive_successes = 0
        self.last_failure_time = time.time()

    def mark_healthy(self) -> None:
        self.state = TargetState.HEALTHY
        self.consecutive_failures = 0

    def mark_unhealthy(self) -> None:
        self.state = TargetState.UNHEALTHY
        self.consecutive_successes = 0

    def to_dict(self) -> dict:
        return {
            "host": self.host,
            "port": self.port,
            "weight": self.weight,
            "priority": self.priority,
            "tags": self.tags,
            "state": self.state.value,
            "active_connections": self.active_connections,
            "total_requests": self.total_requests,
            "total_failures": self.total_failures,
        }
