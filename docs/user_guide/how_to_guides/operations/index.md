---
description: Production operations guides for the Redis SRE Agent.
---

# Operations

Production deployment and operations guides.

<div class="grid cards" markdown>

-   :material-docker:{ .lg .middle } **[Docker deployment](docker_deployment.md)**

    ---

    Run the full stack with Compose, including monitoring sidecars.

-   :material-chart-line:{ .lg .middle } **[Observability](observability.md)**

    ---

    Prometheus metrics, Loki logs, Grafana dashboards.

-   :material-shield-lock:{ .lg .middle } **[Airgap deployment](airgap.md)**

    ---

    Run without internet access using a local model and pre-built indexes.

-   :material-key-variant:{ .lg .middle } **[Secret encryption](encryption.md)**

    ---

    Envelope encryption for stored Redis credentials, key rotation, and migration.

-   :material-alert-circle:{ .lg .middle } **[Gotchas](gotchas.md)**

    ---

    Known sharp edges to avoid in production.

</div>
