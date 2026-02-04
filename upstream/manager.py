import asyncio
from dataclasses import dataclass, field
from typing import Any

import httpx
from fastapi import Request, Response

from models import UpstreamConfig, TargetConfig
from .balancer import LoadBalancer
from .circuit_breaker import CircuitBreaker, CircuitOpenError
from .health_checker import HealthChecker
from .target import Target


@dataclass
class Upstream:
    config: UpstreamConfig
    targets: list[Target] = field(default_factory=list)
    balancer: LoadBalancer = field(default=None)
    circuit_breaker: CircuitBreaker = field(default=None)
    health_checker: HealthChecker = field(default=None)

    def __post_init__(self):
        self.targets = [
            Target(
                host=t.host,
                port=t.port,
                weight=t.weight,
                priority=t.priority,
                tags=t.tags,
            )
            for t in self.config.targets
        ]

        self.balancer = LoadBalancer(self.config.algorithm.value)

        cb_config = self.config.circuit_breaker
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=cb_config.failure_threshold,
            success_threshold=cb_config.success_threshold,
            timeout=cb_config.timeout,
            half_open_requests=cb_config.half_open_requests,
        )

        self.health_checker = HealthChecker(
            config=self.config.health_check,
            targets=self.targets,
        )

    @property
    def name(self) -> str:
        return self.config.name

    def select_target(self, context: dict[str, Any] | None = None) -> Target | None:
        return self.balancer.select(self.targets, context)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "algorithm": self.balancer.algorithm,
            "targets": [t.to_dict() for t in self.targets],
            "circuit_breaker": self.circuit_breaker.to_dict(),
            "health_check": {
                "enabled": self.config.health_check.enabled,
                "interval": self.config.health_check.interval,
            },
        }


class UpstreamManager:
    def __init__(self):
        self._upstreams: dict[str, Upstream] = {}
        self._client: httpx.AsyncClient | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        self._client = httpx.AsyncClient()
        for upstream in self._upstreams.values():
            await upstream.health_checker.start()

    async def stop(self) -> None:
        for upstream in self._upstreams.values():
            await upstream.health_checker.stop()

        if self._client:
            await self._client.aclose()
            self._client = None

    def add_upstream(self, config: UpstreamConfig) -> Upstream:
        upstream = Upstream(config=config)
        self._upstreams[config.name] = upstream
        return upstream

    def get_upstream(self, name: str) -> Upstream | None:
        return self._upstreams.get(name)

    def remove_upstream(self, name: str) -> bool:
        if name in self._upstreams:
            del self._upstreams[name]
            return True
        return False

    def list_upstreams(self) -> list[Upstream]:
        return list(self._upstreams.values())

    async def proxy_request(
        self,
        request: Request,
        upstream_name: str,
        path: str = "",
        additional_headers: dict[str, str] | None = None,
    ) -> Response:
        upstream = self.get_upstream(upstream_name)
        if not upstream:
            return Response(
                content=f'{{"error": "Upstream {upstream_name} not found"}}',
                status_code=502,
                media_type="application/json",
            )

        if not upstream.circuit_breaker.can_execute():
            return Response(
                content='{"error": "Service temporarily unavailable (circuit open)"}',
                status_code=503,
                media_type="application/json",
            )

        context = {"client_ip": request.client.host if request.client else "unknown"}
        target = upstream.select_target(context)

        if not target:
            return Response(
                content='{"error": "No healthy targets available"}',
                status_code=503,
                media_type="application/json",
            )

        return await self._do_proxy(request, upstream, target, path, additional_headers)

    async def _do_proxy(
        self,
        request: Request,
        upstream: Upstream,
        target: Target,
        path: str,
        additional_headers: dict[str, str] | None,
    ) -> Response:
        if not self._client:
            self._client = httpx.AsyncClient()

        target_url = f"{target.url}{path}"
        if request.url.query:
            target_url += f"?{request.url.query}"

        headers = self._filter_headers(dict(request.headers))
        headers["X-Forwarded-For"] = request.client.host if request.client else "unknown"
        headers["X-Forwarded-Proto"] = request.url.scheme
        headers["X-Forwarded-Host"] = request.headers.get("host", "")

        if additional_headers:
            headers.update(additional_headers)

        body = await request.body()
        retry_config = upstream.config.retry
        last_error: Exception | None = None

        for attempt in range(retry_config.max_retries + 1 if retry_config.enabled else 1):
            target.active_connections += 1
            try:
                response = await self._client.request(
                    method=request.method,
                    url=target_url,
                    headers=headers,
                    content=body,
                    timeout=upstream.config.read_timeout / 1000,
                )

                target.active_connections -= 1

                if response.status_code in retry_config.retry_on_status and attempt < retry_config.max_retries:
                    await asyncio.sleep(retry_config.backoff_factor * (2 ** attempt))
                    continue

                target.record_success()
                await upstream.circuit_breaker.record_success()

                response_headers = self._filter_headers(dict(response.headers))
                return Response(
                    content=response.content,
                    status_code=response.status_code,
                    headers=response_headers,
                )

            except httpx.TimeoutException as e:
                target.active_connections -= 1
                target.record_failure()
                last_error = e
                if attempt < retry_config.max_retries:
                    await asyncio.sleep(retry_config.backoff_factor * (2 ** attempt))
                    continue

            except httpx.ConnectError as e:
                target.active_connections -= 1
                target.record_failure()
                last_error = e
                if attempt < retry_config.max_retries:
                    await asyncio.sleep(retry_config.backoff_factor * (2 ** attempt))
                    continue

            except Exception as e:
                target.active_connections -= 1
                target.record_failure()
                last_error = e
                break

        await upstream.circuit_breaker.record_failure()

        if isinstance(last_error, httpx.TimeoutException):
            return Response(
                content='{"error": "Gateway timeout"}',
                status_code=504,
                media_type="application/json",
            )
        elif isinstance(last_error, httpx.ConnectError):
            return Response(
                content='{"error": "Service unavailable"}',
                status_code=503,
                media_type="application/json",
            )
        else:
            return Response(
                content=f'{{"error": "Bad gateway: {str(last_error)}"}}',
                status_code=502,
                media_type="application/json",
            )

    def _filter_headers(self, headers: dict) -> dict:
        hop_by_hop = {
            "connection", "keep-alive", "proxy-authenticate",
            "proxy-authorization", "te", "trailers",
            "transfer-encoding", "upgrade", "host",
        }
        return {k: v for k, v in headers.items() if k.lower() not in hop_by_hop}

    def to_dict(self) -> dict:
        return {
            "upstreams": [u.to_dict() for u in self._upstreams.values()],
        }
