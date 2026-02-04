from urllib.parse import urljoin

import httpx
from fastapi import Request, Response
from fastapi.responses import StreamingResponse

from config import ServiceConfig


class ProxyHandler:
    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def build_target_url(self, service: ServiceConfig, request: Request) -> str:
        path = request.url.path
        remaining_path = path[len(service.prefix) :]
        if remaining_path and not remaining_path.startswith("/"):
            remaining_path = "/" + remaining_path

        target_url = service.target.rstrip("/") + remaining_path

        if request.url.query:
            target_url += "?" + request.url.query

        return target_url

    def filter_headers(self, headers: dict) -> dict:
        hop_by_hop = {
            "connection",
            "keep-alive",
            "proxy-authenticate",
            "proxy-authorization",
            "te",
            "trailers",
            "transfer-encoding",
            "upgrade",
            "host",
        }
        return {k: v for k, v in headers.items() if k.lower() not in hop_by_hop}

    async def proxy_request(
        self,
        request: Request,
        service: ServiceConfig,
        additional_headers: dict | None = None,
    ) -> Response:
        client = await self.get_client()
        target_url = self.build_target_url(service, request)

        headers = self.filter_headers(dict(request.headers))
        if additional_headers:
            headers.update(additional_headers)

        headers["X-Forwarded-For"] = request.client.host if request.client else "unknown"
        headers["X-Forwarded-Proto"] = request.url.scheme
        headers["X-Forwarded-Host"] = request.headers.get("host", "")

        body = await request.body()

        try:
            response = await client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body,
            )

            response_headers = self.filter_headers(dict(response.headers))

            if "content-length" in response.headers:
                response_headers["content-length"] = response.headers["content-length"]

            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=response_headers,
            )

        except httpx.TimeoutException:
            return Response(
                content='{"error": "Gateway timeout"}',
                status_code=504,
                media_type="application/json",
            )
        except httpx.ConnectError:
            return Response(
                content='{"error": "Service unavailable"}',
                status_code=503,
                media_type="application/json",
            )
        except httpx.HTTPError as e:
            return Response(
                content=f'{{"error": "Bad gateway: {str(e)}"}}',
                status_code=502,
                media_type="application/json",
            )

    async def proxy_streaming(
        self,
        request: Request,
        service: ServiceConfig,
        additional_headers: dict | None = None,
    ) -> StreamingResponse:
        client = await self.get_client()
        target_url = self.build_target_url(service, request)

        headers = self.filter_headers(dict(request.headers))
        if additional_headers:
            headers.update(additional_headers)

        headers["X-Forwarded-For"] = request.client.host if request.client else "unknown"
        headers["X-Forwarded-Proto"] = request.url.scheme
        headers["X-Forwarded-Host"] = request.headers.get("host", "")

        body = await request.body()

        async def stream_response():
            async with client.stream(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body,
            ) as response:
                async for chunk in response.aiter_bytes():
                    yield chunk

        return StreamingResponse(
            stream_response(),
            media_type="application/octet-stream",
        )
