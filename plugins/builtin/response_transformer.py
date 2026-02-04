import json
from typing import Any

from fastapi import Response

from plugins.base import Plugin, PluginContext, PluginPhase
from plugins.registry import PluginRegistry


@PluginRegistry.register("response-transformer")
class ResponseTransformerPlugin(Plugin):
    name = "response-transformer"
    priority = 700
    phases = [PluginPhase.HEADER_FILTER, PluginPhase.BODY_FILTER]

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.remove_headers = config.get("remove", {}).get("headers", [])
        self.remove_json = config.get("remove", {}).get("json", [])

        self.rename_headers = config.get("rename", {}).get("headers", {})

        self.replace_headers = config.get("replace", {}).get("headers", {})
        self.replace_json = config.get("replace", {}).get("json", {})

        self.add_headers = config.get("add", {}).get("headers", {})
        self.add_json = config.get("add", {}).get("json", {})

        self.append_headers = config.get("append", {}).get("headers", {})
        self.append_json = config.get("append", {}).get("json", {})

        self._body_buffer: bytes = b""

    async def access(self, ctx: PluginContext) -> Response | None:
        return None

    async def header_filter(self, ctx: PluginContext) -> None:
        if not ctx.response:
            return

        headers = dict(ctx.response.headers)

        for header in self.remove_headers:
            header_lower = header.lower()
            to_remove = [k for k in headers if k.lower() == header_lower]
            for k in to_remove:
                del headers[k]

        for old, new in self.rename_headers.items():
            old_lower = old.lower()
            for k in list(headers.keys()):
                if k.lower() == old_lower:
                    headers[new] = headers.pop(k)

        for key, value in self.replace_headers.items():
            key_lower = key.lower()
            for k in list(headers.keys()):
                if k.lower() == key_lower:
                    headers[k] = value

        for key, value in self.add_headers.items():
            if key.lower() not in [k.lower() for k in headers]:
                headers[key] = value

        for key, value in self.append_headers.items():
            existing = None
            for k in headers:
                if k.lower() == key.lower():
                    existing = k
                    break

            if existing:
                headers[existing] = f"{headers[existing]}, {value}"
            else:
                headers[key] = value

        for key, value in headers.items():
            ctx.response.headers[key] = value

    async def body_filter(self, ctx: PluginContext, chunk: bytes) -> bytes:
        if not (self.remove_json or self.replace_json or self.add_json or self.append_json):
            return chunk

        content_type = ""
        if ctx.response:
            content_type = ctx.response.headers.get("content-type", "")

        if "application/json" not in content_type:
            return chunk

        self._body_buffer += chunk

        try:
            data = json.loads(self._body_buffer)
        except json.JSONDecodeError:
            return b""

        if isinstance(data, dict):
            for key in self.remove_json:
                data.pop(key, None)

            for key, value in self.replace_json.items():
                if key in data:
                    data[key] = value

            for key, value in self.add_json.items():
                if key not in data:
                    data[key] = value

            for key, value in self.append_json.items():
                if key in data:
                    existing = data[key]
                    if isinstance(existing, str):
                        data[key] = existing + str(value)
                    elif isinstance(existing, list):
                        data[key] = existing + [value]
                else:
                    data[key] = value

        self._body_buffer = b""
        return json.dumps(data).encode()
