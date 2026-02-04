import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response

from admin import create_admin_app
from admin.api import set_state
from core import Gateway
from plugins.builtin import (
    JWTAuthPlugin,
    KeyAuthPlugin,
    RateLimitingPlugin,
    CORSPlugin,
    RequestTransformerPlugin,
    ResponseTransformerPlugin,
    LoggingPlugin,
    IPRestrictionPlugin,
    RequestSizeLimitingPlugin,
)

gateway = Gateway("config.yaml")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await gateway.start()

    set_state(
        gateway.upstream_manager,
        {s.name: s for s in gateway.router.list_services()},
        {},
    )

    yield

    await gateway.stop()


app = FastAPI(
    title="API Gateway",
    description="Kong API Gateway built with FastAPI",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/gateway/docs",
    redoc_url="/gateway/redoc",
    openapi_url="/gateway/openapi.json",
)

admin_app = create_admin_app()
app.mount("/admin", admin_app)


@app.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
)
async def proxy(request: Request, path: str) -> Response:
    return await gateway.handle_request(request)


@app.get("/")
async def root():
    return {
        "name": "API Gateway",
        "version": "1.0.0",
        "status": "running",
        "admin_api": "/admin",
        "docs": "/gateway/docs",
    }


if __name__ == "__main__":
    import uvicorn

    config = gateway.config
    host = config.host if config else "0.0.0.0"
    port = config.port if config else 8000

    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=True,
    )
