"""Support package tool provider.

This provider exposes tools for analyzing Redis Enterprise support packages,
providing access to database diagnostics, node logs, and cluster information.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from redis_sre_agent.tools.decorators import status_update
from redis_sre_agent.tools.models import ToolCapability, ToolDefinition
from redis_sre_agent.tools.protocols import ToolProvider

from .models import SupportPackage

logger = logging.getLogger(__name__)


class SupportPackageToolProvider(ToolProvider):
    """Tool provider for analyzing Redis Enterprise support packages.

    Provides tools for:
    - Reading database INFO, SLOWLOG, CLIENT LIST from support packages
    - Browsing and searching node logs
    - Listing available databases and nodes

    Example:
        provider = SupportPackageToolProvider(package_path=Path("./extracted_package"))
        async with provider:
            result = await provider.info(database_id="4")
    """

    def __init__(
        self,
        package_path: Optional[Path] = None,
        package: Optional[SupportPackage] = None,
        redis_instance=None,
    ):
        """Initialize the provider.

        Args:
            package_path: Path to extracted support package directory
            package: Pre-parsed SupportPackage model
            redis_instance: Optional Redis instance (not used, for interface compat)
        """
        super().__init__(redis_instance)
        self._package: Optional[SupportPackage] = package
        self._package_path = package_path

        if package_path and not package:
            self._package = SupportPackage.from_directory(package_path)

    @property
    def provider_name(self) -> str:
        return "support_package"

    @property
    def package(self) -> SupportPackage:
        """Get the loaded support package."""
        if self._package is None:
            raise ValueError("No support package loaded")
        return self._package

    def create_tool_schemas(self) -> List[ToolDefinition]:
        """Create tool schemas for support package operations."""
        return [
            ToolDefinition(
                name=self._make_tool_name("info"),
                description=(
                    "Get Redis INFO output for a database from the support package. "
                    "Returns server statistics, memory usage, client connections, etc."
                ),
                capability=ToolCapability.DIAGNOSTICS,
                parameters={
                    "type": "object",
                    "properties": {
                        "database_id": {
                            "type": "string",
                            "description": "Database ID (e.g., '4')",
                        },
                        "section": {
                            "type": "string",
                            "description": "Optional section to filter (e.g., 'memory', 'clients')",
                        },
                    },
                    "required": ["database_id"],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("slowlog"),
                description=(
                    "Get SLOWLOG entries for a database from the support package. "
                    "Shows slow queries captured at the time the package was generated."
                ),
                capability=ToolCapability.DIAGNOSTICS,
                parameters={
                    "type": "object",
                    "properties": {
                        "database_id": {
                            "type": "string",
                            "description": "Database ID (e.g., '4')",
                        },
                    },
                    "required": ["database_id"],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("clientlist"),
                description=(
                    "Get CLIENT LIST output for a database from the support package. "
                    "Shows connected clients at the time the package was generated."
                ),
                capability=ToolCapability.DIAGNOSTICS,
                parameters={
                    "type": "object",
                    "properties": {
                        "database_id": {
                            "type": "string",
                            "description": "Database ID (e.g., '4')",
                        },
                    },
                    "required": ["database_id"],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("logs"),
                description=(
                    "Read log file from a node in the support package. "
                    "Supports filtering by log level."
                ),
                capability=ToolCapability.LOGS,
                parameters={
                    "type": "object",
                    "properties": {
                        "node_id": {
                            "type": "string",
                            "description": "Node ID (e.g., '1')",
                        },
                        "log_name": {
                            "type": "string",
                            "description": "Log file name (e.g., 'event_log.log')",
                        },
                        "level": {
                            "type": "string",
                            "description": "Filter by log level (INFO, WARNING, ERROR, CRITICAL)",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of lines to return",
                        },
                    },
                    "required": ["node_id", "log_name"],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("list_databases"),
                description="List all databases in the support package.",
                capability=ToolCapability.DIAGNOSTICS,
                parameters={"type": "object", "properties": {}, "required": []},
            ),
            ToolDefinition(
                name=self._make_tool_name("list_nodes"),
                description="List all nodes in the support package.",
                capability=ToolCapability.DIAGNOSTICS,
                parameters={"type": "object", "properties": {}, "required": []},
            ),
            ToolDefinition(
                name=self._make_tool_name("list_node_logs"),
                description="List available log files for a node.",
                capability=ToolCapability.LOGS,
                parameters={
                    "type": "object",
                    "properties": {
                        "node_id": {
                            "type": "string",
                            "description": "Node ID (e.g., '1')",
                        },
                    },
                    "required": ["node_id"],
                },
            ),
        ]

    # ----------------------------- Tool Implementations -----------------------------

    @status_update("Reading database INFO from support package for database {database_id}.")
    async def info(self, database_id: str, section: Optional[str] = None) -> Dict[str, Any]:
        """Get Redis INFO output for a database.

        Args:
            database_id: Database ID
            section: Optional section to filter

        Returns:
            Dict with status and data
        """
        db = self.package.get_database(database_id)
        if not db:
            return {
                "status": "error",
                "error": f"Database {database_id} not found in support package",
            }

        if not db.info_content:
            return {
                "status": "error",
                "error": f"No INFO data available for database {database_id}",
            }

        data = db.info_content
        if section:
            # Filter to specific section
            lines = []
            in_section = False
            for line in data.splitlines():
                if line.startswith(f"# {section.capitalize()}"):
                    in_section = True
                elif line.startswith("#") and in_section:
                    break
                if in_section:
                    lines.append(line)
            data = "\n".join(lines) if lines else data

        return {"status": "success", "database_id": database_id, "data": data}

    @status_update("Reading SLOWLOG from support package for database {database_id}.")
    async def slowlog(self, database_id: str) -> Dict[str, Any]:
        """Get SLOWLOG entries for a database.

        Args:
            database_id: Database ID

        Returns:
            Dict with status and data
        """
        db = self.package.get_database(database_id)
        if not db:
            return {
                "status": "error",
                "error": f"Database {database_id} not found in support package",
            }

        if not db.slowlog_content:
            return {
                "status": "error",
                "error": f"No SLOWLOG data available for database {database_id}",
            }

        return {"status": "success", "database_id": database_id, "data": db.slowlog_content}

    @status_update("Reading CLIENT LIST from support package for database {database_id}.")
    async def clientlist(self, database_id: str) -> Dict[str, Any]:
        """Get CLIENT LIST output for a database.

        Args:
            database_id: Database ID

        Returns:
            Dict with status and data
        """
        db = self.package.get_database(database_id)
        if not db:
            return {
                "status": "error",
                "error": f"Database {database_id} not found in support package",
            }

        if not db.clientlist_content:
            return {
                "status": "error",
                "error": f"No CLIENT LIST data available for database {database_id}",
            }

        return {"status": "success", "database_id": database_id, "data": db.clientlist_content}

    @status_update("Reading log {log_name} from node {node_id}.")
    async def logs(
        self,
        node_id: str,
        log_name: str,
        level: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Read a log file from a node.

        Args:
            node_id: Node ID
            log_name: Log file name
            level: Optional log level filter
            limit: Maximum number of lines

        Returns:
            Dict with status and data
        """
        node = self.package.get_node(node_id)
        if not node:
            return {
                "status": "error",
                "error": f"Node {node_id} not found in support package",
            }

        log_content = node.read_log(log_name)
        if not log_content:
            return {
                "status": "error",
                "error": f"Log file {log_name} not found for node {node_id}",
            }

        lines = log_content.splitlines()

        # Filter by level if specified
        if level:
            level_upper = level.upper()
            lines = [line for line in lines if level_upper in line.upper()]

        # Apply limit
        if limit and limit > 0:
            lines = lines[:limit]

        return {
            "status": "success",
            "node_id": node_id,
            "log_name": log_name,
            "data": "\n".join(lines),
            "line_count": len(lines),
        }

    async def list_databases(self) -> Dict[str, Any]:
        """List all databases in the support package.

        Returns:
            Dict with status and database list
        """
        databases = [
            {
                "database_id": db.database_id,
                "name": db.name,
                "has_info": db.info_content is not None,
                "has_slowlog": db.slowlog_content is not None,
                "has_clientlist": db.clientlist_content is not None,
            }
            for db in self.package.databases
        ]
        return {"status": "success", "databases": databases}

    async def list_nodes(self) -> Dict[str, Any]:
        """List all nodes in the support package.

        Returns:
            Dict with status and node list
        """
        nodes = [
            {
                "node_id": node.node_id,
                "name": node.name,
                "log_count": len(node.log_files),
                "has_sys_info": node.sys_info_content is not None,
            }
            for node in self.package.nodes
        ]
        return {"status": "success", "nodes": nodes}

    async def list_node_logs(self, node_id: str) -> Dict[str, Any]:
        """List available log files for a node.

        Args:
            node_id: Node ID

        Returns:
            Dict with status and log file list
        """
        node = self.package.get_node(node_id)
        if not node:
            return {
                "status": "error",
                "error": f"Node {node_id} not found in support package",
            }

        return {
            "status": "success",
            "node_id": node_id,
            "log_files": list(node.log_files.keys()),
        }
