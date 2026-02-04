from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class GatewayConfig:
    host: str = "0.0.0.0"
    port: int = 8000


@dataclass
class JWTConfig:
    secret_key: str = "your-secret-key"
    algorithm: str = "HS256"


@dataclass
class RateLimitConfig:
    requests_per_minute: int = 60
    enabled: bool = True


@dataclass
class ServiceConfig:
    name: str
    prefix: str
    target: str
    auth_required: bool = True


@dataclass
class Config:
    gateway: GatewayConfig = field(default_factory=GatewayConfig)
    jwt: JWTConfig = field(default_factory=JWTConfig)
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    services: list[ServiceConfig] = field(default_factory=list)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "Config":
        path = Path(path)
        if not path.exists():
            return cls()

        with open(path) as f:
            data = yaml.safe_load(f) or {}

        gateway_data = data.get("gateway", {})
        gateway = GatewayConfig(
            host=gateway_data.get("host", "0.0.0.0"),
            port=gateway_data.get("port", 8000),
        )

        jwt_data = data.get("jwt", {})
        jwt = JWTConfig(
            secret_key=jwt_data.get("secret_key", "your-secret-key"),
            algorithm=jwt_data.get("algorithm", "HS256"),
        )

        rate_limit_data = data.get("rate_limit", {})
        rate_limit = RateLimitConfig(
            requests_per_minute=rate_limit_data.get("requests_per_minute", 60),
            enabled=rate_limit_data.get("enabled", True),
        )

        services_data = data.get("services", [])
        services = [
            ServiceConfig(
                name=svc["name"],
                prefix=svc["prefix"],
                target=svc["target"],
                auth_required=svc.get("auth_required", True),
            )
            for svc in services_data
        ]

        return cls(
            gateway=gateway,
            jwt=jwt,
            rate_limit=rate_limit,
            services=services,
        )

    def get_service_for_path(self, path: str) -> Optional[ServiceConfig]:
        for service in self.services:
            if path.startswith(service.prefix):
                return service
        return None


def load_config(config_path: str | Path = "config.yaml") -> Config:
    return Config.from_yaml(config_path)
