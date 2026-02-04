from typing import Any

from fastapi import Response
from jose import JWTError, jwt

from plugins.base import Plugin, PluginContext, PluginPhase
from plugins.registry import PluginRegistry


@PluginRegistry.register("jwt-auth")
class JWTAuthPlugin(Plugin):
    name = "jwt-auth"
    priority = 1000
    phases = [PluginPhase.ACCESS]

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.secret = config.get("secret", "your-secret-key")
        self.algorithm = config.get("algorithm", "HS256")
        self.header_names = config.get("header_names", ["Authorization"])
        self.claims_to_verify = config.get("claims_to_verify", ["exp"])
        self.key_claim_name = config.get("key_claim_name", "iss")
        self.anonymous = config.get("anonymous")
        self.run_on_preflight = config.get("run_on_preflight", True)

    async def access(self, ctx: PluginContext) -> Response | None:
        request = ctx.request

        if request.method == "OPTIONS" and not self.run_on_preflight:
            return None

        token = self._extract_token(ctx)

        if not token:
            if self.anonymous:
                ctx.consumer = {"username": self.anonymous}
                ctx.authenticated = False
                return None

            return Response(
                content='{"error": "Missing authentication token"}',
                status_code=401,
                media_type="application/json",
                headers={"WWW-Authenticate": "Bearer"},
            )

        try:
            options = {}
            if "exp" not in self.claims_to_verify:
                options["verify_exp"] = False

            payload = jwt.decode(
                token,
                self.secret,
                algorithms=[self.algorithm],
                options=options,
            )

            ctx.consumer = payload
            ctx.authenticated = True
            ctx.set("jwt_claims", payload)
            ctx.set("user_id", payload.get("sub"))

        except JWTError as e:
            return Response(
                content=f'{{"error": "Invalid token: {str(e)}"}}',
                status_code=401,
                media_type="application/json",
                headers={"WWW-Authenticate": "Bearer error=\"invalid_token\""},
            )

        return None

    def _extract_token(self, ctx: PluginContext) -> str | None:
        request = ctx.request

        for header_name in self.header_names:
            header_value = request.headers.get(header_name)
            if header_value:
                if header_value.startswith("Bearer "):
                    return header_value[7:]
                return header_value

        token = request.query_params.get("jwt")
        if token:
            return token

        return None
