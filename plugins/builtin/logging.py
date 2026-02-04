import json
import time
from typing import Any

from fastapi import Response

from plugins.base import Plugin, PluginContext, PluginPhase
from plugins.registry import PluginRegistry


@PluginRegistry.register("logging")
class LoggingPlugin(Plugin):
    name = "logging"
    priority = 100
    phases = [PluginPhase.LOG]

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.http_endpoint = config.get("http_endpoint")
        self.content_type = config.get("content_type", "application/json")
        self.log_bodies = config.get("log_bodies", False)
        self.max_body_size = config.get("max_body_size", 10000)
        self.custom_fields = config.get("custom_fields", {})

        self.include_request = config.get("include_request", True)
        self.include_response = config.get("include_response", True)
        self.include_latencies = config.get("include_latencies", True)
        self.include_consumer = config.get("include_consumer", True)

    async def access(self, ctx: PluginContext) -> Response | None:
        ctx.start_time = time.time()
        return None

    async def log(self, ctx: PluginContext) -> None:
        log_entry = self._build_log_entry(ctx)
        await self._send_log(log_entry)

    def _build_log_entry(self, ctx: PluginContext) -> dict[str, Any]:
        request = ctx.request
        response = ctx.response

        entry: dict[str, Any] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
        }

        if self.include_request:
            entry["request"] = {
                "method": request.method,
                "uri": str(request.url),
                "url": str(request.url.path),
                "querystring": dict(request.query_params),
                "headers": dict(request.headers),
                "size": int(request.headers.get("content-length", 0)),
            }

            if request.client:
                entry["client_ip"] = request.client.host

        if self.include_response and response:
            entry["response"] = {
                "status": response.status_code,
                "headers": dict(response.headers),
                "size": int(response.headers.get("content-length", 0)),
            }

        if self.include_latencies:
            total_latency = (time.time() - ctx.start_time) * 1000 if ctx.start_time else 0
            entry["latencies"] = {
                "request": ctx.latencies.get("request", 0),
                "proxy": ctx.latencies.get("proxy", 0),
                "gateway": total_latency,
            }

        if self.include_consumer and ctx.consumer:
            entry["consumer"] = {
                "username": ctx.consumer.get("username"),
                "custom_id": ctx.consumer.get("custom_id"),
            }

        if ctx.authenticated:
            entry["authenticated"] = True

        if ctx.service_name:
            entry["service"] = {"name": ctx.service_name}

        if ctx.route_name:
            entry["route"] = {"name": ctx.route_name}

        if ctx.upstream_name:
            entry["upstream"] = {"name": ctx.upstream_name}

        for key, value in self.custom_fields.items():
            entry[key] = value

        return entry

    async def _send_log(self, log_entry: dict[str, Any]) -> None:
        log_line = json.dumps(log_entry, default=str)
        print(log_line)

        if self.http_endpoint:
            try:
                import httpx
                async with httpx.AsyncClient() as client:
                    await client.post(
                        self.http_endpoint,
                        json=log_entry,
                        headers={"Content-Type": self.content_type},
                        timeout=5.0,
                    )
            except Exception:
                pass
