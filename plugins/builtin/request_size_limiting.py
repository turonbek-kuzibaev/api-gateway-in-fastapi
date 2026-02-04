from typing import Any

from fastapi import Response

from plugins.base import Plugin, PluginContext, PluginPhase
from plugins.registry import PluginRegistry


@PluginRegistry.register("request-size-limiting")
class RequestSizeLimitingPlugin(Plugin):
    name = "request-size-limiting"
    priority = 990
    phases = [PluginPhase.ACCESS]

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.allowed_payload_size = config.get("allowed_payload_size", 128)
        self.size_unit = config.get("size_unit", "megabytes")
        self.require_content_length = config.get("require_content_length", False)

    def _get_max_bytes(self) -> int:
        multipliers = {
            "bytes": 1,
            "kilobytes": 1024,
            "megabytes": 1024 * 1024,
            "gigabytes": 1024 * 1024 * 1024,
        }
        multiplier = multipliers.get(self.size_unit, 1024 * 1024)
        return self.allowed_payload_size * multiplier

    async def access(self, ctx: PluginContext) -> Response | None:
        request = ctx.request
        max_bytes = self._get_max_bytes()

        content_length_header = request.headers.get("Content-Length")

        if self.require_content_length and content_length_header is None:
            if request.method in ["POST", "PUT", "PATCH"]:
                return Response(
                    content='{"error": "Missing Content-Length header"}',
                    status_code=411,
                    media_type="application/json",
                )

        if content_length_header:
            try:
                content_length = int(content_length_header)
                if content_length > max_bytes:
                    return Response(
                        content=f'{{"error": "Request body too large. Maximum allowed size is {self.allowed_payload_size} {self.size_unit}"}}',
                        status_code=413,
                        media_type="application/json",
                        headers={"Retry-After": "0"},
                    )
            except ValueError:
                pass

        return None
