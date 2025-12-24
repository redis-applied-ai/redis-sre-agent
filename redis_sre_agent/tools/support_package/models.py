"""Models for Redis Enterprise support packages.

Support packages are tar.gz archives containing diagnostic data from
Redis Enterprise clusters, including:
- Database diagnostics (INFO, SLOWLOG, CLIENT LIST, rladmin output)
- Node diagnostics (system info, logs, configuration)
- Cluster-wide data (usage reports)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class SupportPackageDatabase(BaseModel):
    """Represents a database within a support package."""

    database_id: str = Field(..., description="Database ID (e.g., '4')")
    name: str = Field(..., description="Directory name (e.g., 'database_4')")
    path: Path = Field(..., description="Path to the database directory")
    info_content: Optional[str] = Field(None, description="Content of INFO command output")
    slowlog_content: Optional[str] = Field(None, description="Content of SLOWLOG output")
    clientlist_content: Optional[str] = Field(None, description="Content of CLIENT LIST output")
    rladmin_content: Optional[str] = Field(None, description="Content of rladmin output")
    ccs_info_content: Optional[str] = Field(None, description="Content of CCS info")

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    def from_directory(cls, directory: Path) -> "SupportPackageDatabase":
        """Parse a database directory from a support package.

        Args:
            directory: Path to database directory (e.g., 'database_4')

        Returns:
            SupportPackageDatabase instance
        """
        name = directory.name
        # Extract database ID from directory name (e.g., 'database_4' -> '4')
        match = re.search(r"database_(\d+)", name)
        database_id = match.group(1) if match else name

        # Read available files
        info_content = None
        slowlog_content = None
        clientlist_content = None
        rladmin_content = None
        ccs_info_content = None

        info_file = directory / f"{name}.info"
        if info_file.exists():
            info_content = info_file.read_text(errors="replace")

        slowlog_file = directory / f"{name}.slowlog"
        if slowlog_file.exists():
            slowlog_content = slowlog_file.read_text(errors="replace")

        clientlist_file = directory / f"{name}.clientlist"
        if clientlist_file.exists():
            clientlist_content = clientlist_file.read_text(errors="replace")

        rladmin_file = directory / f"{name}.rladmin"
        if rladmin_file.exists():
            rladmin_content = rladmin_file.read_text(errors="replace")

        ccs_info_file = directory / f"{name}_ccs_info.txt"
        if ccs_info_file.exists():
            ccs_info_content = ccs_info_file.read_text(errors="replace")

        return cls(
            database_id=database_id,
            name=name,
            path=directory,
            info_content=info_content,
            slowlog_content=slowlog_content,
            clientlist_content=clientlist_content,
            rladmin_content=rladmin_content,
            ccs_info_content=ccs_info_content,
        )


class SupportPackageNode(BaseModel):
    """Represents a node within a support package."""

    node_id: str = Field(..., description="Node ID (e.g., '1')")
    name: str = Field(..., description="Directory name (e.g., 'node_1')")
    path: Path = Field(..., description="Path to the node directory")
    sys_info_content: Optional[str] = Field(None, description="System info content")
    rladmin_content: Optional[str] = Field(None, description="rladmin status content")
    log_files: Dict[str, Path] = Field(
        default_factory=dict, description="Map of log file names to paths"
    )

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    def from_directory(cls, directory: Path) -> "SupportPackageNode":
        """Parse a node directory from a support package.

        Args:
            directory: Path to node directory (e.g., 'node_1')

        Returns:
            SupportPackageNode instance
        """
        name = directory.name
        # Extract node ID from directory name (e.g., 'node_1' -> '1')
        match = re.search(r"node_(\d+)", name)
        node_id = match.group(1) if match else name

        sys_info_content = None
        rladmin_content = None
        log_files: Dict[str, Path] = {}

        # Read system info
        sys_info_file = directory / f"{name}_sys_info.txt"
        if sys_info_file.exists():
            sys_info_content = sys_info_file.read_text(errors="replace")

        # Read rladmin status
        rladmin_file = directory / f"{name}.rladmin"
        if rladmin_file.exists():
            rladmin_content = rladmin_file.read_text(errors="replace")

        # Find log files
        logs_dir = directory / "logs"
        if logs_dir.exists() and logs_dir.is_dir():
            for log_file in logs_dir.iterdir():
                if log_file.is_file() and log_file.suffix == ".log":
                    log_files[log_file.name] = log_file

        return cls(
            node_id=node_id,
            name=name,
            path=directory,
            sys_info_content=sys_info_content,
            rladmin_content=rladmin_content,
            log_files=log_files,
        )

    def read_log(self, log_name: str) -> Optional[str]:
        """Read content of a specific log file.

        Args:
            log_name: Name of the log file

        Returns:
            Log content or None if not found
        """
        if log_name in self.log_files:
            return self.log_files[log_name].read_text(errors="replace")
        return None


class SupportPackage(BaseModel):
    """Represents a complete Redis Enterprise support package."""

    path: Path = Field(..., description="Path to the extracted package directory")
    databases: List[SupportPackageDatabase] = Field(
        default_factory=list, description="Databases in the package"
    )
    nodes: List[SupportPackageNode] = Field(
        default_factory=list, description="Nodes in the package"
    )
    usage_report_content: Optional[str] = Field(None, description="Usage report content")

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    def from_directory(cls, directory: Path) -> "SupportPackage":
        """Parse a support package from an extracted directory.

        Args:
            directory: Path to extracted support package directory

        Returns:
            SupportPackage instance
        """
        databases: List[SupportPackageDatabase] = []
        nodes: List[SupportPackageNode] = []
        usage_report_content = None

        for item in directory.iterdir():
            if not item.is_dir():
                if item.name == "usage_report.usg":
                    usage_report_content = item.read_text(errors="replace")
                continue

            if item.name.startswith("database_"):
                databases.append(SupportPackageDatabase.from_directory(item))
            elif item.name.startswith("node_"):
                nodes.append(SupportPackageNode.from_directory(item))

        return cls(
            path=directory,
            databases=databases,
            nodes=nodes,
            usage_report_content=usage_report_content,
        )

    def get_database(self, database_id: str) -> Optional[SupportPackageDatabase]:
        """Get a database by its ID.

        Args:
            database_id: Database ID to find

        Returns:
            SupportPackageDatabase or None if not found
        """
        for db in self.databases:
            if db.database_id == database_id:
                return db
        return None

    def get_node(self, node_id: str) -> Optional[SupportPackageNode]:
        """Get a node by its ID.

        Args:
            node_id: Node ID to find

        Returns:
            SupportPackageNode or None if not found
        """
        for node in self.nodes:
            if node.node_id == node_id:
                return node
        return None
