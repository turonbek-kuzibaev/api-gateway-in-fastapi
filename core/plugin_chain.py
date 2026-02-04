from typing import Any

from fastapi import Response

from plugins.base import Plugin, PluginContext, PluginPhase
from plugins.registry import PluginRegistry


class PluginChain:
    def __init__(self):
        self._global_plugins: list[Plugin] = []
        self._service_plugins: dict[str, list[Plugin]] = {}
        self._route_plugins: dict[str, list[Plugin]] = {}

    def add_global_plugin(self, name: str, config: dict[str, Any]) -> Plugin | None:
        plugin = PluginRegistry.create(name, config)
        if plugin:
            self._global_plugins.append(plugin)
            self._global_plugins.sort(key=lambda p: p.priority, reverse=True)
        return plugin

    def add_service_plugin(
        self, service_name: str, plugin_name: str, config: dict[str, Any]
    ) -> Plugin | None:
        plugin = PluginRegistry.create(plugin_name, config)
        if plugin:
            if service_name not in self._service_plugins:
                self._service_plugins[service_name] = []
            self._service_plugins[service_name].append(plugin)
            self._service_plugins[service_name].sort(key=lambda p: p.priority, reverse=True)
        return plugin

    def add_route_plugin(
        self, route_name: str, plugin_name: str, config: dict[str, Any]
    ) -> Plugin | None:
        plugin = PluginRegistry.create(plugin_name, config)
        if plugin:
            if route_name not in self._route_plugins:
                self._route_plugins[route_name] = []
            self._route_plugins[route_name].append(plugin)
            self._route_plugins[route_name].sort(key=lambda p: p.priority, reverse=True)
        return plugin

    def get_plugins_for_request(
        self,
        service_name: str | None = None,
        route_name: str | None = None,
    ) -> list[Plugin]:
        plugins = list(self._global_plugins)

        if service_name and service_name in self._service_plugins:
            plugins.extend(self._service_plugins[service_name])

        if route_name and route_name in self._route_plugins:
            plugins.extend(self._route_plugins[route_name])

        plugins.sort(key=lambda p: p.priority, reverse=True)
        return plugins

    async def run_access_phase(
        self,
        ctx: PluginContext,
        service_name: str | None = None,
        route_name: str | None = None,
    ) -> Response | None:
        plugins = self.get_plugins_for_request(service_name, route_name)

        for plugin in plugins:
            if not plugin.enabled:
                continue
            if PluginPhase.ACCESS not in plugin.phases:
                continue

            response = await plugin.access(ctx)
            if response is not None:
                return response

        return None

    async def run_rewrite_phase(
        self,
        ctx: PluginContext,
        service_name: str | None = None,
        route_name: str | None = None,
    ) -> None:
        plugins = self.get_plugins_for_request(service_name, route_name)

        for plugin in plugins:
            if not plugin.enabled:
                continue
            if PluginPhase.REWRITE not in plugin.phases:
                continue

            await plugin.rewrite(ctx)

    async def run_header_filter_phase(
        self,
        ctx: PluginContext,
        service_name: str | None = None,
        route_name: str | None = None,
    ) -> None:
        plugins = self.get_plugins_for_request(service_name, route_name)

        for plugin in plugins:
            if not plugin.enabled:
                continue
            if PluginPhase.HEADER_FILTER not in plugin.phases:
                continue

            await plugin.header_filter(ctx)

    async def run_body_filter_phase(
        self,
        ctx: PluginContext,
        chunk: bytes,
        service_name: str | None = None,
        route_name: str | None = None,
    ) -> bytes:
        plugins = self.get_plugins_for_request(service_name, route_name)

        for plugin in plugins:
            if not plugin.enabled:
                continue
            if PluginPhase.BODY_FILTER not in plugin.phases:
                continue

            chunk = await plugin.body_filter(ctx, chunk)

        return chunk

    async def run_log_phase(
        self,
        ctx: PluginContext,
        service_name: str | None = None,
        route_name: str | None = None,
    ) -> None:
        plugins = self.get_plugins_for_request(service_name, route_name)

        for plugin in plugins:
            if not plugin.enabled:
                continue
            if PluginPhase.LOG not in plugin.phases:
                continue

            try:
                await plugin.log(ctx)
            except Exception:
                pass
