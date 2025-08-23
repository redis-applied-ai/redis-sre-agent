# Redis SRE Agent - Source Documents

This directory contains source documents for the Redis SRE Agent knowledge base.

## Directory Structure

```
source_documents/
├── runbooks/           # SRE troubleshooting runbooks
│   ├── redis-connection-limit-exceeded.md
│   ├── redis-connection-timeouts-network-issues.md
│   └── redis-connection-pool-exhaustion-leak-detection.md
└── README.md          # This file
```

## Runbooks

### Connection Troubleshooting
- **redis-connection-limit-exceeded.md** - Critical connection limit issues ("ERR max number of clients reached")
- **redis-connection-timeouts-network-issues.md** - Network and timeout troubleshooting
- **redis-connection-pool-exhaustion-leak-detection.md** - Application connection pool issues

## Adding New Documents

### For Runbooks
1. Create a new `.md` file in the appropriate subdirectory
2. Include metadata at the top:
   ```markdown
   # Document Title
   
   **Category**: runbook_category
   **Severity**: critical|warning|info
   **Source**: document_source
   ```
3. Follow the established structure with sections like:
   - Symptoms
   - Root Cause Analysis
   - Immediate Remediation
   - Long-term Prevention
   - Production Checklist

### Ingestion Process
Documents in this directory can be ingested into the knowledge base using:

```bash
# Future ingestion script (to be implemented)
uv run python -m redis_sre_agent.cli ingest-source-documents
```

## Document Guidelines

- Use clear, actionable language
- Include specific commands and code examples
- Provide both immediate fixes and long-term solutions
- Include monitoring and alerting guidance
- Add production checklists for operational procedures
- Reference real Redis commands and configuration options