# Redis Enterprise Analyzer MCP Server

Standalone `stdio` MCP server for Redis Enterprise Analyzer.

This package runs alongside an agent and talks to a running Analyzer instance over HTTP. It does not need the full `re-analyzer` monorepo checkout at runtime.

## Configuration

Required environment variables:

- `ANALYZER_BASE_URL`
- `ANALYZER_API_TOKEN`

Optional environment variables:

- `ANALYZER_REPORT_USER`
- `ANALYZER_REPORT_PASSWORD`
- `ANALYZER_TIMEOUT_MS` (defaults to `30000`)

## Development

```bash
npm install
npm test
npm run build
```

Run locally:

```bash
ANALYZER_BASE_URL=http://127.0.0.1:3000 \
ANALYZER_API_TOKEN=test-token \
ANALYZER_REPORT_USER=report \
ANALYZER_REPORT_PASSWORD=testpass \
npm start
```

## Agent launch

This repo is intended to be launched by an agent over `stdio`.

If the repo is checked out locally:

```bash
npx analyzer-mcp
```

If you want to launch directly from a GitHub repo without publishing to npm yet, the intended pattern is:

```bash
npx -y git+https://github.com/<org>/<repo>.git
```

That works because the package exposes a `bin` entry and runs `prepare` to build on install.
