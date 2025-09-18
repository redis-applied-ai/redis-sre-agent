"""Docker container log search and analysis tools.

This module provides tools for searching and analyzing logs from Docker containers,
particularly useful for Docker Compose environments where multiple services are running.
"""

import json
import logging
import re
import subprocess
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class DockerLogEntry:
    """Represents a single log entry from a Docker container."""
    
    def __init__(self, timestamp: datetime, container: str, message: str, level: Optional[str] = None):
        self.timestamp = timestamp
        self.container = container
        self.message = message
        self.level = level or self._extract_log_level(message)
    
    def _extract_log_level(self, message: str) -> str:
        """Extract log level from message content."""
        message_upper = message.upper()
        for level in ['ERROR', 'WARN', 'WARNING', 'INFO', 'DEBUG', 'TRACE', 'FATAL', 'CRITICAL']:
            if level in message_upper:
                return level
        return 'INFO'  # Default level
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'timestamp': self.timestamp.isoformat(),
            'container': self.container,
            'message': self.message,
            'level': self.level
        }


async def search_docker_logs(
    query: str,
    containers: Optional[List[str]] = None,
    time_range_hours: float = 1.0,
    level_filter: Optional[str] = None,
    limit: int = 100,
    compose_project: Optional[str] = None
) -> Dict[str, Any]:
    """Search Docker container logs for specific patterns.
    
    Args:
        query: Search query/pattern to look for in logs
        containers: List of container names to search (if None, searches all)
        time_range_hours: How far back to search in hours
        level_filter: Filter by log level (ERROR, WARN, INFO, etc.)
        limit: Maximum number of log entries to return
        compose_project: Docker Compose project name (auto-detected if None)
        
    Returns:
        Dictionary containing search results and metadata
    """
    try:
        # Auto-detect compose project if not provided
        if compose_project is None:
            compose_project = await _detect_compose_project()
        
        # Get available containers
        available_containers = await _get_docker_containers(compose_project)
        
        if not available_containers:
            return {
                "error": "No Docker containers found",
                "compose_project": compose_project,
                "available_containers": []
            }
        
        # Filter containers if specified
        if containers:
            target_containers = [c for c in available_containers if any(name in c for name in containers)]
            if not target_containers:
                return {
                    "error": f"None of the specified containers found: {containers}",
                    "available_containers": available_containers
                }
        else:
            target_containers = available_containers
        
        # Calculate time range
        since_time = datetime.now() - timedelta(hours=time_range_hours)
        since_str = since_time.strftime('%Y-%m-%dT%H:%M:%S')
        
        # Search logs for each container
        all_entries = []
        container_results = {}
        
        for container in target_containers:
            try:
                entries = await _search_container_logs(
                    container, query, since_str, level_filter, limit
                )
                all_entries.extend(entries)
                container_results[container] = {
                    "entries_found": len(entries),
                    "entries": [entry.to_dict() for entry in entries]
                }
                
            except Exception as e:
                logger.error(f"Error searching logs for container {container}: {e}")
                container_results[container] = {
                    "error": str(e),
                    "entries_found": 0,
                    "entries": []
                }
        
        # Sort all entries by timestamp (most recent first)
        all_entries.sort(key=lambda x: x.timestamp, reverse=True)
        
        # Apply global limit
        if len(all_entries) > limit:
            all_entries = all_entries[:limit]
        
        # Generate summary
        total_entries = len(all_entries)
        level_counts = {}
        container_counts = {}
        
        for entry in all_entries:
            level_counts[entry.level] = level_counts.get(entry.level, 0) + 1
            container_counts[entry.container] = container_counts.get(entry.container, 0) + 1
        
        return {
            "query": query,
            "time_range_hours": time_range_hours,
            "level_filter": level_filter,
            "containers_searched": len(target_containers),
            "total_entries_found": total_entries,
            "level_distribution": level_counts,
            "container_distribution": container_counts,
            "entries": [entry.to_dict() for entry in all_entries],
            "container_results": container_results,
            "available_containers": available_containers
        }
        
    except Exception as e:
        logger.error(f"Error in search_docker_logs: {e}")
        return {"error": str(e)}


async def _detect_compose_project() -> Optional[str]:
    """Auto-detect Docker Compose project name."""
    try:
        # Try to get project name from docker-compose
        result = subprocess.run(
            ['docker', 'compose', 'config', '--format', 'json'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            config = json.loads(result.stdout)
            return config.get('name', 'sre-2')  # Default to sre-2
        
        # Fallback: try to detect from current directory
        result = subprocess.run(['pwd'], capture_output=True, text=True)
        if result.returncode == 0:
            current_dir = result.stdout.strip().split('/')[-1]
            return current_dir
            
    except Exception as e:
        logger.debug(f"Could not auto-detect compose project: {e}")
    
    return 'sre-2'  # Default fallback


async def _get_docker_containers(compose_project: Optional[str] = None) -> List[str]:
    """Get list of running Docker containers."""
    try:
        # Try docker compose ps first if project specified
        if compose_project:
            result = subprocess.run(
                ['docker', 'compose', '-p', compose_project, 'ps', '--format', 'json'],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0 and result.stdout.strip():
                containers = []
                for line in result.stdout.strip().split('\n'):
                    if line:
                        try:
                            container_info = json.loads(line)
                            if container_info.get('State') == 'running':
                                containers.append(container_info['Name'])
                        except json.JSONDecodeError:
                            continue
                if containers:
                    return containers

        # Fallback: use docker ps to get all running containers
        result = subprocess.run(
            ['docker', 'ps', '--format', '{{.Names}}', '--filter', 'status=running'],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            containers = [name.strip() for name in result.stdout.strip().split('\n') if name.strip()]
            return containers

    except Exception as e:
        logger.error(f"Error getting Docker containers: {e}")

    return []


async def _search_container_logs(
    container: str,
    query: str,
    since: str,
    level_filter: Optional[str],
    limit: int
) -> List[DockerLogEntry]:
    """Search logs for a specific container."""
    try:
        # Build docker logs command
        cmd = ['docker', 'logs', '--since', since, '--timestamps', container]

        # Execute command
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            logger.error(f"Docker logs command failed for {container}: {result.stderr}")
            return []

        # Parse log lines from both stdout and stderr
        entries = []
        log_lines = []

        # Docker logs can output to both stdout and stderr
        if result.stdout:
            log_lines.extend(result.stdout.split('\n'))
        if result.stderr:
            log_lines.extend(result.stderr.split('\n'))

        for line in log_lines:
            if not line.strip():
                continue

            entry = _parse_log_line(line, container)
            if entry is None:
                continue

            # Apply query filter (case-insensitive)
            if query and query.lower() not in entry.message.lower():
                continue

            # Apply level filter
            if level_filter and level_filter.upper() != entry.level.upper():
                continue

            entries.append(entry)

            # Apply limit per container
            if len(entries) >= limit:
                break

        # Sort by timestamp (most recent first)
        entries.sort(key=lambda x: x.timestamp, reverse=True)

        return entries

    except Exception as e:
        logger.error(f"Error searching logs for container {container}: {e}")
        return []


def _parse_log_line(line: str, container: str) -> Optional[DockerLogEntry]:
    """Parse a single log line from Docker logs output."""
    try:
        # Docker logs format: 2024-01-15T10:30:45.123456789Z message content
        timestamp_match = re.match(r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)\s+(.*)$', line)
        
        if timestamp_match:
            timestamp_str = timestamp_match.group(1)
            message = timestamp_match.group(2)
            
            # Parse timestamp
            try:
                # Handle different timestamp formats
                if timestamp_str.endswith('Z'):
                    timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                else:
                    timestamp = datetime.fromisoformat(timestamp_str)
            except ValueError:
                # Fallback to current time if parsing fails
                timestamp = datetime.now()
            
            return DockerLogEntry(timestamp, container, message)
        else:
            # If no timestamp, use current time
            return DockerLogEntry(datetime.now(), container, line)
            
    except Exception as e:
        logger.debug(f"Error parsing log line: {e}")
        return None
