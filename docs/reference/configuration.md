## Configuration Reference

Key environment variables and pointers. For step-by-step setup, see: how-to/configuration.md

- OPENAI_API_KEY: LLM access
- REDIS_SRE_MASTER_KEY: 32-byte base64 master key for envelope encryption
- TOOLS_PROMETHEUS_URL, TOOLS_LOKI_URL: Provider endpoints
- REDIS_URL: Agent storage Redis URL (for local/dev)

See also
- Advanced Encryption: how-to/configuration/encryption.md
- Tool Providers: how-to/tool-providers.md
