"""AWS X-Ray traces provider implementation.

This provider connects to AWS X-Ray to search and analyze distributed traces.
It helps identify performance issues and service dependencies.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False

from ..protocols import TraceSpan, TracesProvider, TimeRange

logger = logging.getLogger(__name__)


class XRayTracesProvider:
    """AWS X-Ray traces provider.
    
    This provider connects to AWS X-Ray and can search traces, analyze
    service maps, and identify performance bottlenecks.
    """
    
    def __init__(self, region_name: str = "us-east-1", aws_access_key_id: Optional[str] = None, aws_secret_access_key: Optional[str] = None):
        if not BOTO3_AVAILABLE:
            raise ImportError("boto3 is required for X-Ray provider. Install with: pip install boto3")
        
        self.region_name = region_name
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key
        self._client = None
    
    @property
    def provider_name(self) -> str:
        return f"AWS X-Ray ({self.region_name})"
    
    def _get_client(self):
        """Get or create X-Ray client."""
        if self._client is None:
            session_kwargs = {"region_name": self.region_name}
            if self.aws_access_key_id and self.aws_secret_access_key:
                session_kwargs.update({
                    "aws_access_key_id": self.aws_access_key_id,
                    "aws_secret_access_key": self.aws_secret_access_key
                })
            
            session = boto3.Session(**session_kwargs)
            self._client = session.client("xray")
        
        return self._client
    
    async def search_traces(
        self,
        service_name: Optional[str] = None,
        operation_name: Optional[str] = None,
        time_range: Optional[TimeRange] = None,
        min_duration_ms: Optional[float] = None,
        tags: Optional[Dict[str, str]] = None,
        limit: int = 100
    ) -> List[TraceSpan]:
        """Search X-Ray traces with filters."""
        try:
            client = self._get_client()
            
            # Set default time range if not provided
            if time_range is None:
                end_time = datetime.now()
                start_time = end_time - timedelta(hours=1)
                time_range = TimeRange(start_time, end_time)
            
            # Build filter expression
            filter_parts = []
            
            if service_name:
                filter_parts.append(f'service("{service_name}")')
            
            if operation_name:
                filter_parts.append(f'annotation.operation = "{operation_name}"')
            
            if min_duration_ms:
                duration_seconds = min_duration_ms / 1000.0
                filter_parts.append(f"duration >= {duration_seconds}")
            
            if tags:
                for key, value in tags.items():
                    filter_parts.append(f'annotation.{key} = "{value}"')
            
            filter_expression = " AND ".join(filter_parts) if filter_parts else None
            
            # Get trace summaries
            kwargs = {
                "TimeRangeType": "TimeRangeByStartTime",
                "StartTime": time_range.start,
                "EndTime": time_range.end
            }
            
            if filter_expression:
                kwargs["FilterExpression"] = filter_expression
            
            response = client.get_trace_summaries(**kwargs)
            
            trace_summaries = response.get("TraceSummaries", [])
            
            # Convert to TraceSpan objects
            trace_spans = []
            for summary in trace_summaries[:limit]:
                # Get the root span information
                root_span = None
                if summary.get("ServiceIds"):
                    # Use the first service as the root
                    service_id = summary["ServiceIds"][0]
                    root_span = TraceSpan(
                        trace_id=summary["Id"],
                        span_id=summary["Id"],  # Use trace ID as span ID for root
                        operation_name=service_id.get("Name", "unknown"),
                        start_time=summary["StartTime"],
                        duration_ms=summary["Duration"] * 1000,  # Convert to milliseconds
                        tags={
                            "service_name": service_id.get("Name", "unknown"),
                            "response_time": str(summary.get("ResponseTime", 0)),
                            "has_error": str(summary.get("HasError", False)),
                            "has_fault": str(summary.get("HasFault", False)),
                            "has_throttle": str(summary.get("HasThrottle", False))
                        }
                    )
                    trace_spans.append(root_span)
            
            return trace_spans
            
        except (ClientError, NoCredentialsError) as e:
            logger.error(f"AWS error searching traces: {e}")
            return []
        except Exception as e:
            logger.error(f"Error searching X-Ray traces: {e}")
            return []
    
    async def get_trace_details(self, trace_id: str) -> Dict[str, Any]:
        """Get detailed information about a specific trace."""
        try:
            client = self._get_client()
            
            response = client.batch_get_traces(TraceIds=[trace_id])
            
            traces = response.get("Traces", [])
            if not traces:
                return {"error": "Trace not found"}
            
            trace = traces[0]
            segments = trace.get("Segments", [])
            
            # Process segments to extract detailed information
            trace_details = {
                "trace_id": trace_id,
                "duration_ms": trace.get("Duration", 0) * 1000,
                "segments": []
            }
            
            for segment in segments:
                import json
                segment_doc = json.loads(segment.get("Document", "{}"))
                
                segment_info = {
                    "id": segment_doc.get("id"),
                    "name": segment_doc.get("name"),
                    "start_time": segment_doc.get("start_time"),
                    "end_time": segment_doc.get("end_time"),
                    "duration": (segment_doc.get("end_time", 0) - segment_doc.get("start_time", 0)) * 1000,
                    "service": segment_doc.get("service", {}),
                    "annotations": segment_doc.get("annotations", {}),
                    "metadata": segment_doc.get("metadata", {}),
                    "error": segment_doc.get("error", False),
                    "fault": segment_doc.get("fault", False),
                    "throttle": segment_doc.get("throttle", False)
                }
                
                trace_details["segments"].append(segment_info)
            
            return trace_details
            
        except (ClientError, NoCredentialsError) as e:
            logger.error(f"AWS error getting trace details: {e}")
            return {"error": str(e)}
        except Exception as e:
            logger.error(f"Error getting X-Ray trace details: {e}")
            return {"error": str(e)}
    
    async def get_service_map(self, time_range: Optional[TimeRange] = None) -> Dict[str, Any]:
        """Get X-Ray service dependency map."""
        try:
            client = self._get_client()
            
            # Set default time range if not provided
            if time_range is None:
                end_time = datetime.now()
                start_time = end_time - timedelta(hours=1)
                time_range = TimeRange(start_time, end_time)
            
            response = client.get_service_graph(
                StartTime=time_range.start,
                EndTime=time_range.end
            )
            
            services = response.get("Services", [])
            
            # Process service map
            service_map = {
                "services": [],
                "connections": []
            }
            
            for service in services:
                service_info = {
                    "name": service.get("Name"),
                    "type": service.get("Type"),
                    "state": service.get("State"),
                    "start_time": service.get("StartTime"),
                    "end_time": service.get("EndTime"),
                    "response_time_histogram": service.get("ResponseTimeHistogram", {}),
                    "duration_histogram": service.get("DurationHistogram", {}),
                    "summary_statistics": service.get("SummaryStatistics", {})
                }
                service_map["services"].append(service_info)
                
                # Extract connections/edges
                edges = service.get("Edges", [])
                for edge in edges:
                    connection = {
                        "source": service.get("Name"),
                        "destination": edge.get("Alias", {}).get("Name"),
                        "response_time_histogram": edge.get("ResponseTimeHistogram", {}),
                        "summary_statistics": edge.get("SummaryStatistics", {})
                    }
                    service_map["connections"].append(connection)
            
            return service_map
            
        except (ClientError, NoCredentialsError) as e:
            logger.error(f"AWS error getting service map: {e}")
            return {"error": str(e)}
        except Exception as e:
            logger.error(f"Error getting X-Ray service map: {e}")
            return {"error": str(e)}
    
    async def health_check(self) -> Dict[str, Any]:
        """Check X-Ray connection health."""
        try:
            client = self._get_client()
            
            # Test API access by getting encryption config
            response = client.get_encryption_config()
            
            return {
                "status": "healthy",
                "provider": self.provider_name,
                "connected": True,
                "encryption_type": response.get("EncryptionConfig", {}).get("Type"),
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


# Helper function to create instances
def create_xray_traces_provider(
    region_name: str = "us-east-1",
    aws_access_key_id: Optional[str] = None,
    aws_secret_access_key: Optional[str] = None
) -> XRayTracesProvider:
    """Create an X-Ray traces provider instance."""
    return XRayTracesProvider(region_name, aws_access_key_id, aws_secret_access_key)
