import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from fastapi import Response

from plugins.base import Plugin, PluginContext, PluginPhase
from plugins.registry import PluginRegistry


@dataclass
class TokenBucket:
    tokens: float
    last_update: float
    capacity: float
    refill_rate: float

    def consume(self, tokens: int = 1) -> tuple[bool, float]:
        now = time.time()
        elapsed = now - self.last_update
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_update = now

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True, self.tokens
        return False, self.tokens


@dataclass
class SlidingWindow:
    requests: list[float]
    window_size: float
    max_requests: int

    def is_allowed(self) -> tuple[bool, int]:
        now = time.time()
        cutoff = now - self.window_size
        self.requests = [t for t in self.requests if t > cutoff]

        if len(self.requests) < self.max_requests:
            self.requests.append(now)
            return True, self.max_requests - len(self.requests)
        return False, 0


@PluginRegistry.register("rate-limiting")
class RateLimitingPlugin(Plugin):
    name = "rate-limiting"
    priority = 900
    phases = [PluginPhase.ACCESS]

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.second = config.get("second")
        self.minute = config.get("minute", 60)
        self.hour = config.get("hour")
        self.day = config.get("day")
        self.limit_by = config.get("limit_by", "ip")
        self.policy = config.get("policy", "local")
        self.hide_client_headers = config.get("hide_client_headers", False)
        self.error_code = config.get("error_code", 429)
        self.error_message = config.get("error_message", "Rate limit exceeded")

        self._buckets: dict[str, dict[str, TokenBucket]] = defaultdict(dict)
        self._windows: dict[str, dict[str, SlidingWindow]] = defaultdict(dict)

    async def access(self, ctx: PluginContext) -> Response | None:
        identifier = self._get_identifier(ctx)

        limits = [
            ("second", self.second, 1),
            ("minute", self.minute, 60),
            ("hour", self.hour, 3600),
            ("day", self.day, 86400),
        ]

        headers = {}
        for name, limit, window in limits:
            if limit is None:
                continue

            allowed, remaining = self._check_limit(identifier, name, limit, window)

            if not self.hide_client_headers:
                headers[f"X-RateLimit-Limit-{name}"] = str(limit)
                headers[f"X-RateLimit-Remaining-{name}"] = str(int(remaining))

            if not allowed:
                retry_after = self._calculate_retry_after(identifier, name, window)
                headers["Retry-After"] = str(retry_after)

                return Response(
                    content=f'{{"error": "{self.error_message}"}}',
                    status_code=self.error_code,
                    media_type="application/json",
                    headers=headers,
                )

        ctx.set("rate_limit_headers", headers)
        return None

    async def header_filter(self, ctx: PluginContext) -> None:
        if ctx.response and not self.hide_client_headers:
            headers = ctx.get("rate_limit_headers", {})
            for key, value in headers.items():
                ctx.response.headers[key] = value

    def _get_identifier(self, ctx: PluginContext) -> str:
        request = ctx.request

        if self.limit_by == "consumer":
            if ctx.consumer:
                return f"consumer:{ctx.consumer.get('username', 'anonymous')}"
            return "consumer:anonymous"

        if self.limit_by == "credential":
            api_key = ctx.get("api_key")
            if api_key:
                return f"credential:{api_key}"
            user_id = ctx.get("user_id")
            if user_id:
                return f"credential:{user_id}"

        if self.limit_by == "header":
            header_name = self.config.get("header_name", "X-Consumer-ID")
            value = request.headers.get(header_name)
            if value:
                return f"header:{value}"

        if request.client:
            return f"ip:{request.client.host}"
        return "ip:unknown"

    def _check_limit(
        self,
        identifier: str,
        period: str,
        limit: int,
        window: int,
    ) -> tuple[bool, float]:
        bucket_key = f"{identifier}:{period}"

        if bucket_key not in self._buckets[period]:
            self._buckets[period][bucket_key] = TokenBucket(
                tokens=float(limit),
                last_update=time.time(),
                capacity=float(limit),
                refill_rate=limit / window,
            )

        bucket = self._buckets[period][bucket_key]
        return bucket.consume()

    def _calculate_retry_after(self, identifier: str, period: str, window: int) -> int:
        bucket_key = f"{identifier}:{period}"
        bucket = self._buckets[period].get(bucket_key)

        if bucket:
            tokens_needed = 1 - bucket.tokens
            return max(1, int(tokens_needed / bucket.refill_rate))
        return 1
