import json
from typing import Callable

from fastapi import Request, Response
from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware

from config import Config


class JWTAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: Config):
        super().__init__(app)
        self.config = config
        self.secret_key = config.jwt.secret_key
        self.algorithm = config.jwt.algorithm

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        service = self.config.get_service_for_path(request.url.path)

        if service is None or not service.auth_required:
            return await call_next(request)

        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return Response(
                content='{"error": "Missing authorization header"}',
                status_code=401,
                media_type="application/json",
            )

        if not auth_header.startswith("Bearer "):
            return Response(
                content='{"error": "Invalid authorization header format"}',
                status_code=401,
                media_type="application/json",
            )

        token = auth_header[7:]

        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
            )
            request.state.user = payload
            request.state.user_id = payload.get("sub")

        except JWTError as e:
            return Response(
                content=f'{{"error": "Invalid token: {str(e)}"}}',
                status_code=401,
                media_type="application/json",
            )

        return await call_next(request)
