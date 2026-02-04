from typing import Any

from fastapi import Response

from plugins.base import Plugin, PluginContext, PluginPhase
from plugins.registry import PluginRegistry


@PluginRegistry.register("key-auth")
class KeyAuthPlugin(Plugin):
    name = "key-auth"
    priority = 1001
    phases = [PluginPhase.ACCESS]

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.key_names = config.get("key_names", ["X-API-Key", "apikey"])
        self.key_in_header = config.get("key_in_header", True)
        self.key_in_query = config.get("key_in_query", True)
        self.key_in_body = config.get("key_in_body", False)
        self.hide_credentials = config.get("hide_credentials", True)
        self.anonymous = config.get("anonymous")
        self.keys = config.get("keys", {})
        self.run_on_preflight = config.get("run_on_preflight", True)

    async def access(self, ctx: PluginContext) -> Response | None:
        request = ctx.request

        if request.method == "OPTIONS" and not self.run_on_preflight:
            return None

        api_key = self._extract_key(ctx)

        if not api_key:
            if self.anonymous:
                ctx.consumer = {"username": self.anonymous}
                ctx.authenticated = False
                return None

            return Response(
                content='{"error": "Missing API key"}',
                status_code=401,
                media_type="application/json",
            )

        consumer = self.keys.get(api_key)
        if not consumer:
            return Response(
                content='{"error": "Invalid API key"}',
                status_code=401,
                media_type="application/json",
            )

        if isinstance(consumer, str):
            ctx.consumer = {"username": consumer}
        else:
            ctx.consumer = consumer

        ctx.authenticated = True
        ctx.set("api_key", api_key)

        return None

    def _extract_key(self, ctx: PluginContext) -> str | None:
        request = ctx.request

        if self.key_in_header:
            for key_name in self.key_names:
                value = request.headers.get(key_name)
                if value:
                    return value

        if self.key_in_query:
            for key_name in self.key_names:
                value = request.query_params.get(key_name.lower())
                if value:
                    return value

        return None

    async def rewrite(self, ctx: PluginContext) -> None:
        if self.hide_credentials:
            pass
