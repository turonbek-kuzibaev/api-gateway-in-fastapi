import ipaddress
from typing import Any

from fastapi import Response

from plugins.base import Plugin, PluginContext, PluginPhase
from plugins.registry import PluginRegistry


@PluginRegistry.register("ip-restriction")
class IPRestrictionPlugin(Plugin):
    name = "ip-restriction"
    priority = 950
    phases = [PluginPhase.ACCESS]

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.allow = config.get("allow", [])
        self.deny = config.get("deny", [])
        self.status = config.get("status", 403)
        self.message = config.get("message", "Your IP address is not allowed")

        self._allow_networks = self._parse_networks(self.allow)
        self._deny_networks = self._parse_networks(self.deny)

    def _parse_networks(self, ip_list: list[str]) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
        networks = []
        for ip_str in ip_list:
            try:
                if "/" in ip_str:
                    networks.append(ipaddress.ip_network(ip_str, strict=False))
                else:
                    addr = ipaddress.ip_address(ip_str)
                    if isinstance(addr, ipaddress.IPv4Address):
                        networks.append(ipaddress.ip_network(f"{ip_str}/32"))
                    else:
                        networks.append(ipaddress.ip_network(f"{ip_str}/128"))
            except ValueError:
                continue
        return networks

    async def access(self, ctx: PluginContext) -> Response | None:
        request = ctx.request
        client_ip = request.client.host if request.client else None

        if not client_ip:
            return Response(
                content=f'{{"error": "{self.message}"}}',
                status_code=self.status,
                media_type="application/json",
            )

        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            client_ip = real_ip.strip()

        try:
            ip_addr = ipaddress.ip_address(client_ip)
        except ValueError:
            return Response(
                content=f'{{"error": "{self.message}"}}',
                status_code=self.status,
                media_type="application/json",
            )

        if self._deny_networks:
            for network in self._deny_networks:
                if ip_addr in network:
                    return Response(
                        content=f'{{"error": "{self.message}"}}',
                        status_code=self.status,
                        media_type="application/json",
                    )

        if self._allow_networks:
            allowed = False
            for network in self._allow_networks:
                if ip_addr in network:
                    allowed = True
                    break

            if not allowed:
                return Response(
                    content=f'{{"error": "{self.message}"}}',
                    status_code=self.status,
                    media_type="application/json",
                )

        return None
