"""Fake authenticated tool provider for pluggable target integration tests."""

from __future__ import annotations

from pydantic import BaseModel, SecretStr

from redis_sre_agent.tools.models import ToolCapability, ToolDefinition
from redis_sre_agent.tools.protocols import ToolProvider


class FakeTargetAuthConfig(BaseModel):
    """Per-target fake auth config carried by the authenticated client factory."""

    username: str
    token: SecretStr
    audience: str | None = None


class FakeAuthenticatedToolProvider(ToolProvider):
    """Minimal provider that proves an authenticated fake target can load tools."""

    capabilities = {ToolCapability.UTILITIES}
    instance_config_model = FakeTargetAuthConfig
    extension_namespace = "fake_target"

    @property
    def provider_name(self) -> str:
        return "fake_target"

    @property
    def requires_redis_instance(self) -> bool:
        return True

    async def auth_status(self) -> dict:
        if self.redis_instance is None or self.instance_config is None:
            return {
                "status": "error",
                "message": "Fake authenticated target context is unavailable.",
            }

        token_value = self.instance_config.token.get_secret_value()
        return {
            "status": "success",
            "authenticated": True,
            "target_handle": self.redis_instance.id,
            "target_name": self.redis_instance.name,
            "username": self.instance_config.username,
            "audience": self.instance_config.audience,
            "token_suffix": token_value[-4:] if token_value else "",
        }

    def create_tool_schemas(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name=self._make_tool_name("auth_status"),
                description="Inspect the fake authenticated target binding.",
                capability=ToolCapability.UTILITIES,
                parameters={"type": "object", "properties": {}},
            )
        ]
