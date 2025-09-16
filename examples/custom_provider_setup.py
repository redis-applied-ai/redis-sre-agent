"""Example: Setting up custom SRE tool providers.

This example shows how users can configure and register their own
SRE tool providers using the Protocol-based system.
"""

import asyncio
import os
from typing import Any, Dict

from redis_sre_agent.tools.providers import (
    create_aws_provider,
    create_github_provider,
    create_redis_provider,
)
from redis_sre_agent.tools.registry import get_global_registry, auto_register_default_providers


async def setup_custom_providers():
    """Example of setting up custom SRE tool providers."""
    
    # Get the global registry
    registry = get_global_registry()
    
    print("Setting up custom SRE tool providers...")
    
    # Method 1: Auto-register providers based on environment variables
    config = {
        "redis_url": os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        "prometheus_url": os.getenv("PROMETHEUS_URL"),
        "aws_region": os.getenv("AWS_REGION", "us-east-1"),
        "aws_access_key_id": os.getenv("AWS_ACCESS_KEY_ID"),
        "aws_secret_access_key": os.getenv("AWS_SECRET_ACCESS_KEY"),
        "github_token": os.getenv("GITHUB_TOKEN"),
        "github_organization": os.getenv("GITHUB_ORGANIZATION"),
        "github_default_repo": os.getenv("GITHUB_DEFAULT_REPO"),
    }
    
    auto_register_default_providers(config)
    
    # Method 2: Manually create and register specific providers
    
    # Redis provider with Prometheus support
    if config["redis_url"]:
        redis_provider = create_redis_provider(
            redis_url=config["redis_url"],
            prometheus_url=config["prometheus_url"]
        )
        registry.register_provider("production-redis", redis_provider)
    
    # AWS provider for logs and traces
    if config["aws_access_key_id"]:
        aws_provider = create_aws_provider(
            region_name=config["aws_region"],
            aws_access_key_id=config["aws_access_key_id"],
            aws_secret_access_key=config["aws_secret_access_key"]
        )
        registry.register_provider("aws-production", aws_provider)
    
    # GitHub provider for tickets and code search
    if config["github_token"]:
        github_provider = create_github_provider(
            token=config["github_token"],
            organization=config["github_organization"],
            default_repo=config["github_default_repo"]
        )
        registry.register_provider("github-main", github_provider)
    
    # Show registry status
    status = registry.get_registry_status()
    print(f"\nRegistered {status['total_providers']} providers:")
    for provider_name in status['providers']:
        print(f"  - {provider_name}")
    
    print(f"\nAvailable capabilities: {status['capabilities_available']}")
    
    # Test provider health
    print("\nTesting provider health...")
    health_results = await registry.health_check_all()
    
    for provider_name, health in health_results.items():
        status_emoji = "✅" if health.get("status") == "healthy" else "❌"
        print(f"  {status_emoji} {provider_name}: {health.get('status', 'unknown')}")
        if health.get("error"):
            print(f"    Error: {health['error']}")


async def demonstrate_tool_usage():
    """Demonstrate using the Protocol-based tools."""
    
    from redis_sre_agent.tools.dynamic_tools import (
        list_available_metrics,
        query_instance_metrics,
        search_logs,
    )
    
    print("\n" + "="*50)
    print("DEMONSTRATING PROTOCOL-BASED TOOLS")
    print("="*50)
    
    # List available metrics
    print("\n1. Listing available metrics...")
    metrics_result = await list_available_metrics()
    
    if "error" not in metrics_result:
        print(f"Found metrics from {metrics_result['providers_queried']} providers:")
        for provider_result in metrics_result['results']:
            if "error" not in provider_result:
                print(f"  - {provider_result['provider']}: {provider_result['metrics_count']} metrics")
                # Show first few metrics as examples
                for metric in provider_result['metrics'][:3]:
                    print(f"    • {metric['name']}: {metric['description']}")
    else:
        print(f"Error: {metrics_result['error']}")
    
    # Query a specific metric
    print("\n2. Querying Redis memory usage...")
    memory_result = await query_instance_metrics("used_memory")
    
    if "error" not in memory_result:
        print(f"Memory usage results from {memory_result['providers_queried']} providers:")
        for result in memory_result['results']:
            if "error" not in result:
                if "current_value" in result:
                    print(f"  - {result['provider']}: {result['current_value']} bytes")
                else:
                    print(f"  - {result['provider']}: {result.get('values_count', 0)} historical values")
            else:
                print(f"  - {result['provider']}: Error - {result['error']}")
    else:
        print(f"Error: {memory_result['error']}")
    
    # Search logs (if log providers are available)
    print("\n3. Searching for Redis-related logs...")
    logs_result = await search_logs("redis", time_range_hours=0.5, limit=5)
    
    if "error" not in logs_result:
        print(f"Log search results from {logs_result['providers_queried']} providers:")
        for result in logs_result['results']:
            if "error" not in result:
                print(f"  - {result['provider']}: {result['entries_found']} entries found")
                for entry in result['entries'][:2]:  # Show first 2 entries
                    print(f"    [{entry['timestamp']}] {entry['level']}: {entry['message'][:100]}...")
            else:
                print(f"  - {result['provider']}: Error - {result['error']}")
    else:
        print(f"Error: {logs_result['error']}")


class CustomMetricsProvider:
    """Example of a custom metrics provider implementation.
    
    This shows how users can create their own providers that implement
    the MetricsProvider protocol.
    """
    
    def __init__(self, name: str):
        self.name = name
    
    @property
    def provider_name(self) -> str:
        return f"Custom Metrics Provider ({self.name})"
    
    @property
    def supports_time_queries(self) -> bool:
        return False  # This example doesn't support time queries
    
    async def list_metrics(self):
        from redis_sre_agent.tools.protocols import MetricDefinition
        
        # Return some custom metrics
        return [
            MetricDefinition("custom_metric_1", "Example custom metric", "count", "gauge"),
            MetricDefinition("custom_metric_2", "Another custom metric", "bytes", "gauge"),
        ]
    
    async def get_current_value(self, metric_name: str, labels=None):
        from redis_sre_agent.tools.protocols import MetricValue
        
        # Return mock values for demonstration
        if metric_name == "custom_metric_1":
            return MetricValue(42)
        elif metric_name == "custom_metric_2":
            return MetricValue(1024)
        return None
    
    async def query_time_range(self, metric_name: str, time_range, labels=None, step=None):
        raise NotImplementedError("Custom provider doesn't support time queries")
    
    async def health_check(self) -> Dict[str, Any]:
        return {
            "status": "healthy",
            "provider": self.provider_name,
            "connected": True
        }


async def demonstrate_custom_provider():
    """Demonstrate registering and using a custom provider."""
    
    print("\n" + "="*50)
    print("DEMONSTRATING CUSTOM PROVIDER")
    print("="*50)
    
    from redis_sre_agent.tools.protocols import ToolCapability
    
    # Create a custom provider wrapper
    class CustomSREProvider:
        def __init__(self):
            self._metrics_provider = CustomMetricsProvider("demo")
        
        @property
        def provider_name(self) -> str:
            return "Custom SRE Demo Provider"
        
        @property
        def capabilities(self):
            return [ToolCapability.METRICS]
        
        async def get_metrics_provider(self):
            return self._metrics_provider
        
        async def get_logs_provider(self):
            return None
        
        async def get_tickets_provider(self):
            return None
        
        async def get_repos_provider(self):
            return None
        
        async def get_traces_provider(self):
            return None
        
        async def initialize(self, config: Dict[str, Any]) -> None:
            pass
        
        async def health_check(self) -> Dict[str, Any]:
            return await self._metrics_provider.health_check()
    
    # Register the custom provider
    registry = get_global_registry()
    custom_provider = CustomSREProvider()
    registry.register_provider("custom-demo", custom_provider)
    
    print("Registered custom provider!")
    
    # Test the custom provider
    from redis_sre_agent.tools.dynamic_tools import query_instance_metrics
    
    result = await query_instance_metrics("custom_metric_1", provider_name="custom-demo")
    print(f"Custom metric result: {result}")


async def main():
    """Main demonstration function."""
    await setup_custom_providers()
    await demonstrate_tool_usage()
    await demonstrate_custom_provider()


if __name__ == "__main__":
    asyncio.run(main())
