from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from models import ServiceConfig, UpstreamConfig, TargetConfig, RouteConfig, PluginConfig
from plugins import PluginRegistry
from upstream import UpstreamManager


class TargetCreate(BaseModel):
    host: str
    port: int = 80
    weight: int = 100
    priority: int = 0
    tags: list[str] = []


class UpstreamCreate(BaseModel):
    name: str
    algorithm: str = "round-robin"
    targets: list[TargetCreate]


class RouteCreate(BaseModel):
    name: str
    paths: list[str]
    methods: list[str] = ["GET", "POST", "PUT", "DELETE", "PATCH"]
    strip_path: bool = True


class ServiceCreate(BaseModel):
    name: str
    upstream: str
    routes: list[RouteCreate]
    path: str = ""


class PluginCreate(BaseModel):
    name: str
    enabled: bool = True
    config: dict[str, Any] = {}


class StatusResponse(BaseModel):
    status: str
    version: str


class GatewayState:
    def __init__(self):
        self.upstream_manager: UpstreamManager | None = None
        self.services: dict[str, ServiceConfig] = {}
        self.routes: dict[str, RouteConfig] = {}
        self.plugins: dict[str, list[PluginConfig]] = {}


_state = GatewayState()


def set_state(
    upstream_manager: UpstreamManager,
    services: dict[str, ServiceConfig],
    routes: dict[str, RouteConfig],
) -> None:
    _state.upstream_manager = upstream_manager
    _state.services = services
    _state.routes = routes


def create_admin_app() -> FastAPI:
    app = FastAPI(
        title="API Gateway Admin",
        description="Admin API for managing the gateway configuration at runtime",
        version="1.0.0",
    )

    @app.get("/", response_model=StatusResponse)
    async def root():
        return {"status": "ok", "version": "1.0.0"}

    @app.get("/status")
    async def status():
        info = {
            "status": "running",
            "version": "1.0.0",
            "upstreams": len(_state.upstream_manager.list_upstreams()) if _state.upstream_manager else 0,
            "services": len(_state.services),
            "routes": len(_state.routes),
            "plugins": list(PluginRegistry.list_plugins()),
        }
        return info

    @app.get("/upstreams")
    async def list_upstreams():
        if not _state.upstream_manager:
            return {"data": []}
        return {"data": [u.to_dict() for u in _state.upstream_manager.list_upstreams()]}

    @app.get("/upstreams/{name}")
    async def get_upstream(name: str):
        if not _state.upstream_manager:
            raise HTTPException(status_code=404, detail="Upstream not found")

        upstream = _state.upstream_manager.get_upstream(name)
        if not upstream:
            raise HTTPException(status_code=404, detail="Upstream not found")
        return {"data": upstream.to_dict()}

    @app.post("/upstreams", status_code=201)
    async def create_upstream(body: UpstreamCreate):
        if not _state.upstream_manager:
            raise HTTPException(status_code=500, detail="Gateway not initialized")

        if _state.upstream_manager.get_upstream(body.name):
            raise HTTPException(status_code=409, detail="Upstream already exists")

        config = UpstreamConfig(
            name=body.name,
            algorithm=body.algorithm,
            targets=[
                TargetConfig(
                    host=t.host,
                    port=t.port,
                    weight=t.weight,
                    priority=t.priority,
                    tags=t.tags,
                )
                for t in body.targets
            ],
        )
        upstream = _state.upstream_manager.add_upstream(config)
        return {"data": upstream.to_dict()}

    @app.delete("/upstreams/{name}", status_code=204)
    async def delete_upstream(name: str):
        if not _state.upstream_manager:
            raise HTTPException(status_code=500, detail="Gateway not initialized")

        if not _state.upstream_manager.remove_upstream(name):
            raise HTTPException(status_code=404, detail="Upstream not found")

    @app.get("/upstreams/{name}/targets")
    async def list_targets(name: str):
        if not _state.upstream_manager:
            raise HTTPException(status_code=404, detail="Upstream not found")

        upstream = _state.upstream_manager.get_upstream(name)
        if not upstream:
            raise HTTPException(status_code=404, detail="Upstream not found")

        return {"data": [t.to_dict() for t in upstream.targets]}

    @app.post("/upstreams/{name}/targets", status_code=201)
    async def add_target(name: str, body: TargetCreate):
        if not _state.upstream_manager:
            raise HTTPException(status_code=500, detail="Gateway not initialized")

        upstream = _state.upstream_manager.get_upstream(name)
        if not upstream:
            raise HTTPException(status_code=404, detail="Upstream not found")

        from upstream import Target
        target = Target(
            host=body.host,
            port=body.port,
            weight=body.weight,
            priority=body.priority,
            tags=body.tags,
        )
        upstream.targets.append(target)
        upstream.health_checker.add_target(target)

        return {"data": target.to_dict()}

    @app.get("/upstreams/{name}/health")
    async def upstream_health(name: str):
        if not _state.upstream_manager:
            raise HTTPException(status_code=404, detail="Upstream not found")

        upstream = _state.upstream_manager.get_upstream(name)
        if not upstream:
            raise HTTPException(status_code=404, detail="Upstream not found")

        return {
            "data": {
                "name": name,
                "targets": [
                    {
                        "address": t.address,
                        "state": t.state.value,
                        "weight": t.weight,
                    }
                    for t in upstream.targets
                ],
                "circuit_breaker": upstream.circuit_breaker.to_dict(),
            }
        }

    @app.get("/services")
    async def list_services():
        return {"data": [s.model_dump() for s in _state.services.values()]}

    @app.get("/services/{name}")
    async def get_service(name: str):
        service = _state.services.get(name)
        if not service:
            raise HTTPException(status_code=404, detail="Service not found")
        return {"data": service.model_dump()}

    @app.get("/routes")
    async def list_routes():
        return {"data": [r.model_dump() for r in _state.routes.values()]}

    @app.get("/routes/{name}")
    async def get_route(name: str):
        route = _state.routes.get(name)
        if not route:
            raise HTTPException(status_code=404, detail="Route not found")
        return {"data": route.model_dump()}

    @app.get("/plugins")
    async def list_plugins():
        return {"data": PluginRegistry.list_plugins()}

    @app.get("/plugins/{name}/schema")
    async def get_plugin_schema(name: str):
        plugin_cls = PluginRegistry.get(name)
        if not plugin_cls:
            raise HTTPException(status_code=404, detail="Plugin not found")

        return {
            "data": {
                "name": plugin_cls.name,
                "priority": plugin_cls.priority,
                "phases": [p.name for p in plugin_cls.phases],
            }
        }

    return app
