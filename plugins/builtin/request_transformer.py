import json
import re
from typing import Any
from urllib.parse import parse_qs, urlencode

from fastapi import Response

from plugins.base import Plugin, PluginContext, PluginPhase
from plugins.registry import PluginRegistry


@PluginRegistry.register("request-transformer")
class RequestTransformerPlugin(Plugin):
    name = "request-transformer"
    priority = 800
    phases = [PluginPhase.REWRITE]

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.remove_headers = config.get("remove", {}).get("headers", [])
        self.remove_querystring = config.get("remove", {}).get("querystring", [])
        self.remove_body = config.get("remove", {}).get("body", [])

        self.rename_headers = config.get("rename", {}).get("headers", {})
        self.rename_querystring = config.get("rename", {}).get("querystring", {})
        self.rename_body = config.get("rename", {}).get("body", {})

        self.replace_headers = config.get("replace", {}).get("headers", {})
        self.replace_querystring = config.get("replace", {}).get("querystring", {})
        self.replace_body = config.get("replace", {}).get("body", {})

        self.add_headers = config.get("add", {}).get("headers", {})
        self.add_querystring = config.get("add", {}).get("querystring", {})
        self.add_body = config.get("add", {}).get("body", {})

        self.append_headers = config.get("append", {}).get("headers", {})
        self.append_querystring = config.get("append", {}).get("querystring", {})
        self.append_body = config.get("append", {}).get("body", {})

    async def access(self, ctx: PluginContext) -> Response | None:
        return None

    async def rewrite(self, ctx: PluginContext) -> None:
        self._transform_headers(ctx)
        self._transform_querystring(ctx)
        await self._transform_body(ctx)

    def _transform_headers(self, ctx: PluginContext) -> None:
        headers = dict(ctx.request.headers)
        modified_headers = {}

        for key, value in headers.items():
            if key.lower() in [h.lower() for h in self.remove_headers]:
                continue

            new_key = key
            for old, new in self.rename_headers.items():
                if key.lower() == old.lower():
                    new_key = new
                    break

            if new_key.lower() in [h.lower() for h in self.replace_headers]:
                value = self.replace_headers.get(new_key, value)

            modified_headers[new_key] = value

        for key, value in self.add_headers.items():
            if key.lower() not in [h.lower() for h in modified_headers]:
                modified_headers[key] = self._interpolate(value, ctx)

        for key, value in self.append_headers.items():
            existing = modified_headers.get(key, "")
            if existing:
                modified_headers[key] = f"{existing}, {self._interpolate(value, ctx)}"
            else:
                modified_headers[key] = self._interpolate(value, ctx)

        ctx.set("transformed_headers", modified_headers)

    def _transform_querystring(self, ctx: PluginContext) -> None:
        query_params = dict(ctx.request.query_params)

        for key in self.remove_querystring:
            query_params.pop(key, None)

        for old, new in self.rename_querystring.items():
            if old in query_params:
                query_params[new] = query_params.pop(old)

        for key, value in self.replace_querystring.items():
            if key in query_params:
                query_params[key] = self._interpolate(value, ctx)

        for key, value in self.add_querystring.items():
            if key not in query_params:
                query_params[key] = self._interpolate(value, ctx)

        for key, value in self.append_querystring.items():
            existing = query_params.get(key, "")
            if existing:
                query_params[key] = f"{existing},{self._interpolate(value, ctx)}"
            else:
                query_params[key] = self._interpolate(value, ctx)

        ctx.set("transformed_querystring", query_params)

    async def _transform_body(self, ctx: PluginContext) -> None:
        content_type = ctx.request.headers.get("content-type", "")
        if "application/json" not in content_type:
            return

        try:
            body = await ctx.request.body()
            if not body:
                return

            data = json.loads(body)
            if not isinstance(data, dict):
                return

            for key in self.remove_body:
                data.pop(key, None)

            for old, new in self.rename_body.items():
                if old in data:
                    data[new] = data.pop(old)

            for key, value in self.replace_body.items():
                if key in data:
                    data[key] = self._interpolate(value, ctx)

            for key, value in self.add_body.items():
                if key not in data:
                    data[key] = self._interpolate(value, ctx)

            for key, value in self.append_body.items():
                existing = data.get(key, "")
                if existing:
                    data[key] = f"{existing}{self._interpolate(value, ctx)}"
                else:
                    data[key] = self._interpolate(value, ctx)

            ctx.set("transformed_body", json.dumps(data))

        except json.JSONDecodeError:
            pass

    def _interpolate(self, value: str, ctx: PluginContext) -> str:
        if not isinstance(value, str):
            return value

        pattern = r'\$\(([^)]+)\)'
        matches = re.findall(pattern, value)

        for match in matches:
            parts = match.split(".")
            if parts[0] == "headers":
                header_value = ctx.request.headers.get(parts[1], "")
                value = value.replace(f"$({match})", header_value)
            elif parts[0] == "query":
                query_value = ctx.request.query_params.get(parts[1], "")
                value = value.replace(f"$({match})", query_value)
            elif parts[0] == "consumer":
                if ctx.consumer:
                    consumer_value = ctx.consumer.get(parts[1], "")
                    value = value.replace(f"$({match})", str(consumer_value))

        return value
