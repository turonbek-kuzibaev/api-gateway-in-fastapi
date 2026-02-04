import re
from dataclasses import dataclass, field
from typing import Any

from models import ServiceConfig, RouteConfig


@dataclass
class MatchedRoute:
    service: ServiceConfig
    route: RouteConfig
    path_params: dict[str, str] = field(default_factory=dict)
    remaining_path: str = ""


class Router:
    def __init__(self):
        self._services: dict[str, ServiceConfig] = {}
        self._routes: list[tuple[re.Pattern, RouteConfig, ServiceConfig]] = []

    def add_service(self, service: ServiceConfig) -> None:
        self._services[service.name] = service

        for route in service.routes:
            for path in route.paths:
                pattern = self._path_to_regex(path)
                self._routes.append((pattern, route, service))

    def remove_service(self, name: str) -> bool:
        if name not in self._services:
            return False

        service = self._services.pop(name)
        self._routes = [
            (p, r, s) for p, r, s in self._routes if s.name != name
        ]
        return True

    def get_service(self, name: str) -> ServiceConfig | None:
        return self._services.get(name)

    def list_services(self) -> list[ServiceConfig]:
        return list(self._services.values())

    def match(self, path: str, method: str, headers: dict[str, str] | None = None) -> MatchedRoute | None:
        for pattern, route, service in self._routes:
            if not service.enabled:
                continue

            if method not in route.methods:
                continue

            if route.hosts:
                host = headers.get("host", "") if headers else ""
                if not self._match_host(host, route.hosts):
                    continue

            if route.headers:
                if not self._match_headers(headers or {}, route.headers):
                    continue

            match = pattern.match(path)
            if match:
                path_params = match.groupdict()
                remaining_path = path[match.end():]

                if route.strip_path:
                    for route_path in route.paths:
                        base_path = route_path.split("{")[0].rstrip("/")
                        if path.startswith(base_path):
                            remaining_path = path[len(base_path):]
                            break

                return MatchedRoute(
                    service=service,
                    route=route,
                    path_params=path_params,
                    remaining_path=remaining_path,
                )

        return None

    def _path_to_regex(self, path: str) -> re.Pattern:
        pattern = path

        pattern = re.sub(r'\{(\w+)\}', r'(?P<\1>[^/]+)', pattern)

        if pattern.endswith("*"):
            pattern = pattern[:-1] + ".*"

        if not pattern.endswith(".*"):
            pattern = pattern.rstrip("/") + "/?.*"

        return re.compile(f"^{pattern}")

    def _match_host(self, host: str, allowed_hosts: list[str]) -> bool:
        host = host.split(":")[0]

        for allowed in allowed_hosts:
            if allowed.startswith("*."):
                suffix = allowed[1:]
                if host.endswith(suffix) or host == allowed[2:]:
                    return True
            elif host == allowed:
                return True

        return False

    def _match_headers(self, headers: dict[str, str], required: dict[str, str]) -> bool:
        for key, value in required.items():
            header_value = headers.get(key.lower())
            if header_value is None:
                return False

            if value.startswith("~"):
                pattern = value[1:]
                if not re.match(pattern, header_value):
                    return False
            elif header_value != value:
                return False

        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "services": [s.model_dump() for s in self._services.values()],
            "routes_count": len(self._routes),
        }
