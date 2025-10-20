# Redis Cloud Management API Tool Provider

This tool provider enables the Redis SRE Agent to interact with the Redis Cloud Management API for managing subscriptions, databases, users, and other cloud resources.

## Features

- **Account Management**: View account details and available regions
- **Subscription Management**: List and inspect Pro and Essentials subscriptions
- **Database Management**: List and inspect databases within subscriptions
- **User Management**: List and view users in the account
- **Task Tracking**: Monitor asynchronous operations
- **Cloud Accounts**: Manage linked cloud provider accounts (AWS)

## Configuration

The provider requires Redis Cloud API credentials, which can be obtained from the Redis Cloud console.

### Environment Variables

Set the following environment variables:

```bash
# Required
TOOLS_REDIS_CLOUD_API_KEY=your-api-key-here
TOOLS_REDIS_CLOUD_API_SECRET_KEY=your-secret-key-here

# Optional
TOOLS_REDIS_CLOUD_BASE_URL=https://api.redislabs.com/v1  # Default
TOOLS_REDIS_CLOUD_TIMEOUT=30.0  # Request timeout in seconds
```

### Getting API Credentials

1. Log in to the [Redis Cloud console](https://app.redislabs.com/)
2. Navigate to **Settings** → **Account** → **API Keys**
3. Click **Generate API Key**
4. Copy the API Key and Secret Key (the secret is only shown once!)
5. Set the environment variables as shown above

See the [official documentation](https://docs.redislabs.com/latest/rc/api/get-started/enable-the-api/) for more details.

## Usage

### Enabling the Provider

Add the provider to your `tool_providers` configuration:

```python
from redis_sre_agent.core.config import settings

settings.tool_providers.append(
    "redis_sre_agent.tools.cloud.redis_cloud.provider.RedisCloudToolProvider"
)
```

Or set via environment variable:

```bash
TOOL_PROVIDERS='["redis_sre_agent.tools.cloud.redis_cloud.provider.RedisCloudToolProvider"]'
```

### Available Tools

The provider exposes the following tools to the LLM:

#### Account Operations
- `redis_cloud_{hash}_get_account`: Get current account details
- `redis_cloud_{hash}_get_regions`: List available regions

#### Subscription Operations
- `redis_cloud_{hash}_list_subscriptions`: List all subscriptions
- `redis_cloud_{hash}_get_subscription`: Get subscription details

#### Database Operations
- `redis_cloud_{hash}_list_databases`: List databases in a subscription
- `redis_cloud_{hash}_get_database`: Get database details

#### User Operations
- `redis_cloud_{hash}_list_users`: List all users
- `redis_cloud_{hash}_get_user`: Get user details

#### Task Operations
- `redis_cloud_{hash}_list_tasks`: List all tasks
- `redis_cloud_{hash}_get_task`: Get task status

#### Cloud Account Operations
- `redis_cloud_{hash}_list_cloud_accounts`: List linked cloud accounts

### Example Queries

Once configured, you can ask the agent questions like:

- "List all my Redis Cloud subscriptions"
- "Show me the databases in subscription 12345"
- "What's the status of database 67890 in subscription 12345?"
- "List all users in my Redis Cloud account"
- "What regions are available for Redis Cloud Pro?"
- "Check the status of task abc-123-def"

## API Client

The provider includes a typed Python client (`RedisCloudClient`) that can be used independently:

```python
from redis_sre_agent.tools.cloud.redis_cloud import RedisCloudClient

async with RedisCloudClient(
    api_key="your-key",
    api_secret_key="your-secret"
) as client:
    # List subscriptions
    subscriptions = await client.list_subscriptions()

    # Get database details
    database = await client.get_database(
        subscription_id=12345,
        database_id=67890
    )

    # List users
    users = await client.list_users()
```

## API Coverage

The client currently implements the most commonly used read operations from the Redis Cloud API:

- ✅ Account operations (get account, list regions)
- ✅ Subscription operations (list, get, create, update, delete)
- ✅ Database operations (list, get, create, update, delete)
- ✅ User operations (list, get, create, update, delete)
- ✅ Task operations (list, get)
- ✅ RBAC operations (list, get, create, update, delete ACL users)
- ✅ Cloud account operations (list, get, create, update, delete)
- ⚠️ Connectivity operations (partial - transit gateways, VPC peering, etc.)
- ⚠️ Essentials subscription/database operations (partial)

Additional operations can be added by extending the `RedisCloudClient` class.

## Error Handling

The client raises `RedisCloudAPIError` for API errors, which includes:
- HTTP status code
- Error message
- Response data (if available)

Example:

```python
from redis_sre_agent.tools.cloud.redis_cloud import RedisCloudAPIError

try:
    database = await client.get_database(subscription_id=999, database_id=999)
except RedisCloudAPIError as e:
    print(f"API error: {e}")
    print(f"Status code: {e.status_code}")
    print(f"Response: {e.response}")
```

## Security Notes

- API credentials are stored as `SecretStr` in Pydantic models to prevent accidental logging
- Credentials are passed via HTTP headers (`x-api-key` and `x-api-secret-key`)
- The API uses HTTPS for all requests
- Never commit API credentials to version control

## References

- [Redis Cloud API Documentation](https://docs.redislabs.com/latest/rc/api/)
- [API Getting Started Guide](https://docs.redislabs.com/latest/rc/api/get-started/)
- [OpenAPI Specification](https://api.redislabs.com/v1/swagger-ui.html)
