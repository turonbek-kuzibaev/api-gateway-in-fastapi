from typing import Any

from fastapi import Response

from plugins.base import Plugin, PluginContext, PluginPhase
from plugins.registry import PluginRegistry


@PluginRegistry.register("cors")
class CORSPlugin(Plugin):
    name = "cors"
    priority = 2000
    phases = [PluginPhase.ACCESS, PluginPhase.HEADER_FILTER]

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.origins = config.get("origins", ["*"])
        self.methods = config.get("methods", ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
        self.headers = config.get("headers", ["*"])
        self.exposed_headers = config.get("exposed_headers", [])
        self.credentials = config.get("credentials", False)
        self.max_age = config.get("max_age", 86400)
        self.preflight_continue = config.get("preflight_continue", False)

    async def access(self, ctx: PluginContext) -> Response | None:
        request = ctx.request

        if request.method != "OPTIONS":
            return None

        origin = request.headers.get("Origin")
        if not origin:
            return None

        if not self._is_origin_allowed(origin):
            return Response(
                content='{"error": "Origin not allowed"}',
                status_code=403,
                media_type="application/json",
            )

        if self.preflight_continue:
            return None

        headers = self._build_cors_headers(origin, preflight=True)
        return Response(
            content="",
            status_code=204,
            headers=headers,
        )

    async def header_filter(self, ctx: PluginContext) -> None:
        if not ctx.response:
            return

        request = ctx.request
        origin = request.headers.get("Origin")

        if not origin:
            return

        if not self._is_origin_allowed(origin):
            return

        headers = self._build_cors_headers(origin, preflight=False)
        for key, value in headers.items():
            ctx.response.headers[key] = value

    def _is_origin_allowed(self, origin: str) -> bool:
        if "*" in self.origins:
            return True
        return origin in self.origins

    def _build_cors_headers(self, origin: str, preflight: bool = False) -> dict[str, str]:
        headers = {}

        if "*" in self.origins and not self.credentials:
            headers["Access-Control-Allow-Origin"] = "*"
        else:
            headers["Access-Control-Allow-Origin"] = origin

        if self.credentials:
            headers["Access-Control-Allow-Credentials"] = "true"

        if preflight:
            headers["Access-Control-Allow-Methods"] = ", ".join(self.methods)

            if "*" in self.headers:
                headers["Access-Control-Allow-Headers"] = "*"
            else:
                headers["Access-Control-Allow-Headers"] = ", ".join(self.headers)

            headers["Access-Control-Max-Age"] = str(self.max_age)

        if self.exposed_headers:
            headers["Access-Control-Expose-Headers"] = ", ".join(self.exposed_headers)

        return headers
