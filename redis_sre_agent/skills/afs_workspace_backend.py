"""AFS-backed SkillBackend implementation that reads through the runtime skills API."""

from __future__ import annotations

import hashlib
import os
import json
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:
    import httpx
except ModuleNotFoundError:  # pragma: no cover - runtime image fallback
    httpx = None  # type: ignore[assignment]

from redis_sre_agent.core.config import Settings


def _first_non_empty(config: Settings, names: tuple[tuple[str, str], ...], default: str = "") -> str:
    for attr_name, env_name in names:
        value = _env_or_attr(config, attr_name, env_name)
        if value:
            return value
    return default


def _env_or_attr(config: Settings, attr_name: str, env_name: str, default: str = "") -> str:
    value = getattr(config, attr_name, "")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return os.environ.get(env_name, default).strip()


def _slug_fragment(value: str) -> str:
    lowered = value.strip().lower()
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in lowered)
    return "-".join(part for part in cleaned.split("-") if part) or "workspace"


def _build_skills_workspace_id(*, tenant_id: str, project_id: str, agent_id: str) -> str:
    readable = "-".join(
        _slug_fragment(value) for value in (project_id, agent_id) if value.strip()
    ) or "workspace"
    digest = hashlib.sha1(f"{tenant_id}:{project_id}:{agent_id}".encode("utf-8")).hexdigest()[:12]
    return f"skills-{readable[:36]}-{digest}"


def _parse_event_stream_payload(raw_body: str) -> dict[str, Any]:
    data_lines: list[str] = []
    for raw_line in raw_body.splitlines():
        line = raw_line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload:
            data_lines.append(payload)
    if not data_lines:
        raise ValueError("event-stream response did not include a data payload")
    parsed = json.loads("\n".join(data_lines))
    if not isinstance(parsed, Mapping):
        raise ValueError("event-stream response did not include an object payload")
    return dict(parsed)


@dataclass
class AFSWorkspaceSkillBackend:
    """Runtime skill backend backed by the workspace-scoped skills facade."""

    base_url: str
    tenant_id: str
    project_id: str
    agent_id: str
    bearer_token: str | None = None
    timeout_seconds: float = 15.0
    skill_reference_char_budget: int = 12000
    gateway_url: str | None = None
    gateway_token: str | None = None
    workspace_id: str | None = None
    client_factory: Callable[..., Any] | None = httpx.AsyncClient if httpx is not None else None
    _gateway_session_id: str | None = None
    _gateway_protocol_version: str | None = None

    @classmethod
    def from_settings(cls, config: Settings) -> "AFSWorkspaceSkillBackend":
        base_url = _first_non_empty(
            config,
            (
                ("skills_api_base_url", "RAR_SKILLS_API_BASE_URL"),
                ("skills_api_base_url", "SKILLS_API_BASE_URL"),
                ("skills_api_base_url", "RAK_API_BASE_URL"),
            ),
        )
        tenant_id = _first_non_empty(
            config,
            (
                ("skills_api_tenant_id", "RAR_SKILLS_API_TENANT_ID"),
                ("skills_api_tenant_id", "SKILLS_API_TENANT_ID"),
                ("skills_api_tenant_id", "RAK_TENANT_ID"),
            ),
        )
        project_id = _first_non_empty(
            config,
            (
                ("skills_api_project_id", "RAR_SKILLS_API_PROJECT_ID"),
                ("skills_api_project_id", "SKILLS_API_PROJECT_ID"),
                ("skills_api_project_id", "RAK_PROJECT_ID"),
                ("skills_api_project_id", "RAK_PROJECT"),
            ),
        )
        agent_id = _first_non_empty(
            config,
            (
                ("skills_api_agent_id", "RAR_SKILLS_API_AGENT_ID"),
                ("skills_api_agent_id", "SKILLS_API_AGENT_ID"),
                ("skills_api_agent_id", "RAK_SELF_AGENT_ID"),
                ("skills_api_agent_id", "RAK_AGENT"),
            ),
        )
        if not base_url or not tenant_id or not project_id or not agent_id:
            raise ValueError(
                "AFS workspace skill backend requires base URL plus tenant, project, and agent ids"
            )
        token = _first_non_empty(
            config,
            (
                ("skills_api_token", "RAR_SKILLS_API_TOKEN"),
                ("skills_api_token", "SKILLS_API_TOKEN"),
                ("skills_api_token", "RAK_API_TOKEN"),
                ("skills_api_token", "RAK_SERVICE_TOKEN"),
            ),
        )
        timeout_raw = _first_non_empty(
            config,
            (
                ("skills_api_timeout_seconds", "RAR_SKILLS_API_TIMEOUT_SECONDS"),
                ("skills_api_timeout_seconds", "SKILLS_API_TIMEOUT_SECONDS"),
            ),
            default="15",
        )
        try:
            timeout_seconds = float(timeout_raw)
        except ValueError as exc:
            raise ValueError("skills API timeout must be numeric") from exc
        gateway_url = os.environ.get("RAR_RUNTIME_AFS_MCP_URL", "").strip() or None
        gateway_token = os.environ.get("RAR_RUNTIME_AFS_MCP_TOKEN", "").strip() or None
        workspace_id = (
            os.environ.get("RAR_SKILLS_WORKSPACE_ID", "").strip()
            or _build_skills_workspace_id(
                tenant_id=tenant_id,
                project_id=project_id,
                agent_id=agent_id,
            )
        )
        return cls(
            base_url=base_url.rstrip("/"),
            tenant_id=tenant_id,
            project_id=project_id,
            agent_id=agent_id,
            bearer_token=token or None,
            timeout_seconds=timeout_seconds,
            skill_reference_char_budget=max(int(config.skill_reference_char_budget), 1),
            gateway_url=gateway_url,
            gateway_token=gateway_token,
            workspace_id=workspace_id or None,
        )

    async def list_skills(
        self,
        *,
        query: str | None,
        limit: int,
        offset: int,
        version: str | None,
        distance_threshold: float | None = 0.8,
    ) -> dict[str, Any]:
        del distance_threshold
        api_result: dict[str, Any] | None = None
        api_error: Exception | None = None
        try:
            api_result = await self._list_skills_via_api(
                query=query,
                limit=limit,
                offset=offset,
                version=version,
            )
        except Exception as exc:
            api_error = exc
        else:
            if int(api_result.get("results_count", 0)) > 0 or not self._use_gateway():
                return api_result

        if self._use_gateway():
            gateway_result = await self._list_skills_via_gateway(
                query=query,
                limit=limit,
                offset=offset,
                version=version,
            )
            if int(gateway_result.get("results_count", 0)) > 0 or api_result is None:
                return gateway_result

        if api_result is not None:
            return api_result
        if api_error is not None:
            raise api_error
        return {
            "query": query,
            "version": version,
            "offset": offset,
            "limit": limit,
            "results_count": 0,
            "total_fetched": 0,
            "skills": [],
        }

    async def get_skill(self, *, skill_name: str, version: str | None) -> dict[str, Any]:
        api_result: dict[str, Any] | None = None
        api_error: Exception | None = None
        try:
            api_result = await self._get_skill_via_api(skill_name=skill_name, version=version)
        except Exception as exc:
            api_error = exc
        else:
            if not self._is_missing_result(api_result, "Skill not found") or not self._use_gateway():
                return api_result

        if self._use_gateway():
            gateway_result = await self._get_skill_via_gateway(skill_name=skill_name, version=version)
            if not self._is_missing_result(gateway_result, "Skill not found") or api_result is None:
                return gateway_result

        if api_result is not None:
            return api_result
        if api_error is not None:
            raise api_error
        return {"skill_name": skill_name, "error": "Skill not found"}

    async def get_skill_resource(
        self,
        *,
        skill_name: str,
        resource_path: str,
        version: str | None,
    ) -> dict[str, Any]:
        api_result: dict[str, Any] | None = None
        api_error: Exception | None = None
        try:
            api_result = await self._get_skill_resource_via_api(
                skill_name=skill_name,
                resource_path=resource_path,
                version=version,
            )
        except Exception as exc:
            api_error = exc
        else:
            if (
                not self._is_missing_result(api_result, "Skill resource not found")
                or not self._use_gateway()
            ):
                return api_result

        if self._use_gateway():
            gateway_result = await self._get_skill_resource_via_gateway(
                skill_name=skill_name,
                resource_path=resource_path,
                version=version,
            )
            if (
                not self._is_missing_result(gateway_result, "Skill resource not found")
                or api_result is None
            ):
                return gateway_result

        if api_result is not None:
            return api_result
        if api_error is not None:
            raise api_error
        return {
            "skill_name": skill_name,
            "resource_path": resource_path,
            "error": "Skill resource not found",
        }

    async def _list_skills_via_api(
        self,
        *,
        query: str | None,
        limit: int,
        offset: int,
        version: str | None,
    ) -> dict[str, Any]:
        path = self._base_path()
        params: dict[str, Any] = {"version": version} if version else {}
        if query:
            path = f"{path}/search"
            params["q"] = query
            params["limit"] = max(limit + offset, 1)
        else:
            params["limit"] = limit
            params["offset"] = offset
        payload = await self._request_json("GET", path, params=params)
        data = self._data_payload(payload)
        raw_skills = data.get("skills", [])
        if not isinstance(raw_skills, list):
            raw_skills = []
        normalized_skills = [
            self._normalize_skill_summary(skill, matched_path=None)
            for skill in raw_skills[offset : offset + limit]
            if isinstance(skill, Mapping)
        ] if query else [
            self._normalize_skill_summary(skill, matched_path=None)
            for skill in raw_skills
            if isinstance(skill, Mapping)
        ]
        if query:
            matches = data.get("matches", [])
            if isinstance(matches, list):
                by_identity = {
                    (str(item.get("skillSlug", "")).strip(), str(item.get("version", "")).strip()): item
                    for item in matches
                    if isinstance(item, Mapping)
                }
                normalized_skills = [
                    self._normalize_skill_summary(
                        skill,
                        matched_path=str(
                            by_identity.get(
                                (
                                    str(skill.get("skillSlug", "")).strip(),
                                    str(skill.get("version", "")).strip(),
                                ),
                                {},
                            ).get("path", "")
                        ).strip()
                        or None,
                    )
                    for skill in raw_skills[offset : offset + limit]
                    if isinstance(skill, Mapping)
                ]
        return {
            "query": query,
            "version": version,
            "offset": offset,
            "limit": limit,
            "results_count": len(normalized_skills),
            "total_fetched": int(data.get("total", len(normalized_skills))),
            "skills": normalized_skills,
        }

    async def _list_skills_via_gateway(
        self,
        *,
        query: str | None,
        limit: int,
        offset: int,
        version: str | None,
    ) -> dict[str, Any]:
        raw_skills = await self._gateway_catalog_entries(version=version)
        if query:
            query_text = query.strip().lower()
            raw_skills = [
                skill for skill in raw_skills if query_text in json.dumps(skill, sort_keys=True).lower()
            ]
        paged = raw_skills[offset : offset + limit]
        normalized_skills = [
            self._normalize_skill_summary(skill, matched_path=None) for skill in paged
        ]
        return {
            "query": query,
            "version": version,
            "offset": offset,
            "limit": limit,
            "results_count": len(normalized_skills),
            "total_fetched": len(raw_skills),
            "skills": normalized_skills,
        }

    async def _get_skill_via_api(self, *, skill_name: str, version: str | None) -> dict[str, Any]:
        try:
            payload = await self._request_json(
                "GET",
                f"{self._base_path()}/{skill_name}",
                params={"version": version} if version else None,
            )
        except Exception as exc:
            if _status_code(exc) == 404:
                return {"skill_name": skill_name, "error": "Skill not found"}
            raise
        data = self._data_payload(payload)
        skill = data.get("skill")
        if not isinstance(skill, Mapping):
            return {"skill_name": skill_name, "error": "Skill not found"}
        return self._serialize_skill_payload(skill, default_skill_name=skill_name, default_version=version)

    async def _get_skill_via_gateway(
        self,
        *,
        skill_name: str,
        version: str | None,
    ) -> dict[str, Any]:
        skill = await self._gateway_skill_metadata(skill_name=skill_name, version=version)
        if skill is None:
            return {"skill_name": skill_name, "error": "Skill not found"}
        entrypoint_path = str(skill.get("entrypointPath", "SKILL.md")).strip() or "SKILL.md"
        entrypoint_content = await self._gateway_read_text(
            self._gateway_skill_resource_path(
                skill_slug=str(skill.get("skillSlug", skill_name)).strip() or skill_name,
                version=str(skill.get("version", version or "v1")).strip() or "v1",
                resource_path=entrypoint_path,
            )
        )
        return self._serialize_skill_payload(
            skill,
            default_skill_name=skill_name,
            default_version=version,
            entrypoint_content=entrypoint_content,
        )

    async def _get_skill_resource_via_api(
        self,
        *,
        skill_name: str,
        resource_path: str,
        version: str | None,
    ) -> dict[str, Any]:
        try:
            payload = await self._request_json(
                "GET",
                f"{self._base_path()}/{skill_name}/resource",
                params={
                    "version": version,
                    "resourcePath": resource_path,
                },
            )
        except Exception as exc:
            if _status_code(exc) == 404:
                return {
                    "skill_name": skill_name,
                    "resource_path": resource_path,
                    "error": "Skill resource not found",
                }
            raise
        data = self._data_payload(payload)
        resource = data.get("resource")
        if not isinstance(resource, Mapping):
            return {
                "skill_name": skill_name,
                "resource_path": resource_path,
                "error": "Skill resource not found",
            }
        content = str(resource.get("content", ""))
        truncated_content, truncated = self._truncate_resource_content(content)
        return {
            "skill_name": skill_name,
            "resource_path": str(resource.get("path", resource_path)).strip() or resource_path,
            "version": str(resource.get("version", version or "v1")).strip() or "v1",
            "content": truncated_content,
            "truncated": truncated,
            "backend_kind": "afs_workspace",
            "mime_type": "text/plain",
        }

    async def _get_skill_resource_via_gateway(
        self,
        *,
        skill_name: str,
        resource_path: str,
        version: str | None,
    ) -> dict[str, Any]:
        skill = await self._gateway_skill_metadata(skill_name=skill_name, version=version)
        if skill is None:
            return {
                "skill_name": skill_name,
                "resource_path": resource_path,
                "error": "Skill resource not found",
            }
        normalized_resource_path = resource_path.strip().strip("/")
        allowed_paths = {
            str(item.get("path", "")).strip()
            for item in skill.get("resources", [])
            if isinstance(item, Mapping)
        }
        if normalized_resource_path not in allowed_paths and normalized_resource_path != "SKILL.md":
            return {
                "skill_name": skill_name,
                "resource_path": resource_path,
                "error": "Skill resource not found",
            }
        content = await self._gateway_read_text(
            self._gateway_skill_resource_path(
                skill_slug=str(skill.get("skillSlug", skill_name)).strip() or skill_name,
                version=str(skill.get("version", version or "v1")).strip() or "v1",
                resource_path=normalized_resource_path,
            )
        )
        truncated_content, truncated = self._truncate_resource_content(content)
        return {
            "skill_name": skill_name,
            "resource_path": normalized_resource_path,
            "version": str(skill.get("version", version or "v1")).strip() or "v1",
            "content": truncated_content,
            "truncated": truncated,
            "backend_kind": "afs_workspace",
            "mime_type": "text/plain",
        }

    def _truncate_resource_content(self, content: str) -> tuple[str, bool]:
        if len(content) <= self.skill_reference_char_budget:
            return content, False
        if self.skill_reference_char_budget <= 3:
            return content[: self.skill_reference_char_budget], True
        return f"{content[: self.skill_reference_char_budget - 3].rstrip()}...", True

    def _normalize_skill_summary(
        self,
        skill: Mapping[str, Any],
        *,
        matched_path: str | None,
    ) -> dict[str, Any]:
        skill_slug = str(skill.get("skillSlug", "")).strip()
        version = str(skill.get("version", "v1")).strip() or "v1"
        resources = skill.get("resources", [])
        resource_paths = (
            [str(item.get("path", "")).strip() for item in resources if isinstance(item, Mapping)]
            if isinstance(resources, list)
            else []
        )
        return {
            "name": skill_slug,
            "document_hash": "",
            "title": str(skill.get("displayName", skill_slug)).strip() or skill_slug,
            "source": f"{self._base_path()}/{skill_slug}",
            "version": version,
            "priority": 0,
            "summary": str(skill.get("description", "")).strip(),
            "index_type": "skills",
            "backend_kind": "afs_workspace",
            "protocol": "agent_skills_v1",
            "has_references": any(path.startswith("references/") for path in resource_paths),
            "has_scripts": any(path.startswith("scripts/") for path in resource_paths),
            "has_assets": any(path.startswith("assets/") for path in resource_paths),
            "matched_resource_kind": self._matched_resource_kind(matched_path),
            "matched_resource_path": matched_path or "SKILL.md",
        }

    def _matched_resource_kind(self, matched_path: str | None) -> str:
        if not matched_path:
            return "entrypoint"
        if "/references/" in matched_path or matched_path.startswith("references/"):
            return "reference"
        if "/scripts/" in matched_path or matched_path.startswith("scripts/"):
            return "script"
        if "/assets/" in matched_path or matched_path.startswith("assets/"):
            return "asset"
        return "entrypoint"

    def _base_path(self) -> str:
        return f"/v1/projects/{self.project_id}/agents/{self.agent_id}/skills"

    def _use_gateway(self) -> bool:
        return bool(self.gateway_url and self.gateway_token and self.workspace_id)

    def _serialize_skill_payload(
        self,
        skill: Mapping[str, Any],
        *,
        default_skill_name: str,
        default_version: str | None,
        entrypoint_content: str | None = None,
    ) -> dict[str, Any]:
        if entrypoint_content is None:
            entrypoint = skill.get("entrypoint")
            if isinstance(entrypoint, Mapping):
                entrypoint_content = str(entrypoint.get("content", ""))
            else:
                entrypoint_content = ""
        references: list[dict[str, str]] = []
        scripts: list[dict[str, str]] = []
        assets: list[dict[str, str]] = []
        for item in skill.get("resources", []):
            if not isinstance(item, Mapping):
                continue
            normalized = {
                "path": str(item.get("path", "")).strip(),
                "kind": str(item.get("kind", "")).strip(),
            }
            if normalized["kind"] == "reference":
                references.append(normalized)
            elif normalized["kind"] == "script":
                scripts.append(normalized)
            elif normalized["kind"] == "asset":
                assets.append(normalized)
        return {
            "skill_name": str(skill.get("skillSlug", default_skill_name)).strip() or default_skill_name,
            "title": str(skill.get("displayName", default_skill_name)).strip() or default_skill_name,
            "summary": str(skill.get("description", "")).strip(),
            "version": str(skill.get("version", default_version or "v1")).strip() or "v1",
            "content": entrypoint_content,
            "protocol": "agent_skills_v1",
            "backend_kind": "afs_workspace",
            "references": references,
            "scripts": scripts,
            "assets": assets,
        }

    @staticmethod
    def _is_missing_result(payload: Mapping[str, Any], expected_error: str) -> bool:
        return str(payload.get("error", "")).strip() == expected_error

    def _gateway_endpoint(self) -> str:
        if not self.gateway_url:
            raise ValueError("AFS gateway URL is not configured")
        base = self.gateway_url.rstrip("/")
        if base.endswith("/mcp"):
            return base
        return f"{base}/mcp"

    async def _gateway_catalog_entries(self, *, version: str | None) -> list[Mapping[str, Any]]:
        try:
            raw_catalog = await self._gateway_read_text("/skills/_catalog.json")
        except Exception:
            return []
        try:
            payload = json.loads(raw_catalog)
        except json.JSONDecodeError:
            return []
        if not isinstance(payload, Mapping):
            return []
        raw_entries = payload.get("skills", [])
        if not isinstance(raw_entries, list):
            return []
        entries = [entry for entry in raw_entries if isinstance(entry, Mapping)]
        if version and version != "latest":
            entries = [entry for entry in entries if str(entry.get("version", "")).strip() == version]
        return entries

    async def _gateway_skill_metadata(
        self,
        *,
        skill_name: str,
        version: str | None,
    ) -> Mapping[str, Any] | None:
        entries = await self._gateway_catalog_entries(version=version)
        matches = [
            entry
            for entry in entries
            if str(entry.get("skillSlug", "")).strip() == skill_name
        ]
        if not matches:
            return None
        if version and version != "latest":
            return matches[0]
        matches.sort(key=lambda entry: str(entry.get("version", "")).strip(), reverse=True)
        return matches[0]

    def _gateway_skill_resource_path(
        self,
        *,
        skill_slug: str,
        version: str,
        resource_path: str,
    ) -> str:
        normalized = resource_path.strip().lstrip("/") or "SKILL.md"
        return f"/skills/{skill_slug}/versions/{version}/{normalized}"

    async def _gateway_read_text(self, path: str) -> str:
        payload = await self._gateway_call_tool("file_read", {"path": path})
        content = payload.get("content")
        if isinstance(content, str):
            return content
        raise ValueError(f"AFS gateway file_read returned invalid content for {path}")

    async def _gateway_call_tool(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        session_id = await self._gateway_ensure_session()
        payload_body = {
            "jsonrpc": "2.0",
            "id": f"skills-{tool_name}",
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": dict(arguments)},
        }
        payload = self._stdlib_request_json(
            "POST",
            self._gateway_endpoint(),
            headers=self._gateway_headers(session_id=session_id),
            body=payload_body,
        )
        if not isinstance(payload, Mapping):
            raise ValueError("AFS gateway returned a non-object response")
        error = payload.get("error")
        if isinstance(error, Mapping):
            raise ValueError(str(error.get("message", "AFS gateway tool call failed")).strip())
        result = payload.get("result")
        if not isinstance(result, Mapping):
            return {}
        structured = result.get("structuredContent")
        if isinstance(structured, Mapping):
            return dict(structured)
        content = result.get("content")
        if isinstance(content, list) and content:
            first = content[0]
            if isinstance(first, Mapping):
                text = first.get("text")
                if isinstance(text, str) and text.strip():
                    try:
                        parsed = json.loads(text)
                    except json.JSONDecodeError:
                        return {"content": text}
                    if isinstance(parsed, Mapping):
                        return dict(parsed)
        return {}

    async def _gateway_ensure_session(self) -> str:
        if self._gateway_session_id:
            return self._gateway_session_id
        body = {
            "jsonrpc": "2.0",
            "id": "skills-initialize",
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "redis-sre-agent", "version": "0.1.0"},
            },
        }
        headers = self._gateway_headers()
        response_headers: Mapping[str, str]
        payload, response_headers = self._stdlib_request_json_with_headers(
            "POST",
            self._gateway_endpoint(),
            headers=headers,
            body=body,
        )
        if not isinstance(payload, Mapping):
            raise ValueError("AFS gateway initialize returned a non-object response")
        error = payload.get("error")
        if isinstance(error, Mapping):
            raise ValueError(str(error.get("message", "AFS gateway initialize failed")).strip())
        session_id = str(response_headers.get("mcp-session-id", "")).strip()
        if not session_id:
            raise ValueError("AFS gateway initialize did not return mcp-session-id")
        result = payload.get("result")
        if isinstance(result, Mapping):
            protocol_version = str(result.get("protocolVersion", "")).strip()
            if protocol_version:
                self._gateway_protocol_version = protocol_version
        self._gateway_session_id = session_id
        return session_id

    def _gateway_headers(self, *, session_id: str | None = None) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.gateway_token}",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "X-RAR-Tenant-ID": self.tenant_id,
            "X-RAR-Project-ID": self.project_id,
            "X-RAR-Workspace-ID": str(self.workspace_id or ""),
        }
        if session_id:
            headers["mcp-session-id"] = session_id
            if self._gateway_protocol_version:
                headers["mcp-protocol-version"] = self._gateway_protocol_version
        return headers

    def _headers(self) -> dict[str, str]:
        headers = {
            "x-rar-tenant-id": self.tenant_id,
            "x-rar-principal-id": "redis-sre-agent",
            "x-rar-auth-scheme": "oauth2",
            "x-rar-scopes": "agents:discover,agents:invoke,tools:invoke,tasks:read,tasks:write",
        }
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        return headers

    def _data_payload(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        data = payload.get("data")
        if isinstance(data, Mapping):
            return data
        raise ValueError("skills API response did not include a data object")

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.client_factory is not None:
            async with self.client_factory(
                base_url=self.base_url,
                headers=self._headers(),
                timeout=self.timeout_seconds,
            ) as client:
                response = await client.request(method, path, params=params)
                response.raise_for_status()
                payload = response.json()
        else:
            query = f"?{urlencode({k: v for k, v in (params or {}).items() if v is not None})}" if params else ""
            payload = self._stdlib_request_json(
                method,
                f"{self.base_url.rstrip('/')}{path}{query}",
                headers=self._headers(),
                body=None,
            )
        if not isinstance(payload, Mapping):
            raise ValueError("skills API returned a non-object response")
        return dict(payload)

    def _stdlib_request_json(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        body: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        payload, _ = self._stdlib_request_json_with_headers(method, url, headers=headers, body=body)
        return payload

    def _stdlib_request_json_with_headers(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        body: Mapping[str, Any] | None,
    ) -> tuple[dict[str, Any], Mapping[str, str]]:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = Request(url, data=data, headers=dict(headers), method=method)
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw_body = response.read().decode("utf-8")
                response_headers = {
                    str(key).lower(): str(value) for key, value in response.headers.items()
                }
                content_type = response_headers.get("content-type", "")
                if "text/event-stream" in content_type:
                    parsed = _parse_event_stream_payload(raw_body)
                else:
                    parsed = json.loads(raw_body) if raw_body else {}
                if not isinstance(parsed, Mapping):
                    raise ValueError("HTTP request returned a non-object response")
                return dict(parsed), response_headers
        except HTTPError:
            raise
        except URLError as exc:
            raise ValueError(f"HTTP request failed: {exc.reason}") from exc


def _status_code(exc: Exception) -> int | None:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if isinstance(status_code, int):
        return status_code
    if isinstance(exc, HTTPError):
        return int(exc.code)
    return None
