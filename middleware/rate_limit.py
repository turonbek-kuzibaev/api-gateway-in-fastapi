import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from config import Config


@dataclass
class TokenBucket:
    tokens: float
    last_update: float
    capacity: float
    refill_rate: float

    def consume(self, tokens: int = 1) -> bool:
        now = time.time()
        elapsed = now - self.last_update

        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_update = now

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: Config):
        super().__init__(app)
        self.config = config
        self.enabled = config.rate_limit.enabled
        self.requests_per_minute = config.rate_limit.requests_per_minute
        self.refill_rate = self.requests_per_minute / 60.0
        self.buckets: dict[str, TokenBucket] = defaultdict(self._create_bucket)

    def _create_bucket(self) -> TokenBucket:
        return TokenBucket(
            tokens=float(self.requests_per_minute),
            last_update=time.time(),
            capacity=float(self.requests_per_minute),
            refill_rate=self.refill_rate,
        )

    def _get_client_key(self, request: Request) -> str:
        api_key = request.headers.get("X-API-Key")
        if api_key:
            return f"api_key:{api_key}"

        if request.client:
            return f"ip:{request.client.host}"

        return "unknown"

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not self.enabled:
            return await call_next(request)

        client_key = self._get_client_key(request)
        bucket = self.buckets[client_key]

        if not bucket.consume():
            retry_after = int((1 - bucket.tokens) / bucket.refill_rate) + 1
            return Response(
                content='{"error": "Rate limit exceeded"}',
                status_code=429,
                media_type="application/json",
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(self.requests_per_minute),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)

        response.headers["X-RateLimit-Limit"] = str(self.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(int(bucket.tokens))

        return response
