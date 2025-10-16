# Known Issues

## Instance Storage Architecture

### Issue
Redis instances are currently stored as a single JSON blob in Redis at key `sre:instances`. This means:
- Every API call loads ALL instances
- Updates require loading all instances, modifying one, and saving all back
- Race conditions possible with concurrent updates
- Poor performance with many instances
- No ability to query individual instances efficiently

### Current Implementation
```python
# All instances stored as single JSON string
await redis_client.set("sre:instances", json.dumps([...all instances...]))

# Every lookup loads everything
instances = json.loads(await redis_client.get("sre:instances"))
for inst in instances:
    if inst.id == target_id:
        return inst
```

### Recommended Fix
Refactor to use individual Redis hashes:
```python
# Store each instance as a hash
await redis_client.hset(f"sre:instance:{instance_id}", mapping=instance_data)

# Direct lookup
instance_data = await redis_client.hgetall(f"sre:instance:{instance_id}")

# List all instances
instance_ids = await redis_client.smembers("sre:instances:index")
```

### Impact
- **Performance**: O(n) for every operation instead of O(1)
- **Scalability**: Doesn't scale beyond ~100 instances
- **Concurrency**: Race conditions on updates
- **Reliability**: One bad instance can break loading all instances

### Priority
**Medium** - Works for small deployments but needs refactoring before production use with many instances.

---

## Masked URLs in Redis

### Issue
Some instances in Redis have masked connection URLs (`**********`) instead of real URLs. This happens when:
1. The UI sends back masked URLs from the response model
2. An update request includes the masked URL from a previous GET response

### Detection
Run the diagnostic script:
```bash
python scripts/fix_masked_instance_urls.py
```

### Fix
Update each affected instance via the API with the real connection URL:
```bash
curl -X PUT http://localhost:8000/api/v1/instances/<instance_id> \
  -H 'Content-Type: application/json' \
  -d '{"connection_url": "redis://your-real-host:6379"}'
```

### Prevention
- API now validates connection URLs on create/update (rejects masked URLs with 400)
- Loading from Redis skips invalid instances but logs errors
- UI should not send masked URLs back in update requests

---

## Prometheus Tool Configuration

### Issue
The Prometheus tool tries to connect to `localhost:9090` by default, which may not exist in all environments.

### Fix
Configure Prometheus URL per instance using the `monitoring_identifier` or add Prometheus configuration to instance metadata.

### Workaround
If Prometheus is not available, the tool will fail gracefully and log errors, but other tools will continue to work.
