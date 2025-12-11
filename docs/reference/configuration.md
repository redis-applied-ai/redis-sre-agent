## Configuration Reference

Key environment variables and pointers. For step-by-step setup, see: how-to/configuration.md

### Environment Variables

- `OPENAI_API_KEY`: LLM access (required)
- `REDIS_SRE_MASTER_KEY`: 32-byte base64 master key for envelope encryption
- `TOOLS_PROMETHEUS_URL`, `TOOLS_LOKI_URL`: Provider endpoints
- `REDIS_URL`: Agent storage Redis URL (for local/dev)
- `SRE_AGENT_CONFIG`: Path to YAML config file (optional)

### YAML Configuration

For complex nested settings, use a YAML config file (`config.yaml`):

```yaml
mcp_servers:
  server-name:
    command: string        # Command to run (e.g., "npx", "docker", "uv")
    args: [string]         # Command arguments
    env: {key: value}      # Environment variables
    url: string            # Optional: URL for HTTP-based servers
    tools:                 # Optional: Tool-specific configurations
      tool-name:
        description: string    # Override tool description ({original} for default)
        capability: string     # Tool capability category
```

See `config.yaml.example` for a complete example.

### See also

- Advanced Encryption: how-to/configuration/encryption.md
- Tool Providers: how-to/tool-providers.md
