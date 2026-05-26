# Incident Brief: Checkout API latency

**Incident ID:** inc-001
**Primary service:** checkout-api
**Window:** 2026-04-14T10:00:00Z/2026-04-14T11:00:00Z
**Evidence source:** example incident fixtures

## Summary

- **Impact:** Elevated p95 latency affected checkout requests in one region.
- **Current state:** The incident is mitigating while payments-platform rolls back deploy api-2026.05.14.7.
- **Primary hypothesis:** The checkout-api deploy correlates with the latency spike and should be treated as the leading suspect.

## Evidence Timeline

- **2026-04-14T10:07:00Z**: checkout-api deploy api-2026.05.14.7 completed.
- **2026-04-14T10:18:00Z**: p95 latency alert fired for checkout-api.
- **2026-04-14T10:42:00Z**: rollback started by payments-platform.

## Tool Findings

### Inventory

- **Service ownership:** checkout-api is owned by payments-platform and depends on cart-api and pricing-api.

### Metrics

- **Latency regression:** p95 latency rose from 180 ms to a 920 ms peak while request rate changed only 3 percent.

### Events

- **Deploy correlation:** deploy api-2026.05.14.7 completed before the latency alert fired.

## Action Items

- **payments-platform rollback owner:** Continue rollback and verify p95 latency returns to baseline.
- **payments-platform:** Check whether cart-api retries amplified checkout-api latency.

## Open Questions

- **Retry amplification:** Did cart-api retries increase load during the checkout-api regression?
