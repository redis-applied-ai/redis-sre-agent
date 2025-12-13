## Scheduling flows (recurring health checks)

Create recurring checks to continuously monitor Redis and stream results to threads.

### 1) Create a schedule (CLI)
```bash
uv run redis-sre-agent schedule create \
  --name "redis-health" \
  --interval-type minutes \
  --interval-value 15 \
  --instructions "Check memory pressure and top slow operations" \
  --redis-instance-id <instance_id>
```

List schedules:
```bash
uv run redis-sre-agent schedule list
```

Trigger a run now:
```bash
uv run redis-sre-agent schedule run-now <schedule_id>
```

### 2) Create a schedule (API)
```bash
curl -X POST http://localhost:8080/api/v1/schedules \
  -H "Content-Type: application/json" \
  -d '{
        "name": "redis-health",
        "interval_type": "minutes",
        "interval_value": 15,
        "instructions": "Check memory pressure and top slow operations",
        "redis_instance_id": "<instance_id>",
        "enabled": true
      }'
```

List schedules:
```bash
curl http://localhost:8080/api/v1/schedules/
```

Get a schedule:
```bash
curl http://localhost:8080/api/v1/schedules/{schedule_id}
```

Trigger a run immediately:
```bash
curl -X POST http://localhost:8080/api/v1/schedules/{schedule_id}/trigger
```

List recent runs:
```bash
curl http://localhost:8080/api/v1/schedules/{schedule_id}/runs
```
