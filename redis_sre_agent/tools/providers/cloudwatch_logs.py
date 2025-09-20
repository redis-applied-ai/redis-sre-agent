"""AWS CloudWatch Logs provider implementation.

This provider connects to AWS CloudWatch Logs to search and analyze log data.
It supports filtering by log groups, time ranges, and log levels.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False

from ..protocols import LogEntry, TimeRange

logger = logging.getLogger(__name__)


class CloudWatchLogsProvider:
    """AWS CloudWatch Logs provider.
    
    This provider connects to AWS CloudWatch Logs and can search across
    log groups with various filters and time ranges.
    """

    def __init__(self, region_name: str = "us-east-1", aws_access_key_id: Optional[str] = None, aws_secret_access_key: Optional[str] = None):
        if not BOTO3_AVAILABLE:
            raise ImportError("boto3 is required for CloudWatch Logs provider. Install with: pip install boto3")

        self.region_name = region_name
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key
        self._client = None

    @property
    def provider_name(self) -> str:
        return f"AWS CloudWatch Logs ({self.region_name})"

    def _get_client(self):
        """Get or create CloudWatch Logs client."""
        if self._client is None:
            session_kwargs = {"region_name": self.region_name}
            if self.aws_access_key_id and self.aws_secret_access_key:
                session_kwargs.update({
                    "aws_access_key_id": self.aws_access_key_id,
                    "aws_secret_access_key": self.aws_secret_access_key
                })

            session = boto3.Session(**session_kwargs)
            self._client = session.client("logs")

        return self._client

    async def search_logs(
        self,
        query: str,
        time_range: TimeRange,
        log_groups: Optional[List[str]] = None,
        level_filter: Optional[str] = None,
        limit: int = 100
    ) -> List[LogEntry]:
        """Search CloudWatch logs with filters."""
        try:
            client = self._get_client()

            # Convert datetime to milliseconds timestamp
            start_time = int(time_range.start.timestamp() * 1000)
            end_time = int(time_range.end.timestamp() * 1000)

            # Build CloudWatch Insights query
            insights_query = "fields @timestamp, @message, @logStream"

            # Add level filter if specified
            if level_filter:
                insights_query += f" | filter @message like /{level_filter}/i"

            # Add search query
            if query:
                insights_query += f" | filter @message like /{query}/i"

            insights_query += f" | sort @timestamp desc | limit {limit}"

            # If no log groups specified, get available ones
            if not log_groups:
                log_groups = await self._get_default_log_groups()

            if not log_groups:
                logger.warning("No log groups available for search")
                return []

            # Start CloudWatch Insights query
            response = client.start_query(
                logGroupNames=log_groups,
                startTime=start_time,
                endTime=end_time,
                queryString=insights_query
            )

            query_id = response["queryId"]

            # Poll for query completion
            import asyncio
            max_attempts = 30  # 30 seconds timeout
            attempt = 0

            while attempt < max_attempts:
                await asyncio.sleep(1)
                attempt += 1

                result = client.get_query_results(queryId=query_id)
                status = result["status"]

                if status == "Complete":
                    break
                elif status == "Failed":
                    logger.error(f"CloudWatch Insights query failed: {result.get('statistics', {})}")
                    return []

            if attempt >= max_attempts:
                logger.error("CloudWatch Insights query timed out")
                return []

            # Process results
            log_entries = []
            for result_row in result.get("results", []):
                entry_data = {}
                for field in result_row:
                    entry_data[field["field"]] = field["value"]

                # Extract timestamp
                timestamp_str = entry_data.get("@timestamp")
                if timestamp_str:
                    try:
                        timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                    except ValueError:
                        timestamp = datetime.now()
                else:
                    timestamp = datetime.now()

                # Extract log level from message
                message = entry_data.get("@message", "")
                log_level = self._extract_log_level(message, level_filter)

                # Create log entry
                log_entry = LogEntry(
                    timestamp=timestamp,
                    level=log_level,
                    message=message,
                    source=entry_data.get("@logStream", "unknown"),
                    labels={
                        "log_group": entry_data.get("@logGroup", ""),
                        "log_stream": entry_data.get("@logStream", "")
                    }
                )
                log_entries.append(log_entry)

            return log_entries

        except (ClientError, NoCredentialsError) as e:
            logger.error(f"AWS error searching logs: {e}")
            return []
        except Exception as e:
            logger.error(f"Error searching CloudWatch logs: {e}")
            return []

    async def get_log_groups(self) -> List[str]:
        """Get available CloudWatch log groups."""
        try:
            client = self._get_client()

            log_groups = []
            paginator = client.get_paginator("describe_log_groups")

            for page in paginator.paginate():
                for log_group in page["logGroups"]:
                    log_groups.append(log_group["logGroupName"])

            return log_groups

        except (ClientError, NoCredentialsError) as e:
            logger.error(f"AWS error getting log groups: {e}")
            return []
        except Exception as e:
            logger.error(f"Error getting CloudWatch log groups: {e}")
            return []

    async def health_check(self) -> Dict[str, Any]:
        """Check CloudWatch Logs connection health."""
        try:
            client = self._get_client()

            # Try to list log groups as a health check
            response = client.describe_log_groups(limit=1)

            return {
                "status": "healthy",
                "provider": self.provider_name,
                "connected": True,
                "log_groups_accessible": True,
                "timestamp": datetime.now().isoformat()
            }

        except NoCredentialsError:
            return {
                "status": "unhealthy",
                "provider": self.provider_name,
                "error": "AWS credentials not configured",
                "connected": False,
                "timestamp": datetime.now().isoformat()
            }
        except ClientError as e:
            return {
                "status": "unhealthy",
                "provider": self.provider_name,
                "error": f"AWS error: {e}",
                "connected": False,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "provider": self.provider_name,
                "error": str(e),
                "connected": False,
                "timestamp": datetime.now().isoformat()
            }

    async def _get_default_log_groups(self) -> List[str]:
        """Get a default set of log groups for searching."""
        all_groups = await self.get_log_groups()

        # Filter for common application log groups
        default_groups = []
        for group in all_groups:
            if any(keyword in group.lower() for keyword in ["redis", "app", "service", "api", "web"]):
                default_groups.append(group)

        # If no specific groups found, return first 5 groups
        if not default_groups and all_groups:
            default_groups = all_groups[:5]

        return default_groups

    def _extract_log_level(self, message: str, level_filter: Optional[str] = None) -> str:
        """Extract log level from message content."""
        if level_filter:
            return level_filter.upper()

        message_upper = message.upper()

        # Common log level patterns
        if "ERROR" in message_upper or "ERR" in message_upper:
            return "ERROR"
        elif "WARN" in message_upper:
            return "WARN"
        elif "INFO" in message_upper:
            return "INFO"
        elif "DEBUG" in message_upper:
            return "DEBUG"
        else:
            return "INFO"  # Default


# Helper function to create instances
def create_cloudwatch_logs_provider(
    region_name: str = "us-east-1",
    aws_access_key_id: Optional[str] = None,
    aws_secret_access_key: Optional[str] = None
) -> CloudWatchLogsProvider:
    """Create a CloudWatch Logs provider instance."""
    return CloudWatchLogsProvider(region_name, aws_access_key_id, aws_secret_access_key)
