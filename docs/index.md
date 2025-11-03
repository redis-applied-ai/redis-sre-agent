# Redis SRE Agent

Use AI to answer Redis questions and triage live issues. Run one‑off checks or schedule recurring health checks.

This is an early release with built-in support for Prometheus, Loki, Redis CLI diagnostics, and host telemetry. More integrations coming for popular observability and cloud platforms. The tool system is fully extensible - write your own providers to integrate with any system.

## Get started
- Local Development: [quickstarts/local.md](quickstarts/local.md)
- VM Deployment (Redis Enterprise): [quickstarts/vm-deployment.md](quickstarts/vm-deployment.md)

## Do things
- Ad‑hoc Triage (CLI): [how-to/cli.md](how-to/cli.md)
- Ad‑hoc Triage (API): [how-to/api.md](how-to/api.md)
- Scheduled Health Checks: [how-to/cli.md#6-schedule-recurring-checks](how-to/cli.md#6-schedule-recurring-checks)
- Integrations (Providers): [how-to/tool-providers.md](how-to/tool-providers.md)

## Concepts
- **Without Redis instance details**: Get knowledge-based advice from docs and runbooks
- **With Redis instance details**: Get live triage with metrics, logs, and instance-specific analysis using a deep-research approach (parallel investigation tracks)
- **Tasks**: How you interact with the agent (create, poll status)
- **Threads**: What happened during execution (messages, results, history)
- **Providers**: Pluggable integrations for metrics/logs/diagnostics - fully extensible
