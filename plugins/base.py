from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from fastapi import Request, Response


class PluginPhase(Enum):
    ACCESS = auto()
    REWRITE = auto()
    HEADER_FILTER = auto()
    BODY_FILTER = auto()
    LOG = auto()


@dataclass
class PluginContext:
    request: Request
    response: Response | None = None
    service_name: str | None = None
    route_name: str | None = None
    upstream_name: str | None = None
    consumer: dict[str, Any] | None = None
    authenticated: bool = False
    start_time: float = 0.0
    latencies: dict[str, float] = field(default_factory=dict)
    shared: dict[str, Any] = field(default_factory=dict)

    def set(self, key: str, value: Any) -> None:
        self.shared[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.shared.get(key, default)


class Plugin(ABC):
    name: str = "base"
    priority: int = 1000
    phases: list[PluginPhase] = [PluginPhase.ACCESS]

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.enabled = True

    @abstractmethod
    async def access(self, ctx: PluginContext) -> Response | None:
        """
        Called before proxying the request.
        Return a Response to short-circuit and skip proxying.
        Return None to continue to the next plugin.
        """
        pass

    async def rewrite(self, ctx: PluginContext) -> None:
        """
        Called to rewrite the request before proxying.
        Modify request headers, path, etc.
        """
        pass

    async def header_filter(self, ctx: PluginContext) -> None:
        """
        Called after receiving response headers from upstream.
        Modify response headers.
        """
        pass

    async def body_filter(self, ctx: PluginContext, chunk: bytes) -> bytes:
        """
        Called for each chunk of the response body.
        Transform the response body.
        """
        return chunk

    async def log(self, ctx: PluginContext) -> None:
        """
        Called after the response has been sent.
        Used for logging, metrics, etc.
        """
        pass


class PluginError(Exception):
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(message)
