import time
from pathlib import Path
from typing import Any

import yaml
from fastapi import Request, Response

from models import GatewayConfig, ServiceConfig, UpstreamConfig, TargetConfig, RouteConfig, PluginConfig
from plugins.base import PluginContext
from upstream import UpstreamManager
from .plugin_chain import PluginChain
from .router import Router


class Gateway:
    def __init__(self, config_path: str | Path | None = None):
        self.config: GatewayConfig | None = None
        self.router = Router()
        self.upstream_manager = UpstreamManager()
        self.plugin_chain = PluginChain()
        self._config_path = config_path

        if config_path:
            self.load_config(config_path)

    def load_config(self, config_path: str | Path) -> None:
        path = Path(config_path)
        if not path.exists():
            self.config = GatewayConfig()
            return

        with open(path) as f:
            data = yaml.safe_load(f) or {}

        self._parse_config(data)

    def _parse_config(self, data: dict[str, Any]) -> None:
        upstreams_data = data.get("upstreams", [])
        for u_data in upstreams_data:
            targets = [
                TargetConfig(
                    host=t["host"],
                    port=t.get("port", 80),
                    weight=t.get("weight", 100),
                    priority=t.get("priority", 0),
                    tags=t.get("tags", []),
                )
                for t in u_data.get("targets", [])
            ]

            upstream_config = UpstreamConfig(
                name=u_data["name"],
                targets=targets,
                algorithm=u_data.get("algorithm", "round-robin"),
            )
            self.upstream_manager.add_upstream(upstream_config)

        services_data = data.get("services", [])
        for s_data in services_data:
            routes = []
            for r_data in s_data.get("routes", []):
                route_plugins = [
                    PluginConfig(
                        name=p["name"],
                        enabled=p.get("enabled", True),
                        config=p.get("config", {}),
                    )
                    for p in r_data.get("plugins", [])
                ]

                route = RouteConfig(
                    name=r_data["name"],
                    paths=r_data.get("paths", []),
                    methods=r_data.get("methods", ["GET", "POST", "PUT", "DELETE", "PATCH"]),
                    hosts=r_data.get("hosts", []),
                    headers=r_data.get("headers", {}),
                    strip_path=r_data.get("strip_path", True),
                    preserve_host=r_data.get("preserve_host", False),
                    plugins=route_plugins,
                )
                routes.append(route)

                for p in route_plugins:
                    self.plugin_chain.add_route_plugin(route.name, p.name, p.config)

            service_plugins = [
                PluginConfig(
                    name=p["name"],
                    enabled=p.get("enabled", True),
                    config=p.get("config", {}),
                )
                for p in s_data.get("plugins", [])
            ]

            service = ServiceConfig(
                name=s_data["name"],
                upstream=s_data["upstream"],
                routes=routes,
                plugins=service_plugins,
                protocol=s_data.get("protocol", "http"),
                path=s_data.get("path", ""),
                enabled=s_data.get("enabled", True),
            )
            self.router.add_service(service)

            for p in service_plugins:
                self.plugin_chain.add_service_plugin(service.name, p.name, p.config)

        global_plugins = data.get("plugins", [])
        for p_data in global_plugins:
            self.plugin_chain.add_global_plugin(
                p_data["name"],
                p_data.get("config", {}),
            )

        gateway_data = data.get("gateway", {})
        self.config = GatewayConfig(
            host=gateway_data.get("host", "0.0.0.0"),
            port=gateway_data.get("port", 8000),
            admin_port=gateway_data.get("admin_port", 8001),
            admin_enabled=gateway_data.get("admin_enabled", True),
        )

    async def start(self) -> None:
        await self.upstream_manager.start()

    async def stop(self) -> None:
        await self.upstream_manager.stop()

    async def handle_request(self, request: Request) -> Response:
        start_time = time.time()
        path = request.url.path
        method = request.method
        headers = dict(request.headers)

        match = self.router.match(path, method, headers)
        if not match:
            return Response(
                content='{"error": "No route matched"}',
                status_code=404,
                media_type="application/json",
            )

        ctx = PluginContext(
            request=request,
            service_name=match.service.name,
            route_name=match.route.name,
            upstream_name=match.service.upstream,
            start_time=start_time,
        )

        access_response = await self.plugin_chain.run_access_phase(
            ctx, match.service.name, match.route.name
        )
        if access_response:
            await self.plugin_chain.run_log_phase(ctx, match.service.name, match.route.name)
            return access_response

        await self.plugin_chain.run_rewrite_phase(ctx, match.service.name, match.route.name)

        additional_headers = {}
        if ctx.consumer:
            import json
            additional_headers["X-Consumer-Username"] = ctx.consumer.get("username", "")
            additional_headers["X-Consumer-Custom-ID"] = ctx.consumer.get("custom_id", "")
            if ctx.authenticated:
                additional_headers["X-Authenticated-Consumer"] = "true"

        transformed_headers = ctx.get("transformed_headers")
        if transformed_headers:
            additional_headers.update(transformed_headers)

        user_id = ctx.get("user_id")
        if user_id:
            additional_headers["X-User-ID"] = str(user_id)

        target_path = match.service.path + match.remaining_path

        proxy_start = time.time()
        response = await self.upstream_manager.proxy_request(
            request,
            match.service.upstream,
            target_path,
            additional_headers,
        )
        ctx.latencies["proxy"] = (time.time() - proxy_start) * 1000

        ctx.response = response
        await self.plugin_chain.run_header_filter_phase(ctx, match.service.name, match.route.name)

        ctx.latencies["request"] = (time.time() - start_time) * 1000
        await self.plugin_chain.run_log_phase(ctx, match.service.name, match.route.name)

        return response
